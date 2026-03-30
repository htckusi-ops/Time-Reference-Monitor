#!/bin/bash
# kiosk.sh – runs inside the X session started by xinit
# Called by: chromium-kiosk.service via xinit … -- :0 vt7
#
# Waits for the backend HTTP server, then opens Chromium in kiosk mode.

set -euo pipefail

BACKEND_URL="http://localhost:8088"
KIOSK_URL="${BACKEND_URL}/"
WAIT_TIMEOUT=60   # seconds to wait for backend before opening anyway

# ── Runtime configuration ─────────────────────────────────────────────────────
# Defaults (overridden by /etc/time-reference-monitor.conf)
HDMI_MODE=sdi-1080i50

KIOSK_CONF="/etc/time-reference-monitor.conf"
# shellcheck source=/dev/null
[ -f "$KIOSK_CONF" ] && source "$KIOSK_CONF"

# ── Display tweaks ────────────────────────────────────────────────────────────
# Disable DPMS (Energy Star) power-saving and screen blanking.
xset -dpms
xset s off
xset s noblank

# Hide the mouse pointer after 1 second of inactivity (requires unclutter).
if command -v unclutter &>/dev/null; then
    unclutter -idle 1 -root &
fi

# ── HDMI-Auflösung setzen ─────────────────────────────────────────────────────
# HDMI_MODE wird aus /etc/time-reference-monitor.conf gelesen (s.o.).
# Den korrekten Output-Namen ermitteln: xrandr --query
# Üblich auf RPi: HDMI-1 (RPi 4) oder HDMI-A-1 (RPi 5 / neuere Kernel)

OUTPUT=""
for name in HDMI-1 HDMI-A-1 HDMI-2 HDMI-A-2; do
    if xrandr --query | grep -q "^${name} connected"; then
        OUTPUT="$name"
        break
    fi
done

if [ -n "$OUTPUT" ]; then
    case "$HDMI_MODE" in
      sdi-1080i50)
        echo "[kiosk] Setze ${OUTPUT} auf 1920×1080i @ 50 Hz (1080i50, CEA-20)…"
        # Modeline 1080i50: Pixelclock 74.25 MHz, SMPTE 274M interlaced
        xrandr --newmode "1920x1080i50" 74.25 \
            1920 2448 2492 2640 \
            1080 1084 1094 1125 \
            interlace +hsync +vsync 2>/dev/null || true
        xrandr --addmode "$OUTPUT" "1920x1080i50" 2>/dev/null || true
        xrandr --output "$OUTPUT" --mode "1920x1080i50" \
            || { echo "[kiosk] WARN: 1080i50 nicht gesetzt – Fallback auf auto."; \
                 xrandr --output "$OUTPUT" --auto; }
        ;;
      sdi-1080p50)
        echo "[kiosk] Setze ${OUTPUT} auf 1920×1080p @ 50 Hz (1080p50, CEA-31)…"
        # Modeline 1080p50: Pixelclock 148.5 MHz, SMPTE 274M progressive
        xrandr --newmode "1920x1080p50" 148.50 \
            1920 2448 2492 2640 \
            1080 1084 1089 1125 \
            +hsync +vsync 2>/dev/null || true
        xrandr --addmode "$OUTPUT" "1920x1080p50" 2>/dev/null || true
        xrandr --output "$OUTPUT" --mode "1920x1080p50" \
            || { echo "[kiosk] WARN: 1080p50 nicht gesetzt – Fallback auf auto."; \
                 xrandr --output "$OUTPUT" --auto; }
        ;;
      auto|*)
        echo "[kiosk] Setze ${OUTPUT} auf Auto-Auflösung (Monitor-Präferenz)…"
        xrandr --output "$OUTPUT" --auto
        ;;
    esac
    echo "[kiosk] Auflösung aktiv: $(xrandr --query | grep "^${OUTPUT}" | grep -o '[0-9]*x[0-9]*+[0-9]*+[0-9]*' | head -1)"
else
    echo "[kiosk] WARN: Kein verbundener HDMI-Output gefunden – Auflösung nicht gesetzt."
fi

# ── Wait for the backend ──────────────────────────────────────────────────────
echo "[kiosk] Waiting for backend at ${BACKEND_URL} …"
deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
while ! curl -sf --max-time 2 "${BACKEND_URL}/api/status" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "[kiosk] Backend not ready after ${WAIT_TIMEOUT}s – opening anyway."
        break
    fi
    sleep 2
done
echo "[kiosk] Backend ready – starting Chromium."

# ── Chromium kiosk ───────────────────────────────────────────────────────────
# --kiosk              : full-screen, no window decorations, no address bar
# --noerrdialogs       : suppress crash / error pop-ups
# --disable-infobars   : no "Chrome is being controlled…" bar
# --no-first-run       : skip first-run wizard
# --disable-pinch      : disable touchscreen zoom gestures
# --overscroll-history-navigation=0 : disable swipe-back/forward
# --disable-restore-session-state   : never show "restore pages?" dialog
# --temp-profile       : do not persist browsing state between sessions
exec /usr/bin/chromium \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --no-first-run \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-restore-session-state \
    --temp-profile \
    "${KIOSK_URL}"

