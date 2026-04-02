from __future__ import annotations
import argparse
import dataclasses
import threading
import time
from datetime import datetime, timezone

import config
from db import DBWriter
from models import LTCStatus
from sources_ntp import read_chrony_tracking
from sources_ptp import poll_ptp_real
from sources_ltc import LTCMonitor
from mock_sim import MockParams, MockPTP, MockNTPParams, MockNTP
from status_bus import StatusBus
from webapp import create_app
from spectrum import SpectrumManager


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ptp_monitor.py", description=config.APP_TITLE)

    ap.add_argument("--db", default=config.DEFAULT_DB_PATH, help="SQLite database path (events). Use empty to disable.")
    ap.add_argument("--db-max-events", type=int, default=config.DEFAULT_DB_MAX_EVENTS, help="Max events in DB (retention).")

    ap.add_argument("--iface", default="eth0", help="Interface name (labeling)")
    ap.add_argument("--domain", type=int, default=0, help="PTP domain number (pmc -b)")
    ap.add_argument("--source", choices=["mock", "real"], default="real", help="PTP source type")
    ap.add_argument("--poll", type=float, default=0.5, help="PTP polling interval (seconds)")
    ap.add_argument("--display-decimals", type=int, default=6, help="Decimals for displayed PTP time (0..6)")

    ap.add_argument("--http", action="store_true", help="Enable HTTP server with UI and /api/status")
    ap.add_argument("--http-host", default="0.0.0.0")
    ap.add_argument("--http-port", type=int, default=8088)

    ap.add_argument("--ui-refresh-ms", type=int, default=config.DEFAULT_UI_REFRESH_MS, help="UI clock refresh interval (ms)")
    ap.add_argument("--ui-api-poll-ms", type=int, default=config.DEFAULT_UI_API_POLL_MS, help="UI API polling interval (ms) for /api/status")
    ap.add_argument("--stale-threshold-ms", type=int, default=config.DEFAULT_STALE_THRESHOLD_MS, help="Stale threshold (ms) for state ALARM")
    ap.add_argument("--gm-window-s", type=int, default=config.DEFAULT_GM_WINDOW_S, help="GM change window (seconds)")
    ap.add_argument("--error-window-s", type=int, default=config.DEFAULT_ERROR_WINDOW_S, help="Rolling error summary window (seconds)")
    ap.add_argument("--startup-grace-s", type=float, default=6.0, help="Startup grace before WARN/ALARM are counted (until first PTP OK).")
    ap.add_argument("--trace", action="store_true", help="Enable verbose diagnostics (kept for compat)")

    ap.add_argument("--ntp-refresh-s", type=float, default=config.DEFAULT_NTP_REFRESH_S, help="NTP refresh interval (seconds)")

    ap.add_argument("--ltc", action="store_true", help="Enable LTC monitoring")
    ap.add_argument("--ltc-device", default="default", help="ALSA device for LTC input, e.g. hw:1,0")
    ap.add_argument("--ltc-fps", default="25", help="Expected LTC frame rate")
    ap.add_argument("--ltc-cmd", default=None, help="Override LTC decode command (must output HH:MM:SS:FF)")
    ap.add_argument("--ltc-refresh-s", type=float, default=config.DEFAULT_LTC_REFRESH_S, help="LTC snapshot refresh interval (seconds)")
    ap.add_argument("--ltc-dropout-timeout-ms", type=int, default=0, help="Mark LTC absent if no frame received for this long (ms). 0 disables.")
    ap.add_argument("--ltc-jump-tolerance-frames", type=int, default=5, help="Warn on LTC time jumps larger than this many frames. 0 disables. Default 5 suppresses jitter.")

    # Mock simulation knobs
    ap.add_argument("--mock-jitter-ns", type=int, default=0)
    ap.add_argument("--mock-wander-ns", type=int, default=0)
    ap.add_argument("--mock-wander-period-s", type=float, default=10.0)
    ap.add_argument("--mock-drift-ppb", type=float, default=0.0)
    ap.add_argument("--mock-step-every-s", type=float, default=0.0)
    ap.add_argument("--mock-step-ns", type=int, default=0)
    ap.add_argument("--mock-dropout-every-s", type=float, default=0.0)
    ap.add_argument("--mock-dropout-duration-s", type=float, default=0.0)
    ap.add_argument("--mock-gm-flap-every-s", type=float, default=0.0)

    return ap


def main() -> None:
    args = build_parser().parse_args()
    args.display_decimals = max(0, min(6, int(args.display_decimals)))

    dbw = None
    if args.db and args.db.strip():
        dbw = DBWriter(args.db, args.db_max_events)
        dbw.open()

    bus = StatusBus(
        gm_window_s=int(args.gm_window_s),
        error_window_s=int(args.error_window_s),
        startup_grace_s=float(args.startup_grace_s),
        db_writer=dbw,
    )

    meta = {
        "iface": args.iface,
        "domain": int(args.domain),
        "source": args.source,
        "poll_s": float(args.poll),
        "gm_window_s": int(args.gm_window_s),
        "error_window_s": int(args.error_window_s),
        "stale_threshold_ms": int(args.stale_threshold_ms),
        "trace": bool(args.trace),
        "display_decimals": int(args.display_decimals),
        "ui_refresh_ms": int(args.ui_refresh_ms),
        "ui_api_poll_ms": int(args.ui_api_poll_ms),
    }

    bus.add_event("INFO", "START", f"Started (source={args.source}, iface={args.iface}, domain={args.domain})")

    # ── NTP mock presets ──────────────────────────────────────────────────────
    NTP_MOCK_PRESETS = {
        "clean":    MockNTPParams(jitter_s=5e-6),
        "jitter":   MockNTPParams(jitter_s=500e-6, wander_s=100e-6),
        "drift":    MockNTPParams(jitter_s=5e-6, drift_ppm=0.5),
        "step":     MockNTPParams(jitter_s=5e-6, step_every_s=30, step_s=0.5),
        "ref_flap": MockNTPParams(jitter_s=5e-6, ref_flap_every_s=20),
        "unsynced": MockNTPParams(jitter_s=5e-6, unsynced_every_s=30, unsynced_duration_s=10),
        "combo":    MockNTPParams(jitter_s=200e-6, wander_s=1e-3, drift_ppm=0.2, ref_flap_every_s=60),
    }

    # ── NTP runtime-switchable source ─────────────────────────────────────────
    _ntp_src_lock = threading.Lock()
    _ntp_src = {"mock": None, "params": None}

    def get_ntp_source():
        with _ntp_src_lock:
            return {"source": "mock" if _ntp_src["mock"] else "real", "params": _ntp_src["params"]}

    def set_ntp_source(mock_instance_or_none, params_dict=None):
        with _ntp_src_lock:
            _ntp_src["mock"] = mock_instance_or_none
            _ntp_src["params"] = params_dict
        label = "mock" if mock_instance_or_none else "real"
        bus.add_event("INFO", "NTP_SOURCE_CHANGED", f"NTP source switched to {label}")

    # ── PTP mock presets ──────────────────────────────────────────────────────
    MOCK_PRESETS = {
        "clean":    MockParams(jitter_ns=50),
        "jitter":   MockParams(jitter_ns=2000, wander_ns=500),
        "wander":   MockParams(jitter_ns=500, wander_ns=10_000, wander_period_s=60),
        "dropout":  MockParams(jitter_ns=100, dropout_every_s=20, dropout_duration_s=5),
        "gm_flap":  MockParams(jitter_ns=100, gm_flap_every_s=30),
        "drift":    MockParams(jitter_ns=100, drift_ppb=500),
        "step":     MockParams(jitter_ns=100, step_every_s=30, step_ns=100_000),
    }

    # ── Runtime-switchable PTP source ─────────────────────────────────────────
    # _src["mock"] = None  → real ptp4l polling
    # _src["mock"] = MockPTP(...)  → simulation
    _src_lock = threading.Lock()
    _initial_mock = None
    if args.source == "mock":
        mp = MockParams(
            jitter_ns=args.mock_jitter_ns,
            wander_ns=args.mock_wander_ns,
            wander_period_s=args.mock_wander_period_s,
            drift_ppb=args.mock_drift_ppb,
            step_every_s=args.mock_step_every_s,
            step_ns=args.mock_step_ns,
            dropout_every_s=args.mock_dropout_every_s,
            dropout_duration_s=args.mock_dropout_duration_s,
            gm_flap_every_s=args.mock_gm_flap_every_s,
        )
        _initial_mock = MockPTP(mp)
    _src = {"mock": _initial_mock, "params": dataclasses.asdict(_initial_mock.p) if _initial_mock else None}

    def get_ptp_source():
        with _src_lock:
            return {"source": "mock" if _src["mock"] else "real", "params": _src["params"]}

    def set_ptp_source(mock_instance_or_none, params_dict=None):
        with _src_lock:
            _src["mock"] = mock_instance_or_none
            _src["params"] = params_dict
        label = "mock" if mock_instance_or_none else "real"
        bus.add_event("INFO", "SOURCE_CHANGED", f"PTP source switched to {label}")

    def meta_provider():
        with _src_lock:
            active = "mock" if _src["mock"] else "real"
        return {**meta, "tz_offset_s": time.localtime().tm_gmtoff, "source": active}

    def ptp_loop():
        last_poll = time.monotonic()
        no_ptp_since = None

        while True:
            t0 = time.monotonic()
            try:
                with _src_lock:
                    cur_mock = _src["mock"]
                if cur_mock is not None:
                    st, raw = cur_mock.poll()
                else:
                    st, raw = poll_ptp_real(int(args.domain), trace=bool(args.trace))

                now = time.monotonic()
                st.poll_age_ms = int((now - last_poll) * 1000.0)
                last_poll = now

                if not st.ptp_valid:
                    if no_ptp_since is None:
                        no_ptp_since = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                    st.no_ptp_since_utc = no_ptp_since
                else:
                    no_ptp_since = None
                    st.no_ptp_since_utc = None

                if args.trace and st.raw is None:
                    st.raw = raw

                bus.update_ptp(st)
            except Exception as e:
                bus.add_event("ALARM", "PTP_POLL_ERROR", f"PTP poll failed: {e!r}")

            dt = time.monotonic() - t0
            time.sleep(max(0.0, float(args.poll) - dt))

    def ntp_loop():
        while True:
            try:
                with _ntp_src_lock:
                    cur_ntp_mock = _ntp_src["mock"]
                if cur_ntp_mock is not None:
                    st, raw = cur_ntp_mock.poll()
                else:
                    st, raw = read_chrony_tracking()
                    if args.trace:
                        st.raw = raw
                if st.last_update_utc:
                    try:
                        t = datetime.fromisoformat(st.last_update_utc)
                        st.last_update_age_s = max(0.0, (utc_now() - t).total_seconds())
                    except Exception:
                        st.last_update_age_s = None
                bus.update_ntp(st)
            except Exception as e:
                bus.add_event("WARN", "NTP_READ_ERROR", f"NTP read failed: {e!r}")
            time.sleep(max(0.2, float(args.ntp_refresh_s)))

    ltc_mon = None

    def ltc_snapshot_loop():
        while True:
            try:
                assert ltc_mon is not None
                bus.update_ltc(ltc_mon.snapshot())
            except Exception as e:
                bus.add_event("WARN", "LTC_SNAPSHOT_ERROR", f"LTC snapshot failed: {e!r}")
            time.sleep(max(0.2, float(args.ltc_refresh_s)))

    threading.Thread(target=ptp_loop, daemon=True, name="ptp-loop").start()
    threading.Thread(target=ntp_loop, daemon=True, name="ntp-loop").start()

    if args.ltc:
        ltc_mon = LTCMonitor(
            True,
            args.ltc_device,
            args.ltc_fps,
            args.ltc_cmd,
            bool(args.trace),
            int(args.error_window_s),
            dropout_timeout_ms=int(args.ltc_dropout_timeout_ms),
            jump_tolerance_frames=int(args.ltc_jump_tolerance_frames),
        )
        ltc_mon.start()
        threading.Thread(target=ltc_snapshot_loop, daemon=True, name="ltc-snap").start()
        bus.add_event("INFO", "LTC_ENABLED", f"LTC enabled: device={args.ltc_device} fps={args.ltc_fps}")
    else:
        bus.update_ltc(LTCStatus(enabled=False, present=False))

    spectrum = SpectrumManager()

    if args.http:
        app = create_app(
            bus,
            meta_provider,
            spectrum=spectrum,
            ui_refresh_ms=int(args.ui_refresh_ms),
            ui_api_poll_ms=int(args.ui_api_poll_ms),
            get_ptp_source=get_ptp_source,
            set_ptp_source=set_ptp_source,
            mock_presets=MOCK_PRESETS,
            ptp_domain=int(args.domain),
            get_ntp_source=get_ntp_source,
            set_ntp_source=set_ntp_source,
            ntp_mock_presets=NTP_MOCK_PRESETS,
        )
        app.run(host=args.http_host, port=int(args.http_port), threaded=True)
    else:
        while True:
            time.sleep(1.0)
