# Clack — BUILD_BACKEND.md

The Python service: audio capture, keyboard logging, collection sessions, live streaming decode, language-model correction, and the FastAPI server that ties them together and serves the UI. Read `CLACK_BUILD_PLAN.md` first for rules, layout, and config. Commit regularly.

Covers files: `capture.py`, `keylog.py`, `prompts.py`, `session.py`, `stream.py`, `correct.py`, `server.py`, plus `scripts/collect.py` and `scripts/serve.py`.

---

## 1. Design principles for the backend

- **One process, one clock.** Audio and key events are captured in the same Python process, both timestamped with `time.perf_counter()`. This makes alignment exact and removes any browser-to-server clock sync.
- **The browser never captures labels.** During collection the browser is a teleprompter only. All labels come from `keylog.py` (the actual keys pressed).
- **Raw audio.** Open the input stream with no OS processing. Capture float32 at `SAMPLE_RATE`.
- **Nothing blocks the audio callback.** The sounddevice callback only appends frames to a queue. All heavy work (featurize, classify) happens elsewhere.
- **Fail loudly** on missing device or permission, with a message that says how to fix it.

---

## 2. Audio capture (`capture.py`)

- `list_input_devices() -> list[dict]`: wrap `sounddevice.query_devices`, return index, name, channels, default sample rate. Used at setup to pin `INPUT_DEVICE`.
- `class Recorder`:
  - `__init__(sr=SAMPLE_RATE, device=INPUT_DEVICE, channels=CHANNELS)`.
  - `start()`: open a raw `InputStream` (no OS processing) with a callback that pushes frames to a `queue.Queue`; at the first callback record `self.audio_start_perf = time.perf_counter()`, `self.input_latency_s` (the stream's input latency), and `self.stream_time_origin` (the callback's `inputBufferAdcTime`) so the event clock maps to the sample clock without assuming sample zero (see BUILD_TRAINER section 5 and master section 9). Raise a clear error if the device cannot open.
  - `read_all() -> np.ndarray`: drain the queue into one float32 mono array.
  - `stop()`: close the stream.
  - `class StreamReader` (for live attack): exposes a rolling buffer of the last `N` seconds via a lock, for `stream.py` to poll.

## 3. Keyboard logging (`keylog.py`)

- `check_permission() -> None`: verify the OS grants input monitoring; on failure raise `PermissionError` with the exact fix (macOS: System Settings, Privacy and Security, Input Monitoring and Accessibility, enable the terminal or app). Call this before any collection.
- `class KeyLogger`:
  - `start()`: a `pynput.keyboard.Listener` recording `{key, t_perf, type:"press"}` for keys in `KEY_SET` (map `Key.space` to `"space"`). Ignore keys not in `KEY_SET` (shift, backspace, modifiers) unless they are added to the set.
  - `stop() -> list[dict]`: stop and return the events.
- Normalize key names: lowercase letters and digits to their character, spacebar to `"space"`.

## 4. Prompt generation (`prompts.py`)

- `balanced_sequence(key_set=KEY_SET, length=TRAINER_DEFAULT_LENGTH, seed=None) -> list[str]`: repeatedly shuffle a copy of `key_set` and concatenate until `length` reached, then trim. Guarantees near-equal per-key counts. Seed for reproducibility, allow a fresh seed per session so typists do not memorize the order. Display `"space"` in the UI as a visible glyph (for example the word "space" or a wide underscore).
- Tests (`test_prompts.py`, Hypothesis): every output uses only keys in the set, length is exact, and per-key counts differ by at most one full cycle.

## 5. Collection session (`session.py`, `scripts/collect.py`)

- `start_session(keyboard_id, typist, mode) -> session_id`: build a `session_id` like `<iso-time>_<keyboard_id>_<typist>`, `check_permission()`, start a `Recorder` and a `KeyLogger`, keep them in a registry keyed by `session_id`, return the id.
- `stop_session(session_id) -> dict`: stop both, write `data/recordings/<session_id>/audio.wav` (soundfile, float32, `SAMPLE_RATE`) and `events.json` (schema in the master plan, including `audio_start_perf`, `keyboard_id`, `typist`, `mode`), return `{session_id, n_events, duration_s, path}`.
- `scripts/collect.py`: a terminal fallback that runs a paced session without the browser: print `balanced_sequence` one char at a time on a metronome, while `session.py` records. Use this if the trainer UI is not up yet.

## 6. Live streaming decode (`stream.py`)

- **Ambient calibration first.** `calibrate_ambient(reader, seconds=AMBIENT_CALIB_S)`: at attack startup, record `AMBIENT_CALIB_S` (2 s) of a quiet room, measure the energy distribution, and set the onset threshold dynamically (an effective `ONSET_K` for the current room) instead of the static default. The room is noisy at a hackathon, and the whole attack begins with onset detection, so this is not optional. Expose a "calibrated" flag and the measured noise floor for the dashboard and preflight.
- `class LiveDecoder`:
  - Holds the loaded model (baseline or CNN) and a `StreamReader`.
  - Runs `calibrate_ambient` once, then a loop that continuously calls `detect_onsets` (with the calibrated threshold) on the tail of the rolling buffer; when a new onset clears the debounce, cut the onset-centered window, featurize, classify, and emit `{"key": best, "confidence": p, "topk": [[key,p],...], "t": perf_now, "latency_ms": ...}` via an async callback.
  - Maintains the running recovered string and exposes it.
  - **Onset debug mode:** optionally emit detected-peak markers and the current threshold so the dashboard can show onsets in real time (invaluable for tuning in the room).
  - Second mode `event_mode=True`: use `keylog` timestamps instead of audio onsets, for one guaranteed-clean demo run. This mode is the ONLY place `stream` touches key events, and it is off by default (see mode separation in section 8).
- Measure and log end-to-end latency per key. Target under ~1 second; if high, shrink the buffer and Mel resolution first.

### Mode separation (provable mic-only attack)

The attack must be provably keyboard-event-free. Enforce it in code:
- **Attack mode:** the pynput listener is never instantiated (`ATTACK_DISABLES_KEYLOGGER=True`). The only exception is the explicit `event_mode=True` clean-run, which the operator turns on deliberately and which the dashboard clearly labels.
- **Trainer mode:** mic on, key capture on, used only to make labeled samples.
- The server exposes the current input-source state (see `/status`) so the dashboard can show `Microphone: ACTIVE, Keyboard Events: DISABLED`. This is both correct engineering and the answer to "how do I know you are not reading the keyboard".

## 7. Language-model correction (`correct.py`)

- Build a character-level n-gram (`NGRAM_ORDER=5`) from a bundled corpus in `data/corpus/` (a public-domain English text; ship a small one so there is no network dependency). Use `nltk` or a small hand-rolled counter.
- `correct(topk_per_position) -> (best_text, score)`: beam search (`BEAM_WIDTH=8`) over the per-position top-k candidates, scoring partial strings with the n-gram log-probability plus the classifier log-probability. Return the best string and its score.
- `USE_LLM_CORRECTION=False` by default. If set, an optional path may call an external model, but it must never be on the critical path and must degrade gracefully to the n-gram if unavailable.
- Report BLEU or exact-match before and after correction so the lift is a number to show.
- Tests (`test_correct.py`): corrected output scores higher than the raw argmax on a noisy candidate lattice for a known sentence.

## 8. FastAPI server (`server.py`, `scripts/serve.py`)

Mount the UI as static files and expose these routes.

### Pages
- `GET /` -> `ui/index.html` (attack dashboard).
- `GET /trainer` -> `ui/trainer.html` (collector).
- Serve `ui/app.js`, `ui/trainer.js`, `ui/style.css` as static assets.

### Trainer / collection
- `POST /trainer/start` body `{keyboard_id, typist, mode}` -> `{session_id}`. Calls `session.start_session`.
- `POST /trainer/stop` body `{session_id}` -> `{session_id, n_events, duration_s, path}`. Calls `session.stop_session`.
- `GET /trainer/prompt?n=&mode=` -> `{chars: [...]}` from `prompts.balanced_sequence`.
- `GET /devices` -> `list_input_devices()` output, so the UI can show and pin the mic.

### Attack (live)
- `POST /attack/start` body `{model_name, event_mode?}` -> `{ok: true}`. Loads the model, starts a `LiveDecoder`.
- `POST /attack/stop` -> `{ok: true}`.
- `WS /ws/attack`: streams decoder events as JSON, one message per keystroke:
  ```json
  {"type":"key","key":"a","confidence":0.92,"topk":[["a",0.92],["s",0.04],["q",0.02]],"text":"the a","t":123.4,"latency_ms":180}
  ```
  Also send periodic frames for the visuals:
  ```json
  {"type":"audio","waveform":[...],"spectrogram":[[...]]}
  ```
  Keep audio frames small and at a fixed rate (for example 20 per second); the UI drops to the latest.

### Defense (see BUILD_DEFENSE.md)
- `POST /defense/on` and `POST /defense/off` toggle the masker.
- `GET /defense/measure` -> `{off_acc, on_acc}` for the before/after bars.

### Preflight / status (do not discover a broken dependency while a judge is standing there)
- `GET /status` -> a full readiness report, each item pass/fail with detail:
  ```json
  {
    "microphone": {"ok": true, "name": "MacBook Microphone"},
    "sample_rate": {"ok": true, "value": 44100},
    "keyboard_permission": {"ok": true},
    "model": {"ok": true, "name": "blue-v3"},
    "attack_keylogger": {"ok": true, "state": "DISABLED"},
    "speaker": {"ok": true},
    "compute": {"ok": true, "device": "mps"},
    "ambient_calibration": {"ok": true, "noise_floor": 0.002}
  }
  ```
- `scripts/preflight.py`: run the same checks from the terminal and print the checklist. Run it before every demo. Treat any failed item as blocking.

### WebSocket rules
- Never block the event loop. Run capture and decode in background tasks or threads; push to the socket from an async queue.
- If a client is slow, drop `audio` frames (keep the latest), never drop `key` messages.

Tests (`test_server.py`, httpx + FastAPI `TestClient` + `pytest-asyncio`): `GET /` and `GET /trainer` return 200; `GET /status` reports each item and shows the attack keylogger DISABLED; the attack WebSocket handshakes and forwards a synthetic key message; trainer start/stop round-trips a session.

## 9. Running

- `python scripts/serve.py` launches uvicorn (`server:app`) on `127.0.0.1:8000`, prints the trainer and dashboard URLs. It calls `ensure_dirs()` (from `config_types`) at startup.
- `python scripts/preflight.py` runs the readiness checklist. Run it before every demo.
- Document in the README: pin the mic with `/devices`, grant input monitoring, open `/trainer` to collect, `run_train.py` to train, then `/` to attack.

## 10. DONE for the backend

- `serve.py` starts; `/trainer` collects auto-labeled sessions; the live attack runs with ambient calibration and the pynput listener provably not instantiated in attack mode; `/` streams live predictions over the WebSocket; `/status` and `preflight.py` report full readiness; correction runs locally with no network; all `test_server.py` tests pass.
- `docs/api.md` (all endpoints and WebSocket message formats) and the preflight section of `docs/runbook.md` are written.
