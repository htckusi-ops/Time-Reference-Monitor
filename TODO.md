# TODO

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
