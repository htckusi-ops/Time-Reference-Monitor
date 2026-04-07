from __future__ import annotations
import subprocess
import re
from datetime import datetime, timezone
from typing import Tuple, Dict, Optional

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

        # "RMS offset : 0.000000123 seconds"  → jitter measure
        rms_offset_s = None
        rms_raw = fields.get("rms offset") or fields.get("rms_offset")
        if rms_raw:
            m = re.match(r"([\d.eE+\-]+)\s+seconds?", rms_raw)
            if m:
                rms_offset_s = float(m.group(1))

        # "Frequency  : 1.234 ppm slow"  → positive = clock too slow (needs to run faster)
        # "Frequency  : 1.234 ppm fast"  → negative = clock too fast
        frequency_ppm = None
        freq_raw = fields.get("frequency")
        if freq_raw:
            m = re.match(r"([\d.eE+\-]+)\s+ppm\s+(slow|fast)", freq_raw)
            if m:
                val = float(m.group(1))
                frequency_ppm = val if m.group(2) == "slow" else -val

        # "Ref time (UTC)  : Mon Apr  7 10:42:36 2026" — time of last reference sample
        last_update_utc: Optional[str] = None
        ref_time_raw = fields.get("ref time (utc)") or fields.get("ref time")
        if ref_time_raw:
            try:
                normalised = re.sub(r"\s+", " ", ref_time_raw.strip())
                dt = datetime.strptime(normalised, "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
                last_update_utc = dt.isoformat(timespec="seconds")
            except ValueError:
                pass

        st = NTPStatus(status=status, stratum=stratum, ref=ref,
                       last_update_utc=last_update_utc,
                       system_offset_s=system_offset_s,
                       rms_offset_s=rms_offset_s,
                       frequency_ppm=frequency_ppm)
        return st, raw
    except FileNotFoundError:
        st = NTPStatus(status="unknown")
        return st, "chronyc not found"
    except Exception as e:
        st = NTPStatus(status="unknown")
        return st, f"chronyc error: {e!r}"
