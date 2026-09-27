# API

Owner: BUILD_BACKEND. Every HTTP and WebSocket endpoint the Clack server exposes.
The server runs on localhost with no network dependency, and the UI is served from
self-hosted files. Start it with `python scripts/serve.py`.

## Pages and static assets

| Method | Path | Returns |
|---|---|---|
| GET | `/` | `ui/index.html` (the attack dashboard) |
| GET | `/trainer` | `ui/trainer.html` (the collector) |
| GET | `/app.js`, `/trainer.js`, `/style.css`, `/fonts/*`, `/vendor/*` | static UI assets |

## Trainer and collection

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/devices` | none | list of `{index, name, channels, default_samplerate}` |
| GET | `/trainer/prompt?n=&mode=` | none | `{chars: [...], mode}` from `balanced_sequence` |
| POST | `/trainer/start` | `{keyboard_id, typist, purpose?, mode?}` | `{session_id}` |
| POST | `/trainer/stop` | `{session_id}` | `{session_id, n_events, duration_s, path}` |

`purpose` is `train`, `eval`, or `demo`. Errors (missing device, missing
permission, unknown session) return a 400 with `{error}`.

## Attack (live)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/attack/start` | `{model_name?, event_mode?, source?}` | `{ok, source, model?}` |
| POST | `/attack/stop` | none | `{ok: true}` |
| WS | `/ws/attack` | none | streamed JSON frames (below) |

`source` is `mic` (default, the real attack) or `synthetic` (a wiring/test stream,
labeled `synthetic` in each frame and never presented as a real result).
`event_mode` is the deliberately operator-enabled clean run; by default the pynput
listener is never instantiated in attack mode.

WebSocket frames:

```json
{"type":"status","microphone":"ACTIVE","keylogger":"DISABLED"}
{"type":"key","key":"a","confidence":0.92,"topk":[["a",0.92],["s",0.04]],"text":"the a","t":123.4,"latency_ms":180}
{"type":"heartbeat","t":123.9}
```

The `status` frame reports the input-source state so the dashboard can show
`Microphone: ACTIVE, Keyboard Events: DISABLED`. `key` frames carry the running
recovered `text`; `audio` frames (waveform/spectrogram) are sent at a fixed low
rate and the UI keeps only the latest. Slow clients drop `audio` frames, never
`key` frames.

## Defense

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/defense/on` | `{level?, band?}` | `{ok, on, level, band}` (Standard Shield, continuous) |
| POST | `/defense/off` | none | `{ok, on: false}` |
| GET | `/defense/measure` | none | the last before/after `{off, on, delta, masker_key_ratio_db, ...}` or 404 if none |

## Exposure and fleet

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/exposure/check` | `{session_id, model_name?, endpoint?}` | `{grade, recovery, snr, reasons, recommendations, detail}` |
| GET | `/exposure/last` | none | the last exposure result, or 404 |
| GET | `/fleet` | none | saved audit reports (newest first) from `data/reports/` |

The grade is a labeled Clack heuristic based on measured recoverability, not an
industry rating.

## Correction

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/correct` | `{lattice: [[key, ...], ...]}` | `{text}` |

The lattice is the per-press ranked candidate keys; the server decodes it with the
local n-gram beam search (bundled corpus, no network) so the dashboard can show the
CORRECTED line next to RAW live.

## Status and preflight

| Method | Path | Returns |
|---|---|---|
| GET | `/status` | a readiness report, each item `{ok, ...detail}` |

```json
{
  "microphone": {"ok": true, "name": "MacBook Pro Microphone"},
  "sample_rate": {"ok": true, "value": 44100},
  "keyboard_permission": {"ok": true},
  "model": {"ok": true, "name": "combined"},
  "attack_keylogger": {"ok": true, "state": "DISABLED"},
  "speaker": {"ok": true},
  "compute": {"ok": true, "device": "mps"},
  "ambient_calibration": {"ok": true, "noise_floor": 0.002}
}
```

`python scripts/preflight.py` runs the same checks from the terminal and exits
non-zero if any item fails. Run it before every demo.
## Protected virtual microphone

- `GET /virtual-mic/devices`: installed-driver flag and validated aggregate routes
  (`bridge_device`, `input_device`, `output_device`, `ready`; invalid configured
  routes include `detail`). No stream is opened.
- `POST /virtual-mic/start`: `{bridge_device?, level?}`, defaults to
  `Clack Protected Bridge` and 0.3. Validates routing before capturing; returns
  status. Level must be finite, 0.1–1.0. Conflicting modes/capture return 409;
  unavailable or invalid routing returns 400; invalid request values return 422.
- `POST /virtual-mic/settings`: `{level}`, updates level without reopening streams.
- `POST /virtual-mic/stop`: stops capture/output; virtual output is silence.
- `GET /virtual-mic/status`: `running`, `ok`, `error`, route names, `level`, `band`,
  `input_rms`, `output_rms`, `latency_ms`, `limited_fraction`, `stream_errors`,
  `speaker_on`, `output_when_stopped`, and `processing`. Running is routing health,
  not proof of consumer selection or effectiveness. A failure may have `ok:false`
  even after cleanup; a subsequent successful start clears it.
- `POST /attack/start` additionally accepts `input_device` (backend device name).
  Omission retains the configured mic. While Virtual Mic runs, use `BlackHole 2ch`.

See [setup and protection boundaries](virtual-microphone.md). Existing
`/defense/on` and `/defense/off` remain speaker-masking controls. Existing recorded
defense measurements remain software-mixed evaluations, not virtual-device tests.

### Demo Claude correction

`POST /correct` accepts `{ "provider": "claude", "candidates": [[["a", 0.8], ["e", 0.2]]] }`.
Each ordered position has 1–5 modeled keys with finite probabilities in [0, 1].
Response preserves `text` and adds `provider`, `model`, `correction_ms`, `usage`
(input/output tokens), and `fallback_reason`. Claude selects one supplied candidate
per position. Invalid requests return 422. Empty input returns empty text without
a network request. Remote correction is capped at 500 positions; valid longer
input (up to 5000 positions) uses explicitly identified local fallback.

Existing `{ "lattice": [["a", "e"]] }` requests remain local. Demo uploads audio
to `/decode?correct=false` and then independently corrects each result through
`/correct`. Attack and offline evaluation retain local correction.
