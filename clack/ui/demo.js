/* Clack Demo: record a clip, decode it with the chosen model, show the recovered
 * keystrokes, the language-model correction, and the password search-space
 * reduction. Audio and acoustic decoding stay local. Optional Claude correction
 * sends only candidate text and probabilities through the backend to Anthropic. Owner: BUILD_FRONTEND (demo surface). */
"use strict";

const $ = (id) => document.getElementById(id);
const modelSel = $("model");
const micSel = $("mic");
const recBtn = $("recBtn");
const statusEl = $("status");
const dot = $("dot");
const meterBar = $("meterBar");
const results = $("results");
const protectedSel = $("protectedMic");
const protectedResults = results.cloneNode(true);
protectedResults.id = "protectedResults";
protectedResults.querySelectorAll("[id]").forEach(el => { el.id = "protected_" + el.id; });
protectedResults.querySelector("h2").textContent = "Protected input (BlackHole)";
const comparison = document.createElement("div");
comparison.className = "comparison";
results.before(comparison);
comparison.append(results, protectedResults);

let correctOn = true;
let recordingGeneration = 0;
let correctionControllers = [];
let topN = 3;

// Human-readable notes for the known demo models (measured held-out numbers).
const MODEL_NOTES = {
  "dak": "All 3 typists, 1200 epochs (default). Held-out vs aditya: 95.6% top-1, 98.4% top-3.",
  "dak-1200": "All 3 typists, 1200 epochs. vs aditya: 95.6% top-1 (best).",
  "dak-900": "All 3 typists, 900 epochs. vs aditya: 95.3% top-1.",
  "dak-600": "All 3 typists, 600 epochs (sweet spot). vs aditya: 94.8% top-1.",
  "dak-300": "All 3 typists, 300 epochs. vs aditya: 92.2% top-1.",
  "dak-aditya": "Aditya's own typing only. Held-out vs aditya: 39% top-1, 70% top-3.",
  "dak-cold": "Cold attacker (josh+vishal, never heard aditya). True cross-typist vs aditya: 39% top-1, 69% top-3.",
};

function noteFor(m) {
  // Fresh checkpoints can replace a named model; prefer its own metadata.
  if (m.metrics && m.metrics.note) return String(m.metrics.note);
  if (MODEL_NOTES[m.name]) return MODEL_NOTES[m.name];
  if (m.type === "centroid") return "Nearest-centroid baseline (the accuracy floor).";
  const met = m.metrics || {};
  if (met.note) return String(met.note);
  if (typeof met.val_accuracy === "number") {
    const tag = met.val_is_trainfit ? "train-fit" : "held-out";
    return `${tag} top-1 ${(met.val_accuracy * 100).toFixed(1)}%`;
  }
  return "";
}

async function loadModels() {
  try {
    const res = await fetch("/models");
    const data = await res.json();
    modelSel.innerHTML = "";
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m.name;
      opt.textContent = m.type === "centroid" ? `${m.name} (floor)` : m.name;
      opt.dataset.note = noteFor(m);
      modelSel.appendChild(opt);
    }
    if (data.default) modelSel.value = data.default;
    updateHint();
  } catch (e) {
    statusEl.innerHTML = `<span class="err">could not load models: ${e}</span>`;
  }
}

function updateHint() {
  const opt = modelSel.selectedOptions[0];
  $("modelHint").textContent = opt ? opt.dataset.note || "" : "";
}

async function loadMics() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const inputs = devices.filter(d => d.kind === "audioinput" && d.deviceId && d.deviceId !== "default");
  const current = await fetch("/virtual-mic/status").then(r => r.json());
  const previous = micSel.value;
  micSel.replaceChildren(new Option("Choose physical microphone", ""));
  protectedSel.replaceChildren(new Option("BlackHole 2ch unavailable", ""));
  for (const d of inputs) {
    if (/BlackHole 2ch/.test(d.label)) {
      protectedSel.replaceChildren(new Option(d.label, d.deviceId));
    } else if (!/Clack Protected Bridge/.test(d.label)) {
      micSel.add(new Option(d.label || "Microphone (grant permission)", d.deviceId));
    }
  }
  const matched = inputs.find(d => d.label.includes(current.input_device || "HyperX SoloCast"));
  if ([...micSel.options].some(o => o.value === previous && previous)) micSel.value = previous;
  else if (matched) micSel.value = matched.deviceId;
  return { inputs, current };
}

// ---- segmented toggles ----
function wireSeg(id, cb) {
  $(id).querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      $(id).querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      cb(b.dataset.v);
    });
  });
}
wireSeg("correct", (v) => { correctOn = v === "on"; });
wireSeg("topn", (v) => { topN = parseInt(v, 10); });
modelSel.addEventListener("change", updateHint);

// ---- capture ----
let audioCtx = null, mediaStreams = [], sources = [], processor = null, merger = null;
let chunks = [[], []], capturing = false, recordingOptions = null, captureProblem = null;
window.addEventListener("clack-protection-status", e => {
  if (capturing && (!e.detail.running || e.detail.error)) captureProblem = "Protected route stopped during recording; repeat the comparison.";
});

async function startCapture() {
  captureProblem = null;
  try {
    // Grant access first so browser device labels can be matched to the validated route.
    const grant = await navigator.mediaDevices.getUserMedia({ audio: true });
    grant.getTracks().forEach(t => t.stop());
    let { inputs, current } = await loadMics();
    if (!current.running) {
      const response = await fetch("/virtual-mic/start", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bridge_device: $("bridgeDevice").value, level: Number($("protectionLevel").value) })
      });
      current = await response.json();
      if (!response.ok || !current.running) throw new Error(current.detail || current.error || "Start Virtual Mic first");
    }
    const raw = inputs.find(d => d.deviceId === micSel.value);
    const protectedInput = inputs.find(d => d.deviceId === protectedSel.value);
    if (!raw || !raw.label.includes(current.input_device)) throw new Error("Select the bridge's physical microphone: " + current.input_device);
    if (!protectedInput || !/BlackHole 2ch/.test(protectedInput.label)) throw new Error("BlackHole 2ch is unavailable; refresh microphones");
    await window.ClackProtection.checkRecordingDevice(protectedInput.deviceId);
    // Open both streams before connecting them to one audio clock and one processor.
    for (const deviceId of [raw.deviceId, protectedInput.deviceId]) {
      mediaStreams.push(await navigator.mediaDevices.getUserMedia({ audio: {
        deviceId: { exact: deviceId }, echoCancellation: false,
        noiseSuppression: false, autoGainControl: false, channelCount: 1
      } }));
    }
    mediaStreams.forEach(stream => stream.getTracks().forEach(track => {
      track.addEventListener("ended", () => { if (capturing) captureProblem = "A microphone disconnected; repeat the comparison."; });
    }));
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 44100 });
    await audioCtx.resume();
    merger = audioCtx.createChannelMerger(2);
    sources = mediaStreams.map(stream => audioCtx.createMediaStreamSource(stream));
    sources.forEach((source, i) => source.connect(merger, 0, i));
    processor = audioCtx.createScriptProcessor(4096, 2, 1);
    chunks = [[], []];
    processor.onaudioprocess = e => {
      for (let i = 0; i < 2; i++) {
        const data = e.inputBuffer.getChannelData(i);
        chunks[i].push(new Float32Array(data));
        let sum = 0;
        for (const value of data) sum += value * value;
        setMeter(Math.sqrt(sum / data.length), i);
      }
    };
    const mute = audioCtx.createGain();
    mute.gain.value = 0;
    merger.connect(processor); processor.connect(mute); mute.connect(audioCtx.destination);
    recordingOptions = { model: modelSel.value, correct: correctOn ? "true" : "false", top_n: String(topN) };
    capturing = true;
    modelSel.disabled = micSel.disabled = protectedSel.disabled = $("refreshDemoMics").disabled = true;
  } catch (error) {
    await stopCapture();
    throw error;
  }
}

function setMeter(rms, channel = 0) {
  const db = rms > 1e-6 ? 20 * Math.log10(rms) : -80;
  const pct = Math.max(0, Math.min(100, ((db + 60) / 50) * 100));
  const bar = channel ? $("protectedMeterBar") : meterBar;
  bar.style.width = pct + "%";
  bar.parentElement.setAttribute("aria-valuenow", String(Math.round(pct)));
}

async function stopCapture() {
  capturing = false;
  if (processor) { processor.onaudioprocess = null; processor.disconnect(); }
  sources.forEach(source => source.disconnect());
  if (merger) merger.disconnect();
  mediaStreams.forEach(stream => stream.getTracks().forEach(track => track.stop()));
  const rate = audioCtx ? audioCtx.sampleRate : 44100;
  const samples = chunks.map(concat);
  if (audioCtx) await audioCtx.close();
  audioCtx = processor = merger = null;
  sources = []; mediaStreams = []; chunks = [[], []];
  setMeter(0); setMeter(0, 1);
  modelSel.disabled = micSel.disabled = protectedSel.disabled = $("refreshDemoMics").disabled = false;
  return { samples, rate };
}

function concat(list) {
  let len = 0;
  for (const c of list) len += c.length;
  const out = new Float32Array(len);
  let o = 0;
  for (const c of list) { out.set(c, o); o += c.length; }
  return out;
}

// Resample to exactly 44.1kHz (the model's rate) if the context gave us something else.
async function to44k(samples, rate) {
  if (rate === 44100 || samples.length === 0) return samples;
  const off = new OfflineAudioContext(1, Math.ceil((samples.length * 44100) / rate), 44100);
  const buf = off.createBuffer(1, samples.length, rate);
  buf.getChannelData(0).set(samples);
  const src = off.createBufferSource();
  src.buffer = buf;
  src.connect(off.destination);
  src.start();
  const rendered = await off.startRendering();
  return rendered.getChannelData(0);
}

function encodeWav(samples, sr) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const wr = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
  wr(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); wr(8, "WAVE");
  wr(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sr, true); view.setUint32(28, sr * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  wr(36, "data"); view.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    o += 2;
  }
  return new Blob([view], { type: "audio/wav" });
}

// ---- record button ----
recBtn.addEventListener("click", async () => {
  recBtn.disabled = true;
  if (!capturing) {
    try {
      statusEl.textContent = "opening both microphones…";
      await startCapture();
      recordingGeneration++;
      correctionControllers.forEach(controller => controller.abort());
      correctionControllers = [];
      results.classList.add("hidden"); protectedResults.classList.add("hidden");
      recBtn.textContent = "Stop and decode both";
      recBtn.classList.add("recording"); dot.classList.add("live");
      statusEl.textContent = "recording raw + protected inputs… type now";
    } catch (e) { statusEl.textContent = "Mic error: " + (e.message || e); }
    finally { recBtn.disabled = false; }
    return;
  }
  recBtn.classList.remove("recording"); dot.classList.remove("live");
  recBtn.textContent = "Start recording";
  statusEl.textContent = "decoding both inputs…";
  try {
    const { samples, rate } = await stopCapture();
    if (captureProblem) throw new Error(captureProblem);
    const generation = recordingGeneration;
    const options = { ...recordingOptions };
    const params = new URLSearchParams({ ...options, correct: "false" });
    const decoded = await Promise.allSettled(samples.map(async (audio, i) => {
      if (!audio.length) throw new Error("No audio captured");
      const at44 = await to44k(audio, rate);
      const response = await fetch("/decode?" + params, {
        method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: encodeWav(at44, 44100)
      });
      const json = await response.json();
      if (!response.ok || !json.ok) throw new Error(json.detail || "Decode failed");
      render(json, i === 1);
      if (options.correct === "true" && json.n_presses) correctWithClaude(json, i === 1, generation);
      return json;
    }));
    decoded.forEach((outcome, i) => {
      if (outcome.status !== "fulfilled") {
        (i ? protectedResults : results).classList.remove("hidden");
        $(i ? "protected_resultStatus" : "resultStatus").textContent = "Decode error: " + outcome.reason.message;
      }
    });
    statusEl.textContent = decoded.every(d => d.status === "fulfilled") ? "Both inputs decoded from the same recording." : "Comparison incomplete; see each result.";
  } catch (e) { statusEl.textContent = "Recording error: " + e.message; }
  finally { recBtn.disabled = false; }
});

async function correctWithClaude(decoded, protectedInput, generation) {
  const find = id => $((protectedInput ? "protected_" : "") + id);
  const controller = new AbortController();
  correctionControllers.push(controller);
  find("correctedPanel").classList.remove("hidden");
  find("correctedPanel").querySelector(".label").textContent = "Claude Opus 5.5 correction";
  find("corrected").textContent = "";
  find("correctionStatus").textContent = "Reconstructing candidate text with Claude…";
  try {
    const response = await fetch("/correct", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
      body: JSON.stringify({ provider: "claude", candidates: decoded.per_key })
    });
    const data = await response.json();
    if (generation !== recordingGeneration) return;
    if (!response.ok) throw new Error(data.detail || "Correction failed");
    find("correctedPanel").querySelector(".label").textContent = data.provider === "claude" ? "Claude Opus 5.5 correction" : "Local n-gram correction (fallback)";
    renderTranscript(find("corrected"), data.text);
    const usage = data.usage ? ` · ${data.usage.input_tokens || 0} input / ${data.usage.output_tokens || 0} output tokens` : "";
    find("correctionStatus").textContent = `${data.correction_ms} ms${usage}` + (data.fallback_reason ? ` · Claude unavailable: ${data.fallback_reason}` : "");
  } catch(error) {
    if (generation !== recordingGeneration || error.name === "AbortError") return;
    find("correctionStatus").textContent = "Correction unavailable: " + error.message + ". Acoustic results remain above.";
  } finally {
    correctionControllers = correctionControllers.filter(c => c !== controller);
  }
}

// ---- render ----
function renderTranscript(el, text) {
  el.innerHTML = "";
  [...text].forEach((ch) => {
    if (ch === " ") {
      const s = document.createElement("span");
      s.className = "sp";
      el.appendChild(s);
    } else {
      el.appendChild(document.createTextNode(ch));
    }
  });
}

function fmtBig(str) {
  if (str.length <= 6) return Number(str).toLocaleString();
  const lead = str.slice(0, 3);
  return `${lead[0]}.${lead.slice(1)}e${str.length - 1}`;
}

function render(j, protectedInput = false) {
  const $ = id => document.getElementById((protectedInput ? "protected_" : "") + id);
  const statusEl = $("resultStatus");
  (protectedInput ? protectedResults : results).classList.remove("hidden");
  if (j.n_presses === 0) {
    statusEl.textContent = j.detail || "no keystrokes detected";
    renderTranscript($("transcript"), "");
    $("lattice").innerHTML = "";
    $("correctedPanel").classList.add("hidden");
    ["spaceFull", "spaceRed", "spaceFactor"].forEach(id => { $(id).textContent = "—"; });
    $("crackLine").textContent = "No keystrokes detected; no password estimate available.";
    return;
  }
  statusEl.textContent = `${j.n_presses} keystrokes | ${j.model} | ${j.duration_s}s audio | ${j.latency_ms}ms decode`;

  renderTranscript($("transcript"), j.transcript);

  if (j.corrected != null) {
    $("correctedPanel").classList.remove("hidden");
    renderTranscript($("corrected"), j.corrected);
  } else {
    $("correctedPanel").classList.add("hidden");
  }

  // Password crackability.
  const full = j.search_space_full || "1";
  const red = j.search_space_reduced || "1";
  $("spaceFull").textContent = fmtBig(full);
  $("spaceRed").textContent = Number(red) < 1e6 ? Number(red).toLocaleString() : fmtBig(red);
  $("spaceRedCap").textContent = `top-${j.top_n} shortlist / key`;
  let factor = "1";
  try { factor = (BigInt(full) / BigInt(red)).toString(); } catch (e) { /* keep 1 */ }
  $("spaceFactor").textContent = fmtBig(factor);
  $("crackLine").textContent =
    `A ${j.n_presses}-character password: brute force must try ${fmtBig(full)} combinations. ` +
    `Clack narrows each key to ${j.top_n} guesses, leaving ${Number(red) < 1e6 ? Number(red).toLocaleString() : fmtBig(red)} ` +
    `to check (${fmtBig(factor)} times smaller).`;

  // Per-keystroke candidate lattice.
  const lat = $("lattice");
  lat.innerHTML = "";
  j.per_key.forEach((cands, i) => {
    const col = document.createElement("div");
    col.className = "col";
    const idx = document.createElement("div");
    idx.className = "idx";
    idx.textContent = i + 1;
    col.appendChild(idx);
    cands.forEach(([key, prob], r) => {
      const c = document.createElement("div");
      c.className = "cand " + (r === 0 ? "top" : "dim");
      const glyph = key === "space" ? "␣" : key;
      c.textContent = `${glyph} ${Math.round(prob * 100)}%`;
      col.appendChild(c);
    });
    lat.appendChild(col);
  });
}

loadModels();
loadMics().catch(() => {});

$("refreshDemoMics").addEventListener("click", async () => {
  try {
    const grant = await navigator.mediaDevices.getUserMedia({ audio: true });
    grant.getTracks().forEach(t => t.stop());
    await loadMics();
  } catch(e) { statusEl.textContent = "Microphone permissions: " + e.message; }
});
