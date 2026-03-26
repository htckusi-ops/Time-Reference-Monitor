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
    .bigtime{{font-family:var(--mono); font-size:34px; line-height:1.05; letter-spacing:.5px; padding:10px 12px; border-radius:14px; border:1px solid var(--line); background:rgba(0,0,0,.25); min-height: 86px; display:flex; flex-direction:column; justify-content:center;}}
    .ptpLine{{display:flex; justify-content:space-between; gap:10px; align-items:baseline;}}
    .ptpLabel{{color:var(--muted); font-size:14px;}}
    .ptpValue{{}}
    .ptpNo{{color:var(--alarm); font-weight:800; letter-spacing:.4px;}}
    .smalltime{{font-family:var(--mono); font-size:16px; color:var(--muted); margin-top:10px;}}
    .row{{display:flex; gap:10px; flex-wrap:wrap; align-items:center;}}
    .kv{{display:grid; grid-template-columns: 170px 1fr; gap:6px 10px; font-size:13px;}}
    .kv-k{{color:var(--muted);}}
    .kv-v{{font-family:var(--mono);}}
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
    .hr{{height:1px; background:rgba(38,50,71,.7); margin:12px 0;}}
    .evtBox{{max-height: 440px; overflow:auto; border:1px solid rgba(38,50,71,.65); border-radius:12px;}}
        .ledMeter{{
  display:flex; gap:3px; align-items:flex-end;
  padding:8px; border-radius:14px;
  border:1px solid rgba(38,50,71,.65);
  background:rgba(0,0,0,.22);
}}
.led{{
  width:10px; height:18px; border-radius:3px;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.35);
  opacity: .18;                 /* off = sehr schwach */
  filter: saturate(1.2);
}}

/* Grundfarbe immer setzen (auch wenn off) */
.led.g{{ background: var(--ok); }}
.led.o{{ background: var(--warn); }}
.led.r{{ background: var(--alarm); }}

/* Peak-Layer: heller */
.led.peak{{
  opacity: .55;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.25), 0 0 10px rgba(255,255,255,.06);
}}

/* RMS-Layer: ganz hell */
.led.rms{{
  opacity: 1;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.15), 0 0 18px rgba(255,255,255,.10);
}}


.ledText{{
  margin-top:6px; font-size:12px; color:var(--muted); text-align:center;
  font-family: var(--mono);
}}
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
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="split">
        <h3>Reference Time</h3>
        <div class="row">
          <div class="btn" id="btnPause">PAUSE</div>
          <a class="btn" href="/ltc-clock" target="_blank" rel="noopener">LTC Clock…</a>
          <a class="btn" id="btnLtcSpectrum" href="/spectrum" target="_blank" rel="noopener">LTC Spectrum…</a>
          <div class="btn btn-sys" id="btnReboot">REBOOT</div>
          <div class="btn btn-sys" id="btnShutdown">SHUTDOWN</div>
        </div>
      </div>

      <div class="bigtime" id="ptpBox">
        <div class="ptpLine">
          <div class="ptpLabel">PTP</div>
          <div class="ptpValue mono" id="ptpTime">—</div>
        </div>
        <div class="ptpLine">
          <div class="ptpLabel">Status</div>
          <div class="ptpValue mono" id="ptpStatusLine"><span class="ptpNo">NO PTP SYNC</span></div>
        </div>
      </div>
      
<div id="ltcDevice" data-device="{config.LTC_ALSA_DEVICE}"></div>

      <div class="smalltime" id="ntpTime">NTP: —</div>
      <div class="smalltime" id="ltcTop">LTC: —</div>
      <div class="smalltime" id="deltaLine">Δ(NTP-PTP): —</div>
      <div class="smalltime" id="deltaLtcLine">Δ(LTC-PTP): —</div>
      <div class="smalltime" id="deltaLtcAdjLine">Δ(LTC-PTP) adj: —</div>
      <div class="smalltime" id="deltaLtcRawLine">Δ(LTC-PTP) raw: —</div>
      <div class="smalltime" id="ltcTzLine">TZ: —</div>
      <div class="smalltime">
      LTC Audio Level ({config.LTC_ALSA_DEVICE})
        </div>
        <div style="margin: 8px 12px 12px 12px;">
            <div id="ltcLedMeter" class="ledMeter"></div>
            <div id="ltcLevelText" class="ledText">—</div>
        </div>
      <div class="hr"></div>

      <div class="kv" style="margin-top:8px;">
        <div class="kv-k">State</div><div class="kv-v" id="stateLine">—</div>
        <div class="kv-k">PTP source</div><div class="kv-v" id="sourceLine">—</div>
        <div class="kv-k">Interface</div><div class="kv-v" id="ifaceLine">—</div>
        <div class="kv-k">Domain</div><div class="kv-v" id="domainLine">—</div>

        <div class="kv-k">PTP valid</div><div class="kv-v" id="ptpValidLine">—</div>
        <div class="kv-k">GM present</div><div class="kv-v" id="gmPresentLine">—</div>
        <div class="kv-k">Port state</div><div class="kv-v" id="portStateLine">—</div>
        <div class="kv-k">PTP versions</div><div class="kv-v" id="ptpVerLine">—</div>

        <div class="kv-k">GM identity</div><div class="kv-v" id="gmLine">—</div>
        <div class="kv-k">Offset (ns)</div><div class="kv-v" id="offLine">—</div>
        <div class="kv-k">Mean path delay (ns)</div><div class="kv-v" id="delayLine">—</div>
        <div class="kv-k">Poll age (ms)</div><div class="kv-v" id="ageLine">—</div>

        <div class="kv-k">GM changes (rolling)</div><div class="kv-v" id="gmChgLine">—</div>
        <div class="kv-k">NO PTP since</div><div class="kv-v" id="noPtpLine">—</div>

        <div class="kv-k">NTP status</div><div class="kv-v" id="ntpLine">—</div>
        <div class="kv-k">LTC status</div><div class="kv-v" id="ltcLine">—</div>
      </div>
    </div>

    <div class="card">
      <div class="split">
        <h3>Rolling Error Summary</h3>
        <div class="row">
          <span class="badge"><span class="dot" id="dotErr"></span><span class="mono" id="errSummary">—</span></span>
        </div>
      </div>

      <div class="kv" style="margin-top:8px;">
        <div class="kv-k">Errors (rolling)</div><div class="kv-v" id="errRoll">—</div>
        <div class="kv-k">Warnings (rolling)</div><div class="kv-v" id="warnRoll">—</div>
        <div class="kv-k">Alarms (rolling)</div><div class="kv-v" id="alarmRoll">—</div>
        <div class="kv-k">PTP losses (rolling)</div><div class="kv-v" id="ptpLossRoll">—</div>
        <div class="kv-k">NTP flaps (rolling)</div><div class="kv-v" id="ntpFlapRoll">—</div>
        <div class="kv-k">LTC losses (rolling)</div><div class="kv-v" id="ltcLossRoll">—</div>
        <div class="kv-k">LTC decode errs (rolling)</div><div class="kv-v" id="ltcDecRoll">—</div>
        <div class="kv-k">GM changes (rolling)</div><div class="kv-v" id="gmChgRoll">—</div>

        <div class="kv-k">Errors (total)</div><div class="kv-v" id="errTot">—</div>
        <div class="kv-k">Warnings (total)</div><div class="kv-v" id="warnTot">—</div>
        <div class="kv-k">Alarms (total)</div><div class="kv-v" id="alarmTot">—</div>
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
  let paused = false;

  // rendering bases (freeze if stale/paused/no-data)
  let lastApi = null;

  // PTP smooth/monotonic: keep a base time and a rate-corrector, never go backwards.
  let ptpBaseMs = null;
  let ptpBaseMono = null;
  let ptpCorrMs = 0.0;
  let ptpTargetCorrMs = 0.0;
  let ptpLastShownMs = null;

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

function renderLedMeter(ledRms, ledPeak){{
  const m = els('ltcLedMeter');
  if(!m) return;

  // nur die echten Segmente (keine extra marker)
  const segs = Array.from(m.querySelectorAll('.led'));

  segs.forEach((el, i) => {{
    const idx = i + 1;

    el.classList.remove('rms', 'peak');

    if(idx <= ledRms){{
      el.classList.add('rms');      // ganz hell
    }} else if(idx <= ledPeak){{
      el.classList.add('peak');     // heller
    }}
  }});
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
    const meta = data.meta || {{}};
    const st = data.status || {{}};
    const ntp = data.ntp || {{}};
    const ltc = data.ltc || {{}};
    const roll = meta.summaries_rolling || {{}};
    const tot = meta.summaries || {{}};

    els('pillMeta').textContent = `${{meta.source || '—'}} | ${{meta.iface || '—'}} | domain=${{meta.domain ?? '—'}} | poll=${{meta.poll_s ?? '—'}}s`;
    els('footMeta').textContent = `API: ${{meta.ts_utc || '—'}}`;

    els('sourceLine').textContent = meta.source || '—';
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
    els('gmLine').textContent = st.gm_identity || '—';
    els('offLine').textContent = (st.offset_ns != null) ? String(st.offset_ns) : '—';
    els('delayLine').textContent = (st.mean_path_delay_ns != null) ? String(st.mean_path_delay_ns) : '—';
    els('ageLine').textContent = (st.poll_age_ms != null) ? String(st.poll_age_ms) : '—';
    els('noPtpLine').textContent = st.no_ptp_since_utc || '—';
    els('gmChgLine').textContent = String(roll.gm_changes_rolling ?? '—');

    const ntpLine = `NTP: ${{ntp.status || 'unknown'}} | stratum=${{(ntp.stratum ?? '—')}} | ref=${{(ntp.ref ?? '—')}} | last_update_age=${{(ntp.last_update_age_s ?? '—')}}`;
    els('ntpLine').textContent = ntpLine;

    const pres = (ltc.enabled && ltc.present) ? 'present' : (ltc.enabled ? 'absent' : 'disabled');
    const tc = ltc.timecode || '—';
    const fps = ltc.fps || '—';
    const age = (ltc.last_update_age_s != null) ? (Math.round(ltc.last_update_age_s*10)/10)+'s' : '—';
    els('ltcLine').textContent = `LTC: ${{pres}} | tc=${{tc}} | fps=${{fps}} | last_update_age=${{age}}`;
    els('ltcTop').textContent = `LTC: ${{pres}} | tc=${{tc}}`;

    // rolling summary
    const eR = Number(roll.errors_rolling ?? 0);
    const wR = Number(roll.warnings_rolling ?? 0);
    const aR = Number(roll.alarms_rolling ?? 0);
    els('errSummary').textContent = `roll err=${{eR}} warn=${{wR}} alarm=${{aR}}`;
    setDot(els('dotErr'), (aR>0)?'ALARM':(wR>0||eR>0)?'WARN':'OK');

    els('errRoll').textContent = String(roll.errors_rolling ?? '—');
    els('warnRoll').textContent = String(roll.warnings_rolling ?? '—');
    els('alarmRoll').textContent = String(roll.alarms_rolling ?? '—');
    els('ptpLossRoll').textContent = String(roll.ptp_loss_rolling ?? '—');
    els('ntpFlapRoll').textContent = String(roll.ntp_flaps_rolling ?? '—');
    els('ltcLossRoll').textContent = String(roll.ltc_loss_rolling ?? '—');
    els('ltcDecRoll').textContent = String(roll.ltc_decode_errors_rolling ?? '—');
    els('gmChgRoll').textContent = String(roll.gm_changes_rolling ?? '—');

    els('errTot').textContent = String(tot.errors_total ?? '—');
    els('warnTot').textContent = String(tot.warnings_total ?? '—');
    els('alarmTot').textContent = String(tot.alarms_total ?? '—');

    // Decide if PTP should tick: only if valid AND not stale AND not paused
    const staleTh = meta.stale_threshold_ms ?? 2000;
    const ageMs = st.poll_age_ms ?? 999999;
    const canTick = (!!st.ptp_valid) && (ageMs <= staleTh) && (!meta.paused);

    if(canTick && st.ptp_time_utc_iso){{
      const d = new Date(st.ptp_time_utc_iso);
      ptpBaseMs = d.getTime();
      ptpBaseMono = performance.now();

      // target correction: bring rendered time towards last sample without backwards jumps
      const nowMs = ptpBaseMs + (performance.now() - ptpBaseMono);
      const err = d.getTime() - nowMs;
      ptpTargetCorrMs = 0.90 * ptpTargetCorrMs + 0.10 * err;

      els('ptpStatusLine').innerHTML = `<span class="mono">SYNC OK</span>`;
    }} else {{
      // freeze
      ptpBaseMs = null; ptpBaseMono = null; ptpCorrMs = 0; ptpTargetCorrMs = 0;
      ptpLastShownMs = null;

      if(meta.paused) els('ptpStatusLine').innerHTML = `<span class="ptpNo">PAUSED</span>`;
      else if(ageMs > staleTh) els('ptpStatusLine').innerHTML = `<span class="ptpNo">STALE DATA</span>`;
      else els('ptpStatusLine').innerHTML = `<span class="ptpNo">NO PTP SYNC</span>`;
    }}

    updateEvents(data.events || []);
  }}

  async function pollApi(){{
    if(paused) return;
    try{{
      const r = await fetch('/api/status', {{cache:'no-store'}});
      if(!r.ok) throw new Error('http '+r.status);
      const data = await r.json();
      applyApi(data);
    }}catch(e){{}}
  }}

  function uiTick(){{
    // NTP displayed as system time for smoothness
    const now = new Date();
    els('ntpTime').textContent = 'NTP: ' + fmtIso(now.toISOString(), 3);

    if(!lastApi) {{
      els('ptpTime').textContent = '—';
      els('deltaLine').textContent = 'Δ(NTP-PTP): —';
      els('deltaLtcLine').textContent = 'Δ(LTC-PTP): —';
      els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
      els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
      els('ltcTzLine').textContent = 'TZ: —';
      return;
    }}

    const meta = lastApi.meta || {{}};
    const st = lastApi.status || {{}};
    const ltc = lastApi.ltc || {{}};

    const staleTh = meta.stale_threshold_ms ?? 2000;
    const ageMs = st.poll_age_ms ?? 999999;
    const canTick = (!!st.ptp_valid) && (ageMs <= staleTh) && (!meta.paused);

    if(canTick && ptpBaseMs != null && ptpBaseMono != null) {{
      // slew correction: never go backwards
      const maxStep = 0.15; // ms per tick
      const diff = ptpTargetCorrMs - ptpCorrMs;
      const step = Math.max(-maxStep, Math.min(maxStep, diff));
      ptpCorrMs += step;

      let ms = ptpBaseMs + (performance.now() - ptpBaseMono) + ptpCorrMs;

      if(ptpLastShownMs != null && ms < ptpLastShownMs) {{
        ms = ptpLastShownMs; // clamp: monotonic visual time
      }}
      ptpLastShownMs = ms;

      const d = new Date(ms);
      const dec = (meta.display_decimals != null) ? meta.display_decimals : 6;
      els('ptpTime').textContent = fmtIso(d.toISOString(), dec);

      const deltaMs = (now.getTime() - ms);
      els('deltaLine').textContent = `Δ(NTP-PTP): ${{deltaMs.toFixed(3)}} ms`;

      // LTC delta (derived):
      if(ltc.enabled && ltc.present && ltc.timecode) {{
        const fps = ltc.fps || meta.ltc_fps || 25;
        const ltcTod = parseTcToTodMs(ltc.timecode, fps);
        const ptpTodLocal = todMsFromLocalDate(d);
        const ptpTodUtc = todMsFromUtcDate(d);
        const tzMs = ptpTodLocal - ptpTodUtc;

        if(ltcTod != null) {{
          const dAdj = wrapDeltaMs(ltcTod - ptpTodLocal);
          const dRaw = wrapDeltaMs(ltcTod - ptpTodUtc);
          els('deltaLtcLine').textContent = `LTC tc=${{ltc.timecode}}`;
          els('deltaLtcAdjLine').textContent = `Δ(LTC-PTP) adj: ${{dAdj.toFixed(3)}} ms`;
          els('deltaLtcRawLine').textContent = `Δ(LTC-PTP) raw: ${{dRaw.toFixed(3)}} ms`;
          els('ltcTzLine').textContent = `TZ: ${{(tzMs/1000).toFixed(0)}} s (${{tzMs.toFixed(0)}} ms)`;
        }} else {{
          els('deltaLtcLine').textContent = `LTC tc=${{ltc.timecode}}`;
          els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
          els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
          els('ltcTzLine').textContent = 'TZ: —';
        }}
      }} else {{
        els('deltaLtcLine').textContent = 'Δ(LTC-PTP): —';
        els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
        els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
        els('ltcTzLine').textContent = 'TZ: —';
      }}
    }} else {{
      els('ptpTime').textContent = '—';
      els('deltaLine').textContent = 'Δ(NTP-PTP): —';
      els('deltaLtcLine').textContent = 'Δ(LTC-PTP): —';
      els('deltaLtcAdjLine').textContent = 'Δ(LTC-PTP) adj: —';
      els('deltaLtcRawLine').textContent = 'Δ(LTC-PTP) raw: —';
      els('ltcTzLine').textContent = 'TZ: —';
    }}
  }}

  els('btnPause').addEventListener('click', async () => {{
    paused = !paused;
    els('btnPause').textContent = paused ? 'RESUME' : 'PAUSE';
    try {{
      await fetch(paused ? '/api/pause' : '/api/resume', {{method:'POST'}});
    }} catch(e) {{}}
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
      const dbRms  = (typeof j.dbfs_rms === 'number')  ? j.dbfs_rms  : -120;

        const ledRms  = dbToLedCountFloor(dbRms);
        const ledPeak = dbToLedCountCeil(dbPeak);
        
        // Safety: falls trotzdem mal invertiert (z.B. NaNs)
        const a = Math.min(ledRms, ledPeak);
        const b = Math.max(ledRms, ledPeak);
        
        renderLedMeter(a, b);

      if (typeof j.dbfs_peak === 'number' && typeof j.dbfs_rms === 'number') {{
        txt.textContent = 'peak ' + dbPeak.toFixed(1) + ' dBFS | rms ' + dbRms.toFixed(1) + ' dBFS';
      }} else {{
        txt.textContent = '—';
      }}
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
        <a class=\"btn\" href=\"/\">Close</a>
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
      <div class=\"muted\">Image</div>
      <div id=\"imgWrap\" class=\"muted\">No image yet. Click GENERATE.</div>
      <div style=\"height:10px;\"></div>
      <img id=\"img\" alt=\"spectrum\" style=\"display:none;\"/>
    </div>
  </div>

<script>
  const el = (id)=>document.getElementById(id);

  async function getStatus(){{ 
    const r = await fetch('/api/spectrum/status', {{cache:'no-store'}});
    const j = await r.json();
    el('status').textContent = JSON.stringify(j, null, 2);
    el('state').textContent = j.state || '—';
    if(j.has_image){{
      el('img').style.display='block';
      el('img').src = '/api/spectrum/image?ts=' + Date.now();
      el('imgWrap').textContent='';
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

    for(let i=0;i<80;i++){{ 
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