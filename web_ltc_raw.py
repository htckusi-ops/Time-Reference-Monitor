"""
web_ltc_raw.py – LTC Raw Output page HTML.

Accessible at /ltc-raw.
Shows the live stdout of the ltcdump/alsaltc subprocess.
Polls /api/ltc/raw-lines?since=N every 400 ms for new lines.
Keeps at most MAX_DISPLAY lines in the terminal view to avoid DOM bloat.
"""

_CSS = """
* { box-sizing: border-box; }
:root {
  --bg: #0b0f14; --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.10);
  --text: #d7dde7; --muted: #7a8898; --ok: #4ade80; --warn: #fbbf24; --alarm: #f87171;
  --mono: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --accent: #60a5fa; --term-bg: #060a0f;
}
body  { font-family: var(--mono); background: var(--bg); color: var(--text); margin:0; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 20px 16px 48px; }
h1    { font-size: 19px; margin: 0 0 3px; }
.sub  { color: var(--muted); font-size: 13px; margin: 0 0 18px; }
.btn { display: inline-flex; align-items: center; justify-content: center;
       padding: 9px 18px; border-radius: 12px; border: 1px solid var(--border);
       background: rgba(255,255,255,0.06); color: var(--text);
       font-family: var(--mono); font-size: 13px; cursor: pointer; user-select: none; }
.btn:hover { background: rgba(255,255,255,0.11); }
.btn.paused { background: rgba(251,191,36,0.15); border-color: var(--warn); color: var(--warn); }
.stat { font-size: 12px; color: var(--muted); display: flex; gap: 18px; margin-bottom: 10px;
        flex-wrap: wrap; }
.stat span { white-space: nowrap; }
.stat .on  { color: var(--ok); }
.stat .off { color: var(--muted); }
.cmd-box { font-size: 11px; color: var(--muted); margin-bottom: 10px;
           background: rgba(0,0,0,0.3); padding: 6px 12px; border-radius: 8px;
           border: 1px solid var(--border); word-break: break-all; }
.term {
  background: var(--term-bg); border: 1px solid var(--border); border-radius: 14px;
  height: 520px; overflow-y: scroll; padding: 12px 14px;
  font-size: 12px; line-height: 1.55; white-space: pre-wrap; word-break: break-all;
  color: #b8cce0;
}
.term .ts   { color: #4a6a8a; }
.term .tc   { color: #60a5fa; }
.term .date { color: #4ade80; }
.term .noltc { color: #f87171; }
.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
"""

_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>LTC Raw Output – Time Reference Monitor</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;">
    <div>
      <h1 style="margin:0 0 4px;">LTC Raw Output</h1>
      <p class="sub" style="margin:0;">Live-Ausgabe des LTC-Decoder-Prozesses</p>
    </div>
    <button class="btn" id="btnClose">&#10005; Close</button>
  </div>

  <div class="cmd-box">Befehl: <span id="cmdLine">—</span></div>

  <div class="toolbar">
    <button class="btn" id="btnPause">&#9646;&#9646; Pause</button>
    <button class="btn" id="btnClear">&#10005; Clear</button>
  </div>

  <div class="stat" id="statBar">
    <span>Status: <span id="statRunning" class="off">warte…</span></span>
    <span id="statLines">0 Zeilen</span>
  </div>

  <div class="term" id="termOut"></div>
</div>

<script>
(async () => {{
  const MAX_DISPLAY = 500;
  const POLL_MS = 400;

  const $ = id => document.getElementById(id);
  let lineSeq = 0;
  let termLines = [];
  let totalReceived = 0;
  let paused = false;

  // ── terminal rendering ────────────────────────────────────────────────────
  function appendLines(lines) {{
    for (const raw of lines) {{
      termLines.push(raw);
    }}
    if (termLines.length > MAX_DISPLAY) {{
      termLines = termLines.slice(termLines.length - MAX_DISPLAY);
    }}
    renderTerm();
  }}

  function renderTerm() {{
    const term = $('termOut');
    const atBottom = term.scrollHeight - term.scrollTop - term.clientHeight < 60;
    term.innerHTML = termLines.map(l => formatLine(l)).join('\\n');
    if (atBottom) term.scrollTop = term.scrollHeight;
  }}

  function formatLine(l) {{
    const escaped = l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    // Line format: "HH:MM:SS.mmm  <payload>"
    const tsMatch = escaped.match(/^(\\d{{2}}:\\d{{2}}:\\d{{2}}\\.\\d+)(\\s+)(.*)$/);
    if (tsMatch) {{
      const payload = tsMatch[3];
      if (/^NO_LTC/.test(payload)) {{
        return '<span class="ts">' + tsMatch[1] + '</span>'
             + tsMatch[2]
             + '<span class="noltc">' + payload + '</span>';
      }}
      // Timecode: HH:MM:SS:FF
      const tcMatch = payload.match(/^(\\d{{2}}:\\d{{2}}:\\d{{2}}:\\d{{2}})(.*)$/);
      if (tcMatch) {{
        const rest = tcMatch[2];
        // Date portion after timecode
        const dateMatch = rest.match(/(\\s+)(\\d{{4}}-\\d{{2}}-\\d{{2}})(.*)/);
        if (dateMatch) {{
          return '<span class="ts">' + tsMatch[1] + '</span>'
               + tsMatch[2]
               + '<span class="tc">' + tcMatch[1] + '</span>'
               + dateMatch[1]
               + '<span class="date">' + dateMatch[2] + '</span>'
               + dateMatch[3];
        }}
        return '<span class="ts">' + tsMatch[1] + '</span>'
             + tsMatch[2]
             + '<span class="tc">' + tcMatch[1] + '</span>'
             + rest;
      }}
      return '<span class="ts">' + tsMatch[1] + '</span>' + tsMatch[2] + payload;
    }}
    return escaped;
  }}

  // ── polling ───────────────────────────────────────────────────────────────
  async function poll() {{
    try {{
      const r = await fetch('/api/ltc/raw-lines?since=' + lineSeq, {{cache:'no-store'}});
      if (!r.ok) return;
      const d = await r.json();
      if (d.cmd) $('cmdLine').textContent = d.cmd;
      if (d.lines && d.lines.length) {{
        totalReceived += d.lines.length;
        if (!paused) appendLines(d.lines);
      }}
      lineSeq = d.seq;

      const runEl = $('statRunning');
      if (d.enabled) {{
        runEl.textContent = 'aktiv';
        runEl.className = 'on';
      }} else {{
        runEl.textContent = 'deaktiviert';
        runEl.className = 'off';
      }}
      $('statLines').textContent = totalReceived + ' Zeilen empfangen (max ' + MAX_DISPLAY + ' im Browser)';
    }} catch(e) {{ /* ignore */ }}
  }}

  // ── controls ──────────────────────────────────────────────────────────────
  $('btnPause').addEventListener('click', () => {{
    paused = !paused;
    $('btnPause').textContent = paused ? '&#9654; Resume' : '&#9646;&#9646; Pause';
    $('btnPause').className = 'btn' + (paused ? ' paused' : '');
  }});

  $('btnClear').addEventListener('click', () => {{
    termLines = []; renderTerm();
  }});

  $('btnClose').addEventListener('click', function() {{
    window.close();
    setTimeout(function() {{ window.location.href = '/'; }}, 150);
  }});

  // ── init ──────────────────────────────────────────────────────────────────
  setInterval(poll, POLL_MS);
  poll();
}})();
</script>
</body>
</html>
"""


def ltc_raw_html() -> str:
    return _HTML.format(css=_CSS)
