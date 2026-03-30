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
      sdi-1080i50|sdi-1080p50)
        # The RPi GPU outputs the correct HDMI timing (interlaced or progressive)
        # based on hdmi_mode in config.txt – set by setup.sh / update.sh.
        # The X framebuffer is always PROGRESSIVE 1920x1080; the GPU handles
        # interlacing at output.  Do NOT use an interlaced xrandr modeline – it
        # conflicts with the GPU's own output timing and produces no signal.
        #
        # Strategy: use 1920x1080 if already available (normal after reboot with
        # correct config.txt), otherwise add a custom progressive modeline.
        echo "[kiosk] SDI-Modus (${HDMI_MODE}): Setze ${OUTPUT} auf 1920×1080 progressiv…"
        if xrandr --query | grep -q "1920x1080"; then
            xrandr --output "$OUTPUT" --mode "1920x1080" \
                || xrandr --output "$OUTPUT" --auto
        else
            # Fallback: add progressive 1920x1080 modeline (60Hz safe default)
            # config.txt already sets the actual 50Hz/interlaced HDMI output timing.
            xrandr --newmode "1920x1080_60" 148.50 \
                1920 2008 2052 2200 \
                1080 1084 1089 1125 \
                +hsync +vsync 2>/dev/null || true
            xrandr --addmode "$OUTPUT" "1920x1080_60" 2>/dev/null || true
            xrandr --output "$OUTPUT" --mode "1920x1080_60" \
                || xrandr --output "$OUTPUT" --auto
        fi
        # Important: config.txt must be set correctly (hdmi_mode=20 for 1080i50,
        # hdmi_mode=31 for 1080p50) and a REBOOT is required for the GPU to output
        # the correct HDMI signal to the Blackmagic converter.
        echo "[kiosk] config.txt HDMI-Signal: $(grep 'hdmi_mode=' /boot/firmware/config.txt /boot/config.txt 2>/dev/null | tail -1 || echo 'unbekannt')"
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

