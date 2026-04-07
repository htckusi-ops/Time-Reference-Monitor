from __future__ import annotations
import subprocess
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple, Optional

from models import PTPStatus
import config


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso_ms(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = utc_now()
    return dt.isoformat(timespec="milliseconds")


def _run_pmc(domain: int, cmd: str, timeout_s: float = config.PMC_TIMEOUT_S) -> str:
    client_sock = f"/tmp/pmc.{os.getpid()}"
    p = subprocess.run(
        ["pmc", "-u", "-i", client_sock, "-s", "/var/run/ptp4lro", "-d", str(domain), cmd],
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
        s = line.strip()
        if not s:
            continue
        if s.startswith("sending:"):
            continue
        if " RESPONSE MANAGEMENT " in s:
            continue

        if ":" in s:
            k, v = s.split(":", 1)
        elif "=" in s:
            k, v = s.split("=", 1)
        else:
            parts = s.split(None, 1)
            if len(parts) != 2:
                continue
            k, v = parts

        kv[k.strip().lower()] = v.strip()
    return kv


def _parse_int(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v.strip().split()[0]))
    except Exception:
        return None


_TIME_SOURCE_LABELS: Dict[int, str] = {
    0x10: "ATOMIC_CLOCK",
    0x20: "GPS",
    0x30: "TERRESTRIAL_RADIO",
    0x40: "PTP",
    0x50: "NTP",
    0x60: "HAND_SET",
    0x90: "OTHER",
    0xa0: "INTERNAL_OSC",
}


def poll_ptp_real(domain: int, trace: bool = False) -> Tuple[PTPStatus, str]:
    cds  = _run_pmc(domain, "GET CURRENT_DATA_SET")
    pds  = _run_pmc(domain, "GET PARENT_DATA_SET")
    ptds = _run_pmc(domain, "GET PORT_DATA_SET")
    tpds = _run_pmc(domain, "GET TIME_PROPERTIES_DATA_SET")
    raw = "\n\n".join([
        "GET CURRENT_DATA_SET\n" + cds,
        "GET PARENT_DATA_SET\n" + pds,
        "GET PORT_DATA_SET\n" + ptds,
        "GET TIME_PROPERTIES_DATA_SET\n" + tpds,
    ])

    kv_cds  = _parse_pmc_kv(cds)
    kv_pds  = _parse_pmc_kv(pds)
    kv_ptds = _parse_pmc_kv(ptds)
    kv_tpds = _parse_pmc_kv(tpds)

    offset_ns = _parse_int(kv_cds.get("offsetfrommaster"))
    if offset_ns is None:
        offset_ns = _parse_int(kv_cds.get("offset from master"))

    delay_ns = _parse_int(kv_cds.get("meanpathdelay"))
    if delay_ns is None:
        delay_ns = _parse_int(kv_cds.get("mean path delay"))

    gm_identity = (kv_pds.get("grandmasteridentity") or kv_pds.get("grand master identity") or "").strip() or None
    port_state  = (kv_ptds.get("portstate") or "UNKNOWN").strip().upper()

    ptp_valid = (
        offset_ns is not None
        and delay_ns is not None
        and port_state in {"SLAVE", "MASTER", "PASSIVE", "LISTENING"}
    )
    gm_present = bool(gm_identity)

    # GM clock quality (only meaningful when GM is present)
    gm_priority1 = _parse_int(kv_pds.get("grandmasterpriority1"))
    gm_priority2 = _parse_int(kv_pds.get("grandmasterpriority2"))
    gm_clock_class = _parse_int(
        kv_pds.get("grandmasterclockquality.clockclass")
        or kv_pds.get("grandmasterclock quality.clockclass")
    )
    gm_clock_acc_raw = (
        kv_pds.get("grandmasterclockquality.clockaccuracy")
        or kv_pds.get("grandmasterclock quality.clockaccuracy")
        or ""
    ).strip() or None
    parent_port = (kv_pds.get("parentportidentity") or kv_pds.get("parent port identity") or "").strip() or None

    # Time properties
    ts_raw = (kv_tpds.get("timesource") or kv_tpds.get("time source") or "").strip()
    time_source: Optional[str] = None
    if ts_raw:
        try:
            ts_val = int(ts_raw, 0)
            time_source = _TIME_SOURCE_LABELS.get(ts_val, ts_raw)
        except ValueError:
            time_source = ts_raw

    def _bool_field(k: str) -> Optional[bool]:
        v = (kv_tpds.get(k) or "").strip()
        if v in ("1", "true", "yes"):
            return True
        if v in ("0", "false", "no"):
            return False
        return None

    time_traceable      = _bool_field("timetraceable")
    frequency_traceable = _bool_field("frequencytraceable")
    utc_offset          = _parse_int(kv_tpds.get("currentutcoffset") or kv_tpds.get("current utc offset"))
    ptp_timescale_raw   = _bool_field("ptptimescale")

    st = PTPStatus(
        ptp_valid=ptp_valid,
        gm_present=gm_present,
        port_state=port_state,
        ptp_versions="v2" if ptp_valid else None,
        gm_identity=gm_identity,
        offset_ns=offset_ns,
        mean_path_delay_ns=delay_ns,
        raw=raw if trace else None,
        gm_priority1=gm_priority1 if gm_present else None,
        gm_priority2=gm_priority2 if gm_present else None,
        gm_clock_class=gm_clock_class if gm_present else None,
        gm_clock_accuracy=gm_clock_acc_raw if gm_present else None,
        parent_port_identity=parent_port,
        time_source=time_source,
        time_traceable=time_traceable,
        frequency_traceable=frequency_traceable,
        utc_offset=utc_offset,
        ptp_timescale=ptp_timescale_raw,
    )

    if st.ptp_valid and st.offset_ns is not None:
        # ptp4l offsetFromMaster = slave - master  →  master = slave - offset
        dt = utc_now() - timedelta(microseconds=st.offset_ns / 1000.0)
        st.ptp_time_utc_iso = utc_iso_ms(dt)
        st.last_ok_utc = utc_iso_ms()
        st.no_ptp_since_utc = None
    else:
        st.ptp_time_utc_iso = None

    return st, raw
