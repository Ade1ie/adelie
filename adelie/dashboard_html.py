"""
adelie/dashboard_html.py

Embedded HTML/CSS/JS template for the Adelie real-time web dashboard.
Served as a single self-contained page — no external assets needed.

Performance-optimized:
  - requestAnimationFrame DOM batching
  - DocumentFragment for bulk log insertion
  - Event throttling for rapid agent updates
  - Phase timeline class-toggle (no full re-render)
"""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Adelie Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;
  --fg:#e6edf3;--fg2:#8b949e;--fg3:#484f58;
  --cyan:#58a6ff;--green:#3fb950;--yellow:#d29922;--red:#f85149;
  --magenta:#bc8cff;--orange:#f0883e;
  --glass:rgba(22,27,34,0.75);
}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;overflow-x:hidden}

/* ── Header ─────────────────────────── */
.header{display:flex;align-items:center;gap:16px;padding:16px 24px;background:var(--bg2);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;backdrop-filter:blur(12px)}
.header .logo{font-size:20px;font-weight:700;color:var(--cyan);display:flex;align-items:center;gap:8px}
.header .logo svg{width:28px;height:28px}
.header .version{font-size:12px;color:var(--fg2);background:var(--bg3);padding:2px 8px;border-radius:10px}
.header .spacer{flex:1}
.header .status-dot{width:8px;height:8px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
.header .status-label{font-size:13px;color:var(--fg2)}
.header .dash-url{font-size:12px;color:var(--fg3);font-family:'JetBrains Mono',monospace}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* ── Info Bar ───────────────────────── */
.info-bar{display:flex;flex-wrap:wrap;gap:12px;padding:16px 24px;background:var(--bg);border-bottom:1px solid var(--border)}
.info-item{display:flex;align-items:center;gap:6px;font-size:13px}
.info-label{color:var(--fg2);font-weight:500}
.info-value{color:var(--fg)}
.phase-badge{background:linear-gradient(135deg,rgba(88,166,255,.15),rgba(188,140,255,.15));border:1px solid rgba(88,166,255,.3);padding:3px 12px;border-radius:14px;font-size:12px;font-weight:600;color:var(--cyan)}

/* ── Main Layout ────────────────────── */
.main{display:grid;grid-template-columns:1fr 300px;grid-template-rows:auto 1fr;gap:16px;padding:16px 24px;max-height:calc(100vh - 120px)}
@media(max-width:1100px){.main{grid-template-columns:1fr}}

/* ── Agent Grid ─────────────────────── */
.section-title{font-size:13px;font-weight:600;color:var(--fg2);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}
.agents-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.agent-card{background:var(--glass);border:1px solid var(--border);border-radius:10px;padding:14px;transition:border-color .3s ease,box-shadow .3s ease;position:relative;overflow:hidden;contain:layout style}
.agent-card:hover{border-color:var(--fg3)}
.agent-card.running{border-color:var(--cyan);box-shadow:0 0 20px rgba(88,166,255,.1)}
.agent-card.running::before{content:'';position:absolute;top:0;left:-100%;width:100%;height:2px;background:linear-gradient(90deg,transparent,var(--cyan),transparent);animation:scan 2s linear infinite}
@keyframes scan{to{left:100%}}
.agent-card.done{border-color:var(--green)}
.agent-card.error{border-color:var(--red)}
.agent-name{font-size:13px;font-weight:600;margin-bottom:6px;display:flex;align-items:center;gap:6px}
.agent-name .dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.dot.idle{background:var(--fg3)}.dot.running{background:var(--cyan);animation:pulse 1.5s infinite}
.dot.done{background:var(--green)}.dot.error{background:var(--red)}.dot.skipped{background:var(--fg3)}
.agent-detail{font-size:11px;color:var(--fg2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.agent-elapsed{font-size:11px;color:var(--fg3);font-family:'JetBrains Mono',monospace}

/* ── Right Panel ────────────────────── */
.right-panel{display:flex;flex-direction:column;gap:16px}

/* ── Metrics ────────────────────────── */
.metrics-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.metric-card{background:var(--glass);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center}
.metric-value{font-size:22px;font-weight:700;font-family:'JetBrains Mono',monospace;line-height:1.2}
.metric-value.cyan{color:var(--cyan)}.metric-value.green{color:var(--green)}
.metric-value.yellow{color:var(--yellow)}.metric-value.magenta{color:var(--magenta)}
.metric-label{font-size:10px;color:var(--fg2);text-transform:uppercase;letter-spacing:.5px;margin-top:4px}

/* ── Phase Timeline ─────────────────── */
.phase-timeline{background:var(--glass);border:1px solid var(--border);border-radius:10px;padding:14px}
.phase-item{display:flex;align-items:center;gap:8px;padding:5px 0;font-size:12px;position:relative}
.phase-item::before{content:'';width:12px;height:12px;border-radius:50%;border:2px solid var(--fg3);flex-shrink:0;background:transparent;transition:all .3s}
.phase-item.active::before{border-color:var(--cyan);background:var(--cyan);box-shadow:0 0 10px rgba(88,166,255,.4)}
.phase-item.completed::before{border-color:var(--green);background:var(--green)}
.phase-item:not(:last-child)::after{content:'';position:absolute;left:5px;top:22px;width:2px;height:calc(100% - 2px);background:var(--border)}
.phase-item.active .phase-name{color:var(--cyan);font-weight:600}
.phase-item.completed .phase-name{color:var(--green)}
.phase-name{color:var(--fg2)}

/* ── Log Stream ─────────────────────── */
.log-container{grid-column:1/-1;background:var(--bg2);border:1px solid var(--border);border-radius:10px;overflow:hidden;display:flex;flex-direction:column;min-height:250px;max-height:400px}
.log-header{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--border);background:var(--bg3)}
.log-header .title{font-size:12px;font-weight:600;color:var(--fg2)}
.log-header .count{font-size:11px;color:var(--fg3);font-family:'JetBrains Mono',monospace}
.log-body{flex:1;overflow-y:auto;padding:8px 0;font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.6}
.log-body::-webkit-scrollbar{width:6px}
.log-body::-webkit-scrollbar-track{background:transparent}
.log-body::-webkit-scrollbar-thumb{background:var(--fg3);border-radius:3px}
.log-entry{padding:2px 14px;display:flex;gap:8px;transition:background .15s}
.log-entry:hover{background:rgba(88,166,255,.04)}
.log-ts{color:var(--fg3);flex-shrink:0;width:70px}
.log-cat{flex-shrink:0;width:12px;text-align:center}
.log-msg{color:var(--fg);word-break:break-word;flex:1}
.log-entry.error .log-msg{color:var(--red)}
.log-entry.warning .log-msg{color:var(--yellow)}
.log-entry.agent_start .log-msg{color:var(--cyan)}
.log-entry.agent_end .log-msg{color:var(--green)}
.log-entry.phase_change .log-msg{color:var(--magenta)}
.log-entry.debug .log-msg{color:var(--fg3)}

/* ── Connection Banner ──────────────── */
.conn-banner{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--red);color:#fff;padding:8px 20px;border-radius:20px;font-size:13px;font-weight:500;display:none;z-index:200;box-shadow:0 4px 20px rgba(248,81,73,.3)}
.conn-banner.show{display:block;animation:slideUp .3s ease}
@keyframes slideUp{from{transform:translateX(-50%) translateY(20px);opacity:0}to{transform:translateX(-50%) translateY(0);opacity:1}}

/* ── Cycle History Chart ────────────── */
.chart-container{background:var(--glass);border:1px solid var(--border);border-radius:10px;padding:14px}
.chart-bars{display:flex;align-items:flex-end;gap:3px;height:60px}
.chart-bar{flex:1;background:linear-gradient(180deg,var(--cyan),rgba(88,166,255,.3));border-radius:3px 3px 0 0;min-width:4px;transition:height .5s ease;position:relative}
.chart-bar:hover{opacity:.8}
.chart-bar .tooltip{display:none;position:absolute;bottom:calc(100% + 4px);left:50%;transform:translateX(-50%);background:var(--bg3);color:var(--fg);font-size:10px;padding:2px 6px;border-radius:4px;white-space:nowrap;font-family:'JetBrains Mono',monospace}
.chart-bar:hover .tooltip{display:block}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="logo">
    <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="12" r="10" fill="#58a6ff" opacity=".15" stroke="#58a6ff" stroke-width="1.5"/><circle cx="13" cy="10" r="1.5" fill="#e6edf3"/><circle cx="19" cy="10" r="1.5" fill="#e6edf3"/><ellipse cx="16" cy="14" rx="3" ry="2" fill="#f0883e"/><path d="M10 20 C10 26 22 26 22 20" stroke="#58a6ff" stroke-width="1.5" fill="none"/><path d="M6 14 C4 18 8 22 10 20" stroke="#58a6ff" stroke-width="1.5" fill="none"/><path d="M26 14 C28 18 24 22 22 20" stroke="#58a6ff" stroke-width="1.5" fill="none"/></svg>
    Adelie Dashboard
  </div>
  <span class="version" id="version">v0.2.0</span>
  <div class="spacer"></div>
  <div class="status-dot" id="statusDot"></div>
  <span class="status-label" id="statusLabel">Connected</span>
</div>

<!-- Info Bar -->
<div class="info-bar">
  <div class="info-item"><span class="info-label">Goal:</span><span class="info-value" id="goal">—</span></div>
  <div class="info-item"><span class="phase-badge" id="phaseBadge">—</span></div>
  <div class="info-item"><span class="info-label">Workspace:</span><span class="info-value" id="workspace" style="font-size:12px;color:var(--fg3)">—</span></div>
  <div class="info-item"><span class="info-label">Cycle:</span><span class="info-value" id="cycleNum" style="font-family:'JetBrains Mono',monospace;color:var(--cyan)">#0</span></div>
</div>

<div class="main">
  <!-- Left Column -->
  <div>
    <!-- Agents -->
    <div class="section-title">Agents</div>
    <div class="agents-grid" id="agentsGrid"></div>

    <!-- Log Stream -->
    <div class="log-container">
      <div class="log-header">
        <span class="title">📋 Live Log</span>
        <span class="count" id="logCount">0 entries</span>
      </div>
      <div class="log-body" id="logBody"></div>
    </div>
  </div>

  <!-- Right Panel -->
  <div class="right-panel">
    <!-- Metrics -->
    <div>
      <div class="section-title">Cycle Metrics</div>
      <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value cyan" id="mTokens">0</div><div class="metric-label">Tokens</div></div>
        <div class="metric-card"><div class="metric-value green" id="mCalls">0</div><div class="metric-label">LLM Calls</div></div>
        <div class="metric-card"><div class="metric-value yellow" id="mFiles">0</div><div class="metric-label">Files</div></div>
        <div class="metric-card"><div class="metric-value magenta" id="mTime">0s</div><div class="metric-label">Cycle Time</div></div>
        <div class="metric-card"><div class="metric-value green" id="mTests">—</div><div class="metric-label">Tests</div></div>
        <div class="metric-card"><div class="metric-value yellow" id="mReview">—</div><div class="metric-label">Review</div></div>
      </div>
    </div>

    <!-- Phase Timeline -->
    <div>
      <div class="section-title">Phase</div>
      <div class="phase-timeline" id="phaseTimeline"></div>
    </div>

    <!-- Cycle History Chart -->
    <div>
      <div class="section-title">Cycle History</div>
      <div class="chart-container">
        <div class="chart-bars" id="chartBars"></div>
      </div>
    </div>
  </div>
</div>

<!-- Connection banner -->
<div class="conn-banner" id="connBanner">⚠ Disconnected — reconnecting…</div>

<script>
(function(){
  "use strict";

  // ── Agents ──────────────────────────
  const AGENTS = ["Writer","Expert","Scanner","Coder","Reviewer","Tester","Runner","Monitor","Analyst","Research"];

  // ── Phases ──────────────────────────
  const PHASES = [
    {value:"initial",label:"초기 — Planning"},
    {value:"mid",label:"중기 — Implementation"},
    {value:"mid_1",label:"중기 1기 — Execution"},
    {value:"mid_2",label:"중기 2기 — Stabilization"},
    {value:"late",label:"후기 — Maintenance"},
    {value:"evolve",label:"자율 발전 — Evolution"}
  ];

  // ── State ───────────────────────────
  let state = {agents:{},cycle:0,phase:"initial",goal:"",workspace:"",metrics:{}};
  let logCount = 0;
  const MAX_LOGS = 300;
  let autoScroll = true;

  // ── DOM refs ────────────────────────
  const $ = id => document.getElementById(id);
  const agentsGrid = $("agentsGrid");
  const logBody = $("logBody");
  const logCountEl = $("logCount");

  // ── RAF Batch Queue ─────────────────
  // All DOM mutations are queued and applied in a single rAF frame
  let pendingUpdates = [];
  let rafScheduled = false;

  function scheduleUpdate(fn) {
    pendingUpdates.push(fn);
    if (!rafScheduled) {
      rafScheduled = true;
      requestAnimationFrame(flushUpdates);
    }
  }

  function flushUpdates() {
    const updates = pendingUpdates;
    pendingUpdates = [];
    rafScheduled = false;
    for (let i = 0; i < updates.length; i++) {
      updates[i]();
    }
  }

  // ── Init agents grid ────────────────
  function initAgents(){
    const frag = document.createDocumentFragment();
    AGENTS.forEach(name => {
      const card = document.createElement("div");
      card.className = "agent-card";
      card.id = "agent-"+name;
      card.innerHTML = `
        <div class="agent-name"><span class="dot idle" id="dot-${name}"></span>${name}</div>
        <div class="agent-detail" id="detail-${name}">idle</div>
        <div class="agent-elapsed" id="elapsed-${name}"></div>`;
      frag.appendChild(card);
    });
    agentsGrid.appendChild(frag);
  }

  // ── Update agent card (throttled) ──
  const agentThrottleMap = {};
  const AGENT_THROTTLE_MS = 80;

  function updateAgent(name, info){
    const now = performance.now();
    const lastUpdate = agentThrottleMap[name] || 0;
    const prevState = agentThrottleMap[name + "_state"];
    const curState = info.state || "idle";

    // Skip if same state and within throttle window
    if (curState === prevState && (now - lastUpdate) < AGENT_THROTTLE_MS) {
      return;
    }
    agentThrottleMap[name] = now;
    agentThrottleMap[name + "_state"] = curState;

    scheduleUpdate(() => {
      const card = $("agent-"+name);
      if(!card) return;
      const dot = $("dot-"+name);
      const detail = $("detail-"+name);
      const elapsed = $("elapsed-"+name);
      const st = info.state || "idle";
      card.className = "agent-card " + st;
      dot.className = "dot " + st;
      detail.textContent = info.detail || st;
      if(info.elapsed > 0) elapsed.textContent = info.elapsed.toFixed(1)+"s";
      else elapsed.textContent = st === "running" ? "…" : "";
    });
  }

  // ── Init phase timeline (once) ─────
  let phaseElements = [];
  function initPhaseTimeline() {
    const tl = $("phaseTimeline");
    const frag = document.createDocumentFragment();
    PHASES.forEach((p, i) => {
      const item = document.createElement("div");
      item.className = "phase-item";
      item.dataset.phase = p.value;
      item.innerHTML = `<span class="phase-name">${p.label}</span>`;
      frag.appendChild(item);
      phaseElements.push(item);
    });
    tl.appendChild(frag);
  }

  // ── Update phase timeline (class toggle only) ──
  let currentPhase = "";
  function updatePhase(current){
    if (current === currentPhase) return;
    currentPhase = current;

    scheduleUpdate(() => {
      let found = false;
      for (let i = 0; i < phaseElements.length; i++) {
        const el = phaseElements[i];
        el.classList.remove("active", "completed");
        if (el.dataset.phase === current) {
          el.classList.add("active");
          found = true;
        } else if (!found) {
          el.classList.add("completed");
        }
      }
      $("phaseBadge").textContent = (PHASES.find(p=>p.value===current)||{}).label || current;
    });
  }

  // ── Update metrics panel ───────────
  function updateMetrics(m){
    if(!m) return;
    scheduleUpdate(() => {
      $("mTokens").textContent = (m.total_tokens||0).toLocaleString();
      $("mCalls").textContent = m.llm_calls || m.calls || 0;
      $("mFiles").textContent = m.files_written || 0;
      $("mTime").textContent = (m.cycle_time||0).toFixed(1)+"s";
      if(m.tests_total > 0) $("mTests").textContent = m.tests_passed+"/"+m.tests_total;
      if(m.review_score > 0) $("mReview").textContent = m.review_score.toFixed(0)+"/10";
    });
  }

  // ── Update cycle chart ─────────────
  function updateChart(history){
    scheduleUpdate(() => {
      const bars = $("chartBars");
      if(!history||!history.length){ bars.innerHTML="<span style='color:var(--fg3);font-size:11px'>No data yet</span>"; return; }
      const slice = history.slice(-30);
      const maxTime = Math.max(...slice.map(h=>h.cycle_time||1), 1);
      const frag = document.createDocumentFragment();
      slice.forEach(h => {
        const pct = Math.max(5, ((h.cycle_time||0)/maxTime)*100);
        const bar = document.createElement("div");
        bar.className = "chart-bar";
        bar.style.height = pct+"%";
        bar.innerHTML = `<div class="tooltip">#${h.cycle} · ${(h.cycle_time||0).toFixed(1)}s · ${((h.tokens||{}).total||0).toLocaleString()} tok</div>`;
        frag.appendChild(bar);
      });
      bars.innerHTML = "";
      bars.appendChild(frag);
    });
  }

  // ── Add log entries (batched) ──────
  const CAT_ICONS = {agent_start:"▶",agent_end:"✓",error:"✕",warning:"⚠",phase_change:"◆",info:"·",debug:"·",cycle_header:"─",cycle_summary:"📊",progress:"→"};
  let pendingLogs = [];
  let logRafScheduled = false;

  function addLog(entry){
    pendingLogs.push(entry);
    logCount++;
    if (!logRafScheduled) {
      logRafScheduled = true;
      requestAnimationFrame(flushLogs);
    }
  }

  function flushLogs() {
    logRafScheduled = false;
    const entries = pendingLogs;
    pendingLogs = [];
    if (!entries.length) return;

    // Trim excess before adding
    const totalAfter = logBody.childElementCount + entries.length;
    if (totalAfter > MAX_LOGS) {
      const toRemove = totalAfter - MAX_LOGS;
      for (let i = 0; i < toRemove && logBody.firstChild; i++) {
        logBody.removeChild(logBody.firstChild);
      }
    }

    // Build all new entries in a DocumentFragment
    const frag = document.createDocumentFragment();
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i];
      const div = document.createElement("div");
      div.className = "log-entry " + (entry.category||"info");
      const ts = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : "";
      div.innerHTML = `<span class="log-ts">${ts}</span><span class="log-cat">${CAT_ICONS[entry.category]||"·"}</span><span class="log-msg">${escHtml(entry.message||"")}</span>`;
      frag.appendChild(div);
    }
    logBody.appendChild(frag);

    logCountEl.textContent = Math.min(logCount, MAX_LOGS) + " entries";
    if(autoScroll) logBody.scrollTop = logBody.scrollHeight;
  }

  function escHtml(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

  // ── Detect auto-scroll ─────────────
  logBody.addEventListener("scroll", () => {
    const gap = logBody.scrollHeight - logBody.scrollTop - logBody.clientHeight;
    autoScroll = gap < 40;
  }, {passive: true});

  // ── Load initial state ──────────────
  async function loadState(){
    try{
      const r = await fetch("/api/state");
      const d = await r.json();
      state = d;
      $("goal").textContent = d.goal || "—";
      $("workspace").textContent = d.workspace || "—";
      $("cycleNum").textContent = "#"+(d.cycle||0);
      updatePhase(d.phase||"initial");
      if(d.agents){
        Object.entries(d.agents).forEach(([name,info])=>updateAgent(name,info));
      }
      if(d.metrics) updateMetrics(d.metrics);
    }catch(e){ console.warn("loadState error:",e); }
  }

  async function loadLogs(){
    try{
      const r = await fetch("/api/logs");
      const d = await r.json();
      (d.logs||[]).forEach(addLog);
    }catch(e){}
  }

  async function loadHistory(){
    try{
      const r = await fetch("/api/metrics");
      const d = await r.json();
      updateChart(d.cycles||[]);
    }catch(e){}
  }

  // ── SSE Connection ─────────────────
  let evtSource = null;
  let reconnectDelay = 1000;
  let reconnectTimer = null;

  function connectSSE(){
    if(evtSource){
      evtSource.close();
      evtSource = null;
    }
    if(reconnectTimer){
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    evtSource = new EventSource("/events");

    evtSource.onopen = () => {
      $("connBanner").classList.remove("show");
      $("statusDot").style.background = "var(--green)";
      $("statusLabel").textContent = "Connected";
      reconnectDelay = 1000;
    };

    evtSource.addEventListener("state", (e) => {
      const d = JSON.parse(e.data);
      if(d.cycle) scheduleUpdate(() => { $("cycleNum").textContent = "#"+d.cycle; });
      if(d.phase) updatePhase(d.phase);
      if(d.goal) scheduleUpdate(() => { $("goal").textContent = d.goal; });
    });

    evtSource.addEventListener("agent", (e) => {
      const d = JSON.parse(e.data);
      updateAgent(d.name, d);
    });

    evtSource.addEventListener("log", (e) => {
      const d = JSON.parse(e.data);
      addLog(d);
    });

    evtSource.addEventListener("metrics", (e) => {
      const d = JSON.parse(e.data);
      updateMetrics(d);
    });

    evtSource.addEventListener("cycle_start", (e) => {
      const d = JSON.parse(e.data);
      scheduleUpdate(() => {
        $("cycleNum").textContent = "#"+(d.iteration||0);
      });
      // Reset agents
      AGENTS.forEach(name => updateAgent(name, {state:"idle",detail:"idle",elapsed:0}));
    });

    evtSource.addEventListener("cycle_end", (e) => {
      const d = JSON.parse(e.data);
      if(d.metrics) updateMetrics(d.metrics);
      loadHistory();
    });

    evtSource.onerror = () => {
      $("connBanner").classList.add("show");
      $("statusDot").style.background = "var(--red)";
      $("statusLabel").textContent = "Disconnected";
      evtSource.close();
      evtSource = null;
      reconnectTimer = setTimeout(connectSSE, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
    };
  }

  // ── Init ────────────────────────────
  initAgents();
  initPhaseTimeline();
  loadState().then(()=>{
    loadLogs();
    loadHistory();
    connectSSE();
  });
})();
</script>
</body>
</html>
"""
