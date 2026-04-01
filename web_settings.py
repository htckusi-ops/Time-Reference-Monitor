"""
web_settings.py – Network / WiFi / NTP settings page and API routes.

Accessible at /settings  (link from main dashboard header).
All write operations call network_mgr which uses sudo nmcli / sudo tee.
"""
from __future__ import annotations

_CSS = """
* { box-sizing: border-box; }
:root {
  --bg: #0b0f14; --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.10);
  --text: #d7dde7; --muted: #7a8898; --ok: #4ade80; --warn: #fbbf24; --alarm: #f87171;
  --mono: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --accent: #60a5fa;
}
body { font-family: var(--mono); background: var(--bg); color: var(--text); margin: 0; padding: 0; }
.wrap { max-width: 720px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 24px; }
.back { display: inline-flex; align-items: center; gap: 6px; color: var(--accent);
        text-decoration: none; font-size: 13px; margin-bottom: 20px; }
.back:hover { text-decoration: underline; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 16px;
        padding: 20px 22px; margin-bottom: 20px; }
.card h2 { font-size: 14px; color: var(--muted); text-transform: uppercase;
           letter-spacing: 0.08em; margin: 0 0 16px; }
.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.field label { font-size: 12px; color: var(--muted); }
.field input, .field select {
  background: rgba(0,0,0,0.4); color: var(--text); border: 1px solid var(--border);
  border-radius: 10px; padding: 9px 12px; font-family: var(--mono); font-size: 14px;
  width: 100%;
}
.field input:disabled { opacity: 0.4; cursor: not-allowed; }
.field input:focus { outline: none; border-color: var(--accent); }
.row-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.btn { display: inline-flex; align-items: center; justify-content: center;
       padding: 10px 20px; border-radius: 12px; border: 1px solid var(--border);
       background: rgba(255,255,255,0.07); color: var(--text);
       font-family: var(--mono); font-size: 13px; cursor: pointer; }
.btn:hover { background: rgba(255,255,255,0.12); }
.btn-primary { background: rgba(96,165,250,0.15); border-color: var(--accent); color: var(--accent); }
.btn-primary:hover { background: rgba(96,165,250,0.25); }
.msg { margin-top: 10px; padding: 8px 12px; border-radius: 8px; font-size: 13px; display: none; }
.msg.ok { background: rgba(74,222,128,0.12); border: 1px solid rgba(74,222,128,0.3);
           color: var(--ok); display: block; }
.msg.err { background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.3);
            color: var(--alarm); display: block; }
.hint { font-size: 12px; color: var(--muted); margin-top: 6px; line-height: 1.5; }
.toggle-row { display: flex; align-items: center; gap: 14px; }
.toggle { position: relative; width: 44px; height: 24px; flex-shrink: 0; }
.toggle input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; inset: 0; border-radius: 24px;
          background: rgba(255,255,255,0.15); cursor: pointer; transition: .2s; }
.toggle input:checked + .slider { background: rgba(96,165,250,0.55); }
.slider:before { content: ''; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px;
                 background: #fff; border-radius: 50%; transition: .2s; }
.toggle input:checked + .slider:before { transform: translateX(20px); }
.current { font-size: 12px; color: var(--muted); background: rgba(0,0,0,0.3);
            border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px;
            margin-bottom: 14px; line-height: 1.7; }
.warn-box { background: rgba(251,191,36,0.10); border: 1px solid rgba(251,191,36,0.3);
             border-radius: 10px; padding: 10px 14px; font-size: 12px; color: var(--warn);
             margin-top: 10px; }
"""

_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Settings – Time Reference Monitor</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&#8592; Zurück zum Monitor</a>
  <h1>Settings</h1>
  <p class="sub">Netzwerk · NTP · WiFi</p>

  <!-- ── Network ── -->
  <div class="card">
    <h2>Netzwerk (eth0)</h2>
    <div class="current" id="currentNet">Lade…</div>

    <div class="field">
      <label>Modus</label>
      <select id="netMethod">
        <option value="dhcp">DHCP (automatisch)</option>
        <option value="static">Statisch</option>
      </select>
    </div>

    <div id="staticFields">
      <div class="row-fields">
        <div class="field">
          <label>IP-Adresse</label>
          <input id="netIp" type="text" placeholder="192.168.1.100"/>
        </div>
        <div class="field">
          <label>Subnetzmaske</label>
          <input id="netMask" type="text" placeholder="255.255.255.0"/>
        </div>
      </div>
      <div class="row-fields">
        <div class="field">
          <label>Gateway</label>
          <input id="netGw" type="text" placeholder="192.168.1.1"/>
        </div>
        <div class="field">
          <label>DNS-Server</label>
          <input id="netDns" type="text" placeholder="8.8.8.8, 1.1.1.1"/>
        </div>
      </div>
    </div>

    <button class="btn btn-primary" id="btnSaveNet">Netzwerk speichern</button>
    <div class="msg" id="msgNet"></div>
    <div class="warn-box" id="warnIpChange" style="display:none">
      &#9888; Änderung der IP-Adresse trennt die aktuelle Browser-Verbindung.
      Neue Adresse manuell im Browser eingeben.
    </div>
  </div>

  <!-- ── NTP Server ── -->
  <div class="card">
    <h2>NTP-Server (chrony)</h2>
    <div class="field">
      <label>NTP-Server</label>
      <input id="ntpServer" type="text" placeholder="pool.ntp.org"/>
    </div>
    <p class="hint">Erster server/pool-Eintrag in chrony.conf wird ersetzt.
    Nach dem Speichern startet chrony automatisch neu.</p>
    <button class="btn btn-primary" id="btnSaveNtp">NTP speichern</button>
    <div class="msg" id="msgNtp"></div>
  </div>

  <!-- ── WiFi ── -->
  <div class="card">
    <h2>WiFi</h2>
    <div class="toggle-row">
      <label class="toggle">
        <input type="checkbox" id="wifiToggle"/>
        <span class="slider"></span>
      </label>
      <span id="wifiLabel">Lade…</span>
    </div>
    <div class="msg" id="msgWifi"></div>
    <p class="hint">
      WLAN-Konfiguration (SSID / Passwort) auf dem Pi bearbeiten:<br>
      <code>sudo nmcli device wifi connect &lt;SSID&gt; password &lt;PW&gt;</code><br>
      oder Dateien in <code>/etc/NetworkManager/system-connections/</code>
    </p>
  </div>
</div>

<script>
(async () => {{
  // ── helpers ──────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);
  function showMsg(id, ok, text) {{
    const el = $(id);
    el.className = 'msg ' + (ok ? 'ok' : 'err');
    el.textContent = text;
    setTimeout(() => {{ el.className = 'msg'; }}, 6000);
  }}

  // ── Network ──────────────────────────────────────────────────────────────
  let origIp = '';
  async function loadNet() {{
    try {{
      const r = await fetch('/api/settings/network', {{cache:'no-store'}});
      const d = await r.json();
      origIp = d.ip || '';
      $('currentNet').textContent =
        `Aktuell: ${{d.ip || '—'}}/${{d.prefix || '?'}}  GW=${{d.gateway || '—'}}  DNS=${{d.dns || '—'}}  (${{d.method}})`;
      $('netMethod').value = d.method === 'static' ? 'static' : 'dhcp';
      $('netIp').value  = d.ip  || '';
      $('netMask').value = d.netmask || '';
      $('netGw').value  = d.gateway || '';
      $('netDns').value = d.dns || '';
      toggleStaticFields();
    }} catch(e) {{
      $('currentNet').textContent = 'Fehler beim Laden der Netzwerkdaten.';
    }}
  }}

  function toggleStaticFields() {{
    const isStatic = $('netMethod').value === 'static';
    $('staticFields').style.display = isStatic ? '' : 'none';
    ['netIp','netMask','netGw','netDns'].forEach(id => $(id).disabled = !isStatic);
  }}

  $('netMethod').addEventListener('change', () => {{
    toggleStaticFields();
    const isStatic = $('netMethod').value === 'static';
    $('warnIpChange').style.display = isStatic ? 'block' : 'none';
  }});

  $('netIp').addEventListener('input', () => {{
    $('warnIpChange').style.display = ($('netIp').value !== origIp) ? 'block' : 'none';
  }});

  $('btnSaveNet').addEventListener('click', async () => {{
    const method = $('netMethod').value;
    let body;
    if (method === 'dhcp') {{
      body = {{ method: 'dhcp' }};
    }} else {{
      body = {{
        method: 'static',
        ip: $('netIp').value.trim(),
        mask: $('netMask').value.trim(),
        gateway: $('netGw').value.trim(),
        dns: $('netDns').value.trim(),
      }};
    }}
    $('btnSaveNet').disabled = true;
    try {{
      const r = await fetch('/api/settings/network', {{
        method: 'POST', headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify(body),
      }});
      const d = await r.json();
      showMsg('msgNet', d.ok, d.message);
      if (d.ok) loadNet();
    }} catch(e) {{
      showMsg('msgNet', false, 'Netzwerkfehler: ' + e.message);
    }} finally {{
      $('btnSaveNet').disabled = false;
    }}
  }});

  // ── NTP ──────────────────────────────────────────────────────────────────
  async function loadNtp() {{
    try {{
      const r = await fetch('/api/settings/ntp', {{cache:'no-store'}});
      const d = await r.json();
      $('ntpServer').value = d.server || '';
    }} catch(e) {{}}
  }}

  $('btnSaveNtp').addEventListener('click', async () => {{
    const server = $('ntpServer').value.trim();
    if (!server) {{ showMsg('msgNtp', false, 'Kein Server angegeben.'); return; }}
    $('btnSaveNtp').disabled = true;
    try {{
      const r = await fetch('/api/settings/ntp', {{
        method: 'POST', headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{ server }}),
      }});
      const d = await r.json();
      showMsg('msgNtp', d.ok, d.message);
    }} catch(e) {{
      showMsg('msgNtp', false, 'Fehler: ' + e.message);
    }} finally {{
      $('btnSaveNtp').disabled = false;
    }}
  }});

  // ── WiFi ─────────────────────────────────────────────────────────────────
  async function loadWifi() {{
    try {{
      const r = await fetch('/api/settings/wifi', {{cache:'no-store'}});
      const d = await r.json();
      $('wifiToggle').checked = !!d.enabled;
      $('wifiLabel').textContent = d.enabled ? 'WiFi aktiviert' : 'WiFi deaktiviert';
    }} catch(e) {{
      $('wifiLabel').textContent = 'Status unbekannt';
    }}
  }}

  $('wifiToggle').addEventListener('change', async () => {{
    const enabled = $('wifiToggle').checked;
    $('wifiLabel').textContent = enabled ? 'Aktiviere…' : 'Deaktiviere…';
    try {{
      const r = await fetch('/api/settings/wifi', {{
        method: 'POST', headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{ enabled }}),
      }});
      const d = await r.json();
      showMsg('msgWifi', d.ok, d.message);
      loadWifi();
    }} catch(e) {{
      showMsg('msgWifi', false, 'Fehler: ' + e.message);
      $('wifiToggle').checked = !enabled; // revert
      loadWifi();
    }}
  }});

  // ── init ─────────────────────────────────────────────────────────────────
  loadNet();
  loadNtp();
  loadWifi();
}})();
</script>
</body>
</html>
"""


def settings_html() -> str:
    return _HTML.format(css=_CSS)
