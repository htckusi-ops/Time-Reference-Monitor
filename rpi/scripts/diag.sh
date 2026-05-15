#!/usr/bin/env bash
# diag.sh – Time Reference Monitor Freeze-Diagnose
#
# Schreibt NICHTS auf die SD-Karte. Alle Ausgaben gehen nach stdout.
#
# Nutzung:
#   bash rpi/scripts/diag.sh            # Ausgabe im Terminal (scrollbar)
#   bash rpi/scripts/diag.sh 2>&1 | less
#
# Für den Python-Thread-Dump (wenn /api/status hängt):
#   Das Script sendet SIGUSR2 an den Python-Prozess — faulthandler dumpt
#   alle Thread-Stacks nach stderr → sichtbar in journalctl danach.

set -uo pipefail

BACKEND="http://localhost:8088"
SEP="════════════════════════════════════════════════════════════════"

section() {
    echo
    echo "$SEP"
    printf "  %s\n" "$1"
    echo "$SEP"
}

ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m⚠\033[0m %s\n" "$*"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$*"; }

# ── Header ───────────────────────────────────────────────────────────────────
echo "$SEP"
echo "  TIME REFERENCE MONITOR — Freeze-Diagnose"
echo "  $(date '+%Y-%m-%d %H:%M:%S %Z')  |  $(hostname)"
echo "$SEP"
uptime

# ── Service Status ────────────────────────────────────────────────────────────
section "SERVICE STATUS — time-reference-monitor"
systemctl status time-reference-monitor --no-pager -l 2>&1 || true

section "SERVICE STATUS — chromium-kiosk"
systemctl status chromium-kiosk --no-pager -l 2>&1 || true

# ── Backend API Check ─────────────────────────────────────────────────────────
section "BACKEND API CHECK"

api_check() {
    local url="$1" label="$2"
    printf "  %-35s " "${label}:"
    local out
    if out=$(curl -sf --max-time 5 "$url" 2>&1); then
        ok "OK — ${out:0:120}"
    else
        err "TIMEOUT / FEHLER (curl exit $?)"
    fi
}

api_check "${BACKEND}/api/ltc/level"    "/api/ltc/level  (timeout 5 s)"
api_check "${BACKEND}/api/status"       "/api/status     (timeout 5 s)"

echo
echo "  /api/debug/logs (in-memory buffer, timeout 3 s):"
if curl -sf --max-time 3 "${BACKEND}/api/debug/logs?n=50" 2>/dev/null \
        | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  [{d.get(\"total_buffered\",\"?\")} Einträge im Buffer, letzte 50:]')
for l in d.get('lines', []): print(' ', l)
" 2>/dev/null; then
    true
else
    warn "/api/debug/logs nicht erreichbar oder Fehler"
fi

# ── Flask-Verbindungen ────────────────────────────────────────────────────────
section "FLASK-VERBINDUNGEN (Port 8088)"
ss -tnp 2>/dev/null | grep -E "8088" | head -20 || echo "  (keine aktiven Verbindungen)"
echo
echo "  Offene Verbindungen total:"
ss -tnp 2>/dev/null | grep -c "8088" || echo "  0"

# ── Prozesse ─────────────────────────────────────────────────────────────────
section "PROZESSE (relevant)"
ps aux | head -1
ps aux | grep -E 'python3|alsaltc|arecord|Xorg|chromium|xinit|openbox' | grep -v grep

# ── Python Thread Dump via SIGUSR2 ────────────────────────────────────────────
section "PYTHON THREAD DUMP (SIGUSR2 → faulthandler)"
PY_PID=$(pgrep -f "python3 run.py" 2>/dev/null | head -1 || true)
if [ -n "${PY_PID:-}" ]; then
    echo "  Python PID: $PY_PID — sende SIGUSR2…"
    kill -SIGUSR2 "$PY_PID" 2>/dev/null && {
        sleep 0.5
        ok "Signal gesendet. Thread-Dump in journalctl (siehe unten)."
    } || err "SIGUSR2 fehlgeschlagen (Berechtigungen?)"
else
    warn "Python-Prozess nicht gefunden — kein Thread-Dump möglich."
fi

# ── Speicher ─────────────────────────────────────────────────────────────────
section "SPEICHER"
free -h

# ── Top-CPU-Prozesse ──────────────────────────────────────────────────────────
section "TOP-PROZESSE NACH CPU"
ps aux --sort=-%cpu 2>/dev/null | head -12 || ps aux | head -12

# ── ALSA ─────────────────────────────────────────────────────────────────────
section "ALSA-GERÄTE"
arecord -l 2>&1 || echo "  (arecord nicht verfügbar)"

echo
echo "  ALSA-Gerätestatus (/proc/asound):"
for f in /proc/asound/card*/pcm*/sub*/status; do
    [ -f "$f" ] || continue
    echo "  --- $f ---"
    sed 's/^/    /' "$f"
done

# ── Journal Logs ──────────────────────────────────────────────────────────────
section "LOGS — time-reference-monitor (letzte 120 Zeilen)"
journalctl -u time-reference-monitor -n 120 --no-pager 2>&1

section "LOGS — chromium-kiosk (letzte 40 Zeilen)"
journalctl -u chromium-kiosk -n 40 --no-pager 2>&1

# Thread-Dump erscheint kurz nach SIGUSR2 in den Logs oben;
# falls noch nicht sichtbar, nochmals nachlesen:
if [ -n "${PY_PID:-}" ]; then
    echo
    echo "  Thread-Dump (letzte 5 Einträge nach SIGUSR2):"
    sleep 0.3
    journalctl -u time-reference-monitor -n 5 --no-pager 2>&1 | sed 's/^/  /'
fi

# ── Xorg Log ─────────────────────────────────────────────────────────────────
section "XORG LOG (letzte 30 Zeilen)"
XORG_LOG="/home/ptp/.local/share/xorg/Xorg.0.log"
if [ -f "$XORG_LOG" ]; then
    tail -30 "$XORG_LOG"
else
    warn "Nicht gefunden: $XORG_LOG"
fi

# ── Kernel dmesg ─────────────────────────────────────────────────────────────
section "KERNEL — dmesg (letzte 30 Zeilen, USB/ALSA-Fehler zuerst)"
echo "  USB/ALSA-Fehler:"
dmesg -T 2>/dev/null | grep -iE 'usb|alsa|snd|audio|xhci|disconnect|error|killed' | tail -20 \
    || dmesg | grep -iE 'usb|alsa|snd|audio|error' | tail -20 || echo "  (keine)"
echo
echo "  Alle letzten 30 Kernel-Meldungen:"
dmesg -T 2>/dev/null | tail -30 || dmesg | tail -30

# ── Fertig ────────────────────────────────────────────────────────────────────
section "FERTIG"
echo "  Zeitstempel Ende: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo
echo "  Nächste Schritte:"
echo "    • Obige Ausgabe komplett kopieren und für die Analyse bereitstellen"
echo "    • Falls /api/status TIMEOUT: StatusBus-Lock blockiert → Thread-Dump prüfen"
echo "    • Falls /api/ltc/level TIMEOUT: Flask-Threadpool erschöpft → ss-Ausgabe prüfen"
echo "    • Kiosk neustarten: sudo systemctl restart chromium-kiosk"
echo "    • Backend neustarten: sudo systemctl restart time-reference-monitor"
echo
