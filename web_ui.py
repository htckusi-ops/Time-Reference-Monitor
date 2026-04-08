from __future__ import annotations
import config


def ui_html() -> str:
    # NOTE: UI runs smooth locally but freezes if data is stale/paused/invalid.
    # It also has a fixed-height PTP box and a scrollable event list.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{config.APP_TITLE}</title>
  <style>
    :root{{
      --bg:#0b0f14; --panel:#111826; --text:#e7eefc; --muted:#9fb0c8;
      --ok:#19c37d; --warn:#f4c430; --alarm:#ff4d4f; --line:#263247;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }}
    body{{margin:0; background:var(--bg); color:var(--text); font-family:var(--sans);}}
    .wrap{{max-width:1200px; margin:0 auto; padding:18px;}}
    .hdr{{display:flex; justify-content:space-between; align-items:flex-end; gap:12px; margin-bottom:14px;}}
    .title{{font-size:22px; font-weight:700; letter-spacing:.2px;}}
    .subtitle{{color:var(--muted); font-size:13px; margin-top:4px;}}
    .pill{{font-family:var(--mono); font-size:12px; padding:6px 10px; border-radius:999px; border:1px solid var(--line); background:rgba(255,255,255,.03); color:var(--muted);}}
    .grid{{display:grid; grid-template-columns: 1.1fr .9fr; gap:12px;}}
    @media (max-width: 980px){{ .grid{{grid-template-columns:1fr;}} }}
    .card{{background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01)); border:1px solid var(--line); border-radius:16px; padding:14px; box-shadow: 0 10px 24px rgba(0,0,0,.25);}}
    .card h3{{margin:0 0 10px 0; font-size:13px; letter-spacing:.15px; color:var(--muted); font-weight:650; text-transform:uppercase;}}
    @font-face{{font-family:'Seg7';src:url('/font/Segment7Standard.otf') format('opentype');font-weight:400;font-style:normal;}}
    .bigtime{{padding:14px 16px; border-radius:14px; border:1px solid var(--line); background:rgba(0,0,0,.25); display:grid; grid-template-columns:76px 140px 1fr; align-items:center; row-gap:16px; column-gap:10px;}}
    .timeLabel{{font-size:30px; font-weight:700;}}
    .timeStatus{{font-family:var(--mono); font-size:17px; font-weight:600; white-space:normal; word-break:break-word; line-height:1.3;}}
    .timeStatus.ok{{color:var(--ok);}} .timeStatus.warn{{color:var(--warn);}} .timeStatus.alarm{{color:var(--alarm);}} .timeStatus.muted{{color:var(--muted);}}
    .seg-wrap{{font-family:'Seg7',var(--mono); font-size:48px; line-height:1; letter-spacing:0.05em; color:var(--text); white-space:nowrap;}}
    .smalltime{{font-family:var(--mono); font-size:13px; color:var(--muted); margin-top:8px;}}
    .delta-grid{{display:grid; grid-template-columns:1fr 1fr; gap:4px 20px; margin-top:8px;}}
    .row{{display:flex; gap:10px; flex-wrap:wrap; align-items:center;}}
    .kv{{display:grid; grid-template-columns: 170px 1fr; gap:6px 10px; font-size:13px;}}
    .kv-k{{color:var(--muted);}}
    .kv-v{{font-family:var(--mono);}}
    .kv2{{display:grid; grid-template-columns:1fr 1fr; gap:0 20px;}}
    .kv2 .kv{{grid-template-columns:130px 1fr;}}
    .badge{{display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:12px; border:1px solid var(--line); background:rgba(0,0,0,.2); font-family:var(--mono); font-size:12px;}}
    .dot{{width:10px; height:10px; border-radius:999px; background:var(--muted);}}
    .dot.ok{{background:var(--ok);}} .dot.warn{{background:var(--warn);}} .dot.alarm{{background:var(--alarm);}}
    .btn{{cursor:pointer; user-select:none; border:1px solid var(--line); background:rgba(255,255,255,.03); color:var(--text);
         border-radius:12px; padding:8px 10px; font-family:var(--mono); font-size:12px;}}
    .btn:hover{{background:rgba(255,255,255,.06);}}
    .btn-sys{{border-color:rgba(255,80,80,.4); color:rgba(255,130,130,.9);}}
    .btn-sys:hover{{background:rgba(255,60,60,.12);}}
    .split{{display:flex; gap:10px; align-items:center; justify-content:space-between; flex-wrap:wrap;}}
    .table{{width:100%; border-collapse:collapse; font-size:12px;}}
    .table th, .table td{{padding:8px 10px; border-bottom:1px solid rgba(38,50,71,.7); vertical-align:top;}}
    .table th{{color:var(--muted); font-weight:650; text-align:left; font-family:var(--mono); position:sticky; top:0; background:rgba(11,15,20,.92); backdrop-filter: blur(6px);}}
    .sev{{font-family:var(--mono); font-weight:700;}}
    .sev.INFO{{color:var(--muted);}} .sev.WARN{{color:var(--warn);}} .sev.ALARM{{color:var(--alarm);}}
    .foot{{margin-top:12px; color:var(--muted); font-size:12px; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;}}
    .mono{{font-family:var(--mono);}}
    .muted{{color:var(--muted);}}
    /* Nav dropdown */
    .nav-wrap{{position:relative; display:inline-block;}}
    .nav-btn{{cursor:pointer; user-select:none; border:1px solid var(--line); background:rgba(255,255,255,.03);
              color:var(--text); border-radius:12px; padding:8px 14px; font-family:var(--mono); font-size:12px;
              display:flex; align-items:center; gap:8px; white-space:nowrap;}}
    .nav-btn:hover{{background:rgba(255,255,255,.07);}}
    .nav-drop{{display:none; position:absolute; top:100%; right:0; min-width:180px;
               padding-top:8px; z-index:999;}}
    .nav-drop-inner{{background:#111826; border:1px solid var(--line); border-radius:14px;
                     box-shadow:0 12px 32px rgba(0,0,0,.45); padding:6px;}}
    .nav-wrap:hover .nav-drop{{display:block;}}
    .nav-item{{display:block; width:100%; text-align:left; padding:9px 14px; border-radius:10px;
               font-family:var(--mono); font-size:12px; color:var(--text); text-decoration:none;
               background:none; border:none; cursor:pointer; box-sizing:border-box;}}
    .nav-item:hover{{background:rgba(255,255,255,.07); color:var(--text);}}
    .nav-item.danger{{color:rgba(255,130,130,.9);}}
    .nav-item.danger:hover{{background:rgba(255,60,60,.12);}}
    .nav-sep{{height:1px; background:var(--line); margin:4px 0;}}
    .hr{{height:1px; background:rgba(38,50,71,.7); margin:12px 0;}}
    .evtBox{{max-height: 440px; overflow:auto; border:1px solid rgba(38,50,71,.65); border-radius:12px;}}
    .ledWrap{{display:flex; align-items:center; gap:8px; margin:6px 0 8px 0;}}
    .ledMeter{{display:inline-flex; gap:2px; align-items:flex-end; padding:5px 6px; border-radius:8px; border:1px solid rgba(38,50,71,.65); background:rgba(0,0,0,.22);}}
    .led{{width:5px; height:9px; border-radius:2px; box-shadow:inset 0 0 0 1px rgba(0,0,0,.35); opacity:.18; filter:saturate(1.2);}}
    .led.g{{background:var(--ok);}} .led.o{{background:var(--warn);}} .led.r{{background:var(--alarm);}}
    .led.peak{{opacity:.55; box-shadow:inset 0 0 0 1px rgba(0,0,0,.25), 0 0 6px rgba(255,255,255,.06);}}
    .led.rms{{opacity:1; box-shadow:inset 0 0 0 1px rgba(0,0,0,.15), 0 0 10px rgba(255,255,255,.10);}}
    .ledText{{font-size:12px; color:var(--muted); font-family:var(--mono); white-space:nowrap;}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div>
      <div class="title">{config.APP_TITLE}</div>
      <div class="subtitle">{config.APP_SUBTITLE}</div>
    </div>
    <div class="row">
      <div class="pill" id="pillMeta">—</div>
      <div class="badge"><span class="dot" id="dotState"></span><span id="txtState">—</span></div>
      <div class="nav-wrap">
        <div class="nav-btn">&#9776; Menu</div>
        <div class="nav-drop">
          <div class="nav-drop-inner">
            <button class="nav-item" id="btnReload">&#8635; Reload</button>
            <a class="nav-item" href="/ltc-clock" target="_blank" rel="noopener">&#9654; Screen Clock…</a>
            <a class="nav-item" id="btnLtcSpectrum" href="/spectrum" target="_blank" rel="noopener">&#126;&#126; LTC Spectrum…</a>
            <a class="nav-item" href="/tcpdump" target="_blank" rel="noopener">&#128268; PTP Capture…</a>
            <a class="nav-item" href="/settings">&#9881; Settings</a>
            <div class="nav-sep"></div>
            <button class="nav-item danger" id="btnReboot">&#9210; Reboot</button>
            <button class="nav-item danger" id="btnShutdown">&#9209; Shutdown</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Reference Time</h3>

      <div class="bigtime" id="ptpBox">
        <div class="timeLabel">PTP</div>
        <div class="timeStatus alarm" id="ptpStatusBadge">NO PTP SYNC</div>
        <div class="seg-wrap" id="ptpTimeSegs" style="opacity:0.18">00:00:00.00</div>

        <div class="timeLabel">NTP</div>
        <div class="timeStatus muted" id="ntpStatusBadge">—</div>
        <div class="seg-wrap" id="ntpTimeSegs" style="opacity:0.18">00:00:00.00</div>

        <div class="timeLabel">LTC</div>
        <div class="timeStatus muted" id="ltcStatusBadge">—</div>
        <div class="seg-wrap" id="ltcTimeSegs" style="opacity:0.18">00:00:00.00</div>
      </div>

<div id="ltcDevice" data-device="{config.LTC_ALSA_DEVICE}"></div>
      <div class="delta-grid">
        <div class="smalltime" id="ntpDateLine">NTP Date: —</div>
        <div class="smalltime" id="ptpDateLine">PTP Date: —</div>

        <div class="smalltime" id="ntpTzLine">NTP TZ: —</div>
        <div class="smalltime" id="ltcTzLine">System TZ (PTP): —</div>

        <div class="smalltime" id="deltaLine">Δ(NTP-PTP): —</div>
        <div class="smalltime" id="deltaLtcNtpLine">Δ(LTC-NTP): —</div>

        <div class="smalltime" id="deltaLtcAdjLine">Δ(LTC-PTP) adj: —</div>
        <div class="smalltime" id="deltaLtcRawLine">Δ(LTC-PTP) raw: —</div>
      </div>
      <div class="smalltime">
      LTC Audio Level ({config.LTC_ALSA_DEVICE})
        </div>
        <div class="ledWrap">
          <div id="ltcLedMeter" class="ledMeter"></div>
          <div id="ltcLevelText" class="ledText">—</div>
        </div>
      <div class="hr"></div>
      <h3 style="margin-bottom:8px;">PTP</h3>
      <div class="kv2">
        <!-- Left: connection & timing -->
        <div class="kv">
          <div class="kv-k">State</div><div class="kv-v" id="stateLine">—</div>
          <div class="kv-k">Port state</div><div class="kv-v" id="portStateLine">—</div>
          <div class="kv-k">PTP valid</div><div class="kv-v" id="ptpValidLine">—</div>
          <div class="kv-k">GM present</div><div class="kv-v" id="gmPresentLine">—</div>
          <div class="kv-k">Interface</div><div class="kv-v" id="ifaceLine">—</div>
          <div class="kv-k">Domain</div><div class="kv-v" id="domainLine">—</div>
          <div class="kv-k">PTP version</div><div class="kv-v" id="ptpVerLine">—</div>
          <div class="kv-k">Offset (ns)</div><div class="kv-v" id="offLine">—</div>
          <div class="kv-k">Path delay (ns)</div><div class="kv-v" id="delayLine">—</div>
          <div class="kv-k">Poll age (ms)</div><div class="kv-v" id="ageLine">—</div>
          <div class="kv-k">GM changes</div><div class="kv-v" id="gmChgLine">—</div>
          <div class="kv-k">NO PTP since</div><div class="kv-v" id="noPtpLine">—</div>
        </div>
        <!-- Right: GM / source info -->
        <div class="kv">
          <div class="kv-k">Source</div><div class="kv-v" id="sourceLine">—</div>
          <div class="kv-k">Time source</div><div class="kv-v" id="timeSourceLine">—</div>
          <div class="kv-k">UTC offset</div><div class="kv-v" id="utcOffsetLine">—</div>
          <div class="kv-k">Time traceable</div><div class="kv-v" id="timeTraceLine">—</div>
          <div class="kv-k">Freq traceable</div><div class="kv-v" id="freqTraceLine">—</div>
          <div class="kv-k">PTP timescale</div><div class="kv-v" id="ptpTimescaleLine">—</div>
          <div class="kv-k">GM identity</div><div class="kv-v" id="gmLine">—</div>
          <div class="kv-k">Parent port</div><div class="kv-v" id="parentPortLine">—</div>
          <div class="kv-k">GM priority1</div><div class="kv-v" id="gmPrio1Line">—</div>
          <div class="kv-k">GM priority2</div><div class="kv-v" id="gmPrio2Line">—</div>
          <div class="kv-k">GM clock class</div><div class="kv-v" id="gmClockClassLine">—</div>
          <div class="kv-k">GM clock acc.</div><div class="kv-v" id="gmClockAccLine">—</div>
        </div>
      </div>

      <div class="hr"></div>
      <h3 style="margin-bottom:8px;">NTP</h3>
      <div class="kv2">
        <!-- Left: sync state -->
        <div class="kv">
          <div class="kv-k">Status</div><div class="kv-v" id="ntpStatusLine">—</div>
          <div class="kv-k">Stratum</div><div class="kv-v" id="ntpStratumLine">—</div>
          <div class="kv-k">Reference</div><div class="kv-v" id="ntpRefLine">—</div>
          <div class="kv-k">Last update</div><div class="kv-v" id="ntpLastUpdateLine">—</div>
          <div class="kv-k">Update age</div><div class="kv-v" id="ntpAgeLine">—</div>
        </div>
        <!-- Right: quality metrics -->
        <div class="kv">
          <div class="kv-k">System offset</div><div class="kv-v" id="ntpSysOffLine">—</div>
          <div class="kv-k">RMS offset</div><div class="kv-v" id="ntpRmsOffLine">—</div>
          <div class="kv-k">Frequency</div><div class="kv-v" id="ntpFreqLine">—</div>
        </div>
      </div>

      <div class="hr"></div>
      <h3 style="margin-bottom:8px;">LTC</h3>
      <div class="kv2">
        <div class="kv">
          <div class="kv-k">Timecode</div><div class="kv-v" id="ltcTcLine">—</div>
          <div class="kv-k">Frame rate</div><div class="kv-v" id="ltcFpsLine">—</div>
          <div class="kv-k">ALSA delay</div><div class="kv-v" id="ltcAlsaLine">—</div>
          <div class="kv-k">Update age</div><div class="kv-v" id="ltcAgeLine">—</div>
        </div>
        <div class="kv">
          <div class="kv-k">User bits</div><div class="kv-v" id="ltcUbLine">—</div>
          <div class="kv-k">LTC date</div><div class="kv-v" id="ltcDateLine">—</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="split">
        <h3>Rolling Error Summary</h3>
        <div class="row">
          <span class="badge"><span class="dot" id="dotErr"></span><span class="mono" id="errSummary">—</span></span>
          <button class="btn" id="btnResetSummaries">Reset</button>
        </div>
      </div>

      <div class="kv2" style="margin-top:8px;">
        <div class="kv">
          <div class="kv-k">Alarms</div><div class="kv-v" id="alarmRoll">—</div>
          <div class="kv-k">Warnings</div><div class="kv-v" id="warnRoll">—</div>
          <div class="kv-k">Errors</div><div class="kv-v" id="errRoll">—</div>
          <div class="kv-k">PTP losses</div><div class="kv-v" id="ptpLossRoll">—</div>
        </div>
        <div class="kv">
          <div class="kv-k">NTP flaps</div><div class="kv-v" id="ntpFlapRoll">—</div>
          <div class="kv-k">LTC losses</div><div class="kv-v" id="ltcLossRoll">—</div>
          <div class="kv-k">LTC decode errs</div><div class="kv-v" id="ltcDecRoll">—</div>
          <div class="kv-k">GM changes</div><div class="kv-v" id="gmChgRoll">—</div>
        </div>
      </div>

      <div class="hr"></div>

      <h3 style="margin-bottom:6px;">Event list (latest first)</h3>
      <div class="muted" style="font-size:12px; margin-bottom:8px;">
        Shows recent INFO/WARN/ALARM events.
      </div>

      <div class="evtBox">
        <table class="table" id="evtTable">
          <thead>
            <tr><th style="width:165px;">UTC</th><th style="width:80px;">SEV</th><th style="width:130px;">TYPE</th><th>MESSAGE</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="foot">
    <div>{config.FOOTER_TEXT}</div>
    <div class="mono" id="footMeta">—</div>
  </div>
</div>

<script>
(() => {{
  // rendering bases (freeze if stale/paused/no-data)
  let lastApi = null;

  // PTP and NTP time display: interpolated from the RPi server timestamp (meta.ts_utc).
  // This ensures both displays freeze when the RPi goes offline, and reflect RPi time
  // (not the browser's local clock) when accessed from a remote computer.
  let srvBaseMs  = null;   // RPi UTC ms at last API receipt
  let srvLocalMs = null;   // browser Date.now() when API was received (monotonic guard)
  let lastApiMs  = null;   // browser Date.now() on every successful API response
  let ptpCanTick = false;

  // EMA smoothing for rapidly-changing display values (α=0.05 ≈ 20-sample window)
  const EMA_A = 0.05;
  function _ema(prev, v) {{ return prev == null ? v : EMA_A * v + (1 - EMA_A) * prev; }}
  let _emaPtpOffNs    = null;
  let _emaPtpDelayNs  = null;
  let _emaDeltaNtpPtp = null;
  let _emaDeltaLtcNtp = null;
  let _emaDeltaLtcAdj = null;
  let _emaDeltaLtcRaw = null;

  // Very light EMA on 7-seg display timestamps to damp second-boundary flicker.
  // α=0.25 at 20 ms refresh → time constant ≈ 60 ms; visually imperceptible lag.
  let _smPtpMs = null;
  let _smNtpMs = null;

  const els = (id) => document.getElementById(id);

  // --- LED meter setup ---
  const LEDS = 30;
  const DB_MIN = -60.0;   // bottom of scale
  const DB_TOP = 0.0;     // 0 dBFS
  const ORANGE_AT = -18.0;
  const RED_AT = -6.0;

  let peakHoldIdx = 0;
  let peakHoldUntil = 0;
  const PEAK_HOLD_MS = 800;
  const PEAK_FALL_PER_TICK = 1; // LED steps per UI tick (after hold)

function dbToLedCountFloor(db){{
  if(!isFinite(db)) return 0;
  const clamped = Math.max(DB_MIN, Math.min(DB_TOP, db));
  const norm = (clamped - DB_MIN) / (DB_TOP - DB_MIN); // 0..1
  return Math.max(0, Math.min(LEDS, Math.floor(norm * LEDS + 1e-9)));
  }}
function dbToLedCountCeil(db){{
  if(!isFinite(db)) return 0;
  const clamped = Math.max(DB_MIN, Math.min(DB_TOP, db));
  const norm = (clamped - DB_MIN) / (DB_TOP - DB_MIN);
  return Math.max(0, Math.min(LEDS, Math.ceil(norm * LEDS - 1e-9)));
}}
  function ledColorForIndex(i){{
    // i: 1..LEDS mapped to dB
    const db = DB_MIN + (i / LEDS) * (DB_TOP - DB_MIN);
    if(db >= RED_AT) return 'r';
    if(db >= ORANGE_AT) return 'o';
    return 'g';
  }}

  function initLedMeter(){{
    const m = els('ltcLedMeter');
    if(!m) return;
    m.innerHTML = '';
    for(let i=1;i<=LEDS;i++){{
      const d = document.createElement('div');
      d.className = 'led ' + ledColorForIndex(i);
      d.dataset.idx = String(i);
      m.appendChild(d);
    }}
  }}

function renderLedMeter(ledPeak){{
  const m = els('ltcLedMeter');
  if(!m) return;
  const segs = Array.from(m.querySelectorAll('.led'));
  segs.forEach((el, i) => {{
    el.classList.remove('rms', 'peak');
    if(i + 1 <= ledPeak) el.classList.add('peak');
  }});
}}


  function pad2(n) {{ return String(n).padStart(2,'0'); }}

  function renderSevenSeg(el, timeStr) {{
    if(!el) return;
    // Use '00:00:00.00' as placeholder (not '--:--:--.--') so that the Seg7 font
    // renders the same-width digit glyphs in both active and inactive states.
    // The '-' glyph is narrower than digits in Seg7, causing the grid column to
    // resize when the display switches between placeholder and live time.
    el.textContent = timeStr || '00:00:00.00';
    el.style.opacity = timeStr ? '' : '0.18';
  }}

  function setDot(dotEl, state){{
    dotEl.classList.remove('ok','warn','alarm');
    if(state==='OK') dotEl.classList.add('ok');
    else if(state==='WARN') dotEl.classList.add('warn');
    else if(state==='ALARM') dotEl.classList.add('alarm');
  }}

  function parseTcToTodMs(tc, fps){{ 
    if(!tc || typeof tc !== 'string') return null;
    const m = tc.match(/^(\d{{2}}):(\d{{2}}):(\d{{2}}):(\d{{2}})$/);
    if(!m) return null;
    const hh = parseInt(m[1],10), mm = parseInt(m[2],10), ss = parseInt(m[3],10), ff = parseInt(m[4],10);
    const fpsN = Math.max(1, parseInt(fps || '25', 10) || 25);
    const ms = Math.round((ff / fpsN) * 1000.0);
    return (hh*3600 + mm*60 + ss)*1000 + ms;
  }}
  function todMsFromLocalDate(d){{ 
    return (d.getHours()*3600 + d.getMinutes()*60 + d.getSeconds())*1000 + d.getMilliseconds();
  }}
  function todMsFromUtcDate(d){{ 
    return (d.getUTCHours()*3600 + d.getUTCMinutes()*60 + d.getUTCSeconds())*1000 + d.getUTCMilliseconds();
  }}
  function wrapDeltaMs(ms){{ 
    const day = 24*3600*1000;
    ms = ((ms % day) + day) % day;
    if(ms >= day/2) ms -= day;
    return ms;
  }}
  function fmtIso(iso, decimals){{
    if(!iso) return '—';
    // iso like: 2026-02-12T08:19:17.512Z
    // Output: 08:19:17.512 (or with fewer decimals)
    const m = String(iso).match(/T(\d{2}:\d{2}:\d{2})(\.(\d+))?Z?$/);
    if(!m) return iso;
    const base = m[1];
    const frac = (m[3] || '').padEnd(6,'0'); // up to microseconds if present
    const d = (decimals == null) ? 3 : Math.max(0, Math.min(6, Number(decimals)));
    return d === 0 ? base : (base + '.' + frac.slice(0,d));
  }}

  function calcState(meta, st, ntp, ltc){{
    if(meta.startup_active) return 'STARTING';
    if(meta.paused) return 'PAUSED';

    const staleTh = meta.stale_threshold_ms ?? 2000;
    const age = st.poll_age_ms ?? 999999;

    // hard alarms: no valid ptp or stale
    if(!st.ptp_valid) return 'ALARM';
    if(age > staleTh) return 'ALARM';

    // warnings: ntp not synced, ltc absent (if enabled), ltc decode errors rolling > 0
    if((ntp.status || 'unknown') !== 'synced') return 'WARN';
    if(ltc.enabled && !ltc.present) return 'WARN';
    const roll = meta.summaries_rolling || {{}};
    if((roll.ltc_decode_errors_rolling ?? 0) > 0) return 'WARN';

    return 'OK';
  }}

  function updateEvents(events){{
    const tb = els('evtTable').querySelector('tbody');
    tb.innerHTML = '';
    let shown = 0;
    for(const ev of (events||[])){{
      const tr = document.createElement('tr');
      const td1 = document.createElement('td'); td1.textContent = ev.ts_utc || '—';
      const td2 = document.createElement('td'); td2.textContent = ev.severity || '—'; 
      td2.className = 'sev ' + (ev.severity || 'INFO');
      const td3 = document.createElement('td'); td3.textContent = ev.type || '—'; td3.className = 'mono';
      const td4 = document.createElement('td'); 
      td4.textContent = (ev.suppressed ? '[startup] ' : '') + (ev.message || '');
      tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3); tr.appendChild(td4);
      tb.appendChild(tr);
      shown++;
      if(shown >= {config.EVENTS_UI_MAX}) break;
    }}
  }}

  function applyApi(data){{
    lastApi = data;
    lastApiMs = Date.now();
    const meta = data.meta || {{}};
    const st = data.status || {{}};
    const ntp = data.ntp || {{}};
    const ltc = data.ltc || {{}};
    const roll = meta.summaries_rolling || {{}};
    const tot = meta.summaries || {{}};

    els('pillMeta').textContent = `${{meta.source || '—'}} | ${{meta.iface || '—'}} | domain=${{meta.domain ?? '—'}} | poll=${{meta.poll_s ?? '—'}}s`;
    els('footMeta').textContent = `API: ${{meta.ts_utc || '—'}}`;

    // Source: "mock", "real / local (MASTER)", "real / remote (SLAVE)", "real"
    (function() {{
      const src = meta.source || '';
      if (src === 'mock') {{ els('sourceLine').textContent = 'mock'; return; }}
      if (src === 'real') {{
        const ps = (st.port_state || '').toUpperCase();
        if (ps === 'MASTER') {{ els('sourceLine').textContent = 'real / local (MASTER)'; }}
        else if (ps === 'SLAVE' || ps === 'UNCALIBRATED') {{ els('sourceLine').textContent = 'real / remote (' + ps + ')'; }}
        else if (ps && ps !== 'UNKNOWN') {{ els('sourceLine').textContent = 'real / ' + ps.toLowerCase(); }}
        else {{ els('sourceLine').textContent = 'real'; }}
        return;
      }}
      els('sourceLine').textContent = src || '—';
    }})();
    els('ifaceLine').textContent = meta.iface || '—';
    els('domainLine').textContent = String(meta.domain ?? '—');

    const state = calcState(meta, st, ntp, ltc);
    els('txtState').textContent = state;
    els('stateLine').textContent = state;
    setDot(els('dotState'), (state==='STARTING'||state==='PAUSED') ? 'WARN' : state);

    els('ptpValidLine').textContent = String(!!st.ptp_valid);
    els('gmPresentLine').textContent = String(!!st.gm_present);
    els('portStateLine').textContent = st.port_state || '—';
    els('ptpVerLine').textContent = st.ptp_versions || '—';
    _emaPtpOffNs   = (st.offset_ns           != null) ? _ema(_emaPtpOffNs,   st.offset_ns)           : null;
    _emaPtpDelayNs = (st.mean_path_delay_ns  != null) ? _ema(_emaPtpDelayNs, st.mean_path_delay_ns)  : null;
    els('offLine').textContent   = (_emaPtpOffNs   != null) ? _emaPtpOffNs.toFixed(0)   + ' ns' : '—';
    els('delayLine').textContent = (_emaPtpDelayNs != null) ? _emaPtpDelayNs.toFixed(0) + ' ns' : '—';
    els('ageLine').textContent = (st.poll_age_ms != null) ? String(st.poll_age_ms) : '—';
    els('noPtpLine').textContent = st.no_ptp_since_utc || '—';
    els('gmChgLine').textContent = String(roll.gm_changes_rolling ?? '—');
    // GM / source info
    els('gmLine').textContent = st.gm_identity || '—';
    els('parentPortLine').textContent = st.parent_port_identity || '—';
    els('gmPrio1Line').textContent = (st.gm_priority1 != null) ? String(st.gm_priority1) : '—';
    els('gmPrio2Line').textContent = (st.gm_priority2 != null) ? String(st.gm_priority2) : '—';
    els('gmClockClassLine').textContent = (st.gm_clock_class != null) ? String(st.gm_clock_class) : '—';
    els('gmClockAccLine').textContent = st.gm_clock_accuracy || '—';
    els('timeSourceLine').textContent = st.time_source || '—';
    els('utcOffsetLine').textContent = (st.utc_offset != null) ? `${{st.utc_offset}}s` : '—';
    els('timeTraceLine').textContent = (st.time_traceable != null) ? (st.time_traceable ? 'yes' : 'no') : '—';
    els('freqTraceLine').textContent = (st.frequency_traceable != null) ? (st.frequency_traceable ? 'yes' : 'no') : '—';
    els('ptpTimescaleLine').textContent = (st.ptp_timescale != null) ? (st.ptp_timescale ? 'PTP' : 'ARB') : '—';

    // NTP detail rows
    els('ntpStatusLine').textContent  = ntp.status || '—';
    els('ntpStratumLine').textContent = (ntp.stratum != null) ? String(ntp.stratum) : '—';
    els('ntpRefLine').textContent     = ntp.ref || '—';
    els('ntpLastUpdateLine').textContent = ntp.last_update_utc || '—';
    els('ntpAgeLine').textContent     = (ntp.last_update_age_s != null) ? ntp.last_update_age_s.toFixed(1)+' s' : '—';
    els('ntpSysOffLine').textContent  = (ntp.system_offset_s != null) ? (ntp.system_offset_s*1000).toFixed(3)+' ms' : '—';
    els('ntpRmsOffLine').textContent  = (ntp.rms_offset_s != null) ? (ntp.rms_offset_s*1000).toFixed(3)+' ms' : '—';
    els('ntpFreqLine').textContent    = (ntp.frequency_ppm != null) ? ntp.frequency_ppm.toFixed(3)+' ppm' : '—';

    // NTP status badge
    const ntpStat = els('ntpStatusBadge');
    const ns = ntp.status || 'unknown';
    if(ns === 'synced') {{ ntpStat.className = 'timeStatus ok'; ntpStat.textContent = 'synced'; }}
    else if(ns === 'unknown') {{ ntpStat.className = 'timeStatus muted'; ntpStat.textContent = 'no data'; }}
    else if(ns === 'unsynced') {{ ntpStat.className = 'timeStatus alarm'; ntpStat.textContent = 'unsynced'; }}
    else if(ns === 'stale') {{
      const ageStr = (ntp.last_update_age_s != null) ? ' ' + Math.round(ntp.last_update_age_s) + 's' : '';
      ntpStat.className = 'timeStatus warn'; ntpStat.textContent = 'stale' + ageStr;
    }}
    else {{ ntpStat.className = 'timeStatus warn'; ntpStat.textContent = ns; }}

    const pres = (ltc.enabled && ltc.present) ? 'present' : (ltc.enabled ? 'absent' : 'disabled');
    const tc = ltc.timecode || '—';
    const fps = ltc.fps || '—';
    const age = (ltc.last_update_age_s != null) ? (Math.round(ltc.last_update_age_s*10)/10)+'s' : '—';

    // LTC status badge
    const ltcStat = els('ltcStatusBadge');
    if(!ltc.enabled) {{ ltcStat.className = 'timeStatus muted'; ltcStat.textContent = 'disabled'; }}
    else if(ltc.present) {{ ltcStat.className = 'timeStatus ok'; ltcStat.textContent = 'present' + (ltc.fps ? ' '+ltc.fps+'fps' : ''); }}
    else {{ ltcStat.className = 'timeStatus warn'; ltcStat.textContent = 'absent'; }}

    // LTC status section
    els('ltcTcLine').textContent    = tc;
    els('ltcFpsLine').textContent   = fps;
    els('ltcAlsaLine').textContent  = (ltc.alsa_delay_ms != null) ? ltc.alsa_delay_ms.toFixed(1) + ' ms' : '—';
    els('ltcAgeLine').textContent   = age;
    els('ltcUbLine').textContent    = ltc.user_bits  || '—';
    els('ltcDateLine').textContent  = ltc.ltc_date   || '—';

    // LTC 7-segment time (convert HH:MM:SS:FF → HH:MM:SS.CC)
    if(ltc.enabled && ltc.present && tc && tc !== '—') {{
      const tcm = tc.match(/^(\d{{2}}):(\d{{2}}):(\d{{2}}):(\d{{2}})$/);
      if(tcm) {{
        const fpsN = Number(ltc.fps) || 25;
        const cs = Math.min(99, Math.round(Number(tcm[4]) / fpsN * 100));
        renderSevenSeg(els('ltcTimeSegs'), tcm[1]+':'+tcm[2]+':'+tcm[3]+'.'+pad2(cs));
      }} else {{ renderSevenSeg(els('ltcTimeSegs'), null); }}
    }} else {{ renderSevenSeg(els('ltcTimeSegs'), null); }}

    // rolling summary
    const eR = Number(roll.errors_rolling ?? 0);
    const wR = Number(roll.warnings_rolling ?? 0);
    const aR = Number(roll.alarms_rolling ?? 0);
    els('errSummary').textContent = `roll err=${{eR}} warn=${{wR}} alarm=${{aR}}`;
    setDot(els('dotErr'), (aR>0)?'ALARM':(wR>0||eR>0)?'WARN':'OK');

    els('alarmRoll').textContent = String(roll.alarms_rolling ?? '—');
    els('warnRoll').textContent = String(roll.warnings_rolling ?? '—');
    els('errRoll').textContent = String(roll.errors_rolling ?? '—');
    els('ptpLossRoll').textContent = String(roll.ptp_loss_rolling ?? '—');
    els('ntpFlapRoll').textContent = String(roll.ntp_flaps_rolling ?? '—');
    els('ltcLossRoll').textContent = String(roll.ltc_loss_rolling ?? '—');
    els('ltcDecRoll').textContent = String(roll.ltc_decode_errors_rolling ?? '—');
    els('gmChgRoll').textContent = String(roll.gm_changes_rolling ?? '—');

    // Decide if PTP should tick: only if valid AND not stale AND not paused
    const staleTh = meta.stale_threshold_ms ?? 2000;
    const ageMs = st.poll_age_ms ?? 999999;
    const canTick = (!!st.ptp_valid) && (ageMs <= staleTh) && (!meta.paused);

    // PTP status badge
    const ptpStat = els('ptpStatusBadge');
    if(meta.paused) {{ ptpStat.className = 'timeStatus warn'; ptpStat.textContent = 'PAUSED'; }}
    else if(!st.ptp_valid) {{ ptpStat.className = 'timeStatus alarm'; ptpStat.textContent = 'NO PTP SYNC'; }}
    else if(ageMs > staleTh) {{ ptpStat.className = 'timeStatus alarm'; ptpStat.textContent = 'STALE DATA'; }}
    else {{ ptpStat.className = 'timeStatus ok'; ptpStat.textContent = 'SYNC OK'; }}

    // PTP date
    els('ptpDateLine').textContent = (st.ptp_valid && st.ptp_time_utc_iso)
      ? 'PTP Date: ' + st.ptp_time_utc_iso.slice(0,10)
      : 'PTP Date: —';

    ptpCanTick = canTick;

    // Store server timestamp for NTP/PTP time interpolation.
    // Monotonic: only advance the base if the new server time is >= the already-interpolated
    // value. This prevents a backward flicker when an API response arrives with a timestamp
    // slightly behind the live interpolation (due to network latency).
    if (meta.ts_utc) {{
      const newBase = new Date(meta.ts_utc).getTime();
      const newNow  = Date.now();
      const curInterp = (srvBaseMs != null && srvLocalMs != null)
          ? srvBaseMs + (newNow - srvLocalMs)
          : null;
      if (curInterp === null || newBase >= curInterp) {{
        srvBaseMs  = newBase;
        srvLocalMs = newNow;
      }}
    }}

    updateEvents(data.events || []);
  }}

  async function pollApi(){{
    try{{
      const r = await fetch('/api/status', {{cache:'no-store'}});
      if(!r.ok) throw new Error('http '+r.status);
      const data = await r.json();
      applyApi(data);
    }}catch(e){{}}
  }}

  function uiTick(){{
    // RPi system clock interpolated from last API response.
    // If the backend has been unreachable longer than the stale threshold,
    // treat srvNow as null so all time displays grey out (not just PTP badge).
    const staleTh = (lastApi?.meta?.stale_threshold_ms ?? 2000);
    const apiAgeMs = lastApiMs != null ? (Date.now() - lastApiMs) : Infinity;
    const srvNow = (srvBaseMs != null && srvLocalMs != null && apiAgeMs <= staleTh + 1000)
      ? new Date(srvBaseMs + (Date.now() - srvLocalMs))
      : null;

    const ntp = lastApi ? (lastApi.ntp || {{}}) : {{}};
    const meta = lastApi ? (lastApi.meta || {{}}) : {{}};
    const st   = lastApi ? (lastApi.status || {{}}) : {{}};

    // ── NTP time ─────────────────────────────────────────────────────────────
    // NTP_time = system_clock + chrony system_offset_s
    // system_offset_s > 0: system is slow (NTP is ahead); < 0: system is fast.
    // Grey out display when NTP is stale or unsynced.
    const ntpLive = (ntp.status === 'synced');
    const ntpOffsetMs = (srvNow && ntpLive && ntp.system_offset_s != null) ? ntp.system_offset_s * 1000 : 0;
    const ntpNow = (srvNow && ntpLive) ? new Date(srvNow.getTime() + ntpOffsetMs) : null;

    if(ntpNow) {{
      _smNtpMs = _smNtpMs == null ? ntpNow.getTime() : 0.25 * ntpNow.getTime() + 0.75 * _smNtpMs;
      const dispNtp = new Date(_smNtpMs);
      const nh = dispNtp.getUTCHours(), nm = dispNtp.getUTCMinutes(), ns2 = dispNtp.getUTCSeconds();
      const ncs = Math.floor(dispNtp.getUTCMilliseconds() / 10);
      renderSevenSeg(els('ntpTimeSegs'), pad2(nh)+':'+pad2(nm)+':'+pad2(ns2)+'.'+pad2(ncs));
      els('ntpDateLine').textContent = 'NTP Date: ' + ntpNow.toISOString().slice(0,10);
      // TZ offset from RPi server (meta.tz_offset_s); falls back to browser TZ if unavailable
      const srvTzOffS = meta.tz_offset_s != null ? meta.tz_offset_s : null;
      const tzOffMin = srvTzOffS != null ? Math.round(srvTzOffS / 60) : -srvNow.getTimezoneOffset();
      const tzH = Math.floor(Math.abs(tzOffMin)/60), tzM = Math.abs(tzOffMin)%60;
      els('ntpTzLine').textContent = 'NTP TZ: UTC' + (tzOffMin>=0?'+':'-') + pad2(tzH)+':'+pad2(tzM);
    }} else {{
      _smNtpMs = null;
      renderSevenSeg(els('ntpTimeSegs'), null);
      els('ntpDateLine').textContent = 'NTP Date: —';
      els('ntpTzLine').textContent = 'NTP TZ: —';
    }}

    const ltc = lastApi ? (lastApi.ltc || {{}}) : {{}};
    const alsaDelayMs = (ltc.alsa_delay_ms != null) ? Number(ltc.alsa_delay_ms) : 0;

    // Δ(LTC-NTP): LTC corrected for ALSA delay vs pure NTP time
    if(ntpNow && ltc.enabled && ltc.present && ltc.timecode) {{
      const fps = ltc.fps || meta.ltc_fps || 25;
      const ltcTod = parseTcToTodMs(ltc.timecode, fps);
      if(ltcTod != null) {{
        const ltcCorr = ltcTod - alsaDelayMs;
        const ntpTod = todMsFromUtcDate(ntpNow);
        _emaDeltaLtcNtp = _ema(_emaDeltaLtcNtp, wrapDeltaMs(ltcCorr - ntpTod));
        els('deltaLtcNtpLine').textContent = 'Δ(LTC-NTP): ' + _emaDeltaLtcNtp.toFixed(3) + ' ms';
      }} else {{
        _emaDeltaLtcNtp = null;
        els('deltaLtcNtpLine').textContent = 'Δ(LTC-NTP): —';
      }}
    }} else {{
      _emaDeltaLtcNtp = null;
      els('deltaLtcNtpLine').textContent = 'Δ(LTC-NTP): —';
    }}

    if(!lastApi) {{
      renderSevenSeg(els('ptpTimeSegs'), null);
      els('ptpDateLine').textContent = 'PTP Date: —';
      els('deltaLine').textContent = 'Δ(NTP-PTP): —';
      els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
      els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
      els('ltcTzLine').textContent = 'System TZ (PTP): —';
      return;
    }}

    // ── PTP time ─────────────────────────────────────────────────────────────
    // PTP_time = system_clock - offsetFromMaster  (ptp4l: slave - master)
    // ptp_time_utc_iso is already corrected in sources_ptp.py; ptpDeltaMs picks
    // up that correction relative to meta.ts_utc (≈ system clock at snapshot time).
    const ptpDeltaMs = (st.ptp_time_utc_iso && meta.ts_utc)
      ? new Date(st.ptp_time_utc_iso).getTime() - new Date(meta.ts_utc).getTime()
      : 0;
    const ptpNow = srvNow ? new Date(srvNow.getTime() + ptpDeltaMs) : null;

    els('ptpDateLine').textContent = (st.ptp_valid && st.ptp_time_utc_iso)
      ? 'PTP Date: ' + st.ptp_time_utc_iso.slice(0,10)
      : 'PTP Date: —';

    if(ptpCanTick && ptpNow) {{
      _smPtpMs = _smPtpMs == null ? ptpNow.getTime() : 0.25 * ptpNow.getTime() + 0.75 * _smPtpMs;
      const dispPtp = new Date(_smPtpMs);
      const ph = dispPtp.getUTCHours(), pm = dispPtp.getUTCMinutes(), ps = dispPtp.getUTCSeconds();
      const pcs = Math.floor(dispPtp.getUTCMilliseconds() / 10);
      renderSevenSeg(els('ptpTimeSegs'), pad2(ph)+':'+pad2(pm)+':'+pad2(ps)+'.'+pad2(pcs));

      // Δ(NTP-PTP) = NTP_time - PTP_time
      // When chrony system_offset_s is available: Δ = ntpOffsetMs - ptpDeltaMs
      // (= sys_offset_s + offset_ns/1e6 in ms).
      // Fallback: offset_ns/1e6 from ptp4l alone (= Δ(system - PTP_master)).
      const offNs = st.offset_ns;
      if(ntp.system_offset_s != null && offNs != null) {{
        _emaDeltaNtpPtp = _ema(_emaDeltaNtpPtp, ntpOffsetMs - ptpDeltaMs);
      }} else if(offNs != null) {{
        _emaDeltaNtpPtp = _ema(_emaDeltaNtpPtp, offNs / 1e6);
      }} else {{
        _emaDeltaNtpPtp = null;
      }}
      els('deltaLine').textContent = _emaDeltaNtpPtp != null
        ? 'Δ(NTP-PTP): ' + _emaDeltaNtpPtp.toFixed(3) + ' ms' : 'Δ(NTP-PTP): —';

      if(ltc.enabled && ltc.present && ltc.timecode) {{
        const fps = ltc.fps || meta.ltc_fps || 25;
        const ltcTod = parseTcToTodMs(ltc.timecode, fps);
        const ptpTodUtc = todMsFromUtcDate(ptpNow);
        // Use RPi server timezone offset (meta.tz_offset_s) so Δ(LTC-PTP) adj is correct
        // even when the WebUI is accessed from a remote browser in a different timezone.
        const srvTzMs = (meta.tz_offset_s != null)
          ? meta.tz_offset_s * 1000
          : (todMsFromLocalDate(srvNow) - todMsFromUtcDate(srvNow));
        const ptpTodLocal = ptpTodUtc + srvTzMs;
        if(ltcTod != null) {{
          const ltcCorr = ltcTod - alsaDelayMs;
          _emaDeltaLtcAdj = _ema(_emaDeltaLtcAdj, wrapDeltaMs(ltcCorr - ptpTodLocal));
          _emaDeltaLtcRaw = _ema(_emaDeltaLtcRaw, wrapDeltaMs(ltcCorr - ptpTodUtc));
          els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: ' + _emaDeltaLtcAdj.toFixed(3) + ' ms';
          els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: ' + _emaDeltaLtcRaw.toFixed(3) + ' ms';
          els('ltcTzLine').textContent = 'System TZ (PTP): ' + (srvTzMs/1000).toFixed(0) + ' s (' + srvTzMs.toFixed(0) + ' ms)';
        }} else {{
          _emaDeltaLtcAdj = null; _emaDeltaLtcRaw = null;
          els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
          els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
          els('ltcTzLine').textContent = 'System TZ (PTP): —';
        }}
      }} else {{
        _emaDeltaLtcAdj = null; _emaDeltaLtcRaw = null;
        els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
        els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
        els('ltcTzLine').textContent = 'System TZ (PTP): —';
      }}
    }} else {{
      _smPtpMs = null;
      _emaDeltaNtpPtp = null; _emaDeltaLtcAdj = null; _emaDeltaLtcRaw = null;
      renderSevenSeg(els('ptpTimeSegs'), null);
      els('deltaLine').textContent = 'Δ(NTP-PTP): —';
      els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
      els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
      els('ltcTzLine').textContent = 'System TZ (PTP): —';
    }}
  }}

  els('btnReload').addEventListener('click', () => {{ window.location.reload(); }});

  els('btnResetSummaries').addEventListener('click', async () => {{
    await fetch('/api/reset-summaries', {{method:'POST'}});
  }});

  els('btnReboot').addEventListener('click', async () => {{
    if (!confirm('System jetzt neu starten?')) return;
    try {{ await fetch('/api/system/reboot', {{method:'POST'}}); }} catch(e) {{}}
  }});

  els('btnShutdown').addEventListener('click', async () => {{
    if (!confirm('System jetzt herunterfahren?')) return;
    try {{ await fetch('/api/system/shutdown', {{method:'POST'}}); }} catch(e) {{}}
  }});

  const params = new URLSearchParams(window.location.search);
  const uiRefreshMs = Number(params.get('ui_refresh_ms') || {config.DEFAULT_UI_REFRESH_MS});
  const apiPollMs   = Number(params.get('ui_api_poll_ms')   || {config.DEFAULT_UI_API_POLL_MS});

  const ltcDeviceEl = document.getElementById('ltcDevice');
  const ltcDevice = ltcDeviceEl?.dataset?.device || '{config.LTC_ALSA_DEVICE}';

  async function pollLtcLevel() {{
    if (!ltcDevice) return;

    try {{
      const url = '/api/ltc/level?device=' + encodeURIComponent(ltcDevice) + '&duration_ms=100';
      const r = await fetch(url, {{ cache: 'no-store' }});
      if (!r.ok) return;

      const j = await r.json();

      const txt  = els('ltcLevelText');
      if (!txt) return;

      const dbPeak = (typeof j.dbfs_peak === 'number') ? j.dbfs_peak : -120;
      renderLedMeter(dbToLedCountCeil(dbPeak));
      txt.textContent = (typeof j.dbfs_peak === 'number') ? dbPeak.toFixed(1) + ' dBFS' : '—';
    }} catch (e) {{
      // ignore
    }}
  }}

  setInterval(uiTick, uiRefreshMs);
  setInterval(pollApi, apiPollMs);
  setInterval(pollLtcLevel, 200);

initLedMeter();
pollApi();
uiTick();
pollLtcLevel();

}})();
</script>
</body>
</html>
"""


def spectrum_html() -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
  <title>LTC Spectrum</title>
  <style>
    body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background:#0b0f14; color:#d7dde7; margin:0; }}
    .wrap {{ max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
    .card {{ background: rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:18px; padding:18px; }}
    .row {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
    input, select {{ background:#0f1620; color:#d7dde7; border:1px solid rgba(255,255,255,0.12); border-radius:12px; padding:10px 12px; }}
    .btn {{ display:inline-block; padding:10px 14px; border-radius:12px; border:1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.06); color:#d7dde7; text-decoration:none; cursor:pointer; }}
    pre {{ background:#0f1620; border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:12px; overflow:auto; }}
    img {{ max-width:100%; border-radius:12px; border:1px solid rgba(255,255,255,0.08); background:#0f1620; }}
    .muted {{ color:#9aa5b1; }}
    .ledMeter{{
  display:flex; gap:3px; align-items:flex-end;
  padding:8px; border-radius:14px;
  border:1px solid rgba(38,50,71,.65);
  background:rgba(0,0,0,.22);
}}
.led{{
  width:10px; height:18px; border-radius:3px;
  background:rgba(255,255,255,.06);
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.35);
  opacity:.35;
}}
.led.on{{ opacity:1; }}
.led.g.on{{ background: var(--ok); }}
.led.o.on{{ background: var(--warn); }}
.led.r.on{{ background: var(--alarm); }}

.led.peak{{
  height:6px;
  margin-top:2px;
  border-radius:999px;
  opacity:1;
  box-shadow:none;
}}

.ledText{{
  margin-top:6px; font-size:12px; color:var(--muted); text-align:center;
  font-family: var(--mono);
}}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div class=\"row\" style=\"justify-content:space-between;\">
        <div>
          <h2 style=\"margin:0 0 6px 0;\">LTC Spectrum</h2>
          <div class=\"muted\">On-demand capture + spectrogram. Monitoring continues in the background.</div>
        </div>
        <button class=\"btn\" id=\"btnClose\">Close</button>
      </div>

      <div style=\"height:14px;\"></div>
      <div class=\"row\">
        <label>ALSA device</label>
        <input id="dev" value="{config.LTC_ALSA_DEVICE}" size="20"/>
        <label>Duration</label>
        <select id=\"dur\">
          <option value=\"5\">5 s</option>
          <option value=\"10\">10 s</option>
          <option value=\"20\">20 s</option>
          <option value=\"30\">30 s</option>
          <option value=\"60\">60 s</option>
        </select>
        <button class=\"btn\" id=\"gen\">GENERATE</button>
        <span id=\"state\" class=\"muted\">—</span>
      </div>

      <div style=\"height:12px;\"></div>
      <div class=\"muted\">Status</div>
      <pre id=\"status\">{{}}</pre>

      <div style=\"height:12px;\"></div>
      <div class=\"row\" style=\"margin-bottom:6px;\">
        <span class=\"muted\">Image</span>
        <a id=\"imgDownload\" class=\"btn\" href=\"#\" download=\"LTC_Spectrum.png\" style=\"display:none;\">&#11015; Download PNG</a>
      </div>
      <div id=\"imgWrap\" class=\"muted\">No image yet. Click GENERATE.</div>
      <div style=\"height:10px;\"></div>
      <img id=\"img\" alt=\"spectrum\" style=\"display:none;\"/>

      <div id=\"audioWrap\" style=\"display:none; margin-top:18px;\">
        <div class=\"row\" style=\"margin-bottom:8px;\">
          <span class=\"muted\">Audio playback</span>
          <a id=\"audioDownload\" class=\"btn\" href=\"#\" download=\"ltc_capture.wav\">&#11015; Download WAV</a>
        </div>
        <audio id=\"audioPlayer\" controls style=\"width:100%; border-radius:12px;\"></audio>
      </div>
    </div>
  </div>

<script>
  const el = (id)=>document.getElementById(id);

  // Close: window.close() if opened as popup/tab; fallback: history.back or home.
  el('btnClose').addEventListener('click', function() {{
    window.close();
    setTimeout(function() {{
      if (history.length > 1) {{ history.back(); }}
      else {{ window.location.href = '/'; }}
    }}, 150);
  }});

  async function getStatus(){{
    const r = await fetch('/api/spectrum/status', {{cache:'no-store'}});
    const j = await r.json();
    el('status').textContent = JSON.stringify(j, null, 2);
    el('state').textContent = j.state || '—';
    if(j.has_image){{
      const imgUrl = '/api/spectrum/image?ts=' + Date.now();
      el('img').style.display='block';
      el('img').src = imgUrl;
      el('imgWrap').textContent='';
      // Build timestamped filename: YYYYMMDD-HH_MM_SS_UTC-LTC_Spectrum.png
      const dl = el('imgDownload');
      dl.href = imgUrl;
      if(j.last_generated_utc) {{
        const d = new Date(j.last_generated_utc);
        const fn = d.getUTCFullYear().toString()
          + String(d.getUTCMonth()+1).padStart(2,'0')
          + String(d.getUTCDate()).padStart(2,'0') + '-'
          + String(d.getUTCHours()).padStart(2,'0') + '_'
          + String(d.getUTCMinutes()).padStart(2,'0') + '_'
          + String(d.getUTCSeconds()).padStart(2,'0')
          + '_UTC-LTC_Spectrum.png';
        dl.download = fn;
      }}
      dl.style.display='';
    }}
    if(j.has_audio){{
      const ts = Date.now();
      const url = '/api/spectrum/audio?ts=' + ts;
      el('audioPlayer').src = url;
      const ad = el('audioDownload');
      ad.href = url;
      const d = j.last_generated_utc ? new Date(j.last_generated_utc) : new Date(ts);
      ad.download = d.getUTCFullYear().toString()
        + String(d.getUTCMonth()+1).padStart(2,'0')
        + String(d.getUTCDate()).padStart(2,'0') + '-'
        + String(d.getUTCHours()).padStart(2,'0') + '_'
        + String(d.getUTCMinutes()).padStart(2,'0') + '_'
        + String(d.getUTCSeconds()).padStart(2,'0')
        + '_UTC-LTC_Capture.wav';
      el('audioWrap').style.display='block';
    }}
    return j;
  }}

  async function generate(){{ 
    el('state').textContent = 'starting…';
    const payload = {{
      device: el('dev').value.trim(),
      duration_s: parseInt(el('dur').value,10)
    }};
    const r = await fetch('/api/spectrum/generate', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify(payload)
    }});
    const j = await r.json();
    el('status').textContent = JSON.stringify(j, null, 2);

    // Poll until done: duration_s capture + up to 30s for sox + 5s headroom,
    // checked every 250 ms.  Fixed 80-iteration cap was too short for ≥30s captures.
    const maxPolls = Math.ceil((payload.duration_s + 35) * 4);
    for(let i=0;i<maxPolls;i++){{
      const st = await getStatus();
      if(st.state !== 'generating') break;
      await new Promise(res=>setTimeout(res, 250));
    }}
  }}

  el('gen').addEventListener('click', ()=>generate());
  getStatus();
</script>
</body>
</html>"""