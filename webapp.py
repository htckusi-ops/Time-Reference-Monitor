# webapp.py
#
# Flask app factory for ptp-monitor v02
# - Uses StatusBus.snapshot(meta) which returns a dict:
#     {"meta": {...}, "status": {...}, "ntp": {...}, "ltc": {...}, "events": [...]}
# - UI HTML generators live in web_ui.py:
#     ui_html() -> str
#     spectrum_html() -> str
#
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from flask import Flask, Response, jsonify, request, send_file
import os
from flask import send_from_directory
from web_ui import ui_html, spectrum_html
from web_clock_ui import ltc_clock_html
from ltc_level import read_ltc_level
from config import LTC_ALSA_DEVICE

def _utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def create_app(
    bus,
    meta_provider: Callable[[], Dict[str, Any]],
    spectrum=None,
    *,
    ui_refresh_ms: int = 50,
    ui_api_poll_ms: int = 250,
) -> Flask:
    app = Flask(__name__)
    BASE_DIR = os.path.dirname(__file__)
    FONT_DIR_1 = os.path.join(BASE_DIR, "font")
    FONT_DIR_2 = os.path.join(BASE_DIR, "fonts")

    @app.get("/font/<path:filename>")
    def serve_font(filename: str):
        # akzeptiert sowohl ./font als auch ./fonts
        if os.path.isdir(FONT_DIR_1) and os.path.exists(os.path.join(FONT_DIR_1, filename)):
            return send_from_directory(FONT_DIR_1, filename)
        return send_from_directory(FONT_DIR_2, filename)

    # ---------------------------
    # UI pages
    # ---------------------------

    @app.get("/")
    def index() -> Response:
        # web_ui.ui_html() takes no args (kept stable)
        return Response(ui_html(), mimetype="text/html")

    @app.get("/spectrum")
    def spectrum_page() -> Response:
        return Response(spectrum_html(), mimetype="text/html")

    # ---------------------------
    # Core API used by web_ui.py
    # ---------------------------

    @app.get("/api/status")
    def api_status() -> Response:
        meta = meta_provider() if callable(meta_provider) else {}
        return jsonify(bus.snapshot(meta))

    @app.post("/api/pause")
    def api_pause() -> Response:
        bus.set_paused(True)
        return jsonify({"ok": True, "paused": True, "ts_utc": _utc_iso_ms()})

    @app.post("/api/resume")
    def api_resume() -> Response:
        bus.set_paused(False)
        return jsonify({"ok": True, "paused": False, "ts_utc": _utc_iso_ms()})

    @app.get("/api/events")
    def api_events() -> Response:
        meta = meta_provider() if callable(meta_provider) else {}
        snap = bus.snapshot(meta)
        return jsonify(snap.get("events", []))

    @app.get("/ltc-clock")
    def ltc_clock_page() -> Response:
        return Response(ltc_clock_html(), mimetype="text/html")

    # ---------------------------
    # Spectrum endpoints (on-demand)
    # ---------------------------

    @app.get("/api/spectrum/status")
    def api_spectrum_status() -> Response:
        if spectrum is None:
            return jsonify(
                {
                    "state": "disabled",
                    "message": "Spectrum is not configured.",
                    "device": "",
                    "duration_s": 0,
                    "has_image": False,
                    "last_generated_utc": None,
                }
            )
        return jsonify(spectrum.status())

    @app.post("/api/spectrum/generate")
    def api_spectrum_generate() -> Response:
        if spectrum is None:
            return jsonify({"ok": False, "message": "Spectrum is not configured.", "ts_utc": _utc_iso_ms()}), 400

        body = request.get_json(silent=True) or {}
        device = str(body.get("device", "")).strip()
        duration_s = int(body.get("duration_s", 0) or 0)

        if not device:
            return jsonify({"ok": False, "message": "Missing 'device'.", "ts_utc": _utc_iso_ms()}), 400
        if duration_s <= 0 or duration_s > 120:
            return jsonify({"ok": False, "message": "Invalid 'duration_s'.", "ts_utc": _utc_iso_ms()}), 400

        out = spectrum.generate(duration_s=duration_s, device=device)
        if isinstance(out, dict):
            out.setdefault("ts_utc", _utc_iso_ms())
            return jsonify(out)
        return jsonify({"ok": True, "message": str(out), "ts_utc": _utc_iso_ms()})

    @app.get("/api/spectrum/image")
    def api_spectrum_image() -> Response:
        if spectrum is None:
            return jsonify({"ok": False, "message": "Spectrum is not configured."}), 400

        b = spectrum.image_bytes()
        if not b:
            return jsonify({"ok": False, "message": "No image available yet."}), 404

        return send_file(io.BytesIO(b), mimetype="image/png")

    from config import LTC_ALSA_DEVICE
    from ltc_level import read_ltc_level

    @app.get("/api/ltc/level")
    def api_ltc_level():
        device = (request.args.get("device") or "").strip()
        if not device:
            device = LTC_ALSA_DEVICE  # <-- zentraler Default

        duration_raw = request.args.get("duration_ms", "250")
        duration_ms = int("".join(c for c in duration_raw if c.isdigit()) or "250")

        if duration_ms <= 0 or duration_ms > 2000:
            return jsonify({"error": "duration_ms out of range"}), 400

        level = read_ltc_level(device=device, duration_ms=duration_ms)
        return jsonify(level)

    return app
