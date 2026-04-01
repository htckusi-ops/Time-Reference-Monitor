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
        useradd --create-home --shell /bin/bash --groups audio,video,input "$APP_USER"
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
    info "  Default device: hw:US2x2HR,0 (Tascam US-2x2HR, stable card name)"
    warn "Action required: if your LTC interface differs, edit /etc/asound.conf"
    warn "  Run: arecord -l   to find the short name, then set pcm \"hw:<Name>,0\""

    # Add APP_USER to the audio group
    usermod -aG audio "$APP_USER"
    info "User ${APP_USER} added to the 'audio' group."

    # Remove user-level .asoundrc – it conflicts with /etc/asound.conf when
    # both define ltc_left_mono (two dsnoop instances fight for the same hw).
    local asoundrc="/home/${APP_USER}/.asoundrc"
    if [ -f "$asoundrc" ]; then
        mv "$asoundrc" "${asoundrc}.disabled"
        warn "~/.asoundrc gefunden und deaktiviert (→ .asoundrc.disabled)."
        warn "  /etc/asound.conf ist die einzige gültige ALSA-Konfiguration."
    fi
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

    # ptp4l UDS socket permissions drop-in:
    # pmc must connect to ptp4l's Unix Domain Socket as the ptp user.
    # Default socket mode is 0600 (root only).  This drop-in sets it to 0666
    # after ptp4l starts so non-root pmc calls succeed.
    mkdir -p /etc/systemd/system/ptp4l.service.d
    cp "${REPO_DIR}/rpi/systemd/ptp4l.service.d/uds-permissions.conf" \
        /etc/systemd/system/ptp4l.service.d/uds-permissions.conf
    info "ptp4l UDS-Berechtigungs-Drop-in installiert."

    # Xwrapper.config: allow non-root user to start X on a specific VT.
    # Without this, rootless Xorg on Bookworm fails with:
    #   (EE) xf86OpenConsole: Cannot open virtual console 7 (Permission denied)
    # needs_root_rights=yes grants the Xorg wrapper root access for VT/DRI devices.
    mkdir -p /etc/X11
    cat > /etc/X11/Xwrapper.config <<'XWRAP'
allowed_users=anybody
needs_root_rights=yes
XWRAP
    info "Xwrapper.config: allowed_users=anybody, needs_root_rights=yes"

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

# ── 6. sudoers: allow ptp user to reboot/poweroff + network/NTP management ───
configure_sudoers() {
    local rule_file="/etc/sudoers.d/time-reference-monitor"
    info "Installing sudoers rules for ${APP_USER}…"
    cat > "$rule_file" <<SUDOEOF
# Time Reference Monitor – generated by setup.sh
${APP_USER} ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/poweroff
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/nmcli
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart chrony
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/chrony/chrony.conf
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/chrony.conf
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tcpdump
${APP_USER} ALL=(ALL) NOPASSWD: /usr/sbin/tcpdump
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/killall
SUDOEOF
    chmod 440 "$rule_file"
    info "Sudoers rule installed: ${rule_file}"
}

# ── 7. Kiosk-Konfigurationsdatei ─────────────────────────────────────────────
install_kiosk_conf() {
    local dest="/etc/time-reference-monitor.conf"
    if [ -f "$dest" ]; then
        info "Kiosk-Konfiguration ${dest} bereits vorhanden – nicht überschrieben."
        info "  Aktuell gesetzter HDMI_MODE: $(grep '^HDMI_MODE' "$dest" || echo '(nicht gesetzt)')"
    else
        cp "${REPO_DIR}/rpi/time-reference-monitor.conf" "$dest"
        info "Kiosk-Konfiguration installiert: ${dest}"
        info "  Standard: HDMI_MODE=sdi-1080i50"
        info "  Ändern mit: sudo nano ${dest}  dann: sudo systemctl restart chromium-kiosk"
    fi
}

# ── 8. HDMI-Ausgabe für HDMI→SDI-Konverter ───────────────────────────────────
# Liest HDMI_MODE aus /etc/time-reference-monitor.conf und setzt config.txt.
#
# hdmi_force_hotplug=1  – HDMI halten, auch ohne EDID (SDI-Konverter)
# hdmi_group=1          – CEA (Broadcast), nicht DMT (PC-Monitor)
# hdmi_mode=20          – 1080i50 (CEA-20, Standard-Broadcast, Standard)
# hdmi_mode=31          – 1080p50 (CEA-31, Progressive, alternativ)
configure_hdmi_sdi() {
    local cfg=""
    for f in /boot/firmware/config.txt /boot/config.txt; do
        [ -f "$f" ] && cfg="$f" && break
    done
    if [ -z "$cfg" ]; then
        warn "config.txt nicht gefunden – HDMI-SDI-Konfiguration übersprungen."
        return
    fi

    # HDMI_MODE aus Kiosk-Konfiguration lesen (Standard: sdi-1080i50)
    local kiosk_conf="/etc/time-reference-monitor.conf"
    local hdmi_mode="sdi-1080i50"
    [ -f "$kiosk_conf" ] && hdmi_mode=$(grep '^HDMI_MODE=' "$kiosk_conf" | cut -d= -f2 | tr -d '[:space:]' || echo "sdi-1080i50")

    local cea_mode
    case "$hdmi_mode" in
      sdi-1080p50) cea_mode=31 ;;
      sdi-1080i50|*) cea_mode=20 ;;
    esac

    info "Konfiguriere HDMI-Ausgabe in ${cfg} (HDMI_MODE=${hdmi_mode}, hdmi_mode=${cea_mode})…"

    # hdmi_force_hotplug und hdmi_group: nur hinzufügen wenn nicht vorhanden
    grep -q "hdmi_force_hotplug=1" "$cfg" || echo "hdmi_force_hotplug=1" >> "$cfg"
    grep -q "hdmi_group=1"         "$cfg" || echo "hdmi_group=1"         >> "$cfg"

    # hdmi_mode: setzen oder aktualisieren
    if grep -q "^hdmi_mode=" "$cfg"; then
        sed -i "s/^hdmi_mode=.*/hdmi_mode=${cea_mode}/" "$cfg"
    else
        echo "hdmi_mode=${cea_mode}" >> "$cfg"
    fi

    info "HDMI konfiguriert: CEA hdmi_mode=${cea_mode} (wirksam nach Reboot)."
    warn "Für PC-Monitor: HDMI_MODE=auto in ${kiosk_conf} setzen und update.sh ausführen."
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
install_kiosk_conf
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
