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
- The backend captures audio and key events in the **same Python process** on the **same `time.perf_counter()` clock**, so `sample_index = round((t_perf - audio_start_perf) * sample_rate)` is exact. No cross-device sync.
- Labels come from the actual keys pressed (pynput), so a typo labels its own sound correctly.

---

## 3. Data output (the contract everything downstream reads)

Each session writes `data/recordings/<session_id>/`:
- `audio.wav`: mono, `SAMPLE_RATE` (44100), float32.
- `events.json`:
```json
{
  "session_id": "2026-09-26T11-20-00_blue_akarsh",
  "sample_rate": 44100,
  "audio_start_perf": 12345.678,
  "keyboard_id": "blue",
  "typist": "akarsh",
  "mode": "paced",
  "events": [{"key": "a", "t_perf": 12346.101, "type": "press"}]
}
```
Only `press` events. Map the spacebar to `"space"`. Drop keys not in `KEY_SET`.

---

## 4. Prompt generation (`prompts.py`)

- `balanced_sequence(key_set=KEY_SET, length=TRAINER_DEFAULT_LENGTH, seed=None) -> list[str]`:
  - Repeatedly shuffle a copy of `key_set` and concatenate the shuffles, then trim to `length`. This guarantees per-key counts differ by at most one shuffle cycle, unlike uniform random sampling which leaves some keys under-sampled by chance.
  - Seed for reproducibility, but allow a fresh seed per session so typists do not memorize the order.
  - Return character tokens; render `"space"` in the UI as a visible glyph (the word "space" or a wide underscore) but treat it as one key.
- Tests (`test_prompts.py`, Hypothesis): for any `length` and `key_set`, output length is exact, every token is in the set, and max minus min per-key count is at most one cycle.

---

## 5. Audio capture (`capture.py`)

- `list_input_devices() -> list[dict]`: wrap `sounddevice.query_devices`; return index, name, channels, default sample rate. Used to pin the mic.
- `class Recorder(sr=SAMPLE_RATE, device=INPUT_DEVICE, channels=CHANNELS)`:
  - `start()`: open an `InputStream` with **no OS processing** (no echo cancellation, noise suppression, or auto gain), callback pushes frames to a `queue.Queue`; set `self.audio_start_perf = time.perf_counter()` at the first callback (not at open). Raise a clear error if the device fails to open.
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

Editorial-minimal, per the design system in BUILD_FRONTEND (paper background, near-black ink, hairlines, mono for data, one accent). It should look intentional if a judge glances at it. Load Space Grotesk and JetBrains Mono from Google Fonts, use the `:root` tokens from BUILD_FRONTEND.

Layout, top to bottom:
1. **Setup row (before Start):** micro-labeled controls: `Keyboard` (text, for example "blue" or "c3equalz"), `Typist` (text), `Mode` (Paced / Flow segmented control), `Length` (number, default `TRAINER_DEFAULT_LENGTH`), `Mic` (dropdown from `GET /devices`). One ghost `Start` button (ink text, hairline border, accent on hover).
2. **The stage (center, large):**
   - **Paced mode (default):** one giant current character in the hero mono size, centered. The next few upcoming characters faint to its right, completed ones faded to the left. A thin metronome line under the current character fills over `TRAINER_PACED_GAP_MS` and resets on each correct press. This isolates presses for the cleanest data.
   - **Flow mode:** a single line of upcoming random characters scrolling right to left, monkeytype-style; the current one marked; correct in `--good`, incorrect in `--accent`. Faster, more data, some natural overlap.
3. **Live readout row:** micro-labels with big mono numerals: `Keys captured`, `Elapsed`, and in flow mode `WPM`.
4. **Coverage strip:** a row of 37 tiny cells, one per key, each filling from `--line` toward `--ink` as that key accumulates samples, so the typist sees which keys still need data. Useful and a nice visual.
5. **Stop button:** calls `/trainer/stop`, then shows a quiet confirmation line with the saved counts and path.

`trainer.js`:
- On Start: `POST /trainer/start`, then `GET /trainer/prompt` for the sequence, start the UI clock and (paced) the metronome.
- The browser's own `keydown` drives only the UI: advance the pointer, color correct/incorrect, tick the coverage strip. It does not label anything.
- On Stop: `POST /trainer/stop`, render the summary.
- Wrap any `localStorage` use (remembered keyboard/typist) in try/catch.

---

## 10. Terminal fallback (`scripts/collect.py`)

A no-browser paced collector for the first minutes on-site before the page is wired: print `balanced_sequence` one character at a time on a metronome while `session.py` records, then stop and report. This unblocks data collection immediately.

---

## 11. How to run a collection session (on-site workflow)

1. Pin the mic: hit `GET /devices`, set `INPUT_DEVICE` in config.
2. Grant OS input monitoring (the app will tell you if it is missing).
3. Open `/trainer`, set `Keyboard` and `Typist`, choose Paced, and collect. Aim for at least 100 presses per key per board (about an hour split across typists). Watch the coverage strip and keep going until every key is filled.
4. Repeat on the second board (change `Keyboard`).
5. Collect a few short extra sessions to reserve as held-out test recordings and as cross-keyboard calibration strings.
6. The recordings are now on disk for BUILD_MODEL to train on.

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

- `/trainer` runs both paced and flow modes with the coverage strip, and `scripts/collect.py` works as a terminal fallback.
- Running a session writes a valid `audio.wav` and `events.json`, and `test_session.py` confirms alignment.
- At least one full balanced dataset per board can be collected, ready for BUILD_MODEL.
