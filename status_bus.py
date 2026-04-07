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
    def __init__(self, gm_window_s: int, error_window_s: int, startup_grace_s: float, db_writer: Optional[DBWriter],
                 ntp_offset_jump_threshold_s: float = 0.1,
                 ptp_offset_jump_threshold_ns: int = 50_000,
                 ptp_drift_warn_ppb: float = 300.0):
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

        self._ntp_offset_jump_threshold_s = float(ntp_offset_jump_threshold_s)
        self._ptp_offset_jump_threshold_ns = int(ptp_offset_jump_threshold_ns)
        self._ptp_drift_warn_ppb = float(ptp_drift_warn_ppb)

        self._last_gm: Optional[str] = None
        self._last_ptp_valid: Optional[bool] = None
        self._last_ptp_offset_ns: Optional[int] = None
        self._last_port_state: Optional[str] = None
        # sliding window for drift: deque of (monotonic_time, offset_ns)
        self._ptp_drift_history: Deque = deque(maxlen=40)
        self._last_ptp_drift_event_mono: Optional[float] = None
        self._last_ntp_status: Optional[str] = None
        self._last_ntp_ref: Optional[str] = None
        self._last_ntp_offset_s: Optional[float] = None
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

    def _append_event_locked(self, ev: Event) -> None:
        """Append event and update all counters. Must be called with _lock already held."""
        self._events.appendleft(ev)
        if self._db:
            self._db.insert_event(ev.ts_utc, ev.severity, ev.type, ev.message, ev.suppressed)
        if ev.suppressed:
            return
        if ev.severity in ("WARN", "ALARM"):
            self._sum.errors_total += 1
            self._roll_err.add()
        if ev.severity == "WARN":
            self._sum.warnings_total += 1
            self._roll_warn.add()
        if ev.severity == "ALARM":
            self._sum.alarms_total += 1
            self._roll_alarm.add()

    def add_event(self, severity: str, type_: str, message: str) -> None:
        suppressed = self._should_suppress_for_state(severity)
        ev = Event(ts_utc=utc_iso_ms(), severity=severity, type=type_, message=message, suppressed=suppressed)
        with self._lock:
            self._append_event_locked(ev)

    def update_ptp(self, ptp: PTPStatus) -> None:
        with self._lock:
            if ptp.ptp_valid:
                self._first_ptp_ok_seen = True

            # ── GM change ─────────────────────────────────────────────────────
            if ptp.gm_identity and self._last_gm and ptp.gm_identity != self._last_gm:
                self._sum.gm_changes_total += 1
                self._roll_gm.add()
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity="WARN", type="PTP_GM_CHANGED",
                                              message=f"Grandmaster changed: {self._last_gm} -> {ptp.gm_identity}",
                                              suppressed=self._should_suppress_for_state("WARN")))
            if ptp.gm_identity:
                self._last_gm = ptp.gm_identity

            # ── loss / recovery ───────────────────────────────────────────────
            if self._last_ptp_valid is not None and self._last_ptp_valid and (not ptp.ptp_valid):
                self._sum.ptp_loss_total += 1
                self._roll_ptp_loss.add()
                self._ptp_drift_history.clear()
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity="ALARM", type="PTP_LOST",
                                              message="PTP sync lost.",
                                              suppressed=self._should_suppress_for_state("ALARM")))
            elif self._last_ptp_valid is not None and (not self._last_ptp_valid) and ptp.ptp_valid:
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity="INFO", type="PTP_RECOVERED",
                                              message=f"PTP sync recovered. GM={ptp.gm_identity or '—'} state={ptp.port_state or '—'}",
                                              suppressed=False))
            self._last_ptp_valid = ptp.ptp_valid

            # ── port state change ─────────────────────────────────────────────
            if ptp.port_state and self._last_port_state and ptp.port_state != self._last_port_state:
                sev = "INFO" if ptp.port_state in ("SLAVE", "MASTER") else "WARN"
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity=sev, type="PTP_PORT_STATE_CHANGED",
                                              message=f"PTP port state: {self._last_port_state} -> {ptp.port_state}",
                                              suppressed=self._should_suppress_for_state(sev)))
            if ptp.port_state:
                self._last_port_state = ptp.port_state

            if ptp.ptp_valid and ptp.offset_ns is not None:
                # ── offset jump (single-poll spike) ───────────────────────────
                if (self._last_ptp_offset_ns is not None
                        and abs(ptp.offset_ns - self._last_ptp_offset_ns) > self._ptp_offset_jump_threshold_ns):
                    delta_us = (ptp.offset_ns - self._last_ptp_offset_ns) / 1000.0
                    self._append_event_locked(Event(
                        ts_utc=utc_iso_ms(), severity="WARN", type="PTP_OFFSET_JUMP",
                        message=f"PTP offset jump: {delta_us:+.1f} µs (now {ptp.offset_ns / 1000:.1f} µs)",
                        suppressed=self._should_suppress_for_state("WARN"),
                    ))
                self._last_ptp_offset_ns = ptp.offset_ns

                # ── sustained drift via linear regression ─────────────────────
                # Store (monotonic_time, offset_ns) for OLS slope estimation.
                # Requires ≥20 samples; SE(slope) ≈ σ_jitter/√Σ(t-t̄)² — with
                # maxlen=40 and 300 ppb threshold this avoids false triggers even
                # at jitter=2 µs while reliably catching drift ≥ 300 ppb.
                mono_now = time.monotonic()
                self._ptp_drift_history.append((mono_now, ptp.offset_ns))
                n = len(self._ptp_drift_history)
                if n >= 20:
                    ts_vals = [t for t, _ in self._ptp_drift_history]
                    os_vals = [o for _, o in self._ptp_drift_history]
                    t_mean = sum(ts_vals) / n
                    o_mean = sum(os_vals) / n
                    num = sum((ts_vals[i] - t_mean) * (os_vals[i] - o_mean) for i in range(n))
                    den = sum((ts_vals[i] - t_mean) ** 2 for i in range(n))
                    if den > 0:
                        drift_ppb = num / den  # ns/s ≡ ppb
                        dt_span = ts_vals[-1] - ts_vals[0]
                        cooldown_ok = (self._last_ptp_drift_event_mono is None
                                       or (mono_now - self._last_ptp_drift_event_mono) > 60.0)
                        if abs(drift_ppb) > self._ptp_drift_warn_ppb and cooldown_ok:
                            self._last_ptp_drift_event_mono = mono_now
                            self._ptp_drift_history.clear()
                            sev = "ALARM" if abs(drift_ppb) > self._ptp_drift_warn_ppb * 5 else "WARN"
                            self._append_event_locked(Event(
                                ts_utc=utc_iso_ms(), severity=sev, type="PTP_DRIFT_DETECTED",
                                message=f"PTP drift: {drift_ppb:+.0f} ppb over {dt_span:.0f} s",
                                suppressed=self._should_suppress_for_state(sev),
                            ))
            else:
                self._ptp_drift_history.clear()

            self._ptp = ptp

    def update_ntp(self, ntp: NTPStatus) -> None:
        with self._lock:
            # ── status transitions ────────────────────────────────────────────
            if self._last_ntp_status is not None and ntp.status != self._last_ntp_status:
                self._sum.ntp_flaps_total += 1
                self._roll_ntp_flap.add()
                if ntp.status == "unsynced":
                    self._append_event_locked(Event(
                        ts_utc=utc_iso_ms(), severity="ALARM", type="NTP_LOST",
                        message="NTP sync lost (unsynced).",
                        suppressed=self._should_suppress_for_state("ALARM"),
                    ))
                elif ntp.status == "synced":
                    self._append_event_locked(Event(
                        ts_utc=utc_iso_ms(), severity="INFO", type="NTP_RECOVERED",
                        message=f"NTP sync recovered. ref={ntp.ref or '—'} stratum={ntp.stratum or '—'}",
                        suppressed=False,
                    ))
                else:
                    self._append_event_locked(Event(
                        ts_utc=utc_iso_ms(), severity="WARN", type="NTP_STATUS_CHANGED",
                        message=f"NTP status changed: {self._last_ntp_status} -> {ntp.status}",
                        suppressed=self._should_suppress_for_state("WARN"),
                    ))
            self._last_ntp_status = ntp.status

            # ── reference server change ───────────────────────────────────────
            if ntp.ref and self._last_ntp_ref and ntp.ref != self._last_ntp_ref:
                self._append_event_locked(Event(
                    ts_utc=utc_iso_ms(), severity="WARN", type="NTP_REF_CHANGED",
                    message=f"NTP reference changed: {self._last_ntp_ref} -> {ntp.ref} (stratum={ntp.stratum or '—'})",
                    suppressed=self._should_suppress_for_state("WARN"),
                ))
            if ntp.ref:
                self._last_ntp_ref = ntp.ref

            # ── large offset jump ─────────────────────────────────────────────
            if (ntp.system_offset_s is not None
                    and self._last_ntp_offset_s is not None
                    and abs(ntp.system_offset_s - self._last_ntp_offset_s) > self._ntp_offset_jump_threshold_s):
                delta_ms = (ntp.system_offset_s - self._last_ntp_offset_s) * 1000.0
                self._append_event_locked(Event(
                    ts_utc=utc_iso_ms(), severity="WARN", type="NTP_OFFSET_JUMP",
                    message=f"NTP offset jump: {delta_ms:+.1f} ms (now {ntp.system_offset_s * 1000:.1f} ms)",
                    suppressed=self._should_suppress_for_state("WARN"),
                ))
            if ntp.system_offset_s is not None:
                self._last_ntp_offset_s = ntp.system_offset_s

            self._ntp = ntp

    def update_ltc(self, ltc: LTCStatus) -> None:
        with self._lock:
            # loss / recovery
            if self._last_ltc_present is not None and self._last_ltc_present and (not ltc.present):
                self._sum.ltc_loss_total += 1
                self._roll_ltc_loss.add()
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity="WARN", type="LTC_LOST",
                                              message="LTC signal lost.",
                                              suppressed=self._should_suppress_for_state("WARN")))
            elif self._last_ltc_present is not None and (not self._last_ltc_present) and ltc.present:
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity="INFO", type="LTC_RECOVERED",
                                              message=f"LTC signal recovered. tc={ltc.timecode or '—'} fps={ltc.fps or '—'}",
                                              suppressed=False))
            self._last_ltc_present = ltc.present

            # decode errors (count as WARN in summary)
            if ltc.decode_errors_total > self._sum.ltc_decode_errors_total:
                delta = ltc.decode_errors_total - self._sum.ltc_decode_errors_total
                self._sum.ltc_decode_errors_total = ltc.decode_errors_total
                for _ in range(delta):
                    self._roll_ltc_decode.add()
                # one event per burst
                self._append_event_locked(Event(ts_utc=utc_iso_ms(), severity="WARN", type="LTC_DECODE_ERROR",
                                              message=f"LTC decode errors increased by {delta} (total={ltc.decode_errors_total}).",
                                              suppressed=self._should_suppress_for_state("WARN")))
            # jumps (time discontinuities)
            if getattr(ltc, "jumps_total", 0) > getattr(self._sum, "ltc_jumps_total", 0):
                delta = int(getattr(ltc, "jumps_total", 0) - getattr(self._sum, "ltc_jumps_total", 0))
                self._sum.ltc_jumps_total = int(getattr(ltc, "jumps_total", 0))
                for _ in range(delta):
                    self._roll_ltc_jump.add()
                self._append_event_locked(Event(
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