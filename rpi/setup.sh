#!/bin/bash
# setup.sh – First-time installation of Time-Reference-Monitor on Raspberry Pi OS
#
# Tested on: Raspberry Pi OS Lite (Debian Bookworm / 64-bit)
# Run as root: sudo bash rpi/setup.sh
#
# What this script does:
#   1. Installs system packages
#   2. Compiles alsaltc (ALSA + libltc LTC decoder)
#   3. Creates /opt/time-reference-monitor with Python venv
#   4. Installs ALSA config (dsnoop_ltc, ltc_left_mono)
#   5. Installs and enables systemd services
#   6. Creates /var/lib/time-reference-monitor (database dir)
#
# After running:
#   - Edit /etc/asound.conf if your LTC card index differs from hw:1,0
#   - Edit /etc/systemd/system/time-reference-monitor.service if you need
#     different --iface, --domain, or --ltc-fps values
#   - Reboot

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
APP_USER="${APP_USER:-pi}"
INSTALL_DIR="/opt/time-reference-monitor"
DATA_DIR="/var/lib/time-reference-monitor"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()  { echo -e "\e[32m[setup]\e[0m  $*"; }
warn()  { echo -e "\e[33m[setup]\e[0m  $*"; }
error() { echo -e "\e[31m[setup]\e[0m  $*" >&2; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || error "Please run as root: sudo bash $0"
}

# ── 1. System packages ────────────────────────────────────────────────────────
install_packages() {
    info "Updating package list…"
    apt-get update -qq

    info "Installing system dependencies…"
    apt-get install -y \
        python3 python3-venv python3-pip \
        linuxptp chrony \
        alsa-utils libasound2-dev libltc-dev \
        gcc make pkg-config \
        xorg openbox unclutter curl \
        chromium
}

# ── 2. Compile alsaltc ────────────────────────────────────────────────────────
build_alsaltc() {
    info "Compiling alsaltc from source…"
    local src="${REPO_DIR}/alsaltc-v02"
    [ -d "$src" ] || error "alsaltc-v02 source directory not found at $src"

    make -C "$src" clean
    make -C "$src"
    install -m 0755 "${src}/alsaltc" /usr/local/bin/alsaltc
    info "alsaltc installed to /usr/local/bin/alsaltc"
}

# ── 3. Install application ────────────────────────────────────────────────────
install_app() {
    info "Creating install directory ${INSTALL_DIR}…"
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='rpi/' --exclude='.git/' --exclude='__pycache__/' \
        "${REPO_DIR}/" "${INSTALL_DIR}/"
    chown -R "${APP_USER}:${APP_USER}" "$INSTALL_DIR"

    info "Creating Python virtual environment…"
    sudo -u "$APP_USER" python3 -m venv "${INSTALL_DIR}/venv"
    sudo -u "$APP_USER" "${INSTALL_DIR}/venv/bin/pip" install -q --upgrade pip
    sudo -u "$APP_USER" "${INSTALL_DIR}/venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

    info "Creating data directory ${DATA_DIR}…"
    mkdir -p "$DATA_DIR"
    chown "${APP_USER}:${APP_USER}" "$DATA_DIR"

    # Copy kiosk script and ensure it is executable
    install -m 0755 "${REPO_DIR}/rpi/scripts/kiosk.sh" "${INSTALL_DIR}/rpi/scripts/kiosk.sh" 2>/dev/null || {
        mkdir -p "${INSTALL_DIR}/rpi/scripts"
        install -m 0755 "${REPO_DIR}/rpi/scripts/kiosk.sh" "${INSTALL_DIR}/rpi/scripts/kiosk.sh"
    }
}

# ── 4. ALSA configuration ─────────────────────────────────────────────────────
install_alsa() {
    if [ -f /etc/asound.conf ]; then
        warn "/etc/asound.conf already exists – backing up to /etc/asound.conf.bak"
        cp /etc/asound.conf /etc/asound.conf.bak
    fi
    cp "${REPO_DIR}/rpi/alsa/asound.conf" /etc/asound.conf
    info "ALSA config installed to /etc/asound.conf"
    warn "Action required: verify the LTC card index in /etc/asound.conf"
    warn "  Run: arecord -l   and adjust hw:X,0 to match your LTC interface."

    # Add APP_USER to the audio group
    usermod -aG audio "$APP_USER"
    info "User ${APP_USER} added to the 'audio' group."
}

# ── 5. systemd services ───────────────────────────────────────────────────────
install_services() {
    info "Installing systemd services…"

    # Substitute the real APP_USER into the service files before installing
    sed "s/User=pi/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
        "${REPO_DIR}/rpi/systemd/time-reference-monitor.service" \
        > /etc/systemd/system/time-reference-monitor.service

    sed "s/User=pi/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
        "${REPO_DIR}/rpi/systemd/chromium-kiosk.service" \
        > /etc/systemd/system/chromium-kiosk.service

    systemctl daemon-reload
    systemctl enable time-reference-monitor.service
    systemctl enable chromium-kiosk.service
    info "Services enabled. They will start on next boot."
    info "To start now (without rebooting):"
    info "  sudo systemctl start time-reference-monitor"
    info "  sudo systemctl start chromium-kiosk"
}

# ── 6. Console autologin for kiosk ────────────────────────────────────────────
# The chromium-kiosk service runs X on VT7 via xinit.
# No desktop autologin is required – systemd starts X directly.
# However, if you want a fallback text login on VT1, ensure it is configured:
configure_autologin() {
    info "Configuring console autologin for ${APP_USER} on tty1 (optional, for fallback)…"
    mkdir -p /etc/systemd/system/getty@tty1.service.d
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${APP_USER} --noclear %I \$TERM
EOF
    systemctl daemon-reload
}

# ── Main ──────────────────────────────────────────────────────────────────────
require_root

info "=== Time-Reference-Monitor RPi Setup ==="
info "Repository  : ${REPO_DIR}"
info "Install dir : ${INSTALL_DIR}"
info "Data dir    : ${DATA_DIR}"
info "User        : ${APP_USER}"
echo

install_packages
build_alsaltc
install_app
install_alsa
install_services
configure_autologin

echo
info "=== Setup complete ==="
info "Next steps:"
info "  1. Check /etc/asound.conf – set the correct hw:X,0 for your LTC card"
info "  2. Review /etc/systemd/system/time-reference-monitor.service"
info "     – set --iface (default: eth0) and --domain to match your PTP setup"
info "     – adjust --ltc-fps if needed (default: 25)"
info "  3. Reboot: sudo reboot"
info ""
info "Log monitoring:"
info "  journalctl -fu time-reference-monitor"
info "  journalctl -fu chromium-kiosk"
