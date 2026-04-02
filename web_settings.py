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
    <p class="hint">Erster server/pool-Eintrag in chrony.conf wird ersetzt; chrony startet neu.<br>
    Die Einstellung wird in <code>/var/lib/time-reference-monitor/ntp_server</code> gespeichert
    und bei jedem <code>sudo bash rpi/update.sh</code> automatisch wiederhergestellt.<br>
    Falls der Eintrag trotzdem zurückgesetzt wird: NetworkManager-DHCP-Dispatcher prüfen
    (<code>/etc/NetworkManager/dispatcher.d/</code>) — dieser kann NTP-Server aus dem
    DHCP-Lease in chrony.conf schreiben.</p>
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

  <!-- ── NTP-Simulation ── -->
  <div class="card">
    <h2>NTP-Simulation</h2>
    <div class="current" id="ntpSrcCurrent">Lade…</div>

    <div class="field">
      <label>Quelle</label>
      <select id="ntpSrcSelect">
        <option value="real">Real — chrony (live)</option>
        <option value="mock">Simulation (Mock)</option>
      </select>
    </div>

    <div id="ntpMockOptions" style="display:none">
      <div class="field">
        <label>Preset</label>
        <select id="ntpMockPreset">
          <option value="clean">Rein ± 5 µs — normaler NTP-Lock</option>
          <option value="jitter">Jitter ± 500 µs — schlechte NTP-Qualität</option>
          <option value="drift">Drift 0.5 ppm — kontinuierlicher Gangfehler</option>
          <option value="step">Sprung 500 ms alle 30 s — Zeitsprünge</option>
          <option value="ref_flap">Ref-Wechsel alle 20 s — NTP-Server-Failover</option>
          <option value="unsynced">Ausfall alle 30 s — NTP-Verlustereignisse</option>
          <option value="combo">Kombination — Wander + Drift + Ref-Wechsel</option>
          <option value="custom">Benutzerdefiniert…</option>
        </select>
      </div>

      <div id="ntpCustomParams" style="display:none">
        <div class="row-fields">
          <div class="field"><label>Jitter (µs)</label>
            <input id="ncpJitter" type="number" value="5" min="0"/></div>
          <div class="field"><label>Wander (µs)</label>
            <input id="ncpWander" type="number" value="0" min="0"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>Drift (ppm)</label>
            <input id="ncpDrift" type="number" value="0" step="0.01"/></div>
          <div class="field"><label>Wander-Periode (s)</label>
            <input id="ncpWanderPeriod" type="number" value="60" min="1"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>Ausfall-Intervall (s, 0=aus)</label>
            <input id="ncpUnsyncedEvery" type="number" value="0" min="0"/></div>
          <div class="field"><label>Ausfall-Dauer (s)</label>
            <input id="ncpUnsyncedDur" type="number" value="10" min="1"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>Ref-Flap-Intervall (s, 0=aus)</label>
            <input id="ncpRefFlap" type="number" value="0" min="0"/></div>
          <div class="field"><label>Sprung alle (s, 0=aus)</label>
            <input id="ncpStepEvery" type="number" value="0" min="0"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>Sprungweite (ms)</label>
            <input id="ncpStepMs" type="number" value="0"/></div>
          <div class="field"><label>Stratum (Basis)</label>
            <input id="ncpStratum" type="number" value="2" min="1" max="15"/></div>
        </div>
      </div>
    </div>

    <button class="btn btn-primary" id="btnSaveNtpSrc">Übernehmen</button>
    <div class="msg" id="msgNtpSrc"></div>
    <p class="hint">
      Im Mock-Modus werden chrony-Abfragen durch einen internen NTP-Simulator ersetzt.<br>
      Der Systemclock und chrony laufen weiter — nur die Monitor-Anzeige nutzt simulierte Werte.<br>
      Rückkehr zu «Real» stellt sofort die echte chrony-Abfrage wieder her.
    </p>
  </div>

  <!-- ── PTP-Quelle / Simulation ── -->
  <div class="card">
    <h2>PTP-Quelle / Test-Simulation</h2>
    <div class="current" id="ptpSrcCurrent">Lade…</div>

    <div class="field">
      <label>Quelle</label>
      <select id="ptpSrcSelect">
        <option value="real">Real — ptp4l (live)</option>
        <option value="mock">Simulation (Mock)</option>
      </select>
    </div>

    <div id="mockOptions" style="display:none">
      <div class="field">
        <label>Preset</label>
        <select id="mockPreset">
          <option value="clean">Rein ± 50 ns — normaler PTP-Lock</option>
          <option value="jitter">Jitter ± 2 µs — schlechte Netzwerkqualität</option>
          <option value="wander">Wander ± 10 µs — langsame Temperaturdrift</option>
          <option value="dropout">Ausfall alle 20 s — PTP-Verlustereignisse</option>
          <option value="gm_flap">GM-Wechsel alle 30 s — Grandmaster-Failover</option>
          <option value="drift">Drift 500 ppb — kontinuierlicher Gangfehler</option>
          <option value="step">Sprung ±100 µs alle 30 s — Zeitsprünge</option>
          <option value="combo_gm">GM-Wechsel + Wander — Kombination</option>
          <option value="combo_drift">Drift + Wander — Kombination</option>
          <option value="combo_storm">Sprung + Ausfall + GM — Sturm</option>
          <option value="custom">Benutzerdefiniert…</option>
        </select>
      </div>

      <div id="customParams" style="display:none">
        <div class="row-fields">
          <div class="field"><label>Jitter (ns)</label>
            <input id="cpJitter" type="number" value="50" min="0"/></div>
          <div class="field"><label>Wander (ns)</label>
            <input id="cpWander" type="number" value="0" min="0"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>Drift (ppb)</label>
            <input id="cpDrift" type="number" value="0"/></div>
          <div class="field"><label>Wander-Periode (s)</label>
            <input id="cpWanderPeriod" type="number" value="60" min="1"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>Ausfall-Intervall (s, 0=aus)</label>
            <input id="cpDropoutEvery" type="number" value="0" min="0"/></div>
          <div class="field"><label>Ausfall-Dauer (s)</label>
            <input id="cpDropoutDur" type="number" value="3" min="1"/></div>
        </div>
        <div class="row-fields">
          <div class="field"><label>GM-Flap-Intervall (s, 0=aus)</label>
            <input id="cpGmFlap" type="number" value="0" min="0"/></div>
          <div class="field"><label>Sprung alle (s, 0=aus)</label>
            <input id="cpStepEvery" type="number" value="0" min="0"/></div>
        </div>
        <div class="field"><label>Sprungweite (ns)</label>
          <input id="cpStepNs" type="number" value="0"/></div>
      </div>
    </div>

    <button class="btn btn-primary" id="btnSavePtpSrc">Übernehmen</button>
    <div class="msg" id="msgPtpSrc"></div>
    <p class="hint">
      Im Mock-Modus werden ptp4l-Abfragen durch einen internen Simulator ersetzt.<br>
      Der Systemclock und ptp4l laufen weiter — nur die Monitor-Anzeige nutzt simulierte Werte.<br>
      Rückkehr zu «Real» stellt sofort die echte ptp4l-Abfrage wieder her.
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

  // ── PTP source / simulation ──────────────────────────────────────────────
  const PRESET_LABELS = {{
    clean:   'Rein ± 50 ns',
    jitter:  'Jitter ± 2 µs',
    wander:  'Wander ± 10 µs',
    dropout: 'Ausfall alle 20 s',
    gm_flap: 'GM-Wechsel alle 30 s',
    drift:       'Drift 500 ppb',
    step:        'Sprung ±100 µs alle 30 s',
    combo_gm:    'GM-Wechsel + Wander',
    combo_drift: 'Drift + Wander',
    combo_storm: 'Sprung + Ausfall + GM',
    custom:      'Benutzerdefiniert',
  }};

  async function loadPtpSource() {{
    try {{
      const r = await fetch('/api/ptp-source', {{cache:'no-store'}});
      const d = await r.json();
      const isMock = d.source === 'mock';
      $('ptpSrcSelect').value = d.source;
      $('mockOptions').style.display = isMock ? '' : 'none';
      if (isMock && d.params && d.params.preset) {{
        $('mockPreset').value = d.params.preset in PRESET_LABELS ? d.params.preset : 'custom';
        $('customParams').style.display = d.params.preset === 'custom' ? '' : 'none';
      }}
      const label = isMock
        ? 'Simulation aktiv: ' + (PRESET_LABELS[d.params?.preset] || d.params?.preset || '—')
        : 'Quelle: Real — ptp4l (live)';
      $('ptpSrcCurrent').textContent = label;
    }} catch(e) {{
      $('ptpSrcCurrent').textContent = 'Nicht verfügbar';
    }}
  }}

  $('ptpSrcSelect').addEventListener('change', () => {{
    $('mockOptions').style.display = $('ptpSrcSelect').value === 'mock' ? '' : 'none';
  }});

  $('mockPreset').addEventListener('change', () => {{
    $('customParams').style.display = $('mockPreset').value === 'custom' ? '' : 'none';
  }});

  $('btnSavePtpSrc').addEventListener('click', async () => {{
    const src = $('ptpSrcSelect').value;
    let body = {{ source: src }};
    if (src === 'mock') {{
      const preset = $('mockPreset').value;
      if (preset === 'custom') {{
        body = {{
          source: 'mock', preset: 'custom',
          jitter_ns: parseInt($('cpJitter').value) || 0,
          wander_ns: parseInt($('cpWander').value) || 0,
          wander_period_s: parseFloat($('cpWanderPeriod').value) || 60,
          drift_ppb: parseFloat($('cpDrift').value) || 0,
          dropout_every_s: parseFloat($('cpDropoutEvery').value) || 0,
          dropout_duration_s: parseFloat($('cpDropoutDur').value) || 3,
          gm_flap_every_s: parseFloat($('cpGmFlap').value) || 0,
          step_every_s: parseFloat($('cpStepEvery').value) || 0,
          step_ns: parseInt($('cpStepNs').value) || 0,
        }};
      }} else {{
        body = {{ source: 'mock', preset }};
      }}
    }}
    try {{
      const r = await fetch('/api/ptp-source', {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(body),
      }});
      const d = await r.json();
      showMsg('msgPtpSrc', d.ok, d.ok
        ? (src === 'mock' ? 'Simulation aktiv: ' + (body.preset || '') : 'Zurück auf Real-Quelle.')
        : (d.message || 'Fehler'));
      loadPtpSource();
    }} catch(e) {{
      showMsg('msgPtpSrc', false, 'Fehler: ' + e.message);
    }}
  }});

  // ── NTP source / simulation ──────────────────────────────────────────────
  const NTP_PRESET_LABELS = {{
    clean:    'Rein ± 5 µs',
    jitter:   'Jitter ± 500 µs',
    drift:    'Drift 0.5 ppm',
    step:     'Sprung 500 ms alle 30 s',
    ref_flap: 'Ref-Wechsel alle 20 s',
    unsynced: 'Ausfall alle 30 s',
    combo:    'Kombination',
    custom:   'Benutzerdefiniert',
  }};

  async function loadNtpSource() {{
    try {{
      const r = await fetch('/api/ntp-source', {{cache:'no-store'}});
      const d = await r.json();
      const isMock = d.source === 'mock';
      $('ntpSrcSelect').value = d.source;
      $('ntpMockOptions').style.display = isMock ? '' : 'none';
      if (isMock && d.params && d.params.preset) {{
        $('ntpMockPreset').value = d.params.preset in NTP_PRESET_LABELS ? d.params.preset : 'custom';
        $('ntpCustomParams').style.display = d.params.preset === 'custom' ? '' : 'none';
      }}
      const label = isMock
        ? 'Simulation aktiv: ' + (NTP_PRESET_LABELS[d.params?.preset] || d.params?.preset || '—')
        : 'Quelle: Real — chrony (live)';
      $('ntpSrcCurrent').textContent = label;
    }} catch(e) {{
      $('ntpSrcCurrent').textContent = 'Nicht verfügbar';
    }}
  }}

  $('ntpSrcSelect').addEventListener('change', () => {{
    $('ntpMockOptions').style.display = $('ntpSrcSelect').value === 'mock' ? '' : 'none';
  }});

  $('ntpMockPreset').addEventListener('change', () => {{
    $('ntpCustomParams').style.display = $('ntpMockPreset').value === 'custom' ? '' : 'none';
  }});

  $('btnSaveNtpSrc').addEventListener('click', async () => {{
    const src = $('ntpSrcSelect').value;
    let body = {{ source: src }};
    if (src === 'mock') {{
      const preset = $('ntpMockPreset').value;
      if (preset === 'custom') {{
        body = {{
          source: 'mock', preset: 'custom',
          jitter_s:          (parseFloat($('ncpJitter').value) || 0) * 1e-6,
          wander_s:          (parseFloat($('ncpWander').value) || 0) * 1e-6,
          wander_period_s:   parseFloat($('ncpWanderPeriod').value) || 60,
          drift_ppm:         parseFloat($('ncpDrift').value) || 0,
          unsynced_every_s:  parseFloat($('ncpUnsyncedEvery').value) || 0,
          unsynced_duration_s: parseFloat($('ncpUnsyncedDur').value) || 10,
          ref_flap_every_s:  parseFloat($('ncpRefFlap').value) || 0,
          step_every_s:      parseFloat($('ncpStepEvery').value) || 0,
          step_s:            (parseFloat($('ncpStepMs').value) || 0) * 1e-3,
          stratum:           parseInt($('ncpStratum').value) || 2,
        }};
      }} else {{
        body = {{ source: 'mock', preset }};
      }}
    }}
    try {{
      const r = await fetch('/api/ntp-source', {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(body),
      }});
      const d = await r.json();
      showMsg('msgNtpSrc', d.ok, d.ok
        ? (src === 'mock' ? 'NTP-Simulation aktiv: ' + (body.preset || '') : 'Zurück auf Real-Quelle (chrony).')
        : (d.message || 'Fehler'));
      loadNtpSource();
    }} catch(e) {{
      showMsg('msgNtpSrc', false, 'Fehler: ' + e.message);
    }}
  }});

  // ── init ─────────────────────────────────────────────────────────────────
  loadNet();
  loadNtp();
  loadWifi();
  loadPtpSource();
  loadNtpSource();
}})();
</script>
</body>
</html>
"""


def settings_html() -> str:
    return _HTML.format(css=_CSS)
