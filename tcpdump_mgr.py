"""
tcpdump_mgr.py – PTP packet capture via tcpdump.

Captures UDP 319/320 (PTP event/general) and EtherType 0x88F7 (PTP over Ethernet).
Text lines are stored in a fixed-size ring buffer (MAX_LINES) to cap memory use.
The pcap file is written to /dev/shm to avoid SD-card writes.

Requires sudo access to tcpdump (configured via sudoers in setup.sh).
"""
from __future__ import annotations

import collections
import os
import signal
import subprocess
import threading
import time
from typing import List, Optional, Tuple


_PTP_FILTER = "(udp port 319 or udp port 320 or ether proto 0x88f7)"
_PCAP_PATH  = "/dev/shm/ptp_capture.pcap"
_MAX_LINES  = 500   # ring-buffer size for text output
_MAX_PCAP_MB = 50   # rotate pcap at this size


class TcpdumpCapture:
    """Singleton-style capture manager (create once, call start/stop repeatedly)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: collections.deque = collections.deque(maxlen=_MAX_LINES)
        self._line_seq = 0          # monotonic counter for poll-since queries
        self._running = False
        self._iface = "eth0"
        self._start_time: Optional[float] = None
        self._text_proc: Optional[subprocess.Popen] = None
        self._pcap_proc: Optional[subprocess.Popen] = None
        self._reader_thr: Optional[threading.Thread] = None

    # ── public API ────────────────────────────────────────────────────────────

    def start(self, iface: str = "eth0") -> Tuple[bool, str]:
        with self._lock:
            if self._running:
                return False, "Already running."
            self._iface = iface
            self._lines.clear()
            self._line_seq = 0
            self._start_time = time.time()

        # pcap writer (background, writes to RAM disk)
        try:
            self._pcap_proc = subprocess.Popen(
                ["sudo", "tcpdump", "-i", iface, "-n", "-s", "0",
                 _PTP_FILTER, "-C", str(_MAX_PCAP_MB), "-w", _PCAP_PATH],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            return False, f"pcap start failed: {e}"

        # text reader (streams decoded lines)
        try:
            self._text_proc = subprocess.Popen(
                ["sudo", "tcpdump", "-i", iface, "-n", "-l", "-tttt", _PTP_FILTER],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except Exception as e:
            self._stop_procs()
            return False, f"text stream start failed: {e}"

        with self._lock:
            self._running = True

        self._reader_thr = threading.Thread(target=self._reader, daemon=True, name="tcpdump-reader")
        self._reader_thr.start()
        return True, f"Capture started on {iface}."

    def stop(self) -> Tuple[bool, str]:
        with self._lock:
            self._running = False
        self._stop_procs()
        return True, "Capture stopped."

    def status(self) -> dict:
        with self._lock:
            pcap_size = _pcap_size_mb()
            return {
                "running": self._running,
                "iface": self._iface,
                "line_count": len(self._lines),
                "line_seq": self._line_seq,
                "max_lines": _MAX_LINES,
                "elapsed_s": round(time.time() - self._start_time, 1) if self._start_time else 0,
                "pcap_path": _PCAP_PATH if os.path.exists(_PCAP_PATH) else None,
                "pcap_size_mb": pcap_size,
            }

    def get_lines_since(self, since_seq: int) -> Tuple[List[str], int]:
        """Return (new_lines, new_seq) where new_seq is the current sequence number."""
        with self._lock:
            all_lines = list(self._lines)
            seq = self._line_seq
        # The ring buffer may have dropped lines; return only those after since_seq
        drop = max(0, seq - len(all_lines))
        start = max(0, since_seq - drop)
        return all_lines[start:], seq

    def pcap_bytes(self) -> Optional[bytes]:
        try:
            with open(_PCAP_PATH, "rb") as f:
                return f.read()
        except Exception:
            return None

    def delete_pcap(self) -> None:
        try:
            os.unlink(_PCAP_PATH)
        except Exception:
            pass

    # ── internals ─────────────────────────────────────────────────────────────

    def _reader(self) -> None:
        proc = self._text_proc
        if not proc or not proc.stdout:
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                with self._lock:
                    if not self._running:
                        break
                    self._lines.append(line)
                    self._line_seq += 1
        except Exception:
            pass
        with self._lock:
            self._running = False

    def _stop_procs(self) -> None:
        for proc in (self._text_proc, self._pcap_proc):
            if proc is None:
                continue
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        # Belt-and-braces: kill any leftover tcpdump processes
        subprocess.run(["sudo", "killall", "-q", "tcpdump"],
                       capture_output=True, timeout=5)
        self._text_proc = None
        self._pcap_proc = None


def _pcap_size_mb() -> float:
    try:
        return os.path.getsize(_PCAP_PATH) / (1024 * 1024)
    except Exception:
        return 0.0
