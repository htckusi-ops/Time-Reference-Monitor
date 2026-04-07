"""
domain_scanner.py – Short-lived PTP domain scanner via tcpdump + PCAP parsing.

Captures PTP packets for a configurable duration on a given interface, then
parses the resulting PCAP to extract all unique domainNumber values found in
PTP (IEEE 1588) headers.  No external Python dependencies required.

Usage:
    scanner = DomainScanner()
    ok, msg = scanner.start("eth0", duration_s=10)
    # ... poll scanner.status() every 500 ms ...
    s = scanner.status()
    # s["state"] == "done", s["domains"] == {0: 145, 127: 3}
"""
from __future__ import annotations

import os
import struct
import subprocess
import threading
import time
from typing import Dict, Optional, Tuple

_SCAN_PCAP   = "/dev/shm/ptp_domain_scan.pcap"
_PTP_FILTER  = "(udp port 319 or udp port 320 or ether proto 0x88f7)"
_MAX_PACKETS = 500          # stop tcpdump after N packets regardless of duration

_ETH_P_1588  = 0x88F7       # IEEE 1588 / PTP over Ethernet (layer-2)
_ETH_P_IP    = 0x0800       # IPv4
_ETH_P_IPV6  = 0x86DD       # IPv6
_ETH_P_8021Q = 0x8100       # 802.1Q VLAN tag
_ETH_P_QINQ  = 0x88A8       # 802.1ad (Q-in-Q)


# ---------------------------------------------------------------------------
# PCAP parsing
# ---------------------------------------------------------------------------

def _parse_pcap_for_domains(path: str) -> Dict[int, int]:
    """Parse a libpcap file; return {domain_number: packet_count}."""
    domains: Dict[int, int] = {}
    try:
        with open(path, "rb") as f:
            raw = f.read(4)
            if len(raw) < 4:
                return {}
            magic = struct.unpack("<I", raw)[0]
            if magic == 0xA1B2C3D4:
                endian = "<"
            elif magic == 0xD4C3B2A1:
                endian = ">"
            elif magic == 0xA1B23C4D:   # nanosecond-resolution pcap
                endian = "<"
            elif magic == 0x4D3CB2A1:
                endian = ">"
            else:
                return {}               # unrecognised magic – not a pcap file

            f.read(20)                  # skip rest of global header (20 bytes)

            while True:
                hdr = f.read(16)
                if len(hdr) < 16:
                    break
                _, _, incl_len, _ = struct.unpack(endian + "IIII", hdr)
                data = f.read(incl_len)
                if len(data) < incl_len:
                    break
                domain = _extract_domain(data)
                if domain is not None:
                    domains[domain] = domains.get(domain, 0) + 1
    except Exception:
        pass
    return domains


def _extract_domain(data: bytes) -> Optional[int]:
    """Return PTP domainNumber (byte 4 of PTP header) from a raw Ethernet frame."""
    if len(data) < 14:
        return None

    ethertype = struct.unpack(">H", data[12:14])[0]
    offset = 14             # past Ethernet dst(6) + src(6) + ethertype(2)

    # Strip 802.1Q / 802.1ad VLAN tags (may be stacked)
    while ethertype in (_ETH_P_8021Q, _ETH_P_QINQ):
        if len(data) < offset + 4:
            return None
        ethertype = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        offset += 4

    if ethertype == _ETH_P_1588:
        # Layer-2 PTP: PTP header starts directly here
        ptp_off = offset

    elif ethertype == _ETH_P_IP:
        if len(data) < offset + 20:
            return None
        if data[offset + 9] != 17:      # IP protocol != UDP
            return None
        ip_hdr_len = (data[offset] & 0x0F) * 4
        ptp_off = offset + ip_hdr_len + 8   # + UDP header (8 bytes)

    elif ethertype == _ETH_P_IPV6:
        if len(data) < offset + 40:
            return None
        if data[offset + 6] != 17:      # Next Header != UDP (ignores ext headers)
            return None
        ptp_off = offset + 40 + 8       # + UDP header (8 bytes)

    else:
        return None

    # IEEE 1588-2008 PTP header: domainNumber is at byte offset 4
    if len(data) < ptp_off + 5:
        return None
    return data[ptp_off + 4]


# ---------------------------------------------------------------------------
# Scanner class
# ---------------------------------------------------------------------------

class DomainScanner:
    """
    Single-instance, async PTP domain scanner.  All public methods are
    thread-safe.  Only one scan can run at a time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = "idle"        # idle | scanning | done | error
        self._iface = ""
        self._duration_s = 10
        self._started_at: Optional[float] = None
        self._domains: Dict[int, int] = {}
        self._error: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None

    # ------------------------------------------------------------------
    def start(self, iface: str, duration_s: int = 10) -> Tuple[bool, str]:
        """Start a domain scan.  Returns (ok, message)."""
        with self._lock:
            if self._state == "scanning":
                return False, "Scan läuft bereits."
            self._state    = "scanning"
            self._iface    = iface
            self._duration_s = max(3, min(30, int(duration_s)))
            self._started_at = time.monotonic()
            self._domains  = {}
            self._error    = None

        threading.Thread(target=self._run, daemon=True, name="domain-scan").start()
        return True, f"Scan gestartet auf {iface}, {self._duration_s} s"

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Abort a running scan (best-effort)."""
        with self._lock:
            proc = self._proc
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def status(self) -> dict:
        """Return current scan state as a JSON-serialisable dict."""
        with self._lock:
            elapsed = (time.monotonic() - self._started_at) if self._started_at else 0.0
            return {
                "state":      self._state,
                "iface":      self._iface,
                "duration_s": self._duration_s,
                "elapsed_s":  round(min(elapsed, float(self._duration_s)), 1),
                "domains":    dict(sorted(self._domains.items())),
                "error":      self._error,
            }

    # ------------------------------------------------------------------
    def _run(self) -> None:
        """Background thread: capture + parse."""
        try:
            # Remove any leftover PCAP from a previous scan.
            # The file may be root-owned (created by sudo tcpdump) – catch
            # PermissionError and skip; tcpdump will overwrite it anyway.
            try:
                os.remove(_SCAN_PCAP)
            except (FileNotFoundError, PermissionError):
                pass

            with self._lock:
                iface      = self._iface
                duration_s = self._duration_s

            proc = subprocess.Popen(
                [
                    "sudo", "tcpdump",
                    "-i", iface,
                    "-n",                       # no DNS lookups
                    "-s", "128",                # snap 128 bytes – enough for PTP header
                    "-c", str(_MAX_PACKETS),    # stop after N packets
                    "-w", _SCAN_PCAP,
                    _PTP_FILTER,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._lock:
                self._proc = proc

            # Wait for tcpdump to finish (packet limit) or hard timeout
            deadline = time.monotonic() + duration_s
            while True:
                if proc.poll() is not None:
                    break
                if time.monotonic() >= deadline:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
                time.sleep(0.25)

            domains = _parse_pcap_for_domains(_SCAN_PCAP)

            with self._lock:
                self._domains = domains
                self._state   = "done"
                self._proc    = None

        except Exception as exc:
            with self._lock:
                self._error = str(exc)
                self._state = "error"
                self._proc  = None
