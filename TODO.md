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
