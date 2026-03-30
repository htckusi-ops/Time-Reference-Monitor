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
# HDMI_MODE und HDMI_OUTPUT aus /etc/time-reference-monitor.conf.
#
# PROBLEM: hdmi_force_hotplug=1 in config.txt erzwingt ALLE RPi-HDMI-Ports
# als "connected" – auch ohne angeschlossenes Gerät.  X11 erstellt dann
# automatisch einen kombinierten Framebuffer (z.B. 3840×1080 auf RPi 4
# mit zwei HDMI-Ports).  Chromium --kiosk füllt diesen vollständig aus;
# der SDI-Konverter zeigt nur den linken 1920-px-Streifen → "halbes Bild".
#
# FIX: Ziel-Output konfigurieren, alle anderen Outputs deaktivieren,
# Framebuffer-Grösse explizit auf 1920×1080 setzen.
#
# HDMI_OUTPUT (aus conf-Datei) erlaubt explizite Port-Wahl:
#   HDMI_OUTPUT=HDMI-1   # RPi 4, Port näher zur USB-C-Buchse
#   HDMI_OUTPUT=HDMI-2   # RPi 4, zweiter Port
#   HDMI_OUTPUT=HDMI-A-1 # RPi 5
# Leer lassen = Auto-Erkennung (erster "connected" in Prioritätsreihenfolge).

# Alle verbundenen Outputs sammeln
ALL_CONNECTED=()
while IFS= read -r line; do
    ALL_CONNECTED+=("$line")
done < <(xrandr --query | grep ' connected' | awk '{print $1}')

echo "[kiosk] Verbundene Outputs: ${ALL_CONNECTED[*]:-keine}"

# Ziel-Output bestimmen
OUTPUT=""
if [ -n "${HDMI_OUTPUT:-}" ]; then
    if xrandr --query | grep -q "^${HDMI_OUTPUT} "; then
        OUTPUT="$HDMI_OUTPUT"
        echo "[kiosk] Verwende konfigurierten Output: ${OUTPUT}"
    else
        echo "[kiosk] WARN: HDMI_OUTPUT=${HDMI_OUTPUT} nicht gefunden – Auto-Erkennung."
    fi
fi
if [ -z "$OUTPUT" ]; then
    for name in HDMI-1 HDMI-A-1 HDMI-2 HDMI-A-2; do
        if xrandr --query | grep -q "^${name} connected"; then
            OUTPUT="$name"
            break
        fi
    done
fi

if [ -n "$OUTPUT" ]; then
    # Modus auf Ziel-Output setzen
    case "$HDMI_MODE" in
      sdi-720p50)
        echo "[kiosk] SDI 720p50: Setze ${OUTPUT} auf 1280×720p @ 50 Hz…"
        # CEA-19: 74.25 MHz – same pixel clock as 1080i50, different blanking
        xrandr --newmode "1280x720p50" 74.25 \
            1280 1720 1760 1980 \
            720 725 730 750 \
            +hsync +vsync 2>/dev/null || true
        xrandr --addmode "$OUTPUT" "1280x720p50" 2>/dev/null || true
        xrandr --output "$OUTPUT" --mode "1280x720p50" \
            || { echo "[kiosk] WARN: 720p50 Modeline fehlgeschlagen – Fallback auto."; \
                 xrandr --output "$OUTPUT" --auto; }
        FB_SIZE="1280x720"
        ;;
      sdi-1080i50)
        # RPi OS Bookworm: vc4-kms-v3d (Full KMS) – config.txt hdmi_mode ignoriert.
        # xrandr steuert den HDMI-Output.  hdmi_force_hotplug=1 hilft Blackmagic-
        # Konvertern ohne EDID (Port erscheint trotzdem als "connected").
        echo "[kiosk] SDI 1080i50: Setze ${OUTPUT} auf 1920×1080i @ 50 Hz…"
        xrandr --newmode "1920x1080i50" 74.25 \
            1920 2448 2492 2640 \
            1080 1084 1094 1125 \
            interlace +hsync +vsync 2>/dev/null || true
        xrandr --addmode "$OUTPUT" "1920x1080i50" 2>/dev/null || true
        xrandr --output "$OUTPUT" --mode "1920x1080i50" \
            || { echo "[kiosk] WARN: 1080i50 Modeline fehlgeschlagen – Fallback auto."; \
                 xrandr --output "$OUTPUT" --auto; }
        FB_SIZE="1920x1080"
        ;;
      sdi-1080p50)
        echo "[kiosk] SDI 1080p50: Setze ${OUTPUT} auf 1920×1080p @ 50 Hz…"
        xrandr --newmode "1920x1080p50" 148.50 \
            1920 2448 2492 2640 \
            1080 1084 1089 1125 \
            +hsync +vsync 2>/dev/null || true
        xrandr --addmode "$OUTPUT" "1920x1080p50" 2>/dev/null || true
        xrandr --output "$OUTPUT" --mode "1920x1080p50" \
            || { echo "[kiosk] WARN: 1080p50 Modeline fehlgeschlagen – Fallback auto."; \
                 xrandr --output "$OUTPUT" --auto; }
        FB_SIZE="1920x1080"
        ;;
      auto|*)
        echo "[kiosk] Auto-Auflösung auf ${OUTPUT}…"
        xrandr --output "$OUTPUT" --auto
        FB_SIZE=""
        ;;
    esac

    # Alle anderen Outputs deaktivieren – verhindert kombinierten Framebuffer.
    for other in "${ALL_CONNECTED[@]}"; do
        [ "$other" = "$OUTPUT" ] && continue
        echo "[kiosk] Deaktiviere ${other} (verhindert kombinierten Framebuffer)"
        xrandr --output "$other" --off 2>/dev/null || true
    done

    # Framebuffer-Grösse explizit setzen – verhindert, dass X einen
    # breiteren virtuellen Screen behält, nachdem andere Outputs deaktiviert wurden.
    if [ -n "${FB_SIZE:-}" ]; then
        xrandr --fb "$FB_SIZE" 2>/dev/null || true
        echo "[kiosk] Framebuffer: ${FB_SIZE}"
    fi

    echo "[kiosk] Auflösung aktiv: $(xrandr --query | grep "^${OUTPUT}" | grep -o '[0-9]*x[0-9]*+[0-9]*+[0-9]*' | head -1)"
else
    echo "[kiosk] WARN: Kein HDMI-Output gefunden – Auflösung nicht gesetzt."
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

