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
sed "s/User=pi/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
    "${REPO_DIR}/rpi/systemd/time-reference-monitor.service" \
    > /etc/systemd/system/time-reference-monitor.service

sed "s/User=pi/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
    "${REPO_DIR}/rpi/systemd/chromium-kiosk.service" \
    > /etc/systemd/system/chromium-kiosk.service

systemctl daemon-reload

# ── 6. sudoers (idempotent) ───────────────────────────────────────────────────
echo "${APP_USER} ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/poweroff" \
    > /etc/sudoers.d/time-reference-monitor
chmod 440 /etc/sudoers.d/time-reference-monitor

# ── 7. Restart monitor service ────────────────────────────────────────────────
info "Restarting time-reference-monitor…"
systemctl restart time-reference-monitor.service

echo
info "=== Update complete ==="
info "Monitor service restarted. Chromium will reload automatically."
info "Check logs: journalctl -fu time-reference-monitor"
