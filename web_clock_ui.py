# web_clock_ui.py
from __future__ import annotations
import config
import json


def ltc_clock_html() -> str:
    # dropdown options + mapping id -> font-family stack
    font_opts = "\n".join(
        f'<option value="{f["id"]}">{f["label"]}</option>'
        for f in config.CLOCK_FONTS
    )

    # JS map: id -> css font-family value
    font_map = {}
    font_faces_css = []

    for f in config.CLOCK_FONTS:
        if f.get("file") and f.get("family"):
            # OTF/TTF supported
            ext = f["file"].split(".")[-1].lower()
            fmt = "opentype" if ext == "otf" else "truetype"
            # NOTE: simple URL; avoid spaces in filenames if possible
            font_faces_css.append(
                f"@font-face{{font-family:'{f['family']}';src:url('/font/{f['file']}') format('{fmt}');font-weight:400;font-style:normal;}}"
            )
            font_map[f["id"]] = f"'{f['family']}', var(--mono)"
        else:
            font_map[f["id"]] = "var(--mono)"

    font_map_json = json.dumps(font_map)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>LTC Clock</title>
  <style>
    :root {{
      --bg:#000000;
      --panel:#0b0f14;
      --panel2:#111826;
      --line:#263247;
      --muted:#9fb0c8;

      /* default color (red) */
      --clock:#ff4d4f;

      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }}
{''.join(font_faces_css)}

    html, body {{
      margin:0; height:100%;
      background: var(--bg);
      color: var(--clock);
      overflow:hidden;
    }}

    .topbar {{
      position: fixed;
      top: 12px; left: 12px; right: 12px;
      display:flex; gap:10px; align-items:center; justify-content:space-between;
      pointer-events:none; /* allow clean screen; menus re-enable */
      z-index: 10;
    }}

    .menu {{
      pointer-events:auto;
      display:flex; gap:10px; align-items:center; flex-wrap:wrap;
      background: rgba(17,24,38,.70);
      border: 1px solid rgba(38,50,71,.65);
      border-radius: 14px;
      padding: 8px 10px;
      backdrop-filter: blur(6px);
      box-shadow: 0 10px 24px rgba(0,0,0,.35);
    }}

    .menu label {{
      color: var(--muted);
      font-family: var(--mono);
      font-size: 12px;
    }}

    select, button {{
      background:#0f1620;
      color:#e7eefc;
      border:1px solid rgba(255,255,255,.12);
      border-radius:12px;
      padding:8px 10px;
      font-family: var(--mono);
      font-size: 12px;
      cursor:pointer;
    }}
    button:hover {{ background: rgba(255,255,255,.08); }}

    .wrap {{
      height:100%;
      display:flex;
      align-items:center;
      justify-content:center;
      padding: 0 3vw; /* optional, damit bei kleineren widths nichts klebt */
    }}

    /* width modes */
    .clockBox {{
      width: 100%;
      max-width: 100vw;
      display:flex;
      justify-content:center;
      align-items:center;
      container-type: inline-size;
      container-name: clock;
      margin: 0 auto;
    }}
    .w1   {{ max-width: 100vw; }}
    .w34  {{ max-width: 75vw; }}
    .w23  {{ max-width: 66.666vw; }}
    .w12  {{ max-width: 50vw; }}
    .w14  {{ max-width: 25vw; }}

    .clock {{
      width:100%;
      text-align:center;
      font-family: var(--mono);
      font-weight: 900;
      letter-spacing: 0.06em;
      
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum" 1, "lnum" 1;


      /* cqw = 1% der Container-Breite (nicht Viewport!) */
      font-size: clamp(64px, 18cqw, 280px);
      line-height: 1.0;
      text-shadow: 0 0 18px rgba(255,255,255,.08);
      user-select:none;
    }}

    .hint {{
      position: fixed;
      bottom: 12px; left: 12px;
      color: rgba(159,176,200,.55);
      font-family: var(--mono);
      font-size: 11px;
      pointer-events:none;
    }}

    /* very subtle hover reveal if you want it “dezent” */
    body.hideMenus .menu {{ opacity: .25; }}
    body.hideMenus .menu:hover {{ opacity: 1; }}
  </style>
</head>
<body class="hideMenus">
  <div class="topbar">
    <div class="menu">
      <label>Color</label>
      <select id="colorSel">
        <option value="#ff4d4f" selected>Red (default)</option>
        <option value="#e7eefc">White</option>
        <option value="#19c37d">Green</option>
        <option value="#f4c430">Amber</option>
        <option value="#3aa0ff">Blue</option>
        <option value="#ff6bd6">Magenta</option>
    </select>
        <label>Font</label>
        <select id="fontSel">
        {font_opts}
    </select>
      <label>Width</label>
      <select id="widthSel">
        <option value="w1" selected>Full</option>
        <option value="w34">3/4</option>
        <option value="w23">2/3</option>
        <option value="w12">1/2</option>
        <option value="w14">1/4</option>
      </select>

      <button id="btnFs">Fullscreen</button>
      <button id="btnHide">Menus</button>
    <button id="btnClose" type="button">Close</button>

    </div>

    <div class="menu" style="gap:8px;">
      <label class="mono">Source</label>
      <select id="srcSel">
        <option value="ltc" selected>LTC</option>
        <option value="ptp">PTP (fallback)</option>
        <option value="local">Local</option>
      </select>
    </div>
  </div>

  <div class="wrap">
    <div id="box" class="clockBox w1">
      <div id="clk" class="clock">--:--:--</div>
    </div>
  </div>

  <div class="hint">LTC device: {config.LTC_ALSA_DEVICE}</div>

<script>
(() => {{
  const el = (id)=>document.getElementById(id);

  const clk = el('clk');
  const box = el('box');
  const colorSel = el('colorSel');
  const widthSel = el('widthSel');
  const srcSel = el('srcSel');
const fontSel = el('fontSel');

const FONT_MAP = {font_map_json};

  let lastApi = null;

  function setClockColor(hex) {{
    document.documentElement.style.setProperty('--clock', hex);
  }}

  function setWidthClass(cls) {{
    box.classList.remove('w1','w34','w23','w12','w14');
    box.classList.add(cls);
  }}

  function setClockFont(fontId){{
    const css = FONT_MAP[fontId] || "var(--mono)";
    clk.style.fontFamily = css;
    // viele 7-seg fonts sehen ohne "bold fake" besser aus:
    clk.style.fontWeight = (fontId === "seg7") ? "400" : "900";
  }}

  function fmtHMS(h,m,s) {{
    const pad = (n)=>String(n).padStart(2,'0');
    return pad(h)+':'+pad(m)+':'+pad(s);
  }}

  function parseTcToHMS(tc) {{
    // expects HH:MM:SS:FF
    if(!tc || typeof tc !== 'string') return null;
    const m = tc.match(/^(\\d{{2}}):(\\d{{2}}):(\\d{{2}}):(\\d{{2}})$/);
    if(!m) return null;
    return {{h:parseInt(m[1],10), m:parseInt(m[2],10), s:parseInt(m[3],10)}};
  }}

  async function pollApi() {{
    try {{
      const r = await fetch('/api/status', {{cache:'no-store'}});
      if(!r.ok) return;
      lastApi = await r.json();
    }} catch(e) {{}}
  }}

function tick(){{
  const src = srcSel ? srcSel.value : 'ltc';

    if(src === 'ltc'){{
      const present = lastApi?.ltc?.present;
      const tc = lastApi?.ltc?.timecode;
      if(!present || !tc){{
        clk.textContent = 'NO LTC';
        return;
      }}
      const hms = parseTcToHMS(tc);
      clk.textContent = hms ? fmtHMS(hms.h, hms.m, hms.s) : 'NO LTC';
      return;
    }}

  // 2) PTP (UTC ISO aus status)
  if(src === 'ptp'){{
    const iso = lastApi?.status?.ptp_time_utc_iso;
    if(!iso){{
      clk.textContent = '';
      return;
    }}
    const d = new Date(iso);
    clk.textContent = fmtHMS(d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds());
    return;
  }}

  // 3) Local (Browser)
  if(src === 'local'){{
    const d = new Date();
    clk.textContent = fmtHMS(d.getHours(), d.getMinutes(), d.getSeconds());
    return;
  }}

  clk.textContent = '';
}}


  async function goFullscreen() {{
    try {{
      if(!document.fullscreenElement) {{
        await document.documentElement.requestFullscreen();
      }} else {{
        await document.exitFullscreen();
      }}
    }} catch(e) {{}}
  }}

  // hooks
  colorSel.addEventListener('change', ()=>setClockColor(colorSel.value));
  widthSel.addEventListener('change', ()=>setWidthClass(widthSel.value));
  fontSel?.addEventListener('change', ()=>setClockFont(fontSel.value));
  srcSel?.addEventListener('change', tick);

  el('btnFs').addEventListener('click', ()=>goFullscreen());
  el('btnHide').addEventListener('click', ()=>document.body.classList.toggle('hideMenus'));
  el('btnClose').addEventListener('click', ()=> {{
    window.close();
    setTimeout(()=>{{ window.location.href = '/'; }}, 150);
  }});
  srcSel?.addEventListener('change', tick);
  
  // init defaults
  setClockColor(colorSel.value);
  setWidthClass(widthSel.value);

  if(fontSel){{
    fontSel.value = "{config.CLOCK_DEFAULT_FONT_ID}";
    setClockFont(fontSel.value);
  }}

  setInterval(pollApi, 200);
  setInterval(tick, 50);
  pollApi(); tick();
}})();
</script>
</body>
</html>
"""
