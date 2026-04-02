from __future__ import annotations
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from models import PTPStatus, NTPStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso_ms(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = utc_now()
    return dt.isoformat(timespec="milliseconds")


@dataclass
class MockParams:
    jitter_ns: int = 0
    wander_ns: int = 0
    wander_period_s: float = 10.0
    drift_ppb: float = 0.0
    step_every_s: float = 0.0
    step_ns: int = 0
    dropout_every_s: float = 0.0
    dropout_duration_s: float = 0.0
    gm_flap_every_s: float = 0.0


@dataclass
class MockNTPParams:
    jitter_s: float = 0.0             # random noise on system_offset_s (seconds)
    wander_s: float = 0.0             # slow sinusoidal wander amplitude (seconds)
    wander_period_s: float = 60.0     # wander period (seconds)
    drift_ppm: float = 0.0            # linear clock drift (ppm)
    step_every_s: float = 0.0         # periodic offset step interval (0 = off)
    step_s: float = 0.0               # step size (seconds, positive = system slow)
    ref_flap_every_s: float = 0.0     # flip NTP reference server every N s (0 = off)
    unsynced_every_s: float = 0.0     # go unsynced every N s (0 = off)
    unsynced_duration_s: float = 0.0  # duration of unsynced state
    stratum: int = 2                  # base NTP stratum


class MockNTP:
    """Simulates chronyc tracking output for NTP failure scenario testing."""
    _REFS = ("192.168.1.1", "10.0.0.1")

    def __init__(self, params: MockNTPParams):
        self.p = params
        self.t0 = time.monotonic()
        self.last_step_t = self.t0
        self.last_unsynced_t = self.t0
        self.in_unsynced_until = 0.0
        self.ref_index = 0
        self.last_ref_flap_t = self.t0

    def poll(self) -> Tuple[NTPStatus, str]:
        now = time.monotonic()
        dt = now - self.t0

        # unsynced / dropout simulation
        if self.p.unsynced_every_s and self.p.unsynced_every_s > 0:
            if now >= self.in_unsynced_until and (now - self.last_unsynced_t) >= self.p.unsynced_every_s:
                self.last_unsynced_t = now
                self.in_unsynced_until = now + max(0.0, self.p.unsynced_duration_s)

        if now < self.in_unsynced_until:
            st = NTPStatus(
                status="unsynced",
                stratum=None,
                ref=None,
                last_update_utc=utc_iso_ms(),
                system_offset_s=None,
            )
            return st, "mock:unsynced"

        # reference server flap simulation
        if self.p.ref_flap_every_s and self.p.ref_flap_every_s > 0 and (now - self.last_ref_flap_t) >= self.p.ref_flap_every_s:
            self.last_ref_flap_t = now
            self.ref_index = 1 - self.ref_index

        # wander (slow sine)
        wander = 0.0
        if self.p.wander_s and self.p.wander_period_s > 0:
            wander = self.p.wander_s * math.sin(2 * math.pi * dt / self.p.wander_period_s)

        # drift (ppm → s accumulated)
        drift = 0.0
        if self.p.drift_ppm:
            drift = (self.p.drift_ppm * 1e-6) * dt

        # random jitter
        jitter = 0.0
        if self.p.jitter_s:
            jitter = random.uniform(-self.p.jitter_s, self.p.jitter_s)

        # step every N seconds (one-poll spike — simulates sudden offset event)
        step = 0.0
        if self.p.step_every_s and self.p.step_every_s > 0 and (now - self.last_step_t) >= self.p.step_every_s:
            self.last_step_t = now
            step = float(self.p.step_s)

        system_offset_s = wander + drift + jitter + step
        ref = self._REFS[self.ref_index]
        # bump stratum by 1 on alternate reference to simulate ref change with quality impact
        stratum = self.p.stratum + self.ref_index

        st = NTPStatus(
            status="synced",
            stratum=stratum,
            ref=ref,
            last_update_utc=utc_iso_ms(),
            system_offset_s=system_offset_s,
        )
        return st, "mock"


class MockPTP:
    def __init__(self, params: MockParams):
        self.p = params
        self.t0 = time.monotonic()
        self.last_step_t = self.t0
        self.last_dropout_t = self.t0
        self.in_dropout_until = 0.0
        self.gm = "AC-DE-48-FF-FE-12-34-56"
        self.last_gm_flap_t = self.t0

    def poll(self) -> Tuple[PTPStatus, str]:
        now = time.monotonic()
        dt = now - self.t0

        # dropout simulation
        if self.p.dropout_every_s and self.p.dropout_every_s > 0:
            if now >= self.in_dropout_until and (now - self.last_dropout_t) >= self.p.dropout_every_s:
                self.last_dropout_t = now
                self.in_dropout_until = now + max(0.0, self.p.dropout_duration_s)

        if now < self.in_dropout_until:
            st = PTPStatus(
                ptp_valid=False,
                gm_present=False,
                port_state="UNKNOWN",
                ptp_versions="v2",
                gm_identity=None,
                offset_ns=None,
                mean_path_delay_ns=None,
                ptp_time_utc_iso=None,
            )
            return st, "mock:dropout"

        # gm flap simulation
        if self.p.gm_flap_every_s and self.p.gm_flap_every_s > 0 and (now - self.last_gm_flap_t) >= self.p.gm_flap_every_s:
            self.last_gm_flap_t = now
            # flip last byte
            if self.gm.endswith("56"):
                self.gm = "AC-DE-48-FF-FE-12-34-57"
            else:
                self.gm = "AC-DE-48-FF-FE-12-34-56"

        # wander (slow sine)
        wander = 0.0
        if self.p.wander_ns and self.p.wander_period_s > 0:
            wander = self.p.wander_ns * math.sin(2 * math.pi * dt / self.p.wander_period_s)

        # drift (linear)
        drift = 0.0
        if self.p.drift_ppb:
            drift = (self.p.drift_ppb * 1e-9) * dt * 1e9  # ppb -> fraction -> ns

        # random jitter
        jitter = 0.0
        if self.p.jitter_ns:
            jitter = random.uniform(-self.p.jitter_ns, self.p.jitter_ns)

        # step every N seconds
        step = 0.0
        if self.p.step_every_s and self.p.step_every_s > 0 and (now - self.last_step_t) >= self.p.step_every_s:
            self.last_step_t = now
            step = float(self.p.step_ns)

        offset_ns = int(wander + drift + jitter + step)
        delay_ns = 8978

        st = PTPStatus(
            ptp_valid=True,
            gm_present=True,
            port_state="SLAVE",
            ptp_versions="v2",
            gm_identity=self.gm,
            offset_ns=offset_ns,
            mean_path_delay_ns=delay_ns,
            ptp_time_utc_iso=utc_iso_ms(utc_now() + timedelta(microseconds=offset_ns / 1000.0)),
            last_ok_utc=utc_iso_ms(),
        )
        return st, "mock"
