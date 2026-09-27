/* Shared speaker / virtual-mic controls. Device IDs from browsers never go to
 * PortAudio; bridge selections use backend-validated aggregate names. */
(function () {
  "use strict";
  const host = document.getElementById("protectionControls");
  if (!host) return;
  host.innerHTML = `
    <div class="toggle-row" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
      <label>Protection <select id="protectionMode"><option value="virtual">Virtual Mic</option><option value="speaker">Speaker Masker</option></select></label>
      <button class="btn secbtn" id="protectionToggle">Start virtual mic</button>
    </div>
    <div id="virtualRoute" style="margin:10px 0">
      <label>Bridge <select id="bridgeDevice"></select></label>
      <button class="btn ghost secbtn" id="refreshBridge">Refresh route</button>
    </div>
    <label style="display:block;margin:10px 0">Masking level <input id="protectionLevel" type="range" min="0.1" max="1" step="0.1" value="0.3"> <span id="protectionLevelValue">0.3</span></label>
    <p id="protectionState" class="note status" role="status" aria-live="polite">Checking route…</p>
    <div id="virtualMeters">Raw mic <meter id="virtualInputMeter" min="0" max="1" value="0"></meter> Sent to BlackHole <meter id="virtualOutputMeter" min="0" max="1" value="0"></meter><p id="virtualStats" class="note status"></p></div>
    <p id="virtualConsumer" class="note">Select <strong>BlackHole 2ch</strong> as the microphone in the receiving app and in the recording selector. The physical mic is unchanged. When stopped, the virtual stream is silent.</p>
    <details id="virtualSetup"><summary>One-time macOS setup</summary>
      <ol><li>Install <a href="https://existential.audio/blackhole/" target="_blank" rel="noreferrer">BlackHole 2ch</a>, then restart Clack and the receiving app.</li>
      <li>In Audio MIDI Setup, create an aggregate named <strong>Clack Protected Bridge</strong>.</li>
      <li>Include only your input-only physical microphone <strong>first</strong> and BlackHole 2ch <strong>second</strong>. Do not include speakers.</li>
      <li>Set both members and the aggregate to <strong>44.1 kHz</strong>. Use the physical mic as clock source and enable drift correction for BlackHole.</li>
      <li>Refresh the route, start Virtual Mic, then select BlackHole 2ch in the recording or calling app.</li></ol>
      <p>Noise and fake clicks are added to the transmitted audio. Suppression is future work. Nearby independent microphones are not protected.</p>
    </details>`;
  const $ = (id) => document.getElementById(id);
  let state = { running: false, speaker_on: false }, ready = false, busy = false;
  async function request(url, body) {
    const response = await fetch(url, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || "Request failed");
    return data;
  }
  function render() {
    const virtual = $("protectionMode").value === "virtual";
    $("virtualRoute").hidden = !virtual;
    $("virtualMeters").hidden = !virtual;
    $("virtualConsumer").hidden = !virtual;
    $("virtualSetup").hidden = !virtual;
    const on = virtual ? state.running : state.speaker_on;
    $("protectionMode").disabled = busy || state.running || state.speaker_on;
    $("bridgeDevice").disabled = busy || state.running;
    $("protectionToggle").disabled = busy || (virtual && !ready && !on);
    $("protectionToggle").textContent = on ? (virtual ? "Stop virtual mic" : "Stop speaker masker") : (virtual ? "Start virtual mic" : "Start speaker masker");
    $("virtualInputMeter").value = state.input_rms || 0;
    $("virtualOutputMeter").value = state.output_rms || 0;
    $("virtualStats").textContent = state.running ? `Audio stream latency: ${state.latency_ms ?? "unknown"} ms · limited samples: ${((state.limited_fraction || 0) * 100).toFixed(2)}% · stream errors: ${state.stream_errors || 0}` : "";
  }
  async function refreshDevices() {
    try {
      const data = await request("/virtual-mic/devices");
      const previous = $("bridgeDevice").value;
      $("bridgeDevice").replaceChildren();
      data.routes.forEach(r => {
        const option = new Option(r.bridge_device + (r.ready ? "" : " (setup incomplete)"), r.bridge_device);
        option.disabled = !r.ready;
        $("bridgeDevice").add(option);
      });
      ready = data.routes.some(r => r.ready);
      if (!ready) $("bridgeDevice").add(new Option("No validated bridge", ""));
      if (data.routes.some(r => r.ready && r.bridge_device === previous)) $("bridgeDevice").value = previous;
      if (!state.running && $("protectionMode").value === "virtual") {
        $("protectionState").textContent = ready ? "Ready to route. Receiving apps must select BlackHole 2ch." :
          (data.detail || data.routes.find(r => r.detail)?.detail || (data.blackhole_installed ? "Create the aggregate device using the setup instructions below." : "BlackHole 2ch is not installed. Complete the one-time setup below."));
      }
      render();
    } catch(e) { $("protectionState").textContent = e.message; }
  }
  async function refreshStatus() {
    try {
      const response = await fetch("/virtual-mic/status");
      if (!response.ok) throw new Error("Could not read protection status");
      state = await response.json();
      window.dispatchEvent(new CustomEvent("clack-protection-status", { detail: state }));
      if (state.running) $("protectionMode").value = "virtual";
      else if (state.speaker_on) $("protectionMode").value = "speaker";
      if (state.running) {
        $("protectionState").textContent = `Routing: ${state.input_device} → noise + fake clicks → BlackHole 2ch. Consumer selection is not verified.`;
      } else if (state.error && $("protectionMode").value === "virtual") {
        $("protectionState").textContent = `Stopped: ${state.error}. Virtual output is silent.`;
      } else if ($("protectionMode").value === "speaker") {
        $("protectionState").textContent = state.speaker_on ? "Masking is playing through the speakers." : "Speaker masker is off.";
      }
      render();
    } catch(e) { $("protectionState").textContent = e.message; $("protectionToggle").disabled = true; }
  }
  $("protectionToggle").addEventListener("click", async () => {
    busy = true; render();
    try {
      const virtual = $("protectionMode").value === "virtual";
      const on = virtual ? state.running : state.speaker_on;
      const level = Number($("protectionLevel").value);
      await request(virtual ? (on ? "/virtual-mic/stop" : "/virtual-mic/start") : (on ? "/defense/off" : "/defense/on"),
        on ? {} : (virtual ? { bridge_device: $("bridgeDevice").value, level } : { level }));
      $("protectionState").textContent = on ? (virtual ? "Virtual mic stopped; output is silent." : "Speaker masker stopped.") : "Starting…";
      await refreshStatus();
    } catch(e) { $("protectionState").textContent = e.message; }
    finally { busy = false; render(); }
  });
  $("protectionLevel").addEventListener("input", () => { $("protectionLevelValue").textContent = $("protectionLevel").value; });
  $("protectionLevel").addEventListener("change", async () => {
    try {
      const level = Number($("protectionLevel").value);
      if (state.running) await request("/virtual-mic/settings", { level });
      else if (state.speaker_on) await request("/defense/on", { level });
    } catch(e) { $("protectionState").textContent = e.message; }
  });
  $("protectionMode").addEventListener("change", () => { render(); refreshDevices(); refreshStatus(); });
  $("refreshBridge").addEventListener("click", refreshDevices);
  // Prevent a nominally protected test from accidentally recording the raw mic.
  window.ClackProtection = {
    async checkRecordingDevice(deviceId) {
      const current = await fetch("/virtual-mic/status").then(r => r.json());
      if (!current.running) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const selected = devices.find(d => d.kind === "audioinput" && d.deviceId === deviceId);
      if (!selected || !/BlackHole 2ch/.test(selected.label)) {
        throw new Error("Virtual Mic is running: select BlackHole 2ch explicitly. Refresh microphone permissions if labels are missing.");
      }
    }
  };
  refreshDevices(); refreshStatus();
  setInterval(refreshStatus, 1000);
})();
