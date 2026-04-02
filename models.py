from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    ts_utc: str
    severity: str  # INFO/WARN/ALARM
    type: str
    message: str
    suppressed: bool = False  # for startup-grace accounting


@dataclass
class PTPStatus:
    ptp_valid: bool = False
    gm_present: bool = False
    port_state: str = "UNKNOWN"
    ptp_versions: str = "v2"
    gm_identity: Optional[str] = None
    offset_ns: Optional[int] = None
    mean_path_delay_ns: Optional[int] = None
    ptp_time_utc_iso: Optional[str] = None
    poll_age_ms: Optional[int] = None
    no_ptp_since_utc: Optional[str] = None
    last_ok_utc: Optional[str] = None
    raw: Optional[str] = None


@dataclass
class NTPStatus:
    status: str = "unknown"          # synced/unsynced/unknown
    stratum: Optional[int] = None
    ref: Optional[str] = None
    last_update_utc: Optional[str] = None
    last_update_age_s: Optional[float] = None
    system_offset_s: Optional[float] = None  # chrony: NTP_time - system_clock (+ = system slow)
    raw: Optional[str] = None


@dataclass
class LTCStatus:
    enabled: bool = False
    device: str = ""
    fps: str = ""
    present: bool = False
    timecode: Optional[str] = None
    last_update_utc: Optional[str] = None
    last_update_age_s: Optional[float] = None
    no_ltc_since_utc: Optional[str] = None
    decode_errors_total: int = 0
    decode_errors_rolling: int = 0
    jumps_total: int = 0
    jumps_rolling: int = 0
    alsa_delay_ms: Optional[float] = None   # ALSA capture buffer latency (probed at startup)
    raw: Optional[str] = None


@dataclass
class Summaries:
    # totals
    errors_total: int = 0
    warnings_total: int = 0
    alarms_total: int = 0
    gm_changes_total: int = 0
    ptp_loss_total: int = 0
    ntp_flaps_total: int = 0
    ltc_loss_total: int = 0
    ltc_decode_errors_total: int = 0
    ltc_jumps_total: int = 0

    # rolling
    errors_rolling: int = 0
    warnings_rolling: int = 0
    alarms_rolling: int = 0
    gm_changes_rolling: int = 0
    ptp_loss_rolling: int = 0
    ntp_flaps_rolling: int = 0
    ltc_loss_rolling: int = 0
    ltc_decode_errors_rolling: int = 0
    ltc_jumps_rolling: int = 0
