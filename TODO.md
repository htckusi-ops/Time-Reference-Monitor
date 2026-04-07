# TODO

## Implementiert (Referenz)

Die folgenden Features wurden seit Erstellung dieses TODO-Dokuments implementiert und sind im aktuellen Codestand enthalten:

- **PTP Domain Scanner** (`domain_scanner.py`): Settings-Seite > PTP Domain-Karte; tcpdump erfasst 500 PTP-Pakete, Python-PCAP-Parser extrahiert `domainNumber` (Byte 4 des PTP-Headers) ohne externe Abhängigkeiten; Domain zur Laufzeit wechseln ("Aktiv bis Reboot" / "Aktiv & Speichern"); Persistenz in `/var/lib/time-reference-monitor/ptp_domain` (überlagert `--domain`-CLI-Argument beim Start)
- **PTP Capture** (`tcpdump_mgr.py`, `/tcpdump`): Live-Terminal mit farblicher Hervorhebung nach Nachrichtentyp, Ring-Buffer 500 Zeilen, PCAP-Download für Wireshark; erfasst UDP 319/320 + EtherType 0x88F7 (L2 PTP)
- **LTC Spektrum** (`spectrum.py`, `/spectrum`): On-Demand-WAV-Aufnahme via `arecord` + FFT-Spektrogramm via `sox`, PNG- und WAV-Download; läuft vollständig in `/dev/shm` (keine SD-Karten-Schreibzugriffe)
- **Screen Clock** (`/ltc-clock`): Vollbild-Uhr, Zeitquelle wählbar (LTC/PTP/Local), Schriftgrösse/Farbe/Breite konfigurierbar und im Browser-Localstorage persistent; Close-Button für Kiosk-Betrieb
- **Einstellungsseite** (`/settings`): Netzwerk (DHCP/statisch), NTP-Server, WLAN, PTP Domain (Scanner + Laufzeitwechsel), PTP-Simulation (Dropout/GM-Flap/Step/Wander/Drift), NTP-Simulation
- **Monotone Zeitinterpolation**: PTP-Zeit wird client-seitig über `performance.now()` hochgerechnet; Monoton-Korrektur verhindert Rückläufer bei Netzwerk-Jitter
- **7-Seg-Breitenstabilisierung**: Platzhalter `00:00:00.00` verhindert Layoutsprünge beim Wechsel zwischen Ziffernbreiten
- **Kiosk-Close-Buttons**: Alle Unterseiten (`/ltc-clock`, `/spectrum`, `/tcpdump`) haben einen Close-Button, der zum Dashboard zurückführt
- **Header-Navigation-Dropdown**: `☰ Menu`-Button im Header, reines CSS-Hover; alle Seitenlinks und Systemaktionen (Reload, Reboot, Shutdown) darin; Dashboard-Karte von Buttons freigehalten
- **Zweispaltige PTP/NTP-Statusblöcke**: PTP und NTP in getrennten, je zweispaltigen `.kv2`-Blöcken mit `<h3>`/`<hr>`-Trennung; PTP erweitert um GM-Priorität, Clock-Klasse/-Genauigkeit, Parent-Port, Time Source (dekodiert), Traceability, UTC-Offset, PTP-Timescale (via `GET TIME_PROPERTIES_DATA_SET`)
- **Stabile Status-Spaltenbreite**: Fixe 140 px für Status-Spalte im bigtime-Grid; `white-space:normal; word-break:break-word` für Zeilenumbruch ohne Layout-Verschiebung
- **NTP-Staleness-Erkennung**: Status `stale` wenn `Ref time (UTC)` älter als `--ntp-stale-threshold-s` (Standard 180 s); NTP-7-Seg graut aus; Event `NTP_STALE` (WARN); `ptp_versions` zeigt nur `v2` wenn PTP aktiv
- **NTP Update-age-Fix**: `last_update_utc` war `utc_iso_ms()` (Abfragezeitpunkt) → immer 0.0; jetzt `Ref time (UTC)` aus `chronyc tracking` geparst
- **Rolling-Counter-Bug-Fix**: `update_ptp/ntp/ltc` erzeugten Events direkt mit `appendleft()` an `add_event()` vorbei → Zähler immer 0; Fix: `_append_event_locked()` zentralisiert Append + Counter-Update
- **Reset-Button Rolling Error Summary**: `POST /api/reset-summaries` → alle Rolling-Counter und Summaries auf 0
- **LED-Pegel halbiert + inline**: LED-Grösse 10×18 → 5×9 px; `inline-flex` statt `flex` (Container schrumpft auf LED-Breite); dBFS-Text rechts neben dem Meter auf einer Linie

---

## Ebene 1: Monitor-Parameter zur Laufzeit ändern

Ziel: Ausgewählte Monitor-interne Parameter ohne Neustart des Prozesses über das Webinterface anpassen.
Kein Eingriff in `ptp4l` oder andere Systemdienste — nur der Python-Prozess selbst wird beeinflusst.

---

### Backend

- [ ] **`status_bus.py`**: Mutable-Config-Objekt einführen
  Aktuell werden alle Parameter einmalig aus `argparse` übernommen und nie verändert.
  Ein zentrales, thread-sicheres Config-Dict (mit `threading.Lock()`) anlegen, aus dem die Loops ihre Werte lesen statt aus fixen lokalen Variablen.

- [ ] **`main.py` – `ptp_loop()`**: Poll-Intervall aus Config lesen
  `time.sleep(args.poll)` → `time.sleep(cfg["poll_s"])`

- [ ] **`status_bus.py` – `snapshot()`**: Stale-Threshold aus Config lesen
  `args.stale_threshold_ms` → `cfg["stale_threshold_ms"]`

- [ ] **`status_bus.py` – Rolling-Fenster**: Fenstergrössen aus Config lesen
  `error_window_s` und `gm_window_s` beim nächsten `add_event()`-Aufruf dynamisch anwenden.

- [ ] **`sources_ltc.py`**: LTC-Parameter aus Config lesen
  `fps`, `jump_tolerance_frames`, `dropout_timeout_ms` — beim nächsten Frame-Zyklus wirksam, kein Subprocess-Neustart nötig.

- [ ] **`webapp.py`**: Neuer Endpoint `POST /api/config`
  Nimmt JSON entgegen, validiert Wertebereiche, schreibt ins Config-Dict.
  Gibt den neuen Zustand als JSON zurück.
  Beispiel-Payload:
  ```json
  {
    "poll_s": 0.5,
    "stale_threshold_ms": 3000,
    "error_window_s": 1800,
    "gm_window_s": 86400,
    "ltc_fps": 25,
    "ltc_jump_tolerance_frames": 2,
    "ltc_dropout_timeout_ms": 800
  }
  ```

- [ ] **`webapp.py`**: Neuer Endpoint `GET /api/config`
  Liefert die aktuell aktiven Werte — damit das UI den aktuellen Stand beim Laden kennt.

---

### Frontend (`web_ui.py`)

- [ ] **Einstellungs-Panel** im UI (aufklappbar oder separates Modal)
  Zeigt alle konfigurierbaren Parameter als Eingabefelder mit aktuellem Wert vor.

- [ ] **Felder im Panel**:
  - PTP Poll-Intervall (s)
  - Stale-Threshold (ms)
  - Fehler-Zeitfenster (s)
  - GM-Wechsel-Zeitfenster (s)
  - LTC Framerate (fps)
  - LTC Jump-Toleranz (Frames)
  - LTC Dropout-Timeout (ms)

- [ ] **Speichern-Button**: `POST /api/config` mit den neuen Werten, danach UI-Refresh.

- [ ] **Keine Persistenz**: Beim Neustart des Prozesses gelten wieder die CLI-Startparameter.
  (Optional später: Werte in eine lokale JSON-Datei schreiben und beim Start laden.)

---

## Ebene 2: Authentifizierung für Remote-Zugriff

Ziel: Localhost (Kiosk auf dem Pi selbst) greift ohne Login auf das Webinterface zu.
Alle anderen IP-Adressen (Remote-Geräte) benötigen eine Authentifizierung.

### Anforderungen

- Kiosk (`127.0.0.1` / `::1`) → **kein Auth** (sonst würde der Kiosk-Browser blockiert)
- Alle anderen IPs → **HTTP Basic Auth** (Benutzername + Passwort)
- Credentials sicher gespeichert (kein Klartext im Service-File)
- Konfigurierbar ohne Code-Änderung (z.B. via Umgebungsvariable oder Datei)

### Backend (`webapp.py`)

- [ ] **`before_request`-Hook** in Flask:
  Prüft `request.remote_addr`. Bei `127.0.0.1` oder `::1` → direkt weiter.
  Sonst: prüft `Authorization`-Header (HTTP Basic Auth).
  Bei fehlendem/falschem Credential → `401 Unauthorized` mit `WWW-Authenticate`-Header.

- [ ] **Credential-Verwaltung**:
  Passwort als bcrypt-Hash in einer Datei (z.B. `/etc/time-reference-monitor/htpasswd`)
  oder als Umgebungsvariable `TRM_AUTH_PASSWORD_HASH` im systemd-Service.
  Kein Klartext-Passwort im Repository oder in Service-Files.

- [ ] **Helper-Script `rpi/set-password.sh`**:
  Interaktiv: fragt nach neuem Passwort, schreibt Hash in die Config-Datei,
  startet den Dienst neu. Kein Python-Wissen vorausgesetzt.

### Kein nginx vorschalten

Bewusste Entscheidung: Auth direkt in Flask, kein zusätzlicher Reverse-Proxy.
Weniger Abhängigkeiten, einfacheres Deployment auf dem Pi.
