"""
network_mgr.py – read and apply eth0 / WiFi / NTP configuration.

Uses NetworkManager (nmcli) for network config — standard on Bookworm.
All write operations require sudo (configured via sudoers in setup.sh).
"""
from __future__ import annotations
import re
import subprocess
from typing import Optional, Dict, Any, Tuple


def _run(*args: str, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)


def _sudo(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(["sudo"] + list(args), capture_output=True, text=True, timeout=timeout)


# ── helpers ───────────────────────────────────────────────────────────────────

def prefix_to_netmask(prefix: int) -> str:
    """Convert CIDR prefix length to dotted netmask (e.g. 24 → '255.255.255.0')."""
    prefix = max(0, min(32, int(prefix)))
    mask = (0xFFFFFFFF >> (32 - prefix)) << (32 - prefix) if prefix else 0
    return ".".join(str((mask >> (24 - 8 * i)) & 0xFF) for i in range(4))


def netmask_to_prefix(netmask: str) -> int:
    """Convert dotted netmask to CIDR prefix length."""
    try:
        return sum(bin(int(x)).count("1") for x in netmask.split("."))
    except Exception:
        return 24


def _get_active_connection(iface: str) -> Optional[str]:
    """Return the NM connection name active on *iface*, or None."""
    r = _run("nmcli", "-t", "-f", "NAME,DEVICE", "con", "show", "--active")
    for line in r.stdout.splitlines():
        # line: "Wired connection 1:eth0"  (name may contain colons)
        if ":" in line and line.rsplit(":", 1)[-1] == iface:
            return line.rsplit(":", 1)[0]
    return None


# ── read ──────────────────────────────────────────────────────────────────────

def get_network_status(iface: str = "eth0") -> Dict[str, Any]:
    """Return current network config for *iface*."""
    result: Dict[str, Any] = {
        "iface": iface,
        "method": "dhcp",   # 'dhcp' | 'static' | 'unknown'
        "ip": "",
        "prefix": "24",
        "netmask": "255.255.255.0",
        "gateway": "",
        "dns": "",
        "connection": "",
        "error": None,
    }

    # Live IP / prefix from kernel
    r = _run("ip", "-4", "addr", "show", iface)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", r.stdout)
    if m:
        result["ip"] = m.group(1)
        result["prefix"] = m.group(2)
        result["netmask"] = prefix_to_netmask(int(m.group(2)))

    # Live default gateway
    r = _run("ip", "route", "show", "dev", iface)
    m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", r.stdout)
    if m:
        result["gateway"] = m.group(1)

    # NM: method + stored DNS
    conn = _get_active_connection(iface)
    if conn:
        result["connection"] = conn
        r = _run("nmcli", "-t", "-f", "ipv4.method,ipv4.dns", "con", "show", conn)
        for line in r.stdout.splitlines():
            key, _, val = line.partition(":")
            if key == "ipv4.method":
                result["method"] = "static" if val == "manual" else "dhcp"
            elif key == "ipv4.dns":
                result["dns"] = val.replace(",", ", ")
    else:
        result["error"] = "No active NetworkManager connection found for " + iface

    return result


def get_wifi_status() -> Dict[str, Any]:
    """Return WiFi radio status."""
    r = _run("nmcli", "radio", "wifi")
    enabled = r.stdout.strip() == "enabled"
    return {
        "enabled": enabled,
        "config_hint": "/etc/NetworkManager/system-connections/  (SSID/Passwort)",
    }


def get_ntp_server() -> str:
    """Return the first configured NTP server from chrony.conf."""
    try:
        with open("/etc/chrony/chrony.conf") as f:
            for line in f:
                s = line.strip()
                if s.startswith(("server ", "pool ")):
                    parts = s.split()
                    if len(parts) >= 2:
                        return parts[1]
    except FileNotFoundError:
        try:
            with open("/etc/chrony.conf") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith(("server ", "pool ")):
                        parts = s.split()
                        if len(parts) >= 2:
                            return parts[1]
        except Exception:
            pass
    except Exception:
        pass
    return ""


# ── write ─────────────────────────────────────────────────────────────────────

def apply_static(
    iface: str, ip: str, prefix: str, gateway: str, dns: str
) -> Tuple[bool, str]:
    """Apply static IP configuration via nmcli."""
    conn = _get_active_connection(iface)
    if not conn:
        return False, f"Keine aktive NM-Verbindung für {iface} gefunden."

    # Accept dotted netmask as prefix
    if "." in str(prefix):
        prefix = str(netmask_to_prefix(prefix))

    cidr = f"{ip}/{prefix}"
    r = _sudo(
        "nmcli", "con", "modify", conn,
        "ipv4.method", "manual",
        "ipv4.addresses", cidr,
        "ipv4.gateway", gateway,
        "ipv4.dns", dns.replace(" ", "").replace(";", ","),
    )
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()

    r = _sudo("nmcli", "con", "up", conn)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()

    return True, f"Statische IP {cidr} gesetzt."


def apply_dhcp(iface: str) -> Tuple[bool, str]:
    """Switch interface to DHCP via nmcli."""
    conn = _get_active_connection(iface)
    if not conn:
        return False, f"Keine aktive NM-Verbindung für {iface} gefunden."

    r = _sudo(
        "nmcli", "con", "modify", conn,
        "ipv4.method", "auto",
        "ipv4.addresses", "",
        "ipv4.gateway", "",
        "ipv4.dns", "",
    )
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()

    r = _sudo("nmcli", "con", "up", conn)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()

    return True, "DHCP aktiviert."


def set_wifi(enabled: bool) -> Tuple[bool, str]:
    """Enable or disable WiFi radio via nmcli."""
    state = "on" if enabled else "off"
    r = _sudo("nmcli", "radio", "wifi", state)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()
    return True, f"WiFi {'aktiviert' if enabled else 'deaktiviert'}."


def set_ntp_server(server: str) -> Tuple[bool, str]:
    """Replace the first server/pool entry in chrony.conf and restart chrony."""
    chrony_paths = ["/etc/chrony/chrony.conf", "/etc/chrony.conf"]
    conf_path = None
    for p in chrony_paths:
        try:
            open(p).close()
            conf_path = p
            break
        except FileNotFoundError:
            continue

    if not conf_path:
        return False, "chrony.conf nicht gefunden."

    try:
        with open(conf_path) as f:
            lines = f.readlines()
    except Exception as e:
        return False, str(e)

    new_lines = []
    replaced = False
    for line in lines:
        if not replaced and line.strip().startswith(("server ", "pool ")):
            new_lines.append(f"server {server} iburst\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.insert(0, f"server {server} iburst\n")

    new_content = "".join(new_lines)

    r = subprocess.run(
        ["sudo", "tee", conf_path],
        input=new_content, capture_output=True, text=True, timeout=10
    )
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()

    r = _sudo("systemctl", "restart", "chrony", timeout=20)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()

    return True, f"NTP-Server auf {server} gesetzt, chrony neu gestartet."
