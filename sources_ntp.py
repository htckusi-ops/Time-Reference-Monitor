from __future__ import annotations
import subprocess
import re
from datetime import datetime, timezone
from typing import Tuple, Dict

from models import NTPStatus


_CHRONY_RE = re.compile(r"^\s*([^:]+)\s*:\s*(.*)\s*$")


def utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_chrony_tracking(timeout_s: float = 1.0) -> Tuple[NTPStatus, str]:
    try:
        p = subprocess.run(
            ["chronyc", "tracking"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        out = (p.stdout or "").strip()
        raw = out + ("\n" + p.stderr.strip() if p.stderr else "")

        fields: Dict[str, str] = {}
        for line in out.splitlines():
            m = _CHRONY_RE.match(line)
            if not m:
                continue
            fields[m.group(1).strip().lower()] = m.group(2).strip()

        stratum = None
        try:
            if "stratum" in fields:
                stratum = int(fields["stratum"].split()[0])
        except Exception:
            stratum = None

        ref = fields.get("reference id") or fields.get("referenceid") or fields.get("ref id")
        leap = (fields.get("leap status", "") or "").lower()

        if stratum is None:
            status = "unknown"
        elif "not synchronised" in leap or "not synchronized" in leap:
            status = "unsynced"
        else:
            status = "synced" if stratum <= 15 else "unsynced"

        # "System time: 0.000001234 seconds slow of NTP time"  → offset = +X (system behind NTP)
        # "System time: 0.000001234 seconds fast of NTP time"  → offset = -X (system ahead of NTP)
        # Stored as: NTP_time = system_clock + system_offset_s
        system_offset_s = None
        sys_time_raw = fields.get("system time") or fields.get("system_time")
        if sys_time_raw:
            m = re.match(r"([\d.eE+\-]+)\s+seconds?\s+(slow|fast)", sys_time_raw)
            if m:
                val = float(m.group(1))
                system_offset_s = val if m.group(2) == "slow" else -val

        st = NTPStatus(status=status, stratum=stratum, ref=ref, last_update_utc=utc_iso_ms(),
                       system_offset_s=system_offset_s)
        return st, raw
    except FileNotFoundError:
        st = NTPStatus(status="unknown", last_update_utc=utc_iso_ms())
        return st, "chronyc not found"
    except Exception as e:
        st = NTPStatus(status="unknown", last_update_utc=utc_iso_ms())
        return st, f"chronyc error: {e!r}"
