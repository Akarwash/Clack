# Clack — BUILD_TRAINER.md

The Clack Trainer: a monkeytype-style typing page whose real job is to generate clean, balanced, auto-labeled keystroke data to train and test the model. This is the first thing to build after the scaffold and the first thing you run on-site, because nothing downstream (model, attack, defense) can be tested without data. Read `CLACK_BUILD_PLAN.md` first for rules, layout, config, and the design tokens. Commit regularly.

This is the authoritative spec for the trainer. It consolidates the trainer-related pieces that also appear in BUILD_BACKEND (capture, keylog, prompts, session, endpoints) and BUILD_FRONTEND (the trainer page). Where they differ, this file wins for the trainer.

Owns these files: `clack/capture.py`, `clack/keylog.py`, `clack/prompts.py`, `clack/session.py`, the trainer routes in `clack/server.py`, `clack/ui/trainer.html`, `clack/ui/trainer.js`, `clack/ui/style.css` (shared), `scripts/collect.py`, and tests `tests/test_prompts.py`, `tests/test_session.py`, plus the trainer part of `tests/test_server.py`.

---

## 1. Purpose and why it is built this way

The model is a supervised classifier: it needs many examples of (keystroke sound, which key). The trainer produces those examples automatically.

- **Why monkeytype-style:** a familiar typing-test flow paces the typist and keeps them engaged through a long collection session, so you get thousands of clean presses without hand-labeling anything.
- **Why random characters, not words:** words over-represent common letters (e, t, a) and starve rare ones (q, z, x), which makes an unbalanced classifier. Random characters give even coverage across every key and remove linguistic bias from the training signal. In paced mode they also isolate each press so segmentation is clean.
- **Why it doubles as the test-data tool:** the same tool produces the held-out recordings used to evaluate the attack, the calibration strings used for cross-keyboard, and the fixed text used for the defense before/after. One tool, all the data.

---

## 2. Architecture: one clock, browser is only a teleprompter

The trap in any browser-plus-Python capture setup is clock sync. Clack avoids it entirely.

```
Browser (teleprompter)                     Python backend (source of truth)
  shows random chars, paces the typist      Recorder  (sounddevice)  -> audio.wav          } one process
  advances UI on the typist's keydown       KeyLogger (pynput)       -> events (t_perf)     } one perf_counter clock
  Start / Stop buttons  ---- HTTP ---->     session.start/stop  -> writes audio.wav + events.json
```

- The browser displays the prompt and advances its own highlight on `keydown`, but it never sends keystrokes as labels.
- The backend captures audio and key events in the **same Python process** on the **same `time.perf_counter()` clock**. It also records the PortAudio stream timing (`input_latency_s`, `stream_time_origin`) so the event clock maps to the audio sample clock without assuming `audio_start_perf` is sample zero. The mapping only needs to be close; the ±`ONSET_SEARCH_MS` onset snap in BUILD_MODEL finishes the alignment.
- Labels come from the actual keys pressed (pynput), so a typo labels its own sound correctly.

---

## 3. Data output (the contract everything downstream reads)

Each session writes `data/recordings/<session_id>/`:
- `audio.wav`: mono, `SAMPLE_RATE` (44100), float32.
- `events.json`:
```json
{
  "session_id": "2026-09-26T11-20-00_blue_akarsh_train",
  "sample_rate": 44100,
  "audio_start_perf": 12345.678,
  "input_latency_s": 0.012,
  "stream_time_origin": 8402.101,
  "keyboard_id": "blue",
  "typist": "akarsh",
  "purpose": "train",
  "mode": "paced",
  "events": [{"key": "a", "t_perf": 12346.101, "type": "press"}]
}
```
`purpose` is `train`, `eval`, or `demo` (the three sessions in section 11). Only `press` events. Map the spacebar to `"space"`. Drop keys not in `KEY_SET`. Do not assume `audio_start_perf` is sample zero; use the stream timing fields for the coarse mapping (see master section 9).

---

## 4. Prompt generation (`prompts.py`)

- `balanced_sequence(key_set=KEY_SET, length=None, seed=None) -> list[str]`:
  - Repeatedly shuffle a copy of `key_set` and concatenate the shuffles, then trim to `length`. This guarantees per-key counts differ by at most one shuffle cycle, unlike uniform random sampling which leaves some keys under-sampled by chance.
  - Default `length` covers `TARGET_SAMPLES_PER_KEY` presses of every key (`TARGET_SAMPLES_PER_KEY * len(key_set)`), so a full session hits the coverage target. The session is coverage-driven, not length-driven: it can serve more prompts if some keys fall behind.
  - Seed for reproducibility, but allow a fresh seed per session so typists do not memorize the order.
  - Return character tokens; render `"space"` in the UI as a visible glyph (the word "space" or a wide underscore) but treat it as one key.
- Tests (`test_prompts.py`, Hypothesis): for any `length` and `key_set`, output length is exact, every token is in the set, and max minus min per-key count is at most one cycle.

---

## 5. Audio capture (`capture.py`)

- `list_input_devices() -> list[dict]`: wrap `sounddevice.query_devices`; return index, name, channels, default sample rate. Used to pin the mic.
- `class Recorder(sr=SAMPLE_RATE, device=INPUT_DEVICE, channels=CHANNELS)`:
  - `start()`: open an `InputStream` with **no OS processing** (no echo cancellation, noise suppression, or auto gain), callback pushes frames to a `queue.Queue`. At the first callback, record `self.audio_start_perf = time.perf_counter()`, `self.input_latency_s = stream.latency` (the input latency PortAudio reports), and `self.stream_time_origin` (the callback's `time.inputBufferAdcTime`, the ADC capture time of the first sample). These let downstream map the event clock to the sample clock without assuming the first callback is sample zero. Raise a clear error if the device fails to open.
  - `read_all() -> np.ndarray`: drain the queue to one float32 mono array.
  - `stop()`: close the stream.
- Keep the callback light (append only); do no processing inside it.

---

## 6. Keyboard logging (`keylog.py`)

- `check_permission() -> None`: verify OS input monitoring is granted; on failure raise `PermissionError` with the exact fix (macOS: System Settings, Privacy and Security, enable Input Monitoring and Accessibility for the terminal or app). Call before any session.
- `class KeyLogger`:
  - `start()`: a `pynput.keyboard.Listener` recording `{key, t_perf, type:"press"}` for keys in `KEY_SET`; normalize letters and digits to their character and `Key.space` to `"space"`; ignore everything else (shift, backspace, modifiers) unless added to `KEY_SET`.
  - `stop() -> list[dict]`: stop and return the events.

---

## 7. Session orchestration (`session.py`)

- `start_session(keyboard_id, typist, mode) -> session_id`: build `session_id` = `<iso-time>_<keyboard_id>_<typist>`, `check_permission()`, start a `Recorder` and a `KeyLogger`, store them in a registry keyed by `session_id`, return the id.
- `stop_session(session_id) -> dict`: stop both, write `audio.wav` (soundfile, float32, `SAMPLE_RATE`) and `events.json` (schema in section 3), return `{session_id, n_events, duration_s, path}`.
- Guard against two sessions running at once on the same device; return a clear error if the id is unknown.

---

## 8. Endpoints (trainer routes, defined here, wired in `server.py`)

- `GET /trainer` -> serves `ui/trainer.html`.
- `GET /devices` -> `list_input_devices()` output, for the mic dropdown.
- `GET /trainer/prompt?n=&mode=` -> `{"chars": [...]}` from `balanced_sequence`.
- `POST /trainer/start` body `{keyboard_id, typist, mode}` -> `{session_id}`.
- `POST /trainer/stop` body `{session_id}` -> `{session_id, n_events, duration_s, path}`.

---

## 9. The trainer page (`trainer.html`, `trainer.js`, `style.css`)

Editorial-minimal, per the design system in BUILD_FRONTEND (paper background, near-black ink, hairlines, mono for data, one accent). It should look intentional if a judge glances at it. Use the self-hosted fonts and `:root` tokens from BUILD_FRONTEND (`ui/fonts/`, no CDN), so the page loads with no network.

Layout, top to bottom:
1. **Setup row (before Start):** micro-labeled controls: `Keyboard` (text, for example "blue" or "c3equalz"), `Typist` (text), `Purpose` (Train / Eval / Demo segmented control, which sets the per-key quota: `TRAIN_SAMPLES_PER_KEY`=40 for Train, `EVAL_SAMPLES_PER_KEY`=10 for Eval, and Demo is a free natural phrase with no quota), `Mode` (Paced / Flow), `Mic` (dropdown from `GET /devices`). One ghost `Start` button (ink text, hairline border, accent on hover).
2. **The stage (center, large):**
   - **Paced mode (default):** one giant current character in the hero mono size, centered. The next few upcoming characters faint to its right, completed ones faded to the left. A thin metronome line under the current character fills over `TRAINER_PACED_GAP_MS` and resets on each correct press. This isolates presses for the cleanest data.
   - **Flow mode:** a single line of upcoming random characters scrolling right to left, monkeytype-style; the current one marked; correct in `--good`, incorrect in `--accent`. Faster, more data, some natural overlap.
3. **Live readout row:** micro-labels with big mono numerals: `Keys captured`, `Coverage` (keys at target / 37), `Elapsed`, and in flow mode `WPM`.
4. **Coverage strip (coverage-driven collection):** a row of 37 cells, one per key, each showing that key's count toward the purpose's quota (for example `a 40/40`, `b 24/40` in Train) and filling from `--line` toward `--ink` as it approaches the quota. Keys below target are highlighted. When every key reaches the quota, the trainer auto-stops and shows "coverage complete". Demo mode has no quota (free phrase). This replaces an arbitrary total length.
5. **Stop button:** calls `/trainer/stop`, then shows a quiet confirmation line with the saved counts and path.

`trainer.js`:
- On Start: `POST /trainer/start`, then `GET /trainer/prompt` for the sequence, start the UI clock and (paced) the metronome.
- The browser's own `keydown` drives only the UI: advance the pointer, color correct/incorrect, update the per-key coverage counts. It does not label anything.
- Track per-key counts client-side toward the purpose's quota (`TRAIN_SAMPLES_PER_KEY` or `EVAL_SAMPLES_PER_KEY`); when all 37 hit it, auto-stop (call `/trainer/stop`) and show completion. If a prompt runs out before coverage is met, fetch another `balanced_sequence` and continue. Demo mode does not auto-stop; the typist stops when the phrase is done.
- On Stop: `POST /trainer/stop`, render the summary.
- Wrap any `localStorage` use (remembered keyboard/typist) in try/catch.

---

## 10. Terminal fallback (`scripts/collect.py`)

A no-browser paced collector for the first minutes on-site before the page is wired: print `balanced_sequence` one character at a time on a metronome while `session.py` records, then stop and report. This unblocks data collection immediately.

---

## 11. How to run a collection session (on-site workflow)

Collect three separate sessions per board so evaluation is honest (session-level split, not a random split of one session):

1. Pin the mic: hit `GET /devices`, set `INPUT_DEVICE` in config. Grant OS input monitoring (the app will tell you if it is missing).
2. **Session A (train):** Purpose = Train. Collect from **2 to 3 teammates** (`TRAINER_MIN_TYPISTS`) on the floor board until every key hits `TRAIN_SAMPLES_PER_KEY` (40). About 15 minutes split across typists.
3. **Session B (eval, held out):** Purpose = Eval, a SEPARATE recording, ideally a **different typist who gave zero training samples**, to `EVAL_SAMPLES_PER_KEY` (10). This is what gives legitimate top-1/top-3 numbers and tests the judge-is-a-different-typist case.
4. **Session C (demo):** Purpose = Demo, a natural free phrase (no quota) at the MVP cadence (>= `DEMO_MIN_GAP_MS`), to prove decoding a realistic sequence the model never saw.
5. Repeat Sessions A and B on the second board (same one mic, same geometry). This is core: the goal is one model across both boards, so both need data. Do a demo Session C on whichever board you will present.
6. The recordings are on disk for BUILD_MODEL: train ONE combined model on both boards' A sessions, evaluate on each board's held-out B session, demo on C.

---

## 11A. Data collection protocol (physical setup, do it the SAME every time)

The model learns the exact acoustic signature of one keyboard, one mic position, and one surface. The single most important rule: **whatever setup you train on, keep it identical for the demo.** Write this protocol into `docs/data-collection.md` (see the master doc standards) and follow it every session.

**Surface and keyboard**
- Put the keyboard flat on a hard, stable surface (a solid desk or table), not a soft or padded one that dampens the sound. Use the same surface for training and the demo.
- Do not move or re-seat the keyboard between collection and demo. If you must, mark its position with tape and return it to the same spot.
- One `keyboard_id` per physical board (for example `blue`, `c3equalz`). Never mix two boards in one session.

**Microphone position (the most sensitive variable)**
- Use the Mac's built-in mic (or one fixed external mic). Place the laptop in a consistent spot relative to the keyboard: the keyboard directly in front of the laptop, roughly 15 to 25 cm from the mic, with a clear line of sight to the keys (nothing between mic and keyboard).
- Mark the laptop and keyboard positions with tape so the exact geometry is reproducible. Distance consistency matters more than the exact distance: pick one and never change it between training and demo.
- Do not pick up, tilt, or slide the laptop after collection. The demo must use the same mic geometry the model trained on.

**Environment**
- Collect in a spot as close as possible to where you will demo (ideally the same table). Room acoustics are part of what the model learns.
- Keep it reasonably quiet during collection: no talking, no chair scraping, no table bumps, phones off the table. The ambient calibration handles steady room noise, but transients pollute training data.
- Same lighting/fan/AC conditions if you can; steady background is fine, sudden noises are not.

**How to press the keys (technique)**
- Paced mode, one key per metronome beat: press the shown key deliberately, bottom it out fully (the bottom-out is part of the signal), and fully release before the next beat. One clean press per beat, no overlap.
- Keep a consistent, natural strike force. Do not slam or feather the keys; type as you normally would but one key at a time.
- Rest your hands off the other keys between presses so you do not create accidental transients. Only the prompted key should make a sound.
- If you mistype, keep going: the actual key pressed is auto-labeled correctly. Do not use backspace (it is not in the key set and adds noise); just continue.
- Do not talk or move while a press is being recorded.

**Typists (cover the judge case)**
- Session A (train): collect from 2 to 3 teammates so the model is not tuned to one pair of hands. Each teammate types a share; the balanced coverage still applies across the whole session.
- Session B (eval): have a teammate who contributed ZERO training samples type it. This is your honest test of "a different person (the judge) sits down."
- Session C (demo): a natural phrase at the demo cadence (>= `DEMO_MIN_GAP_MS`).

**Multiple keyboards (one mic, both boards are core work)**
- One microphone for everything. Collect on BOTH boards (blue and C3 Equalz) through that same mic, same geometry, same surface. Tag each session with its `keyboard_id`.
- Run Sessions A and B on each board (and a demo Session C on whichever board you will show). Collecting both boards is core, not optional, because the goal is one model that works across both.
- BUILD_MODEL section 8A then trains ONE combined model on both boards' data (recommended: it works on either board because it saw both, and enables the "swap keyboards, same model" demo). Per-board models are the fallback.
- Generalizing to a board you never recorded is the separate cross-keyboard stretch (BUILD_MODEL section 8), uncertain and never the floor. Supporting the boards you own does not need it.

---

## 11B. One mic, machine roles, and weight transfer

The team uses ONE microphone for everything, so there is no cross-microphone problem. The rule that remains: all audio (every board, every session) is captured through that one mic, in the same spot with the same geometry. The machine that owns the mic is the collection-and-demo machine.

- **Pick the mic machine (the demo Mac) first.** All Sessions A/B/C, on both boards, are recorded on that machine's mic. The demo also runs on it.
- **Offloading training compute is fine (weights are portable, audio is not the issue here since it is one mic).** If another laptop trains faster, copy the RECORDINGS (`data/recordings/<session_id>/` folders) to it, train, then copy the model folder back. Or just train on the mic machine (small CNN, minutes to under an hour).
- **What "transfer weights" means:** copy the whole `data/models/<name>/` folder (`model.pt`, `config.json`, `metrics.json`, `norm.json` if used, class list). Both machines must be on the same git commit so `config.py` (window, Mel, key set, `SPEC_FRAMES`) matches, or the model input will not line up.
- **Verify after transfer:** on the mic machine, pin its `INPUT_DEVICE` and run the offline attack on the held-out Session B for each board to confirm the model reproduces the expected accuracy on that mic. That is the valid "does it still work" check.

Write this into `docs/data-collection.md` and `docs/runbook.md` so the team follows the same setup.

---

## 12. Tests

- `test_prompts.py`: as in section 4.
- `test_session.py`: run a short synthetic session (feed synthetic audio and a few fake key events), assert `events.json` matches the schema, timestamps are monotonic, and `sample_index` alignment is within tolerance of the injected positions.
- trainer part of `test_server.py` (httpx + TestClient): `GET /trainer` returns 200, `GET /trainer/prompt` returns the right count, `POST /trainer/start` then `/trainer/stop` round-trips a session and writes files.

---

## 13. Predicted failures and fixes

| Problem | Fix |
|---|---|
| Audio and events misaligned | Confirm both use `time.perf_counter()` and `audio_start_perf` is read at first callback, not at stream open. Verify with `test_session.py`. |
| pynput captures nothing | OS input-monitoring permission missing; `check_permission()` should have raised. Grant it and restart. |
| Some keys under-sampled | Use `balanced_sequence` (not uniform random); watch the coverage strip and extend the session for starved keys. |
| Paced mode too slow to collect volume | Switch to flow mode once the balanced paced set exists, to add data faster. |
| Browser mic permission prompt confuses capture | The browser does not capture audio at all; only the Python backend does. Ignore any browser mic prompt. |
| Two sessions collide on the device | `start_session` guards against a second concurrent session; stop the first. |

## 14. DONE for the trainer

- `/trainer` runs both paced and flow modes with the coverage strip and Purpose (train/eval/demo) quotas, and `scripts/collect.py` works as a terminal fallback.
- Running a session writes a valid `audio.wav` and `events.json` (with the clock-mapping fields), and `test_session.py` confirms alignment.
- The physical collection protocol (section 11A) is written into `docs/data-collection.md`, so the team can follow the exact mic placement, key-press technique, and multi-keyboard workflow.
- At least Sessions A/B/C on the floor board can be collected, ready for BUILD_MODEL.
