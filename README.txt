
PTP Monitor V04 – LTC Level ONLY (Minimal Patch)

This archive contains ONLY the minimal additions to add an LTC audio level meter
to an otherwise working v03 codebase.

Files included:
- web_ui.py  (patched: adds LTC level bar + polling JS)
- webapp.py (patched: adds /api/ltc/level endpoint)
- ltc_level.py (new: captures short audio window and returns RMS/PEAK)

IMPORTANT:
- Start from your known-good v03 tree.
- Replace ONLY the files in this ZIP.
- Do NOT change main.py, sources_ptp.py, sources_ntp.py, spectrum.py.

If LTC is absent, the meter will show zero.
The spectrum feature is intentionally untouched.
