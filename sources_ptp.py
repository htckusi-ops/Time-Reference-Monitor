from __future__ import annotations
import subprocess
import re
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple, Optional

from models import PTPStatus
import config


_PMC_RE = re.compile(r"^\s*([A-Za-z0-9 _\-\(\)\.\/]+)\s+([:\=])\s*(.*)$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso_ms(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = utc_now()
    return dt.isoformat(timespec="milliseconds")

def _run_pmc(domain: int, cmd: str, timeout_s: float = config.PMC_TIMEOUT_S) -> str:
    client_sock = f"/tmp/pmc.{os.getpid()}"
    p = subprocess.run(
        ["pmc", "-u", "-i", client_sock, "-s", "/var/run/ptp4lro", "-b", str(domain), cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return out.strip()


def _parse_pmc_kv(text: str) -> Dict[str, str]:
    kv: Dict[str, str] = {}
    for line in text.splitlines():
        m = _PMC_RE.match(line)
        if not m:
            continue
        kv[m.group(1).strip().lower()] = m.group(3).strip()
    return kv


def _parse_int(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v.strip().split()[0]))
    except Exception:
        return None


def poll_ptp_real(domain: int, trace: bool = False) -> Tuple[PTPStatus, str]:
    cds = _run_pmc(domain, "GET CURRENT_DATA_SET")
    pds = _run_pmc(domain, "GET PARENT_DATA_SET")
    ptds = _run_pmc(domain, "GET PORT_DATA_SET")
    raw = "\n\n".join([
        "GET CURRENT_DATA_SET\n" + cds,
        "GET PARENT_DATA_SET\n" + pds,
        "GET PORT_DATA_SET\n" + ptds,
    ])

    kv_cds = _parse_pmc_kv(cds)
    kv_pds = _parse_pmc_kv(pds)
    kv_ptds = _parse_pmc_kv(ptds)

    offset_ns = _parse_int(kv_cds.get("offsetfrommaster")) or _parse_int(kv_cds.get("offset from master"))
    delay_ns = _parse_int(kv_cds.get("meanpathdelay")) or _parse_int(kv_cds.get("mean path delay"))
    gm = kv_pds.get("grandmasteridentity") or kv_pds.get("grand master identity")
    port_state = (kv_ptds.get("portstate") or kv_ptds.get("port state") or "UNKNOWN").upper()

    ptp_valid = (offset_ns is not None) and (delay_ns is not None) and (port_state in {"SLAVE", "MASTER", "PASSIVE", "LISTENING"})
    gm_present = bool(gm)

    st = PTPStatus(
        ptp_valid=ptp_valid,
        gm_present=gm_present,
        port_state=port_state,
        ptp_versions="v2",
        gm_identity=gm,
        offset_ns=offset_ns,
        mean_path_delay_ns=delay_ns,
        raw=raw if trace else None,
    )

    if st.ptp_valid and st.offset_ns is not None:
        # monitoring-only synthetic "PTP time" (UTC + offsetFromMaster)
        dt = utc_now() + timedelta(microseconds=st.offset_ns / 1000.0)
        st.ptp_time_utc_iso = utc_iso_ms(dt)
        st.last_ok_utc = utc_iso_ms()
        st.no_ptp_since_utc = None
    else:
        st.ptp_time_utc_iso = None

    return st, raw
