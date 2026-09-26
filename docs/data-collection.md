# Data Collection Protocol

Owner: BUILD_TRAINER. This is the physical operator protocol the team follows
every collection session. The model learns the exact acoustic signature of one
keyboard, one mic position, and one surface. The single most important rule:
**whatever setup you train on, keep it identical for the demo.**

## The three sessions (per board)

Collect three separate sessions per board so evaluation is honest (a session-level
split, never a random split of one session):

- **Session A (train).** Purpose = Train. Collect from **2 to 3 teammates**
  (`TRAINER_MIN_TYPISTS`) on the board until every key hits
  `TRAIN_SAMPLES_PER_KEY` (40). About 15 minutes split across typists.
- **Session B (eval, held out).** Purpose = Eval, a SEPARATE recording, ideally a
  **different typist who gave zero training samples**, to `EVAL_SAMPLES_PER_KEY`
  (10). This is what gives legitimate top-1/top-3 numbers and tests the
  judge-is-a-different-typist case.
- **Session C (demo).** Purpose = Demo, a natural free phrase (no quota) at the
  MVP cadence (at least `DEMO_MIN_GAP_MS`, 250 ms, about 3 to 4 keys/sec), to
  prove decoding a realistic sequence the model never saw.

Repeat Sessions A and B on the second board (same one mic, same geometry). This is
core: the goal is one model across both boards, so both need data. Train ONE
combined model on both boards' A sessions, evaluate on each board's held-out B
session, and demo on C (BUILD_MODEL section 8A).

## Surface and keyboard

- Put the keyboard flat on a hard, stable surface (a solid desk or table), not a
  soft or padded one that dampens the sound. Use the same surface for training and
  the demo.
- Do not move or re-seat the keyboard between collection and demo. If you must,
  mark its position with tape and return it to the same spot.
- One `keyboard_id` per physical board (for example `blue`, `c3equalz`). Never mix
  two boards in one session.

## Microphone position (the most sensitive variable)

- Use the Mac's built-in mic (or one fixed external mic). Place the laptop in a
  consistent spot relative to the keyboard: the keyboard directly in front of the
  laptop, roughly 15 to 25 cm from the mic, with a clear line of sight to the keys
  (nothing between the mic and the keyboard).
- Mark the laptop and keyboard positions with tape so the exact geometry is
  reproducible. Distance consistency matters more than the exact distance: pick one
  and never change it between training and demo.
- Do not pick up, tilt, or slide the laptop after collection. The demo must use the
  same mic geometry the model trained on.
- Pin the mic before collecting: hit `GET /devices`, set `INPUT_DEVICE` in
  `config.py`, and grant OS input monitoring (the app tells you if it is missing).

## Environment

- Collect in a spot as close as possible to where you will demo (ideally the same
  table). Room acoustics are part of what the model learns.
- Keep it reasonably quiet during collection: no talking, no chair scraping, no
  table bumps, phones off the table. The ambient calibration handles steady room
  noise, but transients pollute training data.
- Same lighting/fan/AC conditions if you can; steady background is fine, sudden
  noises are not.
- Capture raw audio with OS processing off (no echo cancellation, noise
  suppression, or auto gain).

## How to press the keys (technique)

- Paced mode, one key per metronome beat: press the shown key deliberately, bottom
  it out fully (the bottom-out is part of the signal), and fully release before the
  next beat. One clean press per beat, no overlap.
- Keep a consistent, natural strike force. Do not slam or feather the keys; type as
  you normally would but one key at a time.
- Rest your hands off the other keys between presses so you do not create
  accidental transients. Only the prompted key should make a sound.
- If you mistype, keep going: the actual key pressed is auto-labeled correctly. Do
  not use backspace (it is not in the key set and adds noise); just continue.
- Do not talk or move while a press is being recorded.

## Typists (cover the judge case)

- Session A (train): 2 to 3 teammates so the model is not tuned to one pair of
  hands. Each teammate types a share; the balanced coverage still applies across
  the whole session.
- Session B (eval): a teammate who contributed ZERO training samples types it. This
  is the honest test of "a different person (the judge) sits down."
- Session C (demo): a natural phrase at the demo cadence (at least
  `DEMO_MIN_GAP_MS`).

## Multiple keyboards (one mic, both boards are core work)

- One microphone for everything, so there is no cross-microphone problem. Collect
  on BOTH boards (blue and C3 Equalz) through that same mic, same geometry, same
  surface. Tag each session with its `keyboard_id`.
- Run Sessions A and B on each board (and a demo Session C on whichever board you
  will show). Collecting both boards is core, not optional, because the goal is one
  model that works across both.
- Generalizing to a board you never recorded is the separate cross-keyboard stretch
  (BUILD_MODEL section 8), uncertain and never the floor. Supporting the boards you
  own does not need it.

## One mic, machine roles, and weight transfer

The team uses ONE microphone for everything; the machine that owns the mic is the
collection-and-demo machine.

- **Pick the mic machine (the demo Mac) first.** All Sessions A/B/C, on both
  boards, are recorded on that machine's mic. The demo also runs on it.
- **Offloading training compute is fine.** If another laptop trains faster, copy
  the RECORDINGS (`data/recordings/<session_id>/` folders) to it, train, then copy
  the model folder back. Or just train on the mic machine (small CNN, minutes to
  under an hour).
- **What "transfer weights" means:** copy the whole `data/models/<name>/` folder
  (`model.pt`, `config.json`, `metrics.json`, the class list, and `norm.json` if
  used). Both machines must be on the same git commit so `config.py` (window, Mel,
  key set, `SPEC_FRAMES`) matches, or the model input will not line up.
- **Verify after transfer:** on the mic machine, pin its `INPUT_DEVICE` and run the
  offline attack on the held-out Session B for each board to confirm the model
  reproduces the expected accuracy on that mic.

## Running a session

- Web trainer: open `/trainer`, set Keyboard, Typist, Purpose, Mode, and Mic, then
  Start. Paced mode isolates presses for the cleanest data; the coverage strip
  auto-stops the session when every key reaches its quota.
- Terminal fallback (before the page is wired):

  ```bash
  python scripts/collect.py --keyboard blue --typist akarsh --purpose train
  ```

Both write `data/recordings/<session_id>/audio.wav` and `events.json` with the
clock-mapping fields (`audio_start_perf`, `input_latency_s`, `stream_time_origin`)
used to align events to audio samples.
