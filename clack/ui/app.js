// Clack attack dashboard.
//
// Editorial-minimal dashboard driven by the attack WebSocket. A single
// requestAnimationFrame loop reads the latest state and redraws the canvas
// visuals; the socket handler only updates state and never draws, so rendering
// can never slow the decode (the decode runs on the backend). No CDN, no build
// step. See BUILD_FRONTEND.md.
//
// Owner: BUILD_FRONTEND.
"use strict";

(function () {
  var KEY_ROWS = [
    "1234567890",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    " ",
  ];

  var state = {
    running: false,
    ws: null,
    raw: [],          // [{ch, conf}]
    corrected: "",
    lattice: [],      // per-press candidate key lists (for correction + search space)
    kbdHighlight: {}, // key -> 0..1
    lastKey: null,
    wave: new Float32Array(600),
    waveHead: 0,
    spec: [],         // array of columns, each Float32Array
    specMax: 90,
    conf3: [],        // current top-3 [[key,p]]
    theoreticalSpace: 1,
    reducedSpace: 1,
    shownSpace: 1,
    synthetic: false,
  };

  function $(id) { return document.getElementById(id); }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  // ---- Theme ---------------------------------------------------------------
  function applyTheme(theme) {
    if (theme === "dark") { document.documentElement.setAttribute("data-theme", "dark"); }
    else { document.documentElement.removeAttribute("data-theme"); }
    safeSet("clack_theme", theme);
  }
  function toggleTheme() {
    var cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    applyTheme(cur === "dark" ? "light" : "dark");
  }

  // ---- Status --------------------------------------------------------------
  async function refreshStatus() {
    try {
      var r = await fetch("/status");
      var s = await r.json();
      if (s.microphone) { $("srcMic").textContent = s.microphone.ok ? (s.microphone.name || "ACTIVE") : "unavailable"; }
      if (s.attack_keylogger) {
        $("srcKeys").textContent = s.attack_keylogger.state;
        $("srcKeys").className = "val " + (s.attack_keylogger.state === "DISABLED" ? "disabled" : "");
      }
      if (s.ambient_calibration) {
        $("srcAmbient").textContent = s.ambient_calibration.ok ? "calibrated" : "not calibrated";
        if (s.ambient_calibration.ok) { $("srcAmbient").classList.add("active"); }
      }
      if (s.compute) { $("srcCompute").textContent = s.compute.device || "-"; }
    } catch (e) { /* leave defaults */ }
  }

  // ---- Attack control ------------------------------------------------------
  function setLive(on) {
    state.running = on;
    $("liveDot").className = "status-dot" + (on ? " live" : "");
    $("liveLabel").textContent = on ? "LIVE" : "IDLE";
    $("startBtn").disabled = on;
    $("stopBtn").disabled = !on;
  }

  async function startAttack() {
    var synthetic = $("synthSrc").checked;
    state.synthetic = synthetic;
    $("synthBadge").style.display = synthetic ? "inline-block" : "none";
    var body = {
      source: synthetic ? "synthetic" : "mic",
      event_mode: $("cleanRun").checked,
    };
    var sel = $("modelSel").value;
    if (sel) { body.model_name = sel; }

    try {
      var r = await fetch("/attack/start", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      var data = await r.json();
      if (!data.ok) { $("defNote").textContent = "Could not start attack: " + (data.detail || "unknown"); return; }
    } catch (e) { $("defNote").textContent = "Could not start attack: " + e.message; return; }

    // reset recovered state
    state.raw = []; state.corrected = ""; state.lattice = [];
    $("rawText").innerHTML = ""; $("corrText").textContent = "";
    setLive(true);
    connectWs();
  }

  async function stopAttack() {
    try { await fetch("/attack/stop", { method: "POST" }); } catch (e) {}
    if (state.ws) { try { state.ws.close(); } catch (e) {} state.ws = null; }
    setLive(false);
  }

  function connectWs() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    var ws = new WebSocket(proto + "//" + location.host + "/ws/attack");
    state.ws = ws;
    ws.onmessage = function (ev) {
      var msg = JSON.parse(ev.data);
      if (msg.type === "key") { onKey(msg); }
      else if (msg.type === "status") { onStatusFrame(msg); }
      else if (msg.type === "audio") { onAudio(msg); }
      // heartbeat: ignore
    };
    ws.onclose = function () {
      if (state.running) { setTimeout(function () { if (state.running) { connectWs(); } }, 800); }
    };
  }

  function onStatusFrame(msg) {
    if (msg.microphone) { $("srcMic").textContent = msg.microphone === "mic" ? "ACTIVE" : msg.microphone; }
    if (msg.keylogger) {
      $("srcKeys").textContent = msg.keylogger;
      $("srcKeys").className = "val " + (msg.keylogger.indexOf("DISABLED") >= 0 ? "disabled" : "");
    }
  }

  async function onKey(msg) {
    // The socket handler only updates state; drawing happens in the rAF loop.
    state.raw.push({ ch: msg.key === "space" ? " " : msg.key, conf: msg.confidence || 0 });
    state.conf3 = (msg.topk || []).slice(0, 3);
    state.lastKey = msg.key;
    state.kbdHighlight[msg.key] = 1.0;

    // Signal-activity pulse (a visualization of decode activity, not the raw mic).
    pushWavePulse(msg.confidence || 0.5);
    pushSpecColumn(msg.confidence || 0.5);

    // Candidate lattice for correction and search-space collapse.
    var cand = (msg.topk || []).map(function (t) { return t[0]; });
    if (cand.length) { state.lattice.push(cand); }
    updateSearchSpace();
    renderRaw();
    requestCorrection();
    renderConf();
  }

  function onAudio(msg) {
    // If the backend streams real audio frames, render them instead of pulses.
    if (msg.waveform && msg.waveform.length) {
      var w = msg.waveform;
      for (var i = 0; i < w.length; i++) {
        state.wave[state.waveHead] = w[i];
        state.waveHead = (state.waveHead + 1) % state.wave.length;
      }
    }
    if (msg.spectrogram && msg.spectrogram.length) {
      for (var c = 0; c < msg.spectrogram.length; c++) {
        state.spec.push(Float32Array.from(msg.spectrogram[c]));
      }
      while (state.spec.length > 240) { state.spec.shift(); }
    }
  }

  function pushWavePulse(conf) {
    // Inject a short decaying pulse into the ring buffer.
    var n = 40;
    for (var i = 0; i < n; i++) {
      var v = Math.sin(i / 3) * Math.exp(-i / 12) * (0.4 + conf * 0.6);
      state.wave[state.waveHead] = v;
      state.waveHead = (state.waveHead + 1) % state.wave.length;
    }
  }

  function pushSpecColumn(conf) {
    var col = new Float32Array(48);
    for (var i = 0; i < col.length; i++) {
      col[i] = Math.max(0, (1 - i / col.length) * conf + (Math.random() - 0.5) * 0.15);
    }
    state.spec.push(col);
    while (state.spec.length > 240) { state.spec.shift(); }
  }

  var correctPending = false;
  async function requestCorrection() {
    if (correctPending || state.lattice.length === 0) { return; }
    correctPending = true;
    try {
      var r = await fetch("/correct", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lattice: state.lattice }),
      });
      var data = await r.json();
      state.corrected = data.text || "";
      $("corrText").textContent = state.corrected;
    } catch (e) { /* corrected line stays as-is */ }
    correctPending = false;
  }

  function updateSearchSpace() {
    var n = state.lattice.length;
    if (n === 0) { return; }
    state.theoreticalSpace = Math.pow(37, n);
    var reduced = 1;
    for (var i = 0; i < n; i++) { reduced *= Math.min(3, state.lattice[i].length || 1); }
    state.reducedSpace = reduced;
  }

  // ---- Rendering (single rAF loop) ----------------------------------------
  function renderRaw() {
    var el = $("rawText");
    el.innerHTML = "";
    var warn = cssVar("--warn"), good = cssVar("--good");
    state.raw.forEach(function (c) {
      var span = document.createElement("span");
      span.className = "ch";
      span.textContent = c.ch === " " ? "␣" : c.ch;
      span.style.color = lerpColor(warn, good, c.conf);
      el.appendChild(span);
    });
  }

  function renderConf() {
    var box = $("confBars");
    box.innerHTML = "";
    var accent = cssVar("--accent"), ink = cssVar("--ink");
    state.conf3.forEach(function (pair, idx) {
      var row = document.createElement("div");
      row.className = "bar-row";
      var label = pair[0] === "space" ? "␣" : pair[0];
      var pct = Math.round((pair[1] || 0) * 100);
      row.innerHTML =
        '<span class="micro">' + label + " &middot; " + pct + '%</span>' +
        '<div class="bar-track"><div class="bar-fill" style="width:' + pct + "%;background:" +
        (idx === 0 ? accent : ink) + '"></div></div>';
      box.appendChild(row);
    });
  }

  function fitCanvas(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth, h = canvas.clientHeight || parseInt(canvas.getAttribute("height"), 10);
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr); canvas.height = Math.floor(h * dpr);
    }
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }

  function drawWave() {
    var c = $("waveCanvas"); var g = fitCanvas(c); var ctx = g.ctx;
    ctx.clearRect(0, 0, g.w, g.h);
    ctx.strokeStyle = cssVar("--ink"); ctx.lineWidth = 1; ctx.beginPath();
    var mid = g.h / 2;
    for (var x = 0; x < g.w; x++) {
      var idx = Math.floor((x / g.w) * state.wave.length);
      var v = state.wave[(state.waveHead + idx) % state.wave.length] || 0;
      var y = mid - v * (g.h * 0.42);
      if (x === 0) { ctx.moveTo(x, y); } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    // decay the buffer slowly so it settles when idle
    for (var i = 0; i < state.wave.length; i++) { state.wave[i] *= 0.985; }
  }

  function drawSpec() {
    var c = $("specCanvas"); var g = fitCanvas(c); var ctx = g.ctx;
    ctx.clearRect(0, 0, g.w, g.h);
    var cols = state.spec.length; if (cols === 0) { return; }
    var colW = g.w / 240;
    var accent = hexToRgb(cssVar("--accent")), ink = hexToRgb(cssVar("--ink"));
    for (var i = 0; i < cols; i++) {
      var col = state.spec[i];
      var x = g.w - (cols - i) * colW;
      for (var j = 0; j < col.length; j++) {
        var v = Math.max(0, Math.min(1, col[j]));
        var rgb = mixRgb(ink, accent, v);
        ctx.fillStyle = "rgba(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + "," + (0.15 + v * 0.85) + ")";
        var y = g.h - (j + 1) * (g.h / col.length);
        ctx.fillRect(x, y, Math.ceil(colW), Math.ceil(g.h / col.length));
      }
    }
  }

  function drawKeyboard() {
    var c = $("kbdCanvas"); var g = fitCanvas(c); var ctx = g.ctx;
    ctx.clearRect(0, 0, g.w, g.h);
    var line = cssVar("--line"), ink = cssVar("--ink"), accent = hexToRgb(cssVar("--accent"));
    var pad = 8, rows = KEY_ROWS.length;
    var keyH = (g.h - pad * (rows + 1)) / rows;
    for (var r = 0; r < rows; r++) {
      var rowKeys = KEY_ROWS[r].split("");
      var kw = (g.w - pad * (rowKeys.length + 1)) / rowKeys.length;
      for (var k = 0; k < rowKeys.length; k++) {
        var key = rowKeys[k] === " " ? "space" : rowKeys[k];
        var x = pad + k * (kw + pad);
        var y = pad + r * (keyH + pad);
        var hl = state.kbdHighlight[key] || 0;
        ctx.strokeStyle = line; ctx.lineWidth = 1;
        ctx.strokeRect(x, y, kw, keyH);
        if (hl > 0.01) {
          ctx.fillStyle = "rgba(" + accent[0] + "," + accent[1] + "," + accent[2] + "," + hl + ")";
          ctx.fillRect(x, y, kw, keyH);
        }
        ctx.fillStyle = ink; ctx.font = "12px " + cssVar("--font-mono");
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(rowKeys[k] === " " ? "space" : rowKeys[k], x + kw / 2, y + keyH / 2);
      }
    }
    // decay highlights
    for (var key2 in state.kbdHighlight) { state.kbdHighlight[key2] *= 0.90; }
  }

  function drawSearchSpace() {
    // Ease the shown value toward the reduced value.
    if (state.reducedSpace > 0) {
      state.shownSpace += (state.reducedSpace - state.shownSpace) * 0.12;
      var el = $("spaceNum");
      var val = state.shownSpace;
      el.textContent = val >= 1000 ? val.toExponential(1) : Math.round(val).toString();
      var frac = state.theoreticalSpace > 1
        ? Math.log(Math.max(1, state.reducedSpace)) / Math.log(state.theoreticalSpace) : 0;
      $("spaceBar").style.width = Math.round(frac * 100) + "%";
    }
  }

  function loop() {
    drawWave();
    drawSpec();
    drawKeyboard();
    drawSearchSpace();
    requestAnimationFrame(loop);
  }

  // ---- Defense / exposure / fleet -----------------------------------------
  var shieldOn = false;
  async function toggleShield() {
    try {
      if (!shieldOn) {
        var r = await fetch("/defense/on", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        var d = await r.json();
        shieldOn = !!d.ok && d.on;
        $("shieldState").textContent = shieldOn ? ("on, level " + d.level + ", band " + (d.band || []).join("-") + " Hz") : ("failed: " + (d.detail || ""));
        $("shieldBtn").textContent = shieldOn ? "Disarm shield" : "Arm shield";
      } else {
        await fetch("/defense/off", { method: "POST" });
        shieldOn = false;
        $("shieldState").textContent = "off";
        $("shieldBtn").textContent = "Arm shield";
      }
    } catch (e) { $("shieldState").textContent = "error: " + e.message; }
    refreshDefenseMeasure();
  }

  function renderDefense(d) {
    var off = Math.round((d.off || 0) * 100), on = Math.round((d.on || 0) * 100);
    $("offBar").style.width = off + "%";
    $("onBar").style.width = on + "%";
    var db = d.masker_key_ratio_db;
    $("defNote").textContent = "recovery " + off + "% to " + on + "%" +
      (db != null && isFinite(db) ? (", masker/key " + db.toFixed(1) + " dB") : "");
  }

  async function refreshDefenseMeasure() {
    try {
      var r = await fetch("/defense/measure");
      if (r.status === 404) { $("defNote").textContent = "No before/after measurement yet."; return; }
      renderDefense(await r.json());
    } catch (e) {}
  }

  async function runDefenseMeasure() {
    var sid = $("defSession").value;
    if (!sid) { $("defNote").textContent = "no session to measure on"; return; }
    $("defNote").textContent = "measuring before/after (simulated masker)...";
    try {
      var r = await fetch("/defense/measure", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid, model_name: $("modelSel").value }),
      });
      var d = await r.json();
      if (!d.ok) { $("defNote").textContent = "measure failed: " + (d.detail || ""); return; }
      renderDefense(d);
    } catch (e) { $("defNote").textContent = "measure error: " + e.message; }
  }

  async function loadModels() {
    try {
      var r = await fetch("/models"); var d = await r.json();
      var sel = $("modelSel"); sel.innerHTML = "";
      (d.models || []).forEach(function (m) {
        var o = document.createElement("option");
        o.value = m.name;
        o.textContent = m.type === "centroid" ? (m.name + " (floor)") : m.name;
        sel.appendChild(o);
      });
      if (d.default) sel.value = d.default;
    } catch (e) {}
  }

  async function loadSessions() {
    try {
      var r = await fetch("/sessions"); var d = await r.json();
      var sel = $("defSession"); sel.innerHTML = "";
      var list = d.sessions || [];
      if (!list.length) {
        var e0 = document.createElement("option"); e0.value = ""; e0.textContent = "no sessions"; sel.appendChild(e0);
        return;
      }
      list.forEach(function (s) {
        var o = document.createElement("option"); o.value = s.session_id; o.textContent = s.session_id; sel.appendChild(o);
      });
    } catch (e) {}
  }

  async function runExposure() {
    var sid = $("defSession").value;
    if (!sid) { $("reasons").innerHTML = "<li>no recorded session to audit</li>"; return; }
    $("reasons").innerHTML = "<li>running...</li>";
    // Audits the selected recorded session with the selected model. Without a
    // session or model the backend returns a clear error, surfaced honestly.
    try {
      var r = await fetch("/exposure/check", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid, model_name: $("modelSel").value, endpoint: "this-endpoint" }),
      });
      var d = await r.json();
      if (d.error) { $("reasons").innerHTML = "<li>" + d.error + "</li>"; return; }
      renderExposure(d);
      loadFleet();
    } catch (e) { $("reasons").innerHTML = "<li>" + e.message + "</li>"; }
  }

  function renderExposure(d) {
    $("grade").textContent = d.grade;
    $("grade").className = "grade " + d.grade;
    var ul = $("reasons"); ul.innerHTML = "";
    (d.reasons || []).forEach(function (r) { var li = document.createElement("li"); li.textContent = r; ul.appendChild(li); });
    (d.recommendations || []).forEach(function (r) { var li = document.createElement("li"); li.textContent = "→ " + r; ul.appendChild(li); });
  }

  async function loadExposureLast() {
    try { var r = await fetch("/exposure/last"); if (r.ok) { renderExposure(await r.json()); } } catch (e) {}
  }

  async function loadFleet() {
    try {
      var r = await fetch("/fleet"); var reports = await r.json();
      var ul = $("fleet"); ul.innerHTML = "";
      if (!reports.length) { ul.innerHTML = "<li>none</li>"; return; }
      reports.forEach(function (rep) {
        var li = document.createElement("li");
        li.textContent = (rep.machine_id || rep.endpoint || "endpoint") + " · grade " + (rep.grade || "?") +
          (rep.timestamp ? (" · " + rep.timestamp) : "");
        ul.appendChild(li);
      });
    } catch (e) {}
  }

  // ---- Color helpers -------------------------------------------------------
  function hexToRgb(hex) {
    hex = (hex || "#000000").replace("#", "");
    if (hex.length === 3) { hex = hex.split("").map(function (c) { return c + c; }).join(""); }
    return [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)];
  }
  function mixRgb(a, b, t) {
    return [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)];
  }
  function lerpColor(hexA, hexB, t) {
    var a = hexToRgb(hexA), b = hexToRgb(hexB), m = mixRgb(a, b, Math.max(0, Math.min(1, t)));
    return "rgb(" + m[0] + "," + m[1] + "," + m[2] + ")";
  }

  // ---- Wire up -------------------------------------------------------------
  function wire() {
    applyTheme(safeGet("clack_theme") === "dark" ? "dark" : "light");
    $("themeBtn").addEventListener("click", toggleTheme);
    document.addEventListener("keydown", function (e) {
      if ((e.key === "d" || e.key === "D") && e.target.tagName !== "INPUT") { toggleTheme(); }
    });
    $("startBtn").addEventListener("click", startAttack);
    $("stopBtn").addEventListener("click", stopAttack);
    $("shieldBtn").addEventListener("click", toggleShield);
    $("measureBtn").addEventListener("click", runDefenseMeasure);
    $("exposureBtn").addEventListener("click", runExposure);

    refreshStatus();
    loadModels();
    loadSessions();
    refreshDefenseMeasure();
    loadExposureLast();
    loadFleet();
    setInterval(refreshStatus, 4000);
    requestAnimationFrame(loop);
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", wire); }
  else { wire(); }
})();
