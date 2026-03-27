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
# → hw:X,0 in /etc/asound.conf auf die LTC-Karte anpassen (arecord -l)

python3 run.py \
  --source real --iface eth0 \
  --http --http-host 0.0.0.0 --http-port 8088 \
  --poll 0.25 \
  --ltc \
  --ltc-device dsnoop_ltc \
  --ltc-fps 25 \
  --ltc-cmd "alsaltc -d dsnoop_ltc -r 48000 -c 1 -f 25 --dropout-ms 800" \
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
sudo nano /etc/asound.conf          # hw:X,0 setzen

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
| `--ltc-cmd` | `alsaltc -d dsnoop_ltc -r 48000 -c 1 -f 25 --dropout-ms 800 --format S16_LE` | |
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
5. Systemd-Service-Dateien aktualisieren + `daemon-reload`
6. `time-reference-monitor` neu starten

Chromium muss nicht neugestartet werden — es lädt das UI automatisch neu, sobald der Backend-Dienst wieder antwortet.

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

Die Datei `rpi/alsa/asound.conf` definiert zwei Geräte:

| ALSA-Gerät | Typ | Verwendung |
|-----------|-----|-----------|
| `dsnoop_ltc` | dsnoop (shared capture) | `alsaltc` + Spektrum: paralleler Zugriff auf dieselbe Hardware |
| `ltc_left_mono` | plug (mono, Kanal 0) | `ltc_level.py` (Pegel-Meter im UI) |

Karte anpassen in `/etc/asound.conf`:
```
pcm.dsnoop_ltc {
    slave { pcm "hw:1,0"; ... }   # ← hier den richtigen Index eintragen
}
```

---

## LTC-Decoder (alsaltc)

`alsaltc` liest ALSA-Audio und dekodiert LTC über libltc.

```bash
alsaltc -d dsnoop_ltc -r 48000 -c 1 -f 25 --dropout-ms 800 --format S16_LE
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
