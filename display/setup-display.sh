#!/bin/bash
# setup-display.sh – Einrichtung der MAX7219 LED-Matrix Zeitanzeige
#
# Voraussetzung: setup.sh wurde bereits ausgeführt (venv vorhanden).
# Ausführen als root: sudo bash display/setup-display.sh

set -euo pipefail

APP_USER="${APP_USER:-ptp}"
INSTALL_DIR="/opt/time-reference-monitor"

info()  { echo -e "\e[32m[display-setup]\e[0m  $*"; }
warn()  { echo -e "\e[33m[display-setup]\e[0m  $*"; }
error() { echo -e "\e[31m[display-setup]\e[0m  $*" >&2; exit 1; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

[ "$(id -u)" -eq 0 ] || error "Bitte als root ausführen: sudo bash $0"

# ── 1. SPI aktivieren ─────────────────────────────────────────────────────────
info "Aktiviere SPI-Interface…"
# /boot/config.txt (RPi OS Bookworm: /boot/firmware/config.txt)
for cfg in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "$cfg" ]; then
        if grep -q "^dtparam=spi=on" "$cfg"; then
            info "SPI bereits aktiv in ${cfg}."
        else
            echo "dtparam=spi=on" >> "$cfg"
            info "SPI aktiviert in ${cfg} – wird nach Reboot wirksam."
        fi
        break
    fi
done

# Sofort laden falls Modul vorhanden (kein Reboot nötig beim ersten Lauf)
modprobe spi_bcm2835 2>/dev/null && info "spi_bcm2835 Modul geladen." \
    || warn "spi_bcm2835 konnte nicht sofort geladen werden – Reboot nötig."

# ── 2. User-Gruppen ───────────────────────────────────────────────────────────
info "Füge ${APP_USER} zu Gruppen spi und gpio hinzu…"
usermod -aG spi,gpio "$APP_USER" 2>/dev/null \
    || warn "Gruppen spi/gpio nicht gefunden (normal auf Nicht-RPi-Systemen)."

# ── 3. Python-Library installieren ───────────────────────────────────────────
info "Installiere luma.led_matrix ins venv…"
[ -f "${INSTALL_DIR}/venv/bin/pip" ] \
    || error "venv nicht gefunden in ${INSTALL_DIR} – bitte zuerst setup.sh ausführen."
sudo -u "$APP_USER" "${INSTALL_DIR}/venv/bin/pip" install -q "luma.led_matrix>=1.3"
info "luma.led_matrix installiert."

# ── 4. Display-Script ins Install-Verzeichnis kopieren ───────────────────────
info "Kopiere display_driver.py nach ${INSTALL_DIR}/display/…"
mkdir -p "${INSTALL_DIR}/display"
install -m 0755 "${REPO_DIR}/display/display_driver.py" \
    "${INSTALL_DIR}/display/display_driver.py"
chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}/display"

# ── 5. systemd-Service installieren ──────────────────────────────────────────
info "Installiere time-display.service…"
sed "s/User=ptp/User=${APP_USER}/g; s|/opt/time-reference-monitor|${INSTALL_DIR}|g" \
    "${REPO_DIR}/display/systemd/time-display.service" \
    > /etc/systemd/system/time-display.service

systemctl daemon-reload
systemctl enable time-display.service
info "time-display.service aktiviert."

echo
info "=== Display-Setup abgeschlossen ==="
info ""
info "Konfiguration (Module, Quelle, Helligkeit):"
info "  sudo nano /etc/systemd/system/time-display.service"
info "  sudo systemctl daemon-reload && sudo systemctl restart time-display"
info ""
info "Starten (nach Reboot automatisch, oder sofort):"
info "  sudo systemctl start time-display"
info ""
info "Logs:"
info "  journalctl -fu time-display"
warn ""
warn "Falls SPI neu aktiviert wurde: sudo reboot erforderlich."
