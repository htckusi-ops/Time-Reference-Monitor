# Time Reference Monitor – Studio Bundeshaus

Monitoring-Tool für Zeitreferenzen in professionellen Broadcast-Umgebungen.
Überwacht **PTP (IEEE 1588)**, **NTP (chrony)** und optional **LTC (Linear Timecode)** — ohne die Systemzeit zu disziplinieren.

---

## Übersicht

| Signal | Quelle | Anzeige |
|--------|--------|---------|
| PTP | `pmc` (linuxptp) | Offset, Delay, Port-State, GM-Identity, Zeitanzeige (nur wenn gültig) |
| NTP | `chronyc tracking` | Synchronisationsstatus, Stratum, Referenz-ID |
| LTC | `alsaltc` (ALSA + libltc) | Timecode HH:MM:SS:FF, Präsenz, Decode-Fehler, Sprünge, Delta zu PTP |

Alle Werte werden nur **angezeigt und bewertet** — keine Zeitdisziplinierung, kein Eingriff in laufende Dienste.

---

## Voraussetzungen

### Hardware-Kompatibilität (Raspberry Pi + PTP)

PTP-Genauigkeit hängt direkt davon ab, ob das Netzwerk-Interface **Hardware-Timestamping** unterstützt. Folgende RPi-Modelle unterscheiden sich grundlegend:

| Modell | PTP Hardware-Timestamping | Empfehlung |
|--------|--------------------------|------------|
| **RPi 4 Model B** | Nein (BCM54213PE, kein IEEE 1588) | Funktioniert nur mit Software-Timestamps (`-S`), ~10–100 µs Genauigkeit |
| **RPi 5** | Ja (MAC-Level via RP1-Chip) — aber **wiederholte Kernel-Regressionen** | Nicht empfohlen für unbeaufsichtigten Produktionsbetrieb |
| **RPi CM4** | Ja (PHY-Level, BCM54210PE) | Stabil, ~5–15 ns auf direktem Link, ~5–6 µs über Switches |
| **RPi CM5** | Ja (PHY + MAC) | Beste Option; vollständige Unterstützung ab Kernel 6.12 |

**RPi 4 Model B:** ptp4l muss im Software-Timestamp-Modus betrieben werden:
```bash
sudo ptp4l -i eth0 -S -m -q   # -S = software timestamping
```
Im systemd-Service `time-reference-monitor.service` entsprechend `--source real` mit `-S`-Flag in der ptp4l-Konfiguration verwenden. Für ein reines Monitoring-Tool (kein Grandmaster) ist die resultierende Genauigkeit von ~10–50 µs oft ausreichend.

**RPi 5:** Hardware-Timestamping ist im Kernel vorhanden (MAC-Level via RP1-Chip), aber seit 2024 gibt es wiederholte Regressionen. **Raspberry Pi OS Bookworm (Stand Anfang 2026) ist betroffen** — Kernel 6.12.25–6.12.35 funktioniert nicht. Kernel 6.12.10 und 6.15 sind stabil. Workaround bis ein Fix landet: `sudo rpi-update` für einen neueren Pre-Release-Kernel, oder Software-Timestamps mit `-S`.

Zusätzlich benötigt Hardware-Timestamping auf dem RPi 5 folgenden Eintrag in `/etc/linuxptp/ptp4l.conf`, sonst werden Timestamps stillschweigend verworfen:
```ini
hwts_filter    full
```

**Prüfen ob Hardware-Timestamping verfügbar ist:**
```bash
ethtool -T eth0
# Hardware-Timestamping: "PTP Hardware Clock: 0" muss erscheinen
# Software-only: "PTP Hardware Clock: none"
```

### System
- Raspberry Pi OS Bookworm (64-bit) empfohlen, oder Debian/Ubuntu
- Python 3.10+

### Laufzeitabhängigkeiten
```
apt install linuxptp chrony alsa-utils
```

### Python-Pakete
```
pip install -r requirements.txt   # Flask>=2.2
```

### Für LTC-Dekodierung (alsaltc)
```
apt install libasound2-dev libltc-dev gcc make pkg-config
cd alsaltc-v02 && make && sudo make install
```

Der vorkompilierte `alsaltc`-Binary im Repository-Root ist für **x86_64**. Auf dem Raspberry Pi immer aus den Quellen kompilieren.

---

## Schnellstart (Entwicklung / Test)

```bash
# Mock-Modus: simuliert PTP, kein Hardware-Zugriff nötig
python3 run.py \
  --source mock \
  --http --http-host 0.0.0.0 --http-port 8088 \
  --poll 0.25 \
  --mock-jitter-ns 80000 --mock-dropout-every-s 30
```

Dann im Browser: `http://localhost:8088/`

### Mit realer Hardware

```bash
# PTP4L als Slave starten (separates Terminal)
sudo ptp4l -i eth0 -m -q

# Monitor starten
python3 run.py \
  --source real \
  --iface eth0 \
  --domain 0 \
  --http --http-host 0.0.0.0 --http-port 8088 \
  --poll 0.25
```

### Mit LTC (dsnoop für parallelen Zugriff)

```bash
# ALSA-Config installieren (einmalig)
sudo cp rpi/alsa/asound.conf /etc/asound.conf
# → Standard: hw:US2x2HR,0 (Tascam US-2x2HR)
# → Anderes Interface: arecord -l → Kurzname → /etc/asound.conf anpassen

python3 run.py \
  --source real --iface eth0 \
  --http --http-host 0.0.0.0 --http-port 8088 \
  --poll 0.25 \
  --ltc \
  --ltc-device dsnoop_ltc \
  --ltc-fps 25 \
  --ltc-cmd "alsaltc -d ltc_left_mono -r 48000 -c 1 -f 25 --dropout-ms 800" \
  --ltc-dropout-timeout-ms 800 \
  --ltc-jump-tolerance-frames 2
```

---

## Raspberry Pi Kiosk-Deployment

Für den stabilen Gerätebetrieb: Raspberry Pi OS nativ, systemd-Dienste, Chromium-Kiosk beim Booten.

### Betriebsuser `ptp`

Alle Dienste laufen unter dem dedizierten User **`ptp`**. Dieser User existiert auf einem frischen Raspberry Pi OS nicht — das Setup-Script legt ihn automatisch an:

- Home-Verzeichnis: `/home/ptp` (benötigt von X11/xinit)
- Gruppen: `audio`, `video`
- Passwort gesperrt (kein direkter Login)

Der Standardname `ptp` kann überschrieben werden:
```bash
sudo APP_USER=anderer-user bash rpi/setup.sh
```

### Installation

```bash
# Einmalig als root ausführen:
sudo bash rpi/setup.sh
```

Das Skript:
1. Legt den User `ptp` an (falls nicht vorhanden)
2. Installiert alle System-Pakete (`chromium`, `xorg`, `openbox`, `libltc-dev`, …)
3. Kompiliert `alsaltc` aus den Quellen für ARM
4. Legt `/opt/time-reference-monitor/` mit Python-venv an
5. Installiert `/etc/asound.conf` (dsnoop-Config)
6. Aktiviert systemd-Dienste

Nach dem Setup:

```bash
# LTC-Karte prüfen und ggf. anpassen:
arecord -l
sudo nano /etc/asound.conf          # Kartennamen anpassen (Standard: hw:US2x2HR,0)

# Monitor-Konfiguration anpassen (Interface, Domain, LTC-FPS …):
sudo nano /etc/systemd/system/time-reference-monitor.service
sudo systemctl daemon-reload

sudo reboot
```

### Konfiguration des Monitor-Dienstes

Die aktiven Start-Parameter stehen in:
```
/etc/systemd/system/time-reference-monitor.service
```

Das Template dazu liegt im Repository unter `rpi/systemd/time-reference-monitor.service` und wird von `setup.sh` / `update.sh` nach `/etc/systemd/system/` kopiert. **Anpassungen immer in `/etc/systemd/system/` vornehmen**, nicht im Repo-Template — sonst werden sie beim nächsten `update.sh` überschrieben.

Nach jeder Änderung:
```bash
sudo systemctl daemon-reload
sudo systemctl restart time-reference-monitor
```

**Aktuelle Defaults nach setup.sh:**

| Parameter | Default | Anmerkung |
|-----------|---------|-----------|
| `--source` | `real` | `mock` nur für Tests ohne PTP-Hardware |
| `--iface` | `eth0` | **anpassen** falls anderes Interface |
| `--domain` | `0` | PTP-Domain-Nummer |
| `--poll` | `0.25` s | PTP-Abfrageintervall |
| `--http-host` | `0.0.0.0` | von allen Interfaces erreichbar |
| `--http-port` | `8088` | |
| `--ltc` | aktiviert | LTC deaktivieren: Zeile entfernen |
| `--ltc-device` | `dsnoop_ltc` | ALSA-Gerät (aus asound.conf) |
| `--ltc-fps` | `25` | **anpassen** bei 29.97/30 fps LTC |
| `--ltc-cmd` | `alsaltc -d ltc_left_mono -r 48000 -c 1 -f 25 --dropout-ms 800 --format S16_LE` | |
| `--ltc-dropout-timeout-ms` | `800` | |
| `--ltc-jump-tolerance-frames` | `2` | |
| `--db` | `/var/lib/time-reference-monitor/events.sqlite` | |

### Dienste

| Dienst | Beschreibung |
|--------|-------------|
| `time-reference-monitor.service` | Python-Backend (PTP/NTP/LTC), Port 8088 |
| `chromium-kiosk.service` | X11 auf VT7 + Chromium im Kiosk-Modus |
| `ssh.service` | SSH-Server (wird durch setup.sh aktiviert) |

```bash
# Logs beobachten
journalctl -fu time-reference-monitor
journalctl -fu chromium-kiosk

# Dienste manuell starten (ohne Reboot)
sudo systemctl start time-reference-monitor
sudo systemctl start chromium-kiosk
```

### SSH-Zugang

`setup.sh` installiert und aktiviert `openssh-server` automatisch. Nach dem ersten Boot ist der Pi per SSH erreichbar:

```bash
ssh ptp@<ip-adresse>
```

Da der `ptp`-User kein Passwort hat, muss die Authentifizierung über SSH-Key erfolgen. SSH-Key vor dem ersten Reboot hinterlegen:

```bash
# Auf dem Pi (als root, nach setup.sh):
mkdir -p /home/ptp/.ssh
echo "ssh-ed25519 AAAA... dein-public-key" >> /home/ptp/.ssh/authorized_keys
chown -R ptp:ptp /home/ptp/.ssh
chmod 700 /home/ptp/.ssh
chmod 600 /home/ptp/.ssh/authorized_keys
```

### Konsolenzugang / Kiosk beenden

Der Chromium-Kiosk läuft auf **Virtual Terminal 7** (VT7). Folgende Wege führen zurück auf eine Textkonsole:

| Methode | Aktion |
|---------|--------|
| Tastatur am Gerät | `Ctrl+Alt+F1` → VT1 (autologin als `ptp`) |
| Tastatur am Gerät | `Ctrl+Alt+F2` → VT2 (Login-Prompt) |
| Zurück zum Kiosk | `Ctrl+Alt+F7` |
| SSH | `ssh ptp@<ip>` von einem anderen Rechner |
| Kiosk-Service stoppen | `sudo systemctl stop chromium-kiosk` (via SSH oder Konsole) |

`Ctrl+Alt+Fn` wird vom Linux-Kernel verarbeitet — Chromium kann diese Tastenkombination nicht blockieren, auch nicht im `--kiosk`-Modus.

**Browser-Absturz:** `chromium-kiosk.service` ist mit `Restart=always` konfiguriert und startet den Kiosk nach jedem Absturz oder sauberem Beenden automatisch neu (nach 10 s). Um den Kiosk dauerhaft zu beenden:
```bash
sudo systemctl stop chromium-kiosk
```

### HDMI-Auflösung konfigurieren

Die gewünschte HDMI-Ausgabeauflösung wird in `/etc/time-reference-monitor.conf` festgelegt:

```bash
sudo nano /etc/time-reference-monitor.conf
```

| `HDMI_MODE` | Auflösung | Verwendung |
|-------------|-----------|-----------|
| `sdi-1080i50` | 1920×1080i 50 Hz | **Standard** — Broadcast-Format für HDMI→SDI-Konverter |
| `sdi-1080p50` | 1920×1080p 50 Hz | Progressiv für Konverter die p-Signal erfordern |
| `auto` | Monitor-Präferenz | **PC-Monitor** — lässt den Bildschirm seine native Auflösung wählen |

Nach der Änderung:
```bash
# Kiosk neu starten (wirksam sofort, kein Reboot nötig):
sudo systemctl restart chromium-kiosk

# config.txt + kiosk gleichzeitig aktualisieren:
sudo bash rpi/update.sh
```

> **PC-Monitor vs. SDI-Konverter:**
> PC-Monitore unterstützen meist 1080p@60Hz, nicht @50Hz. Wenn das Bild an der linken Seite klebt oder nur teilweise angezeigt wird, `HDMI_MODE=auto` setzen. Für den SDI-Konverter `sdi-1080i50` (Standard-Broadcast) oder `sdi-1080p50` verwenden.

Der HDMI-Output wird beim Start automatisch erkannt. Zur Diagnose via SSH:
```bash
DISPLAY=:0 xrandr --query
```

**Hinweis RPi 4 vs. RPi 5:**
- RPi 4: Output heisst `HDMI-1` (erster Anschluss) / `HDMI-2` (zweiter)
- RPi 5 / neuere Kernel: `HDMI-A-1` / `HDMI-A-2`
- Das Script probiert alle Varianten automatisch durch

**RPi Firmware-Konfiguration (`/boot/firmware/config.txt`):**

`setup.sh` und `update.sh` setzen diese Zeilen automatisch basierend auf `HDMI_MODE`:

```ini
hdmi_force_hotplug=1   # HDMI aktiv halten, auch wenn SDI-Konverter kein EDID sendet
hdmi_group=1           # CEA (Broadcast), nicht DMT (PC-Monitor)
hdmi_mode=20           # 1080i50 (Standard) — oder 31 für 1080p50
```

`hdmi_force_hotplug=1` ist besonders wichtig: Viele HDMI→SDI-Konverter (inkl. Blackmagic) schicken kein EDID zurück — ohne diesen Parameter gibt der RPi gar kein Bildsignal aus.

**Wie RPi + Blackmagic HDMI→SDI zusammenarbeiten:**

```
config.txt hdmi_mode=20
    ↓  GPU gibt 1080i50 HDMI-Signal aus (nach Reboot)
Blackmagic Mini Converter HDMI→SDI
    ↓  konvertiert HDMI 1080i50 → SDI 1080i50
SDI-Monitor / Mischer
```

- Der **X-Framebuffer läuft immer progressiv** (1920×1080p) — die GPU erledigt das Interlacing bei der HDMI-Ausgabe intern
- `kiosk.sh` setzt daher nur `--mode 1920x1080` (progressiv), **kein** interlaced-xrandr-Modeline
- **Nach `setup.sh` oder Änderung von `HDMI_MODE` muss einmalig neu gestartet werden**, damit `config.txt` wirksam wird:
  ```bash
  sudo reboot
  ```
- Ohne Reboot: kein korrektes HDMI-Signal → Blackmagic gibt kein SDI aus

**Diagnose HDMI-Signal:**
```bash
# Aktuell gesetzter GPU-Modus (wirksam seit letztem Reboot):
vcgencmd hdmi_status_show
vcgencmd get_config hdmi_mode
vcgencmd get_config hdmi_group

# Aktuelle xrandr-Auflösung im Kiosk (via SSH):
DISPLAY=:0 xrandr --query
```

---

### Software-Update

```bash
sudo bash rpi/update.sh
```

Das Script führt folgende Schritte aus (kein vollständiges Re-Setup nötig):

1. `git pull` im Repository
2. Rsync der Applikationsdateien nach `/opt/time-reference-monitor/`
3. Python-Abhängigkeiten aktualisieren (`pip install -r requirements.txt`)
4. `alsaltc` neu kompilieren — **nur wenn der C-Source neuer als das installierte Binary ist**
5. Systemd-Service-Dateien aktualisieren + `daemon-reload` (Kiosk-Restart nur bei Änderung)
6. ALSA-Konfiguration aktualisieren (Backup nach `/etc/asound.conf.bak`)
7. Kiosk-Konfigurationsdatei erstellen (nur wenn `/etc/time-reference-monitor.conf` fehlt)
8. `config.txt` HDMI-Mode synchronisieren basierend auf `HDMI_MODE` in der Konfigurationsdatei
9. `time-reference-monitor` neu starten

Chromium muss nicht neugestartet werden — es lädt das UI automatisch neu, sobald der Backend-Dienst wieder antwortet.

---

### PTP-Synchronisation lokal testen (Software-Grandmaster)

Um PTP-Synchronisation unabhängig von einem externen Grandmaster zu testen, kann `ptp4l` auf dem RPi selbst als Grandmaster betrieben werden (Software-Timestamps, ohne dedizierte PTP-Hardware):

```bash
# Temporärer Software-Grandmaster (läuft im Vordergrund, Ctrl+C zum Beenden)
sudo ptp4l -i eth0 -m -S --priority1 1 --masterOnly 1

# Mit explizitem Domain (muss mit time-reference-monitor --domain übereinstimmen):
sudo ptp4l -i eth0 -m -S --priority1 1 --masterOnly 1 --domainNumber 0
```

| Flag | Bedeutung |
|------|-----------|
| `-i eth0` | Netzwerkinterface (ggf. `eth0` → `enp3s0` o.ä. anpassen) |
| `-m` | Meldungen auf stdout (für Diagnose) |
| `-S` | Software-Timestamps (kein Hardware-PTP nötig) |
| `--priority1 1` | Niedrigster Wert = höchste Priorität → Grandmaster |
| `--masterOnly 1` | Wird nie Slave, immer Grandmaster |

**Erwartete Ausgabe:**
```
ptp4l[…]: port 1: MASTER
ptp4l[…]: master offset   0 s0 freq +0 path delay 0
```

Sobald `ptp4l` als Grandmaster läuft, sollte der Time-Monitor unter `PTP` einen Offset-Wert zeigen (nicht `NO_PTP`). Bei Loopback auf demselben Gerät typischerweise < 1 µs.

**Permanenter Test-Grandmaster (systemd-Service):**
```bash
cat > /tmp/gm-test.conf << 'EOF'
[global]
domainNumber    0
priority1       1
priority2       1
masterOnly      1
logAnnounceInterval    -3
logSyncInterval        -4
logMinDelayReqInterval -4
EOF

sudo ptp4l -i eth0 -m -S -f /tmp/gm-test.conf
```

> **Hinweis:** Ein Software-Grandmaster ist für Funktionstests geeignet. Für präzise Broadcast-Synchronisation ist ein Hardware-Grandmaster (GPS-locked PTP-Uhr) erforderlich — Software-Timestamps schwanken je nach CPU-Last um 10–100 µs.

---

## LED-Matrix Zeitanzeige (optional)

Optionale Hardware-Erweiterung: MAX7219 8×8 LED-Matrix Module zeigen PTP-, LTC- oder NTP-Zeit direkt am Gerät an — unabhängig vom Kiosk-Browser, als eigenständiger systemd-Dienst.

### Hardware

**Empfohlen:** MAX7219 8×8 LED-Matrix Module (cascaded)

| Eigenschaft | Wert |
|-------------|------|
| Module für ~32cm | 10 Stück (10 × 32mm = 320mm) |
| Module für ~38cm | 12 Stück |
| Interface | SPI (5 Kabel) |
| Preis | ~1–2 CHF/Modul, als 4er-Strip erhältlich |
| Lesbarkeit | Gut bis ~5m Abstand |

**Verkabelung (SPI):**

| Display-Pin | RPi GPIO | RPi Pin |
|-------------|----------|---------|
| VCC | 5V | Pin 2 |
| GND | GND | Pin 6 |
| DIN | GPIO 10 (MOSI) | Pin 19 |
| CS | GPIO 8 (CE0) | Pin 24 |
| CLK | GPIO 11 (CLK) | Pin 23 |

Bei mehreren Modulen (Daisy-Chain): `DOUT` des ersten Moduls → `DIN` des nächsten. VCC/GND/CLK/CS parallel.

### Installation

```bash
# Nach setup.sh ausführen:
sudo bash display/setup-display.sh
```

Das Script:
1. Aktiviert SPI in `/boot/firmware/config.txt`
2. Fügt User `ptp` zu Gruppen `spi` und `gpio` hinzu
3. Installiert `luma.led_matrix` ins Python-venv
4. Aktiviert `time-display.service`

```bash
# Falls SPI neu aktiviert wurde:
sudo reboot

# Danach startet der Dienst automatisch. Manuell:
sudo systemctl start time-display
journalctl -fu time-display
```

### Konfiguration

Aktive Parameter in `/etc/systemd/system/time-display.service`:

| Parameter | Default | Bedeutung |
|-----------|---------|-----------|
| `--modules` | `10` | Anzahl 8×8 Module |
| `--source` | _(keiner)_ | `PTP`, `LTC` oder `NTP` fix; ohne Angabe: automatisch wechseln |
| `--cycle-s` | `5` | Sekunden pro Quelle beim automatischen Wechsel |
| `--brightness` | `64` | Helligkeit 0–255 (64 = angenehm für Innenraum) |
| `--scroll` | _(aus)_ | Text bei jedem Wechsel einmal durchscrollen |

Nach Änderungen:
```bash
sudo systemctl daemon-reload && sudo systemctl restart time-display
```

### Anzeigeformat

```
PTP 10:23:45    ← PTP-Zeit (nur wenn ptp_valid=true)
LTC 10:23:45    ← LTC-Zeit ohne Frames (nur wenn present=true)
NTP 10:23:45    ← Systemzeit (von chrony diszipliniert)

PTP ------      ← Quelle nicht verfügbar
NO API          ← Backend nicht erreichbar
```

Das Script `display/display_driver.py` läuft vollständig unabhängig vom Monitor-Backend und pollt nur `GET /api/status`.

---

## Web-UI und API

| URL | Inhalt |
|-----|--------|
| `http://<host>:8088/` | Haupt-Dashboard (PTP/NTP/LTC, Events) |
| `http://<host>:8088/ltc-clock` | Vollbild-LTC-Uhr (Studiomonitor) |
| `http://<host>:8088/spectrum` | Spektrum-Analyse (on-demand) |
| `http://<host>:8088/api/status` | JSON-Snapshot aller Status-Werte |
| `http://<host>:8088/api/ltc/level` | Audio-Pegel (RMS/Peak in dBFS) |
| `http://<host>:8088/api/events` | Event-Liste |
| `POST /api/system/reboot` | System neu starten (Kiosk-Funktion) |
| `POST /api/system/shutdown` | System herunterfahren (Kiosk-Funktion) |

### Reboot / Shutdown im Kiosk

Im Haupt-Dashboard sind zwei Buttons **REBOOT** und **SHUTDOWN** vorhanden (rot hervorgehoben). Beide zeigen einen Browser-Bestätigungsdialog bevor der Befehl ausgeführt wird.

Voraussetzung: Die sudoers-Regel aus `setup.sh` muss installiert sein (`/etc/sudoers.d/time-reference-monitor`), damit der `ptp`-User `sudo /sbin/reboot` und `sudo /sbin/poweroff` ohne Passwort ausführen darf.

### Beispiel `/api/status`

```json
{
  "status": {
    "ptp_valid": true,
    "port_state": "SLAVE",
    "gm_identity": "AC-DE-48-FF-FE-12-34-56",
    "offset_ns": -5234,
    "mean_path_delay_ns": 8978,
    "ptp_time_utc_iso": "2026-03-25T10:00:00.123Z"
  },
  "ntp": { "status": "synced", "stratum": 2, "ref": "PTP0" },
  "ltc": {
    "present": true,
    "timecode": "10:00:12:08",
    "fps": "25",
    "jumps_total": 0
  }
}
```

---

## ALSA-Konfiguration (LTC)

Die Datei `rpi/alsa/asound.conf` definiert zwei ALSA-Geräte:

| ALSA-Gerät | Typ | Verwendung |
|-----------|-----|-----------|
| `dsnoop_ltc` | dsnoop (shared capture) | Multiplexing: mehrere Prozesse lesen gleichzeitig vom Interface |
| `ltc_left_mono` | plug (mono, Kanal 0 links) | `alsaltc` + `ltc_level.py`: konvertiert Hardware-Format → S16_LE mono |

**Wichtig:** `alsaltc` muss das Gerät `ltc_left_mono` verwenden, **nicht** `dsnoop_ltc` direkt. Der `plug`-Typ von `ltc_left_mono` übernimmt automatisch Format- und Kanalkonvertierung. Das Hardware-Format (S24_3LE oder S32_LE) wird in `asound.conf` **nicht** fest vorgegeben — ALSA auto-negotiiert es. Damit wird der Fehler `Slave PCM not usable / no configurations available` vermieden.

Das Interface ist auch als **ALSA-Standardgerät** gesetzt (`defaults.pcm.card US2x2HR`), sodass `arecord` ohne `-D` automatisch den US-2x2HR verwendet.

**Hardware-Konfiguration (Tascam US-2x2HR):**

`/etc/asound.conf` verwendet den stabilen Kartennamen `hw:US2x2HR,0` (statt des fragilen Index `hw:3,0`):
```
pcm.dsnoop_ltc {
    slave {
        pcm "hw:US2x2HR,0"  # stabiler Name, überlebt USB-Neuenumeration
        rate 48000
        channels 2
        # format: nicht gesetzt → ALSA auto-negotiiert (S24_3LE oder S32_LE)
    }
}
```

**Anderes Interface:** Kurzname aus `arecord -l` ablesen (Spalte `card X: ShortName`) und in `/etc/asound.conf` eintragen:
```bash
arecord -l
# → card 3: US2x2HR [US-2x2HR], device 0: …
sudo nano /etc/asound.conf   # pcm "hw:US2x2HR,0" und card US2x2HR anpassen
```

**LTC-Kabel:** am linken Eingang (Input 1) anschliessen — der linke Kanal (Kanal 0) wird dekodiert. Für rechten Kanal: Kabel auf rechten Eingang oder `route_policy` in `ltc_left_mono` anpassen.

**ALSA-Diagnose bei Problemen:**
```bash
# Welche Formate unterstützt das Interface nativ?
arecord --dump-hw-params -D hw:US2x2HR,0 /dev/null 2>&1 | grep -E "^FORMAT|^ACCESS|^CHANNELS|^RATE"

# dsnoop testen (auto-Format):
arecord -D dsnoop_ltc -r 48000 -c 2 -d 2 /tmp/test_stereo.wav

# Mono-Plug testen (was alsaltc sieht, S16_LE via plug):
arecord -D ltc_left_mono -r 48000 -f S16_LE -c 1 -d 2 /tmp/test_mono.wav

# alsaltc direkt testen:
/usr/local/bin/alsaltc -d ltc_left_mono -r 48000 -c 1 -f 25 --dropout-ms 800 --format S16_LE
```

---

## LTC-Decoder (alsaltc)

`alsaltc` liest ALSA-Audio und dekodiert LTC über libltc.

```bash
# Korrekte Verwendung: ltc_left_mono (plug übernimmt Format-/Kanalkonvertierung)
alsaltc -d ltc_left_mono -r 48000 -c 1 -f 25 --dropout-ms 800 --format S16_LE
# Ausgabe: 10:00:12:08
#          10:00:12:09
#          NO_LTC          ← bei Signalausfall
```

Optionen:

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `-d DEVICE` | ALSA-Capture-Gerät | `hw:0,0` |
| `-r RATE` | Sample-Rate | `48000` |
| `-c CHANNELS` | Kanäle (ALSA) | `1` |
| `-f FPS` | Erwartete Framerate | `25` |
| `--channel N` | Kanal dekodieren (0=links, 1=rechts) | `0` |
| `--dropout-ms MS` | Timeout für NO_LTC-Ausgabe | `0` (deaktiviert) |
| `--format FMT` | Sample-Format (S16_LE, S32_LE) | `S16_LE` |

Kompilieren auf dem Pi:
```bash
cd alsaltc-v02
make
sudo make install   # → /usr/local/bin/alsaltc
```

---

## Datenbankretention

Events werden in SQLite gespeichert (`ptp_monitor.sqlite`).
Standardmäßig werden die letzten 5000 Events behalten.
Im Dauerbetrieb empfohlen: `--db /var/lib/time-reference-monitor/events.sqlite`
(kein Schreiben ins Projektverzeichnis, SD-Karte schonen).

Spektrum-Bilder landen in `/dev/shm` (RAM), nie auf der SD-Karte.

---

## CLI-Referenz (Kurzform)

```
run.py [--source mock|real] [--iface IFACE] [--domain N] [--poll S]
       [--http] [--http-host HOST] [--http-port PORT]
       [--ui-refresh-ms MS] [--ui-api-poll-ms MS] [--stale-threshold-ms MS]
       [--ltc] [--ltc-device DEV] [--ltc-fps FPS] [--ltc-cmd CMD]
       [--ltc-dropout-timeout-ms MS] [--ltc-jump-tolerance-frames N]
       [--db PATH] [--db-max-events N]
       [--startup-grace-s S] [--error-window-s S] [--gm-window-s S]
       [--trace]
```

Vollständige Beschreibung: `Time_Reference_Monitor_Anleitung_DE.txt`

---

*Markus Gerber &lt;dev@npn.ch&gt;*
