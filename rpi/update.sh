#!/bin/bash
# update.sh – Update Time-Reference-Monitor from the git repository
#
# Run from the cloned repository root (where this script lives under rpi/):
#   sudo bash rpi/update.sh
#
# What this script does:
#   1. git pull (latest code from origin)
#   2. rsync application files to /opt/time-reference-monitor
#   3. Update Python dependencies (if requirements.txt changed)
#   4. Recompile and reinstall alsaltc (if C source is newer than binary)
#   5. Update systemd service files (if changed)
#   6. Update sudoers rule (idempotent)
#   7. Restart the monitor service
#
# The kiosk service (chromium-kiosk) is NOT restarted automatically
# as Chromium will reload the UI on its own once the backend is back up.

set -euo pipefail

APP_USER="${APP_USER:-ptp}"
INSTALL_DIR="/opt/time-reference-monitor"
DATA_DIR="/var/lib/time-reference-monitor"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

info()  { echo -e "\e[32m[update]\e[0m  $*"; }
warn()  { echo -e "\e[33m[update]\e[0m  $*"; }
error() { echo -e "\e[31m[update]\e[0m  $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || error "Please run as root: sudo bash $0"

# ── 1. git pull ───────────────────────────────────────────────────────────────
info "Pulling latest code…"
sudo -u "$APP_USER" git -C "$REPO_DIR" pull --ff-only \
    || { warn "git pull failed or repo is not owned by ${APP_USER} – trying as current user."; git -C "$REPO_DIR" pull --ff-only; }

# ── 2. rsync application files ────────────────────────────────────────────────
info "Syncing files to ${INSTALL_DIR}…"
rsync -a --delete \
    --exclude='venv/' \
    --exclude='rpi/' \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.sqlite' \
    --exclude='*.sqlite-shm' \
    --exclude='*.sqlite-wal' \
    "${REPO_DIR}/" "${INSTALL_DIR}/"
chown -R "${APP_USER}:${APP_USER}" "$INSTALL_DIR"

# Also update the kiosk script
mkdir -p "${INSTALL_DIR}/rpi/scripts"
install -m 0755 "${REPO_DIR}/rpi/scripts/kiosk.sh" "${INSTALL_DIR}/rpi/scripts/kiosk.sh"

# ── 3. Python dependencies ────────────────────────────────────────────────────
info "Updating Python dependencies…"
sudo -u "$APP_USER" "${INSTALL_DIR}/venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "${INSTALL_DIR}/venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

# ── 4. Recompile alsaltc if source changed ────────────────────────────────────
ALSALTC_SRC="${REPO_DIR}/alsaltc-v02/alsaltc.c"
ALSALTC_BIN="/usr/local/bin/alsaltc"
if [ "$ALSALTC_SRC" -nt "$ALSALTC_BIN" ] 2>/dev/null || [ ! -f "$ALSALTC_BIN" ]; then
    info "alsaltc source is newer than installed binary – recompiling…"
    make -C "${REPO_DIR}/alsaltc-v02" clean
    make -C "${REPO_DIR}/alsaltc-v02"
    install -m 0755 "${REPO_DIR}/alsaltc-v02/alsaltc" "$ALSALTC_BIN"
    info "alsaltc reinstalled to ${ALSALTC_BIN}"
else
    info "alsaltc is up to date – skipping recompile."
fi

# ── 5. systemd service files ──────────────────────────────────────────────────
info "Updating systemd service files…"
KIOSK_SERVICE_CHANGED=false
TRM_SERVICE_CHANGED=false

NEW_TRM=$(sed "s/User=pi/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
    "${REPO_DIR}/rpi/systemd/time-reference-monitor.service")
if ! diff -q <(echo "$NEW_TRM") /etc/systemd/system/time-reference-monitor.service &>/dev/null 2>&1; then
    echo "$NEW_TRM" > /etc/systemd/system/time-reference-monitor.service
    TRM_SERVICE_CHANGED=true
    info "time-reference-monitor.service updated."
fi

NEW_KIOSK=$(sed "s/User=pi/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
    "${REPO_DIR}/rpi/systemd/chromium-kiosk.service")
if ! diff -q <(echo "$NEW_KIOSK") /etc/systemd/system/chromium-kiosk.service &>/dev/null 2>&1; then
    echo "$NEW_KIOSK" > /etc/systemd/system/chromium-kiosk.service
    KIOSK_SERVICE_CHANGED=true
    info "chromium-kiosk.service updated."
fi

systemctl daemon-reload

# ── 6. ALSA config ────────────────────────────────────────────────────────────
info "Checking ALSA config…"
if ! diff -q "${REPO_DIR}/rpi/alsa/asound.conf" /etc/asound.conf &>/dev/null 2>&1; then
    cp /etc/asound.conf /etc/asound.conf.bak
    cp "${REPO_DIR}/rpi/alsa/asound.conf" /etc/asound.conf
    info "ALSA config updated (old saved to /etc/asound.conf.bak)."
else
    info "ALSA config unchanged."
fi

# Remove user-level ~/.asoundrc – conflicts with /etc/asound.conf when both
# define ltc_left_mono (duplicate dsnoop instances → "Slave PCM not usable").
ASOUNDRC="/home/${APP_USER}/.asoundrc"
if [ -f "$ASOUNDRC" ]; then
    mv "$ASOUNDRC" "${ASOUNDRC}.disabled"
    warn "~/.asoundrc deaktiviert (→ .asoundrc.disabled) – /etc/asound.conf gilt."
fi

# ── ptp4l service drop-ins ────────────────────────────────────────────────────
mkdir -p /etc/systemd/system/ptp4l.service.d
PTP4L_RESTART=false

for dropin in uds-permissions.conf time-reference-monitor.conf; do
    src="${REPO_DIR}/rpi/systemd/ptp4l.service.d/${dropin}"
    dst="/etc/systemd/system/ptp4l.service.d/${dropin}"
    if ! diff -q "$src" "$dst" &>/dev/null 2>&1; then
        cp "$src" "$dst"
        PTP4L_RESTART=true
        info "ptp4l drop-in aktualisiert: ${dropin}"
    fi
done

# ── ptp4l.conf (free_running monitor-only config) ───────────────────────────
mkdir -p /etc/linuxptp
if ! diff -q "${REPO_DIR}/rpi/ptp4l/ptp4l.conf" /etc/linuxptp/ptp4l.conf &>/dev/null 2>&1; then
    [ -f /etc/linuxptp/ptp4l.conf ] && cp /etc/linuxptp/ptp4l.conf /etc/linuxptp/ptp4l.conf.bak
    cp "${REPO_DIR}/rpi/ptp4l/ptp4l.conf" /etc/linuxptp/ptp4l.conf
    PTP4L_RESTART=true
    info "ptp4l.conf aktualisiert (free_running=1, slaveOnly=1)."
fi

if [ "$PTP4L_RESTART" = true ]; then
    systemctl daemon-reload
    if systemctl is-active --quiet ptp4l.service 2>/dev/null; then
        systemctl restart ptp4l.service
        info "ptp4l neu gestartet."
    fi
fi

# ── chrony.conf (NTP-only) ────────────────────────────────────────────────────
CHRONY_CONF=""
[ -d /etc/chrony ] && CHRONY_CONF="/etc/chrony/chrony.conf" || CHRONY_CONF="/etc/chrony.conf"
if ! diff -q "${REPO_DIR}/rpi/chrony/chrony.conf" "$CHRONY_CONF" &>/dev/null 2>&1; then
    [ -f "$CHRONY_CONF" ] && cp "$CHRONY_CONF" "${CHRONY_CONF}.bak"
    cp "${REPO_DIR}/rpi/chrony/chrony.conf" "$CHRONY_CONF"
    info "chrony.conf aktualisiert (NTP-only)."
else
    info "chrony.conf unverändert."
fi

# Re-apply any NTP server that was set via the Settings UI.
# set_ntp_server() in network_mgr.py writes the chosen server here.
# This survives update.sh runs AND NetworkManager DHCP-triggered conf rewrites.
NTP_PERSIST="/var/lib/time-reference-monitor/ntp_server"
if [ -f "$NTP_PERSIST" ]; then
    CUSTOM_NTP=$(cat "$NTP_PERSIST" | tr -d '[:space:]')
    if [ -n "$CUSTOM_NTP" ]; then
        # Replace only the first server/pool line; keep the rest of the file intact.
        sed -i "0,/^\(server\|pool\) /s|^\(server\|pool\) \S\+|server ${CUSTOM_NTP}|" "$CHRONY_CONF"
        info "NTP-Server wiederhergestellt aus Persistenz-Datei: ${CUSTOM_NTP}"
        systemctl restart chrony 2>/dev/null || true
    fi
else
    systemctl restart chrony 2>/dev/null || true
fi

# ── Xwrapper.config ──────────────────────────────────────────────────────────
# Rootless Xorg on Bookworm cannot open arbitrary VTs without this.
# Idempotent: only writes if content differs.
XWRAP_WANT=$'allowed_users=anybody\nneeds_root_rights=yes'
if [ "$(cat /etc/X11/Xwrapper.config 2>/dev/null)" != "$XWRAP_WANT" ]; then
    mkdir -p /etc/X11
    printf '%s\n' "allowed_users=anybody" "needs_root_rights=yes" > /etc/X11/Xwrapper.config
    info "Xwrapper.config aktualisiert (VT-Zugriff für Xorg)."
fi

# ── 7. Kiosk conf file (install only if missing) ──────────────────────────────
KIOSK_CONF="/etc/time-reference-monitor.conf"
if [ ! -f "$KIOSK_CONF" ]; then
    cp "${REPO_DIR}/rpi/time-reference-monitor.conf" "$KIOSK_CONF"
    info "Kiosk-Konfiguration erstellt: ${KIOSK_CONF}"
else
    info "Kiosk-Konfiguration vorhanden: ${KIOSK_CONF} (nicht überschrieben)."
fi

# ── 8. HDMI config.txt (sync with HDMI_MODE from kiosk conf) ─────────────────
CFG_TXT=""
for f in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "$f" ] && CFG_TXT="$f" && break
done
if [ -n "$CFG_TXT" ]; then
    HDMI_MODE="sdi-1080i50"
    [ -f "$KIOSK_CONF" ] && HDMI_MODE=$(grep '^HDMI_MODE=' "$KIOSK_CONF" \
        | cut -d= -f2 | tr -d '[:space:]' || echo "sdi-1080i50")
    case "$HDMI_MODE" in
      sdi-1080p50) CEA_MODE=31 ;;
      auto)
        info "HDMI_MODE=auto – config.txt nicht angepasst (kein SDI-Modus)."
        CEA_MODE="" ;;
      *) CEA_MODE=20 ;;
    esac
    if [ -n "$CEA_MODE" ]; then
        grep -q "hdmi_force_hotplug=1" "$CFG_TXT" || echo "hdmi_force_hotplug=1" >> "$CFG_TXT"
        grep -q "hdmi_group=1"         "$CFG_TXT" || echo "hdmi_group=1"         >> "$CFG_TXT"
        if grep -q "^hdmi_mode=" "$CFG_TXT"; then
            CURRENT_MODE=$(grep '^hdmi_mode=' "$CFG_TXT" | cut -d= -f2)
            if [ "$CURRENT_MODE" != "$CEA_MODE" ]; then
                sed -i "s/^hdmi_mode=.*/hdmi_mode=${CEA_MODE}/" "$CFG_TXT"
                info "config.txt: hdmi_mode aktualisiert auf ${CEA_MODE} (${HDMI_MODE})."
                warn "Reboot erforderlich für neue HDMI-Auflösung."
            else
                info "config.txt: hdmi_mode=${CEA_MODE} bereits korrekt."
            fi
        else
            echo "hdmi_mode=${CEA_MODE}" >> "$CFG_TXT"
            info "config.txt: hdmi_mode=${CEA_MODE} eingetragen."
        fi
    fi
fi

# ── 9. sudoers (idempotent) ───────────────────────────────────────────────────
cat > /etc/sudoers.d/time-reference-monitor <<SUDOEOF
# Time Reference Monitor – generated by update.sh
${APP_USER} ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/poweroff
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/nmcli
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart chrony
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/chrony/chrony.conf
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/chrony.conf
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tcpdump
${APP_USER} ALL=(ALL) NOPASSWD: /usr/sbin/tcpdump
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/killall
SUDOEOF
chmod 440 /etc/sudoers.d/time-reference-monitor

# ── 10. Restart services ───────────────────────────────────────────────────────
info "Restarting time-reference-monitor…"
systemctl restart time-reference-monitor.service

if [ "$KIOSK_SERVICE_CHANGED" = true ]; then
    info "Chromium-kiosk.service wurde geändert – Kiosk wird neu gestartet…"
    systemctl restart chromium-kiosk.service
else
    info "Kiosk-Service unverändert (kein Neustart nötig)."
fi

echo
info "=== Update complete ==="
info "Monitor service restarted. Check logs:"
info "  journalctl -fu time-reference-monitor"
info "  journalctl -fu chromium-kiosk"
