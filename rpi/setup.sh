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
APP_USER="${APP_USER:-ptp}"
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

# ── 0. Create application user ────────────────────────────────────────────────
create_user() {
    if id "$APP_USER" &>/dev/null; then
        info "User ${APP_USER} already exists – skipping."
    else
        info "Creating user ${APP_USER}…"
        # Regular user (not --system) so that X11 / xinit works.
        # No password is set; login is only via sudo or the kiosk session.
        useradd --create-home --shell /bin/bash --groups audio,video "$APP_USER"
        passwd -l "$APP_USER"   # lock password (no direct login)
        info "User ${APP_USER} created (password locked)."
    fi
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
        chromium \
        openssh-server

    info "Enabling SSH server…"
    systemctl enable ssh
    systemctl start ssh
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

    # Disable lightdm (RPi OS Desktop) if present – it would take over the
    # display and fight with our xinit-based kiosk on the same VT.
    if systemctl list-unit-files lightdm.service &>/dev/null 2>&1; then
        info "Deaktiviere lightdm (Display-Manager)…"
        systemctl disable lightdm 2>/dev/null || true
        systemctl stop    lightdm 2>/dev/null || true
    fi

    systemctl daemon-reload
    systemctl enable time-reference-monitor.service
    systemctl enable chromium-kiosk.service
    info "Services enabled. They will start on next boot."
    info "To start now (without rebooting):"
    info "  sudo systemctl start time-reference-monitor"
    info "  sudo systemctl start chromium-kiosk"
}

# ── 6. sudoers: allow ptp user to reboot/poweroff ────────────────────────────
configure_sudoers() {
    local rule_file="/etc/sudoers.d/time-reference-monitor"
    info "Installing sudoers rule for ${APP_USER} (reboot/poweroff)…"
    echo "${APP_USER} ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/poweroff" > "$rule_file"
    chmod 440 "$rule_file"
    info "Sudoers rule installed: ${rule_file}"
}

# ── 7. HDMI-Ausgabe: 1080p50 für HDMI→SDI-Konverter ─────────────────────────
# hdmi_force_hotplug=1  – HDMI aktiv halten, auch wenn der SDI-Konverter
#                         kein EDID zurückschickt (bei vielen Konvertern so)
# hdmi_group=1          – CEA (Broadcast-Standard), nicht DMT (PC-Monitor)
# hdmi_mode=31          – 1080p50 (SMPTE 274M)
configure_hdmi_sdi() {
    local cfg=""
    for f in /boot/firmware/config.txt /boot/config.txt; do
        [ -f "$f" ] && cfg="$f" && break
    done
    if [ -z "$cfg" ]; then
        warn "config.txt nicht gefunden – HDMI-SDI-Konfiguration übersprungen."
        return
    fi
    info "Konfiguriere HDMI-Ausgabe für 1080p50 / SDI in ${cfg}…"
    # Idempotent: nur hinzufügen wenn noch nicht vorhanden
    grep -q "hdmi_force_hotplug=1" "$cfg" || echo "hdmi_force_hotplug=1" >> "$cfg"
    grep -q "hdmi_group=1"         "$cfg" || echo "hdmi_group=1"         >> "$cfg"
    grep -q "hdmi_mode=31"         "$cfg" || echo "hdmi_mode=31"         >> "$cfg"
    info "HDMI 1080p50 konfiguriert (wirksam nach Reboot)."
}

# ── 8. Console autologin for kiosk ────────────────────────────────────────────
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

create_user
install_packages
build_alsaltc
install_app
install_alsa
install_services
configure_sudoers
configure_hdmi_sdi
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
