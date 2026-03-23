V04 – LTC Level integration (minimal patch)

This bundle ONLY adds an LTC audio level meter to an otherwise working v03 codebase.
Spectrum, PTP, NTP remain unchanged.

Files:
- ltc_level.py        : ALSA capture + RMS/PEAK calculation
- webapp_ltc_level.py : Flask endpoint /api/ltc/level
- web_ui_ltc_level.js : UI additions (horizontal LED-style bar)

Integration steps are documented inline.
