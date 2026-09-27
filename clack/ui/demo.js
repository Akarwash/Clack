/* Clack Demo: record a clip, decode it with the chosen model, show the recovered
 * keystrokes, the language-model correction, and the password search-space
 * reduction. Capture and decode run locally (no network) against the FastAPI
 * backend on this same host. Owner: BUILD_FRONTEND (demo surface). */
"use strict";

const $ = (id) => document.getElementById(id);
const modelSel = $("model");
const micSel = $("mic");
const recBtn = $("recBtn");
const statusEl = $("status");
const dot = $("dot");
const meterBar = $("meterBar");
const results = $("results");

let correctOn = true;
let topN = 3;

// Human-readable notes for the known demo models (measured held-out numbers).
const MODEL_NOTES = {
  "dak": "All 3 typists (aditya+josh+vishal). Held-out vs aditya: 78% top-1, 95% top-3.",
  "dak-aditya": "Aditya's own typing only. Held-out vs aditya: 39% top-1.",
  "dak-cold": "Cold attacker (josh+vishal, never heard aditya). vs aditya: 39% top-1; 27% mean cross-typist.",
};

function noteFor(m) {
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
  try {
    // A getUserMedia call first so device labels are populated (permission).
    const devices = await navigator.mediaDevices.enumerateDevices();
    const inputs = devices.filter((d) => d.kind === "audioinput");
    for (const d of inputs) {
      if (!d.deviceId) continue;
      const opt = document.createElement("option");
      opt.value = d.deviceId;
      opt.textContent = d.label || `mic ${micSel.length}`;
      micSel.appendChild(opt);
    }
  } catch (e) {
    /* labels appear after the first recording grants permission */
  }
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
let audioCtx = null, mediaStream = null, source = null, processor = null;
let chunks = [], capturing = false;

async function startCapture() {
  const deviceId = micSel.value || undefined;
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      deviceId: deviceId ? { exact: deviceId } : undefined,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      channelCount: 1,
    },
  });
  audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 44100 });
  source = audioCtx.createMediaStreamSource(mediaStream);
  processor = audioCtx.createScriptProcessor(4096, 1, 1);
  chunks = [];
  processor.onaudioprocess = (e) => {
    const d = e.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(d));
    let sum = 0;
    for (let i = 0; i < d.length; i++) sum += d[i] * d[i];
    setMeter(Math.sqrt(sum / d.length));
  };
  const mute = audioCtx.createGain();
  mute.gain.value = 0; // keep the processor firing without audible feedback
  source.connect(processor);
  processor.connect(mute);
  mute.connect(audioCtx.destination);
  capturing = true;
}

function setMeter(rms) {
  const db = rms > 1e-6 ? 20 * Math.log10(rms) : -80;
  const pct = Math.max(0, Math.min(100, ((db + 60) / 50) * 100));
  meterBar.style.width = pct + "%";
}

async function stopCapture() {
  capturing = false;
  if (processor) processor.disconnect();
  if (source) source.disconnect();
  if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
  const rate = audioCtx ? audioCtx.sampleRate : 44100;
  const merged = concat(chunks);
  if (audioCtx) await audioCtx.close();
  setMeter(0);
  return { samples: merged, rate };
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
  if (!capturing) {
    try {
      await startCapture();
      if (micSel.length <= 1) loadMics();
      recBtn.textContent = "Stop and decode";
      recBtn.classList.add("recording");
      dot.classList.add("live");
      statusEl.textContent = "listening... type your text or password now";
    } catch (e) {
      statusEl.innerHTML = `<span class="err">mic error: ${e.message || e}</span>`;
    }
    return;
  }
  // Stop -> decode.
  recBtn.disabled = true;
  recBtn.classList.remove("recording");
  dot.classList.remove("live");
  recBtn.textContent = "Start recording";
  statusEl.textContent = "decoding...";
  const { samples, rate } = await stopCapture();
  recBtn.disabled = false;
  if (samples.length === 0) {
    statusEl.innerHTML = `<span class="err">no audio captured</span>`;
    return;
  }
  try {
    const at44 = await to44k(samples, rate);
    const blob = encodeWav(at44, 44100);
    const params = new URLSearchParams({
      model: modelSel.value,
      correct: correctOn ? "true" : "false",
      top_n: String(topN),
    });
    const res = await fetch("/decode?" + params.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: blob,
    });
    const json = await res.json();
    if (!json.ok) {
      statusEl.innerHTML = `<span class="err">${json.detail || "decode failed"}</span>`;
      return;
    }
    render(json);
  } catch (e) {
    statusEl.innerHTML = `<span class="err">decode error: ${e.message || e}</span>`;
  }
});

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

function render(j) {
  results.classList.remove("hidden");
  if (j.n_presses === 0) {
    statusEl.textContent = j.detail || "no keystrokes detected";
    renderTranscript($("transcript"), "");
    $("lattice").innerHTML = "";
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
loadMics();
