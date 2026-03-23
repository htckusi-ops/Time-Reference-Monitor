PTP Time Monitor – Spectrum (on-demand) + dsnoop_ltc

1) ALSA shared capture (dsnoop)
------------------------------
Create ~/.asoundrc (adapt hw:2,0 if needed):

pcm.dsnoop_ltc {
  type dsnoop
  ipc_key 1024
  ipc_perm 0666
  slave {
    pcm "hw:2,0"
    channels 1
    rate 48000
  }
}

ctl.dsnoop_ltc {
  type hw
  card 2
}

2) Run monitor (example)
-----------------------
python3 run.py --source mock --http --http-host 0.0.0.0 --http-port 8088 --poll 0.25 \
  --ui-refresh-ms 20 --ui-api-poll-ms 250 \
  --ltc --ltc-device dsnoop_ltc --ltc-fps 25 \
  --ltc-cmd "./alsaltc -d dsnoop_ltc -r 48000 -c 1 -f 25 --dropout-ms 800" \
  --ltc-dropout-timeout-ms 800 --ltc-jump-tolerance-frames 2

3) Spectrum UI
--------------
Open the main UI and click "Spectrum…".
In the Spectrum window, choose duration (5/10/20/30/60s) and click Generate.

Notes
-----
- Spectrum files are written to /dev/shm (RAM) to avoid SD-card wear.
- Capture continues while generating the spectrum (dsnoop enables parallel readers).
