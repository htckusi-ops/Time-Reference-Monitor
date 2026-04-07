# Konzept: Time Reference Monitor

## 1. Problemstellung

Broadcast-Studios arbeiten mit mehreren gleichzeitigen Zeitreferenzen:

- **PTP (IEEE 1588 / SMPTE ST 2059)** als primäre Netzwerk-Zeitquelle für IP-Produktionsinfrastruktur (AES67, ST 2110)
- **NTP (chrony)** als Betriebssystem-Zeitquelle und Fallback
- **LTC (Linear Timecode / SMPTE)** als traditionelle analoge Zeitreferenz, z.B. von einem Master-Synchronizer oder einer DAW

In der Praxis treten Probleme auf, die schwer zu diagnostizieren sind:

- PTP-Grandmaster wechselt unerwartet (GM-Flap)
- PTP-Offset läuft weg oder fällt aus
- NTP ist nicht synchronisiert, obwohl PTP aktiv ist
- LTC-Signal reisst ab (Dropout) oder springt (Jump)
- Abweichungen zwischen PTP- und LTC-Zeit bleiben unbemerkt

Es fehlte ein Werkzeug, das diese drei Quellen **gleichzeitig und kontinuierlich** beobachtet, Ereignisse protokolliert und eine klare Statussignalisierung liefert — ohne dabei selbst in den Betrieb einzugreifen.

---

## 2. Designziele

| Ziel | Umsetzung |
|------|-----------|
| **Passiv, kein Eingriff** | Nur lesende Zugriffe auf `pmc`, `chronyc`, ALSA. Keine Zeitdisziplinierung. |
| **Echtzeit-Überblick** | Web-UI pollt `/api/status` alle 250 ms, zeigt PTP-Zeit interpoliert mit 20 ms Refresh. |
| **Klare Fehlersignalisierung** | Dreiwertige State Machine: OK / WARN / ALARM mit farblicher Hervorhebung. |
| **Ereignisprotokoll** | Alle Statusübergänge werden mit UTC-Timestamp, Schweregrad und Typ gespeichert (Memory + SQLite). |
| **Rollen de Fehler** | Zähler in konfigurierbaren Zeitfenstern (Standard: 1 h Fehler, 48 h GM-Wechsel) für Trend-Erkennung. |
| **LTC-Integration** | Echtzeit-Dekodierung via `alsaltc` (ALSA + libltc), Delta-Berechnung zu PTP, Sprung- und Dropout-Erkennung. |
| **Raspberry Pi tauglich** | Minimaler RAM/CPU-Bedarf, SD-Karten-schonende Architektur (WAL, Spektrum in /dev/shm). |
| **Kiosk-Betrieb** | Chromium im Vollbild auf dediziertem Display, kein Nutzereingriff nötig. |

---

## 3. Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi                             │
│                                                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐        │
│  │  ptp4l     │  │  chrony    │  │  ALSA (dsnoop_ltc) │        │
│  │  (slave)   │  │  (NTP)     │  │  LTC-Audioeingang  │        │
│  └─────┬──────┘  └─────┬──────┘  └─────────┬──────────┘        │
│        │ pmc            │ chronyc            │                   │
│  ┌─────▼──────────────────────────────────▼──────────────┐    │
│  │              Python-Backend (main.py)                   │    │
│  │                                                         │    │
│  │  sources_ptp ──► status_bus ◄── sources_ntp            │    │
│  │  sources_ltc ──►     │       ◄── ltc_level              │    │
│  │  (alsaltc)           │           (arecord)              │    │
│  │                      │                                  │    │
│  │                   db.py ──► ptp_monitor.sqlite          │    │
│  │                      │                                  │    │
│  │  ┌───────────────────┴──────────────────────────────┐  │    │
│  │  │             webapp.py (Flask)                     │  │    │
│  │  │  Dauerlaufend:                                    │  │    │
│  │  │  /             /api/status   /api/ltc/level       │  │    │
│  │  │  /ltc-clock    /api/events   /settings            │  │    │
│  │  │                                                   │  │    │
│  │  │  On-Demand / Diagnose:                            │  │    │
│  │  │  /spectrum   ←── spectrum.py (SpectrumManager)   │  │    │
│  │  │  /tcpdump    ←── tcpdump_mgr.py (TcpdumpCapture) │  │    │
│  │  │  /settings   ←── domain_scanner.py (DomainScan)  │  │    │
│  │  └───────────────────────────────────────────────────┘  │    │
│  └────────────────────────────┬──────────────────────────────┘    │
│                                │ HTTP :8088                        │
│  ┌─────────────────────────────▼────────────────────────────┐    │
│  │  Chromium (kiosk, VT7)                                   │    │
│  │  → http://localhost:8088/                                │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Threads

Das Backend betreibt vier dauerlaufende Threads neben dem Flask-HTTP-Server:

| Thread | Aufgabe | Intervall |
|--------|---------|-----------|
| `ptp_loop` | `pmc`-Abfragen, PTP-Status in `status_bus` schreiben | `--poll` (250 ms) |
| `ntp_loop` | `chronyc tracking` parsen, NTP-Status schreiben | `--ntp-refresh-s` (250 ms) |
| `ltc_snapshot_loop` | Snapshot von `sources_ltc` holen, in `status_bus` schreiben | `--ltc-refresh-s` (250 ms) |
| `alsaltc` (subprocess) | ALSA-Capture → libltc → `stdout` HH:MM:SS:FF | kontinuierlich |

Alle Zugriffe auf gemeinsamen Zustand laufen über `threading.Lock()`.

Zusätzlich gibt es **kurzlebige Scan-Threads** auf Anfrage:
- `DomainScanner` (`domain_scanner.py`): Startet beim Domain-Scan einen temporären Thread, der `tcpdump` für einen begrenzten Paketblock ausführt und sich nach Abschluss selbst beendet.
- `TcpdumpCapture` (`tcpdump_mgr.py`): Zwei parallele Threads (PCAP-Schreiber + Text-Reader) für die Live-Capture-Seite; laufen nur, solange der Browser die `/tcpdump`-Seite geöffnet hat.
- `SpectrumManager` (`spectrum.py`): Kurzlebiger Prozess (arecord → sox), der nach Abschluss der Aufnahme endet.

---

## 4. Komponenten

### `status_bus.py` — Herz des Systems

Zentrale State-Machine und Event-Bus. Hält den aktuellen Zustand aller drei Zeitquellen und generiert Events bei Übergängen:

- `PTP_LOSS` / `PTP_OK` — Ausfall und Wiederherstellung
- `GM_CHANGE` — Grandmaster-Wechsel
- `NTP_UNSYNC` / `NTP_OK` — NTP-Statswechsel
- `LTC_LOSS` / `LTC_OK` — LTC-Dropout
- `LTC_JUMP` — Zeitsprung im LTC-Signal
- `LTC_DECODE_ERROR` — Dekodierungsfehler

**Startup-Grace-Period:** In den ersten Sekunden nach dem Start werden WARN/ALARM-Events als `suppressed=True` markiert, damit initiale PTP-Lock-Transienten die Fehlerzähler nicht verfälschen.

### `sources_ltc.py` + `alsaltc` — LTC-Pipeline

```
ALSA hw:X,0
    │
    ▼ (dsnoop_ltc – shared capture)
    ├── alsaltc (subprocess)
    │       libltc decoder
    │       stdout: "HH:MM:SS:FF" | "NO_LTC"
    │            │
    │            ▼
    │       sources_ltc.py (Regex-Parser)
    │       Jump-Detektion (Frame-Count-Vergleich)
    │            │
    │            ▼
    │       status_bus.update_ltc()
    │
    └── ltc_level.py (arecord, separater dsnoop-Reader)
            RMS / Peak → /api/ltc/level → UI-Pegelanzeige
```

`alsaltc` wurde entwickelt, weil `ltcdump` und ähnliche Tools kein zuverlässiges Dropout-Signaling über `stdout` bieten. Die C-Implementierung verwendet direkt ALSA-`snd_pcm_readi` und libltc ohne zusätzliche Latenz-Schichten.

### `webapp.py` / `web_ui.py` — Web-Frontend

Bewusstes Design als **Single-Page-Application ohne JavaScript-Framework**:
- Ein einziger `GET /api/status`-Poll alle 250 ms
- PTP-Zeit wird client-seitig **monoton interpoliert** — `performance.now()`-basierte Hochrechnung, Korrektur verhindert Rückläufer bei Netzwerk-Jitter
- Keine WebSockets, keine langen HTTP-Polls — einfach, robust, cache-freundlich
- LTC-Audio-Pegel über separaten `/api/ltc/level`-Endpunkt (200 ms, unabhängig vom Status-Poll)

Verfügbare Seiten:

| URL | Seite |
|-----|-------|
| `/` | Haupt-Dashboard (PTP/NTP/LTC, 7-Seg, Fehlerzähler, Ereignislog) |
| `/ltc-clock` | Screen Clock (Vollbild, LTC/PTP/Local, Schrift/Farbe/Breite konfigurierbar) |
| `/spectrum` | LTC Spektrum (On-Demand-Aufnahme + FFT-PNG + WAV-Download) |
| `/tcpdump` | PTP Capture (Live-tcpdump, Ring-Buffer, PCAP-Download) |
| `/settings` | Einstellungen (Netzwerk, NTP, WLAN, PTP Domain, Simulation) |

---

## 4b. Analyse- und Diagnosewerkzeuge

### `tcpdump_mgr.py` — PTP Capture (`/tcpdump`)

**Klasse:** `TcpdumpCapture`

Zwei parallele kurzlebige Prozesse, die nur laufen, solange der Browser die `/tcpdump`-Seite geöffnet hat:

1. **PCAP-Schreiber**: `tcpdump` mit Filter `(udp port 319 or udp port 320) or ether proto 0x88f7` schreibt eine temporäre PCAP-Datei in `/dev/shm`
2. **Text-Reader**: Ein zweiter `tcpdump`-Prozess liest denselben Filter im lesbaren Format, gibt Zeilen in einen **Ring-Buffer von 500 Zeilen** aus

Die Ausgabe wird über SSE (Server-Sent Events) an den Browser gestreamt — kein Polling nötig, kein WebSocket.

**PCAP-Download:** Die temporäre PCAP-Datei aus `/dev/shm` wird als Download bereitgestellt und kann mit Wireshark geöffnet werden.

**Lehrwert:**
- Sichtbar, welche PTP-Nachrichtentypen ausgetauscht werden (Sync/Follow_Up für Two-Step-Clocks, Delay_Req/Resp für Path-Delay-Messung, Announce für GM-Election)
- Alle aktiven PTP-Domains gleichzeitig sichtbar — nützlich in Broadcast-Umgebungen mit AES67, ST 2110, DANTE
- Grandmaster-Identität aus Announce-Paketen ablesen (Clock Identity, Priority1/2, Clock Class)
- Multicast-Gruppen: `224.0.1.129` (PTP v2 General), `224.0.0.107` (Peer Delay), `01:1b:19` (L2 Multicast)

---

### `domain_scanner.py` — PTP-Domain-Scanner (`/settings > PTP Domain`)

**Klasse:** `DomainScanner`

Kurzlebiger Scan-Thread auf Anfrage (startet, scannt, beendet sich):

1. `tcpdump` erfasst genau **500 PTP-Pakete** (gleicher Filter wie `/tcpdump`)
2. Ein **reiner Python-PCAP-Parser** (keine externen Abhängigkeiten) öffnet die temporäre PCAP-Datei
3. Unterstützte Frame-Typen: **L2 Ethernet** (EtherType 0x88F7), **IPv4** (UDP 319/320), **IPv6**, **VLAN-getaggt** (802.1Q)
4. Aus dem PTP-Header wird **Byte 4** (offset 0-basiert) als `domainNumber` extrahiert
5. Alle gefundenen Domain-Nummern werden mit Vorkommen-Zähler zurückgegeben

**Wichtig:** Der Monitor ruft `pmc` mit `-d N` auf (Domain-Nummer, steuert auf welcher Domain pmc lauscht), **nicht** `-b N` (`-b` ist `boundaryHops` — die Hop-Tiefe bei pmc-UDS-Abfragen, ein anderer Parameter).

**Domain zur Laufzeit wechseln:**

| Aktion | Wirkung |
|--------|---------|
| **Aktiv (bis Reboot)** | Setzt die Domain im laufenden Prozess; kein Schreibzugriff auf Disk |
| **Aktiv & Speichern** | Wie oben, zusätzlich Persistenz-Datei `/var/lib/time-reference-monitor/ptp_domain` schreiben |

Beim Dienststart: Falls die Persistenz-Datei existiert, wird ihr Wert gegenüber dem `--domain`-CLI-Argument bevorzugt — Domain-Änderungen bleiben über Neustarts hinweg wirksam ohne die systemd-Unit-Datei zu editieren.

---

### `spectrum.py` — LTC Spektrum (`/spectrum`)

**Klasse:** `SpectrumManager`

On-Demand-Pipeline zur Signalqualitäts-Diagnose:

```
arecord (ALSA, dsnoop_ltc)
    │
    ▼  WAV in /dev/shm
sox (FFT-Analyse)
    │
    ▼  PNG-Spektrogramm in /dev/shm
Browser: PNG-Anzeige + WAV-Download + PNG-Download
```

Alle Dateien landen in `/dev/shm` (RAM-Disk) — **keine SD-Karten-Schreibzugriffe**.

**Analysenutzen:**
- LTC bei 25 fps SMPTE liegt im Frequenzband ~600 Hz – 2,4 kHz — sofort sichtbar, ob das Signal im richtigen Bereich liegt
- Rauschen (breitbandig), Netzbrumm (50/100 Hz-Peaks) oder falsche Pegel direkt erkennbar
- **WAV-Download**: Aufnahme für Post-Analyse mit Audacity oder anderen Werkzeugen

---

## 5. ALSA-Designentscheidung: dsnoop

Mehrere Komponenten müssen gleichzeitig auf das LTC-Audiosignal zugreifen:

| Komponente | Zweck |
|-----------|-------|
| `alsaltc` | Timecode-Dekodierung (kontinuierlich) |
| `ltc_level.py` | Pegel-Meter (alle 200 ms) |
| `spectrum.py` | Spektrogramm (on-demand) |

ALSA erlaubt standardmäßig nur **einen** gleichzeitigen Capture-Client pro Hardware-Device. Lösung: `dsnoop` — ein ALSA-Plugin, das einen Hardware-Capture-Stream intern multiplext. Alle Clients lesen von `dsnoop_ltc`, ALSA schreibt intern nur einen `hw:X,0`-Stream.

Alternative (PulseAudio/PipeWire) wurde bewusst **nicht** gewählt: zu viel Overhead, zu viele Abhängigkeiten für ein dediziertes Monitoring-Gerät, potenziell instabil bei Headless-Betrieb ohne Nutzer-Session.

---

## 6. Raspberry Pi Deployment

### Systemd statt Supervisor/Docker

Systemd ist der native Init-Daemon von Raspberry Pi OS. Vorteile:
- Abhängigkeitsgraph (`After=network-online.target chrony.service`)
- Automatischer Neustart (`Restart=on-failure`)
- Journal-Integration (`journalctl -fu time-reference-monitor`)
- Keine zusätzliche Abhängigkeit, kein separater Daemon

### Chromium-Kiosk via xinit auf VT7

Ansatz: `chromium-kiosk.service` startet `xinit kiosk.sh -- :0 vt7 -nocursor` als systemd-Service.

Vorteile gegenüber Desktop-Autologin-Methode (LXDE-Autostart):
- Kein vollständiges Desktop-Environment nötig (keine LXDE, keine Taskleiste)
- VT1 bleibt für Notfall-SSH/Konsole frei
- Klare Trennung: der Kiosk ist ein eigener, restartbarer Service

`kiosk.sh` wartet aktiv auf den Backend-HTTP-Server, bevor Chromium geöffnet wird — damit beim Booten kein leerer Fehler-Screen erscheint.

### SD-Karte schonen

| Maßnahme | Details |
|----------|---------|
| SQLite WAL-Mode | Schreibt sequentiell, wenige `fsync`-Aufrufe |
| Retention-Limit | Max. 5000 Events in der DB |
| Spektrum in RAM | `/dev/shm` statt SD-Karte |
| Python-Cache deaktiviert | `__pycache__` nicht im Datenpfad |

---

## 7. Erweiterungsmöglichkeiten (nicht implementiert)

- **SNMP-Trap / Syslog-Export** bei ALARM-Events — auch als SNMP-Traps für bestehende NMS-Infrastruktur
- **Redundante Grandmaster-Überwachung** (BC-Topologie)
- **Historische Offset-Kurven** (Chart.js über SQLite-Abfrage)
- **REST-API für externe Dashboards** (Grafana via Prometheus-Exporter)
- **LTC-Einspeisung aus mehreren Kanälen** gleichzeitig (Stereo-Split L/R auf zwei libltc-Instanzen)
- **HTTP Basic Auth für Remote-Zugriff** — Localhost (Kiosk) ohne Auth, alle anderen IPs mit Credential (bcrypt-Hash in `/etc/time-reference-monitor/htpasswd`)
- **Laufzeit-Konfiguration weiterer Parameter** über `POST /api/config`: Poll-Intervall, Stale-Threshold, Fehlerzeitfenster, LTC-FPS, Jump-Toleranz (aktuell nur PTP-Domain zur Laufzeit änderbar)
- **SNMP-Traps bei ALARM-Events** — Integration in bestehende Netzwerk-Management-Systeme ohne Log-Scraping
