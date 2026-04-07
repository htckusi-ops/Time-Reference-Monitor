# README_LTC_LEVEL — Veraltete Integrationsbeschreibung

> **Hinweis:** Diese Datei beschreibt den alten V04-Integrations-Patch, der `ltc_level.py` als separaten Patch in einen V03-Codestand einbaute.

Die LTC-Pegelanzeige ist seit V05 vollständig in den Haupt-Codestand integriert:

- **`ltc_level.py`**: ALSA-Capture (dsnoop_ltc) mit RMS/Peak-Berechnung, läuft als eigenständiger Thread
- **`web_ui.py`**: Horizontaler LED-Pegel-Meter im Dashboard, aktualisiert über `/api/ltc/level` alle 200 ms

Es sind keine separaten Patch-Dateien (`webapp_ltc_level.py`, `web_ui_ltc_level.js`) mehr nötig.
