"""
network_mgr.py – read and apply eth0 / WiFi / NTP configuration.

Uses NetworkManager (nmcli) for network config — standard on Bookworm.
All write operations require sudo (configured via sudoers in setup.sh).
"""
from __future__ import annotations
import os
import re
import subprocess
from typing import Optional, Dict, Any, Tuple

_LOCATION_PATH = "/var/lib/time-reference-monitor/device_location"


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


_CHRONY_SOURCES_FILE = "/etc/chrony/sources.d/time-reference-monitor.sources"
_NTP_PERSIST_PATH = "/var/lib/time-reference-monitor/ntp_server"

_CHRONY_CONF = (
    "/etc/chrony/chrony.conf" if os.path.isdir("/etc/chrony") else "/etc/chrony.conf"
)


def get_ntp_server() -> str:
    """Return the configured NTP server.

    Reads from the persist file first (set via Settings UI), then falls back
    to the first uncommented server/pool entry in chrony.conf.
    """
    # Primary: persist file written by set_ntp_server()
    try:
        with open(_NTP_PERSIST_PATH) as f:
            v = f.read().strip()
            if v:
                return v
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Fallback: first active server/pool line in chrony.conf
    for path in (_CHRONY_CONF, "/etc/chrony/chrony.conf", "/etc/chrony.conf"):
        try:
            with open(path) as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#") and s.startswith(("server ", "pool ")):
                        parts = s.split()
                        if len(parts) >= 2:
                            return parts[1]
        except FileNotFoundError:
            continue
        except Exception:
            break
    return ""


def set_ntp_server(server: str) -> Tuple[bool, str]:
    """Set a custom NTP server as the exclusive NTP source.

    Rewrites chrony.conf: comments out all existing server/pool lines and
    inserts the custom server in their place.  This ensures no pool servers
    remain active after a restart.

    Persists the server name to _NTP_PERSIST_PATH so update.sh can re-apply
    it after pulling a new chrony.conf from the repository.
    """
    # Read current chrony.conf
    try:
        with open(_CHRONY_CONF) as f:
            original_lines = f.readlines()
    except Exception as e:
        return False, f"Konnte {_CHRONY_CONF} nicht lesen: {e}"

    # Rewrite: comment out all server/pool lines, insert custom server once
    # at the position of the first pool/server line.
    new_lines: list = []
    inserted = False
    for line in original_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.startswith(("server ", "pool ")):
            if not inserted:
                new_lines.append(f"server {server} iburst\n")
                inserted = True
            new_lines.append(f"# {line}" if not line.startswith("#") else line)
        else:
            new_lines.append(line)
    if not inserted:
        new_lines.append(f"server {server} iburst\n")

    content = "".join(new_lines)

    # Write back via sudo tee (allowed by sudoers without password)
    r = subprocess.run(
        ["sudo", "tee", _CHRONY_CONF],
        input=content, capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        return False, f"Schreiben von {_CHRONY_CONF} fehlgeschlagen: " + (r.stderr or r.stdout).strip()

    # Persist for update.sh (re-applied after every git pull)
    try:
        os.makedirs(os.path.dirname(_NTP_PERSIST_PATH), exist_ok=True)
        with open(_NTP_PERSIST_PATH, "w") as f:
            f.write(server + "\n")
    except Exception:
        pass  # Non-fatal

    # Restart chrony to pick up the new config
    r = _sudo("systemctl", "restart", "chrony", timeout=15)
    if r.returncode != 0:
        return True, f"NTP-Server auf {server} gesetzt (chrony restart: {(r.stderr or r.stdout).strip()})"

    return True, f"NTP-Server auf {server} gesetzt."


# ── write ────────────────────────────────────────────────────────────────────

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


# ── Device location ──────────────────────────────────────────────────────────

def get_device_location() -> str:
    """Return the stored device location string, or empty string if not set."""
    try:
        with open(_LOCATION_PATH) as f:
            return f.read().strip()
    except Exception:
        return ""


def set_device_location(location: str) -> Tuple[bool, str]:
    """Persist device location (max 500 chars)."""
    location = str(location).strip()[:500]
    try:
        os.makedirs(os.path.dirname(_LOCATION_PATH), exist_ok=True)
        with open(_LOCATION_PATH, "w") as f:
            f.write(location + "\n")
        return True, "Standort gespeichert."
    except Exception as exc:
        return False, f"Fehler beim Speichern: {exc}"


