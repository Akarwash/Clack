// Clack Trainer teleprompter behavior.
//
// The browser is only a teleprompter: it shows random characters, paces the
// typist, and advances its own highlight on keydown. It NEVER sends keystrokes
// as labels. The Python backend captures audio and key events on one clock and
// owns all labeling (see BUILD_TRAINER section 2).
//
// Owner: BUILD_TRAINER. Talks to the trainer routes wired in server.py.
"use strict";

(function () {
  var KEY_SET = "abcdefghijklmnopqrstuvwxyz0123456789".split("").concat(["space"]);
  var QUOTA = { train: 40, eval: 10, demo: 0 };
  var PACED_GAP_MS = 550;

  var state = {
    purpose: "train",
    mode: "paced",
    running: false,
    sessionId: null,
    seq: [],
    pos: 0,
    counts: {},
    captured: 0,
    startedAt: 0,
    metroTimer: null,
    clockTimer: null,
    levelTimer: null,
    stalled: false,
  };

  function $(id) { return document.getElementById(id); }

  function safeGet(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function safeSet(key, val) {
    try { window.localStorage.setItem(key, val); } catch (e) { /* ignore */ }
  }

  function resetCounts() {
    state.counts = {};
    KEY_SET.forEach(function (k) { state.counts[k] = 0; });
  }

  function renderCoverage() {
    var quota = QUOTA[state.purpose];
    var grid = $("coverage");
    grid.innerHTML = "";
    var met = 0;
    KEY_SET.forEach(function (k) {
      var c = state.counts[k] || 0;
      var cell = document.createElement("div");
      cell.className = "cell";
      var pct = quota > 0 ? Math.min(100, (c / quota) * 100) : 0;
      if (quota > 0 && c >= quota) { cell.classList.add("met"); met += 1; }
      else if (quota > 0) { cell.classList.add("under"); }
      var label = k === "space" ? "␣" : k;
      var target = quota > 0 ? "/" + quota : "";
      cell.innerHTML =
        '<div class="fill" style="width:' + pct + '%"></div>' +
        '<span class="k">' + label + '</span> ' +
        '<span class="c">' + c + target + "</span>";
      grid.appendChild(cell);
    });
    $("statCov").textContent = met + "/" + KEY_SET.length;
    return met;
  }

  function renderPaced() {
    var done = state.seq.slice(Math.max(0, state.pos - 3), state.pos)
      .map(function (c) { return c === "space" ? "␣" : c; }).join(" ");
    var cur = state.seq[state.pos];
    var next = state.seq.slice(state.pos + 1, state.pos + 4)
      .map(function (c) { return c === "space" ? "␣" : c; }).join(" ");
    $("pacedDone").textContent = done;
    $("pacedCur").textContent = cur === "space" ? "␣" : (cur || "✓");
    $("pacedNext").textContent = next;
  }

  function renderFlow() {
    var el = $("flowLine");
    el.innerHTML = "";
    var from = Math.max(0, state.pos - 8);
    var to = Math.min(state.seq.length, state.pos + 24);
    for (var i = from; i < to; i++) {
      var span = document.createElement("span");
      var ch = state.seq[i] === "space" ? "␣" : state.seq[i];
      span.textContent = ch + " ";
      if (i === state.pos) { span.className = "cur"; }
      else if (i < state.pos) { span.className = "good"; }
      else { span.className = "up"; }
      el.appendChild(span);
    }
  }

  function render() {
    if (state.mode === "paced") { renderPaced(); } else { renderFlow(); }
    $("statKeys").textContent = state.captured;
    var elapsed = state.running ? (Date.now() - state.startedAt) / 1000 : 0;
    $("statElapsed").textContent = Math.round(elapsed) + "s";
    if (state.mode === "flow" && elapsed > 0) {
      $("statWpm").textContent = Math.round((state.captured / 5) / (elapsed / 60));
    } else {
      $("statWpm").textContent = "-";
    }
  }

  function toPct(rms) {
    // dB meter: map -60 dB..-10 dB to 0..100%.
    var db = 20 * Math.log10(rms + 1e-9);
    return Math.max(0, Math.min(100, (db + 60) / 50 * 100));
  }

  async function pollLevel() {
    if (!state.running || !state.sessionId) { return; }
    var bar = document.getElementById("micBar");
    var txt = document.getElementById("micText");
    var hint = document.getElementById("micHint");
    var marker = document.getElementById("micTarget");
    try {
      var r = await fetch("/trainer/level?session_id=" + encodeURIComponent(state.sessionId));
      var d = await r.json();
      if (!d.active) { return; }
      var rms = d.rms || 0;
      var pct = toPct(rms);
      var target = d.target_rms || 0;

      // Position the target-hardness marker line.
      if (target > 0 && marker) {
        marker.style.left = toPct(target).toFixed(0) + "%";
        marker.style.display = "block";
      }

      var silent = d.silent_s == null ? 999 : d.silent_s;
      if (silent >= 1.0) {
        // The mic stream has stalled (no audio blocks arriving).
        state.stalled = true;
        bar.style.width = "100%";
        bar.style.background = "var(--accent)";
        txt.style.color = "var(--accent)";
        txt.textContent = "MIC STALLED — no input for " + silent.toFixed(1) + "s. STOP and re-record.";
        if (hint) { hint.textContent = ""; }
      } else {
        if (state.stalled) { state.stalled = false; }
        bar.style.width = pct.toFixed(0) + "%";
        txt.style.color = "var(--muted)";
        var db = 20 * Math.log10(rms + 1e-9);
        txt.textContent = "listening · " + (db > -60 ? db.toFixed(0) + " dB" : "quiet");
        // Hardness feedback: only when a keystroke was captured this window.
        if (hint && target > 0) {
          if (rms > target * 0.35) {
            if (rms >= target * 0.85) {
              bar.style.background = "var(--good)";
              hint.style.color = "var(--good)";
              hint.textContent = "on target ✓";
            } else {
              bar.style.background = "var(--warn)";
              hint.style.color = "var(--warn)";
              hint.textContent = "press harder";
            }
          } else {
            bar.style.background = "var(--good)";
            // keep the last hint during the gap between keystrokes
          }
        } else {
          bar.style.background = "var(--good)";
        }
      }
    } catch (e) { /* transient; keep polling */ }
  }

  function startMetronome() {
    if (state.mode !== "paced") { return; }
    var fill = $("metroFill");
    var t0 = Date.now();
    clearInterval(state.metroTimer);
    state.metroTimer = setInterval(function () {
      var pct = Math.min(100, ((Date.now() - t0) % PACED_GAP_MS) / PACED_GAP_MS * 100);
      fill.style.width = pct + "%";
    }, 16);
    fill.__reset = function () { t0 = Date.now(); };
  }

  async function fetchMoreIfNeeded() {
    if (state.pos < state.seq.length - 2) { return; }
    try {
      var r = await fetch("/trainer/prompt?n=200&mode=" + state.mode);
      var data = await r.json();
      state.seq = state.seq.concat(data.chars || []);
    } catch (e) { /* keep going with what we have */ }
  }

  async function onKeydown(ev) {
    if (!state.running) { return; }
    var expected = state.seq[state.pos];
    if (!expected) { return; }
    var pressed = ev.key === " " ? "space" : ev.key.toLowerCase();
    if (ev.key === "Backspace" || ev.key.length > 1 && ev.key !== " ") {
      // Ignore non-character control keys for UI purposes.
      if (ev.key === " ") { /* fallthrough */ } else { return; }
    }
    ev.preventDefault();

    // The UI counts coverage; the backend owns the true labels.
    if (state.counts.hasOwnProperty(pressed)) {
      state.counts[pressed] = (state.counts[pressed] || 0) + 1;
    }
    state.captured += 1;
    state.pos += 1;

    var fill = $("metroFill");
    if (fill && fill.__reset) { fill.__reset(); }

    await fetchMoreIfNeeded();
    var met = renderCoverage();
    render();

    var quota = QUOTA[state.purpose];
    if (quota > 0 && met === KEY_SET.length) {
      await stop("coverage complete");
    }
  }

  function activeSeg(groupId, value) {
    var group = $(groupId);
    Array.prototype.forEach.call(group.children, function (btn) {
      btn.classList.toggle("on", btn.getAttribute("data-v") === value);
    });
  }

  async function start() {
    var keyboard = $("keyboard").value.trim() || "blue";
    var typist = $("typist").value.trim();
    if (!typist) { $("summary").textContent = "Enter a typist name first."; return; }
    safeSet("clack_keyboard", keyboard);
    safeSet("clack_typist", typist);

    var mic = $("mic").value;
    var body = {
      keyboard_id: keyboard,
      typist: typist,
      purpose: state.purpose,
      mode: state.mode,
    };
    if (mic !== "") { body.device = parseInt(mic, 10); }

    try {
      var r = await fetch("/trainer/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) { throw new Error("start failed: " + r.status); }
      var data = await r.json();
      state.sessionId = data.session_id;
    } catch (e) {
      $("summary").textContent = "Could not start session: " + e.message;
      return;
    }

    var quota = QUOTA[state.purpose] || 40;
    var n = state.purpose === "demo" ? 120 : quota * KEY_SET.length;
    try {
      var pr = await fetch("/trainer/prompt?n=" + n + "&mode=" + state.mode);
      var pd = await pr.json();
      state.seq = pd.chars || [];
    } catch (e) {
      state.seq = [];
    }

    state.running = true;
    state.pos = 0;
    state.captured = 0;
    state.startedAt = Date.now();
    resetCounts();

    $("startBtn").disabled = true;
    $("stopBtn").classList.remove("hidden");
    $("stageHint").classList.add("hidden");
    $("summary").textContent = "";
    $("pacedLine").classList.toggle("hidden", state.mode !== "paced");
    $("metronome").classList.toggle("hidden", state.mode !== "paced");
    $("flowLine").classList.toggle("hidden", state.mode === "paced");

    renderCoverage();
    render();
    startMetronome();
    clearInterval(state.clockTimer);
    state.clockTimer = setInterval(render, 250);
    clearInterval(state.levelTimer);
    state.stalled = false;
    state.levelTimer = setInterval(pollLevel, 150);
  }

  async function stop(note) {
    if (!state.running) { return; }
    state.running = false;
    clearInterval(state.metroTimer);
    clearInterval(state.clockTimer);
    clearInterval(state.levelTimer);
    var micTxt = document.getElementById("micText");
    var micBar = document.getElementById("micBar");
    var micHint = document.getElementById("micHint");
    if (micTxt) { micTxt.textContent = "idle"; micTxt.style.color = "var(--muted)"; }
    if (micBar) { micBar.style.width = "0%"; micBar.style.background = "var(--good)"; }
    if (micHint) { micHint.textContent = ""; }
    $("startBtn").disabled = false;
    $("stopBtn").classList.add("hidden");

    var summary = "";
    try {
      var r = await fetch("/trainer/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId }),
      });
      var data = await r.json();
      summary =
        (data.warning ? "⚠ " + data.warning + "\n\n" : "") +
        (note ? note + "\n" : "") +
        "saved " + data.n_events + " events, " +
        (Math.round((data.duration_s || 0) * 10) / 10) + "s audio" +
        (data.expected_duration_s ? " (keypresses span " + Math.round(data.expected_duration_s) + "s)" : "") +
        "\npath: " + data.path;
    } catch (e) {
      summary = "Stop failed: " + e.message;
    }
    $("summary").textContent = summary;
  }

  async function loadDevices() {
    try {
      var r = await fetch("/devices");
      var devices = await r.json();
      var sel = $("mic");
      devices.forEach(function (d) {
        var opt = document.createElement("option");
        opt.value = d.index;
        opt.textContent = d.name;
        sel.appendChild(opt);
      });
    } catch (e) { /* default option remains */ }
  }

  function wire() {
    $("purpose").addEventListener("click", function (ev) {
      var v = ev.target.getAttribute("data-v");
      if (v) { state.purpose = v; activeSeg("purpose", v); renderCoverage(); }
    });
    $("mode").addEventListener("click", function (ev) {
      var v = ev.target.getAttribute("data-v");
      if (v) { state.mode = v; activeSeg("mode", v); }
    });
    $("startBtn").addEventListener("click", start);
    $("stopBtn").addEventListener("click", function () { stop("stopped"); });
    document.addEventListener("keydown", onKeydown);

    var kb = safeGet("clack_keyboard");
    var tp = safeGet("clack_typist");
    if (kb) { $("keyboard").value = kb; }
    if (tp) { $("typist").value = tp; }

    resetCounts();
    renderCoverage();
    loadDevices();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
