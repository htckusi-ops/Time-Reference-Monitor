#!/usr/bin/env python3
"""
display_driver.py – LED-Matrix Zeitanzeige für Time Reference Monitor
======================================================================
Zeigt PTP / LTC / NTP-Zeit auf MAX7219 8×8 LED-Matrix Modulen (cascaded).
Liest die Zeitquellen über die lokale REST-API (/api/status).

Hardware:   MAX7219 8×8 LED-Matrix Module, via SPI
Verkabelung: DIN→GPIO10 (Pin19), CS→GPIO8 (Pin24), CLK→GPIO11 (Pin23)
Library:    pip install luma.led_matrix

Verwendung:
  python3 display_driver.py                        # 10 Module, Cycle 5s
  python3 display_driver.py --source PTP           # fix auf PTP
  python3 display_driver.py --modules 12 --cycle-s 10
  python3 display_driver.py --scroll               # langer Text scrollt durch
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone

try:
    from luma.led_matrix.device import max7219
    from luma.core.interface.serial import spi, noop
    from luma.core.render import canvas
    from luma.core.legacy import text, show_message
    from luma.core.legacy.font import proportional, CP437_FONT
except ImportError:
    print("ERROR: luma.led_matrix nicht installiert.")
    print("  pip install luma.led_matrix")
    raise

# ── Konfiguration ─────────────────────────────────────────────────────────────

DEFAULT_API    = "http://localhost:8088/api/status"
DEFAULT_MODULES = 10       # Anzahl 8×8 Module (10 = ~32cm)
DEFAULT_CYCLE_S = 5        # Sekunden pro Quelle beim automatischen Wechsel
DEFAULT_BRIGHTNESS = 64    # 0–255; 64 ist für Innenraum angenehm
SOURCES = ["PTP", "LTC", "NTP"]

# ── API ───────────────────────────────────────────────────────────────────────

def fetch_status(api_url: str) -> dict | None:
    """Holt /api/status; gibt None zurück bei Fehler."""
    try:
        with urllib.request.urlopen(api_url, timeout=2) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── Zeitquellen ───────────────────────────────────────────────────────────────

def ptp_time(snap: dict) -> str | None:
    st = snap.get("status", {})
    if st.get("ptp_valid") and st.get("ptp_time_utc_iso"):
        t = datetime.fromisoformat(st["ptp_time_utc_iso"].replace("Z", "+00:00"))
        return t.strftime("%H:%M:%S")
    return None


def ltc_time(snap: dict) -> str | None:
    ltc = snap.get("ltc", {})
    if ltc.get("present") and ltc.get("timecode"):
        return ltc["timecode"][:8]   # HH:MM:SS (ohne :FF Frames)
    return None


def ntp_time(_snap: dict) -> str:
    # Systemzeit – wird von chrony auf NTP diszipliniert
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def get_time(snap: dict, source: str) -> str | None:
    return {"PTP": ptp_time, "LTC": ltc_time, "NTP": ntp_time}[source](snap)


# ── Display ───────────────────────────────────────────────────────────────────

def render_static(device, label: str) -> None:
    """Zeigt Text statisch ab linker Kante."""
    with canvas(device) as draw:
        text(draw, (1, 0), label, fill="white", font=proportional(CP437_FONT))


def render_scroll(device, label: str, scroll_delay: float = 0.05) -> None:
    """Scrollt einen langen Text einmal von rechts nach links durch."""
    show_message(
        device,
        label,
        fill="white",
        font=proportional(CP437_FONT),
        scroll_delay=scroll_delay,
    )


# ── Hauptloop ─────────────────────────────────────────────────────────────────

def run(args) -> None:
    serial = spi(port=0, device=0, gpio=noop())
    device = max7219(
        serial,
        cascaded=args.modules,
        block_orientation=-90,    # Module hochkant montiert (üblich bei Strips)
        rotate=0,
        blocks_arranged_in_reverse_order=False,
    )
    device.contrast(args.brightness)

    sources = [args.source] if args.source else SOURCES
    idx = 0
    last_switch = time.monotonic()

    print(f"[display] Gestartet: {args.modules} Module, "
          f"Quelle={'AUTO' if not args.source else args.source}, "
          f"Cycle={args.cycle_s}s, Brightness={args.brightness}")

    while True:
        now = time.monotonic()

        # Quellenwechsel beim automatischen Cycling
        if not args.source and (now - last_switch) >= args.cycle_s:
            idx = (idx + 1) % len(sources)
            last_switch = now

        source = sources[idx % len(sources)]
        snap = fetch_status(args.api)

        if snap is None:
            label = "NO API"
        else:
            t = get_time(snap, source)
            label = f"{source} {t}" if t else f"{source} ------"

        print(f"[display] {label}")

        try:
            if args.scroll:
                render_scroll(device, label)
            else:
                render_static(device, label)
        except Exception as e:
            print(f"[display] Render-Fehler: {e}")

        # Bei statischer Anzeige jede Sekunde updaten;
        # bei scroll wartet render_scroll bereits die Scrolldauer.
        if not args.scroll:
            time.sleep(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LED-Matrix Zeitanzeige für Time Reference Monitor"
    )
    parser.add_argument(
        "--api", default=DEFAULT_API,
        help=f"API-URL (default: {DEFAULT_API})"
    )
    parser.add_argument(
        "--modules", type=int, default=DEFAULT_MODULES,
        help=f"Anzahl MAX7219 8×8 Module (default: {DEFAULT_MODULES})"
    )
    parser.add_argument(
        "--source", default=None, choices=SOURCES,
        help="Fixe Zeitquelle; ohne diese Option wechselt die Anzeige automatisch"
    )
    parser.add_argument(
        "--cycle-s", type=int, default=DEFAULT_CYCLE_S,
        help=f"Sekunden pro Quelle beim Cycle (default: {DEFAULT_CYCLE_S})"
    )
    parser.add_argument(
        "--brightness", type=int, default=DEFAULT_BRIGHTNESS,
        help=f"Helligkeit 0–255 (default: {DEFAULT_BRIGHTNESS})"
    )
    parser.add_argument(
        "--scroll", action="store_true",
        help="Text bei jedem Wechsel einmal durchscrollen"
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
