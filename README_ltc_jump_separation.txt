Patch: Separate LTC timecode jumps from decode errors

What changes:
  - models.py: adds LTCStatus.jumps_total/jumps_rolling and Summaries.ltc_jumps_total/rolling
  - sources_ltc.py: detects discontinuities in timecode (jump_tolerance_frames default 2) and increments jumps_total
  - status_bus.py: logs LTC_JUMP events and adds rolling jump counter to summaries_rolling

Install:
  1) Replace your files:
     - models.py  <- models_patched.py
     - sources_ltc.py <- sources_ltc_patched.py
     - status_bus.py <- status_bus_patched.py
  2) Restart ptp-monitor
  3) Check UI events: you should now see LTC_JUMP when timecode skips.

Notes:
  - A "wrong first decode" cannot be classified as a jump (no baseline). From the second frame onward, jumps are detectable.
  - decode_errors_total is reserved for process/decoder failures (not time jumps).
