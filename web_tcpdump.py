"""
web_tcpdump.py – PTP Capture page HTML.

Accessible at /tcpdump.
Polls /api/tcpdump/lines?since=N every 400 ms for new lines.
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
.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
.field  { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 11px; color: var(--muted); }
.field input, .field select {
  background: rgba(0,0,0,0.4); color: var(--text); border: 1px solid var(--border);
  border-radius: 10px; padding: 8px 12px; font-family: var(--mono); font-size: 13px;
  width: 130px;
}
.btn { display: inline-flex; align-items: center; justify-content: center;
       padding: 9px 18px; border-radius: 12px; border: 1px solid var(--border);
       background: rgba(255,255,255,0.06); color: var(--text);
       font-family: var(--mono); font-size: 13px; cursor: pointer; user-select: none; }
.btn:hover { background: rgba(255,255,255,0.11); }
.btn.active { background: rgba(248,113,113,0.15); border-color: var(--alarm); color: var(--alarm); }
.btn.dl { background: rgba(96,165,250,0.12); border-color: var(--accent); color: var(--accent); }
.btn.dl:hover { background: rgba(96,165,250,0.22); }
.btn:disabled { opacity: 0.4; cursor: default; }
.stat { font-size: 12px; color: var(--muted); display: flex; gap: 18px; margin-bottom: 10px;
        flex-wrap: wrap; }
.stat span { white-space: nowrap; }
.stat .on  { color: var(--ok); }
.stat .off { color: var(--muted); }
.filter-box { font-size: 11px; color: var(--muted); margin-bottom: 10px;
              background: rgba(0,0,0,0.3); padding: 6px 12px; border-radius: 8px;
              border: 1px solid var(--border); }
.term {
  background: var(--term-bg); border: 1px solid var(--border); border-radius: 14px;
  height: 520px; overflow-y: scroll; padding: 12px 14px;
  font-size: 12px; line-height: 1.55; white-space: pre-wrap; word-break: break-all;
  color: #b8cce0;
}
.term .ts    { color: #4a6a8a; }
.term .ptp   { color: #60a5fa; }
.term .err   { color: var(--alarm); }
.msg { margin-top: 8px; padding: 7px 12px; border-radius: 8px; font-size: 12px; display: none; }
.msg.ok  { background: rgba(74,222,128,.1); border:1px solid rgba(74,222,128,.3);
            color: var(--ok); display: block; }
.msg.err { background: rgba(248,113,113,.1); border:1px solid rgba(248,113,113,.3);
            color: var(--alarm); display: block; }
"""

_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>PTP Capture – Time Reference Monitor</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;">
    <div>
      <h1 style="margin:0 0 4px;">PTP Capture</h1>
      <p class="sub" style="margin:0;">Echtzeit-tcpdump für PTP-Pakete (UDP 319/320 + EtherType 0x88F7)</p>
    </div>
    <button class="btn" id="btnClose">&#10005; Close</button>
  </div>

  <div class="toolbar">
    <div class="field">
      <label>Interface</label>
      <input id="ifaceInput" type="text" value="eth0"/>
    </div>
    <div style="display:flex;gap:8px;align-items:flex-end">
      <button class="btn" id="btnToggle">▶ Start</button>
      <button class="btn dl" id="btnDownload" disabled>⬇ pcap</button>
      <button class="btn" id="btnClear">✕ Clear</button>
    </div>
  </div>

  <div class="filter-box">
    Filter: <strong>(udp port 319 or udp port 320 or ether proto 0x88f7)</strong>
    &nbsp;·&nbsp; Speicher: max 500 Zeilen im Browser &nbsp;·&nbsp; pcap: /dev/shm/ptp_capture.pcap (max 50 MB)
  </div>

  <div class="stat" id="statBar">
    <span>Status: <span class="off" id="statRunning">gestoppt</span></span>
    <span id="statIface"></span>
    <span id="statLines">0 Zeilen</span>
    <span id="statElapsed"></span>
    <span id="statPcap"></span>
  </div>

  <div class="term" id="termOut"></div>
  <div class="msg" id="msgBox"></div>
</div>

<script>
(async () => {{
  const MAX_DISPLAY = 500;  // max lines kept in DOM
  const POLL_MS = 400;

  const $ = id => document.getElementById(id);
  let running = false;
  let pollTimer = null;
  let lineSeq = 0;
  let termLines = [];

  function showMsg(ok, text) {{
    const el = $('msgBox');
    el.className = 'msg ' + (ok ? 'ok' : 'err');
    el.textContent = text;
    setTimeout(() => {{ el.className = 'msg'; }}, 5000);
  }}

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
    // Colorise timestamp prefix (e.g. "2026-04-01 10:15:32.123456")
    const escaped = l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const tsMatch = escaped.match(/^(\\d{{4}}-\\d{{2}}-\\d{{2}} \\d{{2}}:\\d{{2}}:\\d{{2}}\\.\\d+)(.*)$/);
    if (tsMatch) {{
      const rest = tsMatch[2];
      const isPtp = /\\b(319|320|88f7|PTP|Sync|Delay|Follow|Announce)\\b/i.test(rest);
      return '<span class="ts">' + tsMatch[1] + '</span>'
           + (isPtp ? '<span class="ptp">' + rest + '</span>' : rest);
    }}
    if (/tcpdump:|error|Error/i.test(escaped)) {{
      return '<span class="err">' + escaped + '</span>';
    }}
    return escaped;
  }}

  // ── status polling ────────────────────────────────────────────────────────
  async function pollStatus() {{
    try {{
      const r = await fetch('/api/tcpdump/status', {{cache:'no-store'}});
      const d = await r.json();
      running = d.running;
      updateUI(d);
      $('btnDownload').disabled = !d.pcap_path;
    }} catch(e) {{ /* ignore */ }}
  }}

  function updateUI(d) {{
    const runEl = $('statRunning');
    runEl.textContent = d.running ? 'läuft' : 'gestoppt';
    runEl.className = d.running ? 'on' : 'off';
    $('statIface').textContent = d.iface ? 'Interface: ' + d.iface : '';
    $('statLines').textContent = d.line_count + ' / ' + d.max_lines + ' Zeilen';
    $('statElapsed').textContent = d.elapsed_s ? d.elapsed_s + ' s' : '';
    $('statPcap').textContent = d.pcap_size_mb > 0
      ? 'pcap: ' + d.pcap_size_mb.toFixed(1) + ' MB' : '';
    $('btnToggle').textContent = d.running ? '■ Stop' : '▶ Start';
    $('btnToggle').className = 'btn' + (d.running ? ' active' : '');
  }}

  // ── line polling ──────────────────────────────────────────────────────────
  async function pollLines() {{
    if (!running) return;
    try {{
      const r = await fetch('/api/tcpdump/lines?since=' + lineSeq, {{cache:'no-store'}});
      const d = await r.json();
      if (d.lines && d.lines.length) {{
        appendLines(d.lines);
      }}
      lineSeq = d.seq;
    }} catch(e) {{ /* ignore */ }}
  }}

  async function tick() {{
    await Promise.all([pollStatus(), pollLines()]);
  }}

  // ── controls ──────────────────────────────────────────────────────────────
  $('btnToggle').addEventListener('click', async () => {{
    $('btnToggle').disabled = true;
    try {{
      if (running) {{
        const r = await fetch('/api/tcpdump/stop', {{method:'POST'}});
        const d = await r.json();
        showMsg(d.ok, d.message);
      }} else {{
        const iface = $('ifaceInput').value.trim() || 'eth0';
        lineSeq = 0; termLines = [];
        renderTerm();
        const r = await fetch('/api/tcpdump/start', {{
          method: 'POST',
          headers: {{'Content-Type':'application/json'}},
          body: JSON.stringify({{ iface }}),
        }});
        const d = await r.json();
        showMsg(d.ok, d.message);
      }}
    }} catch(e) {{
      showMsg(false, 'Fehler: ' + e.message);
    }} finally {{
      $('btnToggle').disabled = false;
      await pollStatus();
    }}
  }});

  $('btnClear').addEventListener('click', () => {{
    termLines = []; lineSeq = 0; renderTerm();
  }});

  $('btnClose').addEventListener('click', function() {{
    window.close();
    setTimeout(function() {{ window.location.href = '/'; }}, 150);
  }});

  $('btnDownload').addEventListener('click', () => {{
    window.location.href = '/api/tcpdump/download';
  }});

  // ── init ──────────────────────────────────────────────────────────────────
  await pollStatus();
  pollTimer = setInterval(tick, POLL_MS);
}})();
</script>
</body>
</html>
"""


def tcpdump_html() -> str:
    return _HTML.format(css=_CSS)
