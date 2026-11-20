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


# ── LTC jump delta helpers ────────────────────────────────────────────────────

def _ptp_tod_s(iso: Optional[str]) -> Optional[float]:
    """Extract seconds-of-day from a UTC ISO timestamp string."""
    if not iso:
        return None
    t = iso.find('T')
    if t < 0:
        return None
    s = iso[t + 1:]
    try:
        hh, mm, ss = int(s[0:2]), int(s[3:5]), int(s[6:8])
    except (ValueError, IndexError):
        return None
    frac = 0.0
    if len(s) > 9 and s[8] == '.':
        end = 9
        while end < len(s) and s[end].isdigit():
            end += 1
        try:
            frac = float('0.' + s[9:end])
        except ValueError:
            pass
    return float(hh * 3600 + mm * 60 + ss) + frac


def _ltc_tod_s(tc: str, fps: int) -> Optional[float]:
    """Convert LTC timecode HH:MM:SS:FF to seconds of day."""
    p = tc.split(':')
    if len(p) != 4:
        return None
    try:
        return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2]) + int(p[3]) / max(1, fps)
    except (ValueError, IndexError):
        return None


def _ltc_tz_s(ltc_tz: Optional[str]) -> float:
    """Parse '±HHMM' LTC timezone string to signed offset in seconds."""
    if not ltc_tz or len(ltc_tz) < 5:
        return 0.0
    try:
        sign = 1 if ltc_tz[0] == '+' else -1
        return float(sign * (int(ltc_tz[1:3]) * 3600 + int(ltc_tz[3:5]) * 60))
    except (ValueError, IndexError):
        return 0.0


def _wrap_delta_s(ds: float) -> float:
    """Wrap a TOD delta to ±12 h to handle midnight boundary crossings."""
    day = 86400.0
    ds %= day
    return ds - day if ds > day / 2 else ds


def _fmt_delta_ms(ms: float) -> str:
    """Format a millisecond delta as '±NNN ms' or '±Mm SS.SSSs' for large values."""
    sign = '+' if ms >= 0 else '-'
    a = abs(ms)
    if a < 5000.0:
        return f"{sign}{a:.0f} ms"
    mins = int(a // 60000)
    rem = a - mins * 60000
    secs = rem / 1000.0
    if mins > 0:
        return f"{sign}{mins}m {secs:.3f}s"
    return f"{sign}{secs:.3f}s"


class StatusBus:
    def __init__(self, gm_window_s: int, error_window_s: int, startup_grace_s: float, db_writer: Optional[DBWriter],
                 ntp_offset_jump_threshold_s: float = 0.1,
                 ptp_offset_jump_threshold_ns: int = 50_000,
                 ptp_drift_warn_ppb: float = 300.0,
                 ltc_jump_alarm_ms: float = 500.0):
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
        self._roll_ltc_jump_alarm = RollingCounter(self._error_window_s)

        self._sum = Summaries()

        self._ntp_offset_jump_threshold_s = float(ntp_offset_jump_threshold_s)
        self._ptp_offset_jump_threshold_ns = int(ptp_offset_jump_threshold_ns)
        self._ptp_drift_warn_ppb = float(ptp_drift_warn_ppb)
        self._ltc_jump_alarm_ms = float(ltc_jump_alarm_ms)

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
                elif ntp.status == "stale":
                    age = f" ({ntp.last_update_age_s:.0f} s ago)" if ntp.last_update_age_s is not None else ""
                    self._append_event_locked(Event(
                        ts_utc=utc_iso_ms(), severity="WARN", type="NTP_STALE",
                        message=f"NTP reference time stale{age} — server unreachable?",
                        suppressed=self._should_suppress_for_state("WARN"),
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
            # jumps (time discontinuities) — emit rich event with Δ(LTC−PTP/NTP)
            if getattr(ltc, "jumps_total", 0) > getattr(self._sum, "ltc_jumps_total", 0):
                n_new = int(getattr(ltc, "jumps_total", 0) - getattr(self._sum, "ltc_jumps_total", 0))
                self._sum.ltc_jumps_total = int(getattr(ltc, "jumps_total", 0))
                for _ in range(n_new):
                    self._roll_ltc_jump.add()

                fps = max(1, int(float(ltc.fps or "25") or 25))
                tc_after  = ltc.last_jump_tc_after  or ltc.timecode or "?"
                tc_before = ltc.last_jump_tc_before or "?"
                jump_frames = getattr(ltc, "last_jump_delta_frames", 0)
                jump_ms = jump_frames * 1000.0 / fps

                # Δ(LTC−PTP): convert LTC to UTC using its embedded tz offset
                tz_off_s = _ltc_tz_s(ltc.ltc_tz)
                ltc_tod  = _ltc_tod_s(tc_after, fps)
                ptp_tod  = _ptp_tod_s(self._ptp.ptp_time_utc_iso)

                d_ptp_str = "—"
                d_ntp_str = "—"
                is_alarm  = False

                if ltc_tod is not None and ptp_tod is not None:
                    d_ptp = _wrap_delta_s(ltc_tod - tz_off_s - ptp_tod) * 1000.0
                    d_ptp_str = _fmt_delta_ms(d_ptp)
                    if self._ltc_jump_alarm_ms > 0 and abs(d_ptp) > self._ltc_jump_alarm_ms:
                        is_alarm = True

                    # Δ(LTC−NTP) ≈ Δ(LTC−PTP) − system_offset (avoids second datetime.now())
                    ntp_off_s = self._ntp.system_offset_s or 0.0
                    d_ntp = d_ptp - ntp_off_s * 1000.0
                    d_ntp_str = _fmt_delta_ms(d_ntp)
                    if self._ltc_jump_alarm_ms > 0 and abs(d_ntp) > self._ltc_jump_alarm_ms:
                        is_alarm = True

                sev = "ALARM" if is_alarm else "WARN"
                if is_alarm:
                    self._sum.ltc_jump_alarms_total += 1
                    self._roll_ltc_jump_alarm.add()

                msg = (
                    f"LTC jump: {_fmt_delta_ms(jump_ms)} "
                    f"({tc_before} → {tc_after}). "
                    f"Δ(LTC−PTP)={d_ptp_str}, Δ(LTC−NTP)={d_ntp_str}."
                )
                self._append_event_locked(Event(
                    ts_utc=utc_iso_ms(),
                    severity=sev,
                    type="LTC_JUMP",
                    message=msg,
                    suppressed=self._should_suppress_for_state(sev),
                ))

            self._ltc = ltc

    def reset_summaries(self) -> None:
        """Reset all rolling counters and cumulative totals to zero."""
        with self._lock:
            for rc in (self._roll_err, self._roll_warn, self._roll_alarm,
                       self._roll_gm, self._roll_ptp_loss, self._roll_ntp_flap,
                       self._roll_ltc_loss, self._roll_ltc_decode, self._roll_ltc_jump,
                       self._roll_ltc_jump_alarm):
                rc._q.clear()
            self._sum = Summaries()
            # Re-seed LTC delta-tracked totals so the very next update_ltc()
            # doesn't fire false events for already-counted jumps/decode errors.
            if self._ltc is not None:
                self._sum.ltc_decode_errors_total = self._ltc.decode_errors_total
                self._sum.ltc_jumps_total = int(getattr(self._ltc, "jumps_total", 0))

    def snapshot(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        db_meta = self._db.meta() if self._db else None
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
            roll.ltc_jump_alarms_rolling = self._roll_ltc_jump_alarm.count()

            return {
                "meta": {
                    **meta,
                    "ltc_jump_alarm_ms": self._ltc_jump_alarm_ms,
                    "ts_utc": utc_iso_ms(),
                    "startup_active": self.startup_active() and not self._first_ptp_ok_seen,
                    "paused": self._paused,
                    "pause_ts_utc": self._pause_ts_utc,
                    "summaries": dataclasses.asdict(self._sum),
                    "summaries_rolling": dataclasses.asdict(roll),
                    "db": db_meta,
                },
                "status": dataclasses.asdict(self._ptp),
                "ntp": dataclasses.asdict(self._ntp),
                "ltc": dataclasses.asdict(self._ltc),
                "events": [dataclasses.asdict(e) for e in list(self._events)[:200]],
            }