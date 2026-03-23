from __future__ import annotations
import dataclasses
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Deque

from models import Event, PTPStatus, NTPStatus, LTCStatus, Summaries
from rolling import RollingCounter
import config
from db import DBWriter


def utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class StatusBus:
    def __init__(self, gm_window_s: int, error_window_s: int, startup_grace_s: float, db_writer: Optional[DBWriter]):
        self._lock = threading.Lock()

        self._ptp = PTPStatus()
        self._ntp = NTPStatus()
        self._ltc = LTCStatus(enabled=False)

        self._events: Deque[Event] = deque(maxlen=config.EVENTS_MAXLEN)

        self._gm_window_s = int(gm_window_s)
        self._error_window_s = int(error_window_s)

        self._roll_err = RollingCounter(self._error_window_s)
        self._roll_warn = RollingCounter(self._error_window_s)
        self._roll_alarm = RollingCounter(self._error_window_s)
        self._roll_gm = RollingCounter(self._gm_window_s)
        self._roll_ptp_loss = RollingCounter(self._error_window_s)
        self._roll_ntp_flap = RollingCounter(self._error_window_s)
        self._roll_ltc_loss = RollingCounter(self._error_window_s)
        self._roll_ltc_decode = RollingCounter(self._error_window_s)
        self._roll_ltc_jump = RollingCounter(self._error_window_s)

        self._sum = Summaries()

        self._last_gm: Optional[str] = None
        self._last_ptp_valid: Optional[bool] = None
        self._last_ntp_status: Optional[str] = None
        self._last_ltc_present: Optional[bool] = None

        self._db = db_writer

        self._t_start = time.monotonic()
        self._startup_grace_s = float(startup_grace_s)
        self._first_ptp_ok_seen = False

        # Pause control: UI pause should freeze time; API still answers.
        self._paused = False
        self._pause_ts_utc: Optional[str] = None

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = bool(paused)
            self._pause_ts_utc = utc_iso_ms() if self._paused else None

    def paused(self) -> bool:
        with self._lock:
            return self._paused

    def startup_active(self) -> bool:
        return (time.monotonic() - self._t_start) < self._startup_grace_s

    def _should_suppress_for_state(self, severity: str) -> bool:
        if severity not in ("WARN", "ALARM"):
            return False
        # suppress WARN/ALARM during startup grace until first ptp ok seen OR grace ends
        if self.startup_active() and not self._first_ptp_ok_seen:
            return True
        return False

    def add_event(self, severity: str, type_: str, message: str) -> None:
        suppressed = self._should_suppress_for_state(severity)
        ev = Event(ts_utc=utc_iso_ms(), severity=severity, type=type_, message=message, suppressed=suppressed)

        with self._lock:
            self._events.appendleft(ev)

            if self._db:
                self._db.insert_event(ev.ts_utc, ev.severity, ev.type, ev.message, ev.suppressed)

            if suppressed:
                return

            if severity in ("WARN", "ALARM"):
                self._sum.errors_total += 1
                self._roll_err.add()
            if severity == "WARN":
                self._sum.warnings_total += 1
                self._roll_warn.add()
            if severity == "ALARM":
                self._sum.alarms_total += 1
                self._roll_alarm.add()

    def update_ptp(self, ptp: PTPStatus) -> None:
        with self._lock:
            if ptp.ptp_valid:
                self._first_ptp_ok_seen = True

            if ptp.gm_identity and self._last_gm and ptp.gm_identity != self._last_gm:
                self._sum.gm_changes_total += 1
                self._roll_gm.add()
                self._events.appendleft(Event(ts_utc=utc_iso_ms(), severity="WARN", type="PTP_GM_CHANGED",
                                              message=f"Grandmaster changed: {self._last_gm} -> {ptp.gm_identity}",
                                              suppressed=self._should_suppress_for_state("WARN")))
            if ptp.gm_identity:
                self._last_gm = ptp.gm_identity

            if self._last_ptp_valid is not None and self._last_ptp_valid and (not ptp.ptp_valid):
                self._sum.ptp_loss_total += 1
                self._roll_ptp_loss.add()
                self._events.appendleft(Event(ts_utc=utc_iso_ms(), severity="ALARM", type="PTP_LOST",
                                              message="PTP became invalid (monitor hides PTP time).",
                                              suppressed=self._should_suppress_for_state("ALARM")))
            self._last_ptp_valid = ptp.ptp_valid
            self._ptp = ptp

    def update_ntp(self, ntp: NTPStatus) -> None:
        with self._lock:
            if self._last_ntp_status is not None and ntp.status != self._last_ntp_status:
                self._sum.ntp_flaps_total += 1
                self._roll_ntp_flap.add()
                self._events.appendleft(Event(ts_utc=utc_iso_ms(), severity="WARN", type="NTP_STATUS_CHANGED",
                                              message=f"NTP status changed: {self._last_ntp_status} -> {ntp.status}",
                                              suppressed=self._should_suppress_for_state("WARN")))
            self._last_ntp_status = ntp.status
            self._ntp = ntp

    def update_ltc(self, ltc: LTCStatus) -> None:
        with self._lock:
            # loss
            if self._last_ltc_present is not None and self._last_ltc_present and (not ltc.present):
                self._sum.ltc_loss_total += 1
                self._roll_ltc_loss.add()
                self._events.appendleft(Event(ts_utc=utc_iso_ms(), severity="WARN", type="LTC_LOST",
                                              message="LTC became absent.",
                                              suppressed=self._should_suppress_for_state("WARN")))
            self._last_ltc_present = ltc.present

            # decode errors (count as WARN in summary)
            if ltc.decode_errors_total > self._sum.ltc_decode_errors_total:
                delta = ltc.decode_errors_total - self._sum.ltc_decode_errors_total
                self._sum.ltc_decode_errors_total = ltc.decode_errors_total
                for _ in range(delta):
                    self._roll_ltc_decode.add()
                # one event per burst
                self._events.appendleft(Event(ts_utc=utc_iso_ms(), severity="WARN", type="LTC_DECODE_ERROR",
                                              message=f"LTC decode errors increased by {delta} (total={ltc.decode_errors_total}).",
                                              suppressed=self._should_suppress_for_state("WARN")))
            # jumps (time discontinuities)
            if getattr(ltc, "jumps_total", 0) > getattr(self._sum, "ltc_jumps_total", 0):
                delta = int(getattr(ltc, "jumps_total", 0) - getattr(self._sum, "ltc_jumps_total", 0))
                self._sum.ltc_jumps_total = int(getattr(ltc, "jumps_total", 0))
                for _ in range(delta):
                    self._roll_ltc_jump.add()
                self._events.appendleft(Event(
                    ts_utc=utc_iso_ms(),
                    severity="WARN",
                    type="LTC_JUMP",
                    message=f"LTC time jump detected (+{delta}, total={ltc.jumps_total}).",
                    suppressed=self._should_suppress_for_state("WARN"),
                ))

            self._ltc = ltc

    def snapshot(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            roll = dataclasses.replace(self._sum)
            roll.errors_rolling = self._roll_err.count()
            roll.warnings_rolling = self._roll_warn.count()
            roll.alarms_rolling = self._roll_alarm.count()
            roll.gm_changes_rolling = self._roll_gm.count()
            roll.ptp_loss_rolling = self._roll_ptp_loss.count()
            roll.ntp_flaps_rolling = self._roll_ntp_flap.count()
            roll.ltc_loss_rolling = self._roll_ltc_loss.count()
            roll.ltc_decode_errors_rolling = self._roll_ltc_decode.count()
            roll.ltc_jumps_rolling = self._roll_ltc_jump.count()

            return {
                "meta": {
                    **meta,
                    "ts_utc": utc_iso_ms(),
                    "startup_active": self.startup_active() and not self._first_ptp_ok_seen,
                    "paused": self._paused,
                    "pause_ts_utc": self._pause_ts_utc,
                    "summaries": dataclasses.asdict(self._sum),
                    "summaries_rolling": dataclasses.asdict(roll),
                    "db": (self._db.meta() if self._db else None),
                },
                "status": dataclasses.asdict(self._ptp),
                "ntp": dataclasses.asdict(self._ntp),
                "ltc": dataclasses.asdict(self._ltc),
                "events": [dataclasses.asdict(e) for e in list(self._events)[:200]],
            }