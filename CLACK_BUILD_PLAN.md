# Clack — Plan 00: Start Here (orientation + scaffold)

**This is the first plan. Read it fully before touching any other file.** Its two jobs:
1. Give you (the executor) a complete understanding of what Clack is, how it works, and the conventions every later plan assumes.
2. Have you scaffold the entire repository: every folder, every placeholder module, config, docs, dependencies, and a green test harness, committed to git.

When this plan's DONE is met, stop. Then build the project by running the five component plans (BUILD_TRAINER, BUILD_MODEL, BUILD_BACKEND, BUILD_FRONTEND, BUILD_DEFENSE) in the order given in section 5. Do not start writing component logic in this plan. This plan only sets up and orients.

**App:** Clack. **Event:** hackUMBC 2026 (24 hours). **Track:** Cyber, positioned for the overall grand prize.
**Builds on:** Harrison, Toreini, Mehrnezhad, "A Practical Deep Learning-Based Acoustic Side Channel Attack on Keyboards," IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074).

---

## 1. What Clack is

Clack recovers what someone types from the **sound** of their keyboard, live, and then defeats its own attack with a countermeasure.

The demo, in one picture: a judge types a short passphrase on a mechanical keyboard. Clack is only listening through a microphone, never reading the keys. Within about a second of each keystroke, the recovered text appears on screen. Then a defense mode is switched on, the judge types again, and the same attack collapses to noise. Attack and defense, measured, side by side.

Why it wins: the Cyber field at student hackathons is weak (scanners, password meters, dashboards), and a working acoustic side channel with a live demo and a real countermeasure stands out. It is also legible to general judges in three minutes, which is what competes for the overall prize. It is grounded in published research and then goes past it (live decode, cross-keyboard, measured defense).

**Ethics and scope (non-negotiable):** this is a defensive demonstration. It only records the team's own keyboards and consenting typists. It exploits no software and targets no person. The point judges should take away is the defense.

---

## 2. Mental model (understand this before building anything)

Think of the system as three bands that share one classifier.

```
ATTACK   (inference, no labels):   mic audio -> onset detection -> log-Mel spectrogram -> CNN -> top-k keys -> language-model correction -> recovered text
TRAINING (auto-labeled, on-site):  Clack Trainer shows random chars -> backend records audio + key events on one clock -> auto-labeled windows -> augment -> train CNN
DEFENSE  (the payoff):             acoustic masker corrupts the mic input -> attack accuracy craters -> before/after measured
```

The single most important concept, the one bug that will waste your time if you miss it:

> **Segmentation differs between training and attack, but the window must be identical.** At training time, labels come from keyboard events, so you cut a window at each event's exact timestamp. At attack time there are no events, so you find onsets from the audio energy itself. Both paths must produce the same window shape and offset, or the classifier sees one distribution in training and another at inference and accuracy collapses.

Second key idea: **the Clack Trainer.** Data is collected with a monkeytype-style page that shows **random characters** (not words). Random characters give even coverage across every key (words over-represent "e" and starve "q" and "z") and remove linguistic bias from the training signal. The browser is only a teleprompter; the backend captures audio and key events in one Python process on one clock (`time.perf_counter()`), so labels are exact and there is no browser-to-server clock sync problem. Labels come from the actual keys pressed (pynput), so a typo labels its own sound correctly.

Third key idea: **cross-keyboard by embeddings.** The model exposes an `embed()` vector per keystroke. To attack a keyboard it never trained on, type a short calibration string on that board, average the embeddings per key into prototypes, and classify new keystrokes by nearest prototype. No retraining on the day.

Vocabulary used across all plans: **window** (the fixed audio slice around one press), **onset** (a detected press in the audio), **log-Mel** (the spectrogram image fed to the model), **top-k** (the k most likely keys for one press), **prototype** (a per-key mean embedding for calibration), **masker** (the defense sound).

---

## 3. Golden rules (apply in every plan)

1. **Commit regularly.** Commit after every working sub-step, not once at the end, with clear messages (for example `phase 1: sounddevice capture + device enumeration`). Never leave the tree uncommitted between sub-steps.
2. **One codebase, one plan set.** Backend and UI live in the same repo and are built together, not as separate efforts.
3. **Everything runs on localhost.** No cloud dependency to collect, train, attack, or serve.
4. **No live network call on the critical path.** Correction defaults to a local model; any external API is behind a config flag, off by default.
5. **Config over hardcoding.** Every tunable lives in `config.py`.
6. **Deterministic where it matters.** Seed all RNGs from `config.SEED`; log the config used for every training run.
7. **Fail loudly.** Missing device, missing permission, empty dataset: raise a clear, specific error. Never fall back to silent placeholder behavior.
8. **One stated DONE per phase.** When it is met, say so and stop. Findings you notice are added to a list at the end of the run, not turned into work mid-phase.
9. **Docs and tests as you go,** per sections 10 and 11.
10. **No em dashes in any prose you write.** Use commas, parentheses, or colons.

---

## 4. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| ML | PyTorch, torchaudio |
| Audio I/O | sounddevice, soundfile |
| DSP / arrays | numpy, scipy, librosa |
| Keyboard events | pynput |
| Backend | FastAPI, uvicorn, websockets |
| Frontend | single page, vanilla JS + canvas, CDN fonts/libs, no build step |
| Correction | local n-gram (nltk or bundled corpus); LLM API optional, off by default |
| Testing | pytest, pytest-cov, hypothesis, pytest-asyncio, httpx, numpy.testing |

Detect the compute device once at startup: CUDA if available, else Apple MPS, else CPU. Log which one.

---

## 5. The build order (how the five component plans fit)

After this scaffold plan, build in this order. Each component plan is self-contained and states its own DONE.

| Step | Plan | Builds | Depends on | One-line DONE |
|---|---|---|---|---|
| 1 | **BUILD_TRAINER.md** | the monkeytype-style collector: capture, keylog, sessions, prompts, trainer endpoints and page | scaffold | trainer collects auto-labeled sessions to disk |
| 2 | **BUILD_MODEL.md** | features, dataset, CNN, training, offline attack, calibration | recordings from step 1 | same-keyboard model recovers a held-out sentence from audio |
| 3 | **BUILD_BACKEND.md** (live part) | live streaming decode, correction, attack WebSocket, wiring all routes | a trained model | typing into the mic streams live guesses over the socket |
| 4 | **BUILD_FRONTEND.md** | the editorial-minimal attack dashboard and the five hero visuals | the endpoints and socket | dashboard shows live recovery and all five visuals |
| 5 | **BUILD_DEFENSE.md** | the acoustic masker and before/after measurement | a working attack | masker on craters measured accuracy; UI shows the drop |

| 6 | polish + reach | frontend polish pass, cross-keyboard (from BUILD_MODEL) | a solid core | polish never touches the decode path; reach never risks the floor |

Note: the Clack Trainer is built first (step 1, BUILD_TRAINER.md) because nothing downstream can be tested without data. It consolidates the capture, keylog, session, prompt, and trainer-page pieces; BUILD_BACKEND then wires its routes into the full server, and BUILD_FRONTEND owns only the attack dashboard.

Order priority: **lock the floor first** (steps 1 to 4, same-keyboard live attack), then **defense** (step 5, it wins the track), then polish and the cross-keyboard reach. Two rules never move: the reach never risks the guaranteed demo, and UI polish never touches the decode path.

The trainer's terminal fallback (`scripts/collect.py`) lets you collect data on-site before the trainer page is wired.

---

## 5A. Agents and parallel build

The build parallelizes well because the plans fix the contracts up front: the data schema (section 9), `config.py` (section 8), the endpoint and WebSocket formats (BUILD_BACKEND), and the design tokens (BUILD_FRONTEND). An agent can build its module against those contracts and test it on synthetic fixtures, without waiting for the others. Orchestrate subagents in waves.

**Two hard rules for parallel work:**
- **Disjoint file ownership.** No two agents edit the same file in the same wave. This is what keeps parallel work conflict-free. `server.py` is the single integration file and is owned only by the orchestrator, wired last.
- **Each agent gets a bounded scope and one stated DONE.** An agent builds its named files, writes their tests, makes them pass on synthetic fixtures, commits, and stops. It does not wander into another module or start integrating.

**Wave 0 (serial): scaffold.** This plan. It must finish before any fan-out, because it creates the stubs and encodes the contracts in code. One agent.

**Wave 1 (parallel subagents, disjoint files):**
| Agent | Owns (files) | Source plan | Builds and tests against |
|---|---|---|---|
| TRAINER | `capture.py`, `keylog.py`, `prompts.py`, `session.py`, `scripts/collect.py`, `ui/trainer.html`, `ui/trainer.js` + tests (`test_prompts`, `test_session`) | BUILD_TRAINER | the data schema (section 9); writes real sessions to disk |
| ML | `segment.py`, `features.py`, `dataset.py`, `model.py`, `train.py`, `attack.py`, `calibrate.py`, `scripts/run_train.py`, `scripts/run_attack.py` + tests | BUILD_MODEL | the `conftest` synthetic fixtures; real training waits for real data |
| CORRECT | `correct.py` + test, plus a small bundled corpus | BUILD_BACKEND (correction) | a known noisy candidate lattice |
| FRONTEND | `ui/index.html`, `ui/app.js`, `ui/style.css` (the design system and dashboard) | BUILD_FRONTEND | the documented endpoint and WebSocket contracts, using a mock socket and mock data |
| DEFENSE | `defense.py` + test | BUILD_DEFENSE | its own unit tests (band content, on/off) |

Shared-token note: `ui/style.css` (owned by FRONTEND) holds the `:root` design tokens. The TRAINER agent's `trainer.html` links `style.css` for those tokens (read-only) and keeps any trainer-specific styles inline in its own file, so no two agents edit `style.css`.

**Wave 2 (integration, orchestrator only, after Wave 1 merges):**
- `stream.py` (live decode), which needs `model` + `capture` + `segment`/`features`.
- `server.py`, which wires every endpoint, the WebSocket, the static UI, and the defense routes. Single owner.
- `scripts/serve.py`. Then connect the FRONTEND to the real socket and the DEFENSE to the real attack.

**Wave 3 (serial, on-site, cannot be parallelized):** collect real data on the boards, train the real model, verify the live attack, then fan out again for the frontend polish pass and the cross-keyboard reach.

**Honest limits of parallelism:** agents speed up writing the independent modules in the first hours. The later bottleneck (collecting data on-site, training, and tuning onset detection live in the room) is inherently serial and empirical, so no number of agents shortens it. Integrate in an explicit wave, not continuously, and review each agent's output against the contracts before wiring it into `server.py`. Commit each agent's work as its own set of commits.

---

## 6. Hardware for the demo

| Item | Role |
|---|---|
| **Keyboard A: blue-switch board (clicky)** | Loudest, sharpest onsets. Strongest attack signal, best floor board. |
| **Keyboard B: C3 Equalz board (linear/tactile)** | Quieter, smooth. Still attackable, and different enough to be a real cross-keyboard target. |
| **The Mac** | Runs everything. Built-in mic captures keystrokes, built-in speakers play the defense masker. No external mic or speaker needed. |

Rules from this hardware:
- **Pick the floor board by data, not vibes.** Early on-site, collect and train on both boards; the higher-accuracy one is the guaranteed same-keyboard demo (expect the blue board). The other is the cross-keyboard target.
- **Train on the actual board you will demo on.** Switch type changes only the training data, not code or config.
- **One machine for mic and speaker.** Co-located mic and speaker make the defense stronger (the masker easily swamps the mic). Keep the keyboard directly in front of the Mac.
- **Capture raw audio with OS processing off** (no echo cancellation, noise suppression, auto gain).

---

## 7. Repository layout (create all of this in the scaffold)

```
clack/
  README.md  CONTRIBUTING.md  CHANGELOG.md  VERSION  LICENSE  CITATION.cff
  requirements.txt  pyproject.toml  .gitignore  conftest.py
  config.py                    # all tunables in one place
  docs/architecture.md
  data/                        # gitignored, created at runtime
    recordings/  datasets/  models/  corpus/
  clack/
    __init__.py
    config_types.py            # dataclasses mirroring config.py
    capture.py                 # sounddevice recording + device enumeration   [BUILD_BACKEND]
    keylog.py                  # pynput event capture + permission check       [BUILD_BACKEND]
    prompts.py                 # balanced random-character generator           [BUILD_BACKEND]
    session.py                 # start/stop a collection session, write files  [BUILD_BACKEND]
    segment.py                 # onset detection + event-window cut            [BUILD_MODEL]
    features.py                # log-Mel spectrogram + normalization           [BUILD_MODEL]
    dataset.py                 # (window,label) pairs, augmentation, loaders   [BUILD_MODEL]
    model.py                   # CNN classifier + embedding head               [BUILD_MODEL]
    train.py                   # training loop, seeding, run logging           [BUILD_MODEL]
    attack.py                  # offline batch attack on held-out audio        [BUILD_MODEL]
    calibrate.py               # cross-keyboard few-shot prototypes            [BUILD_MODEL]
    stream.py                  # live streaming decode (rolling buffer)        [BUILD_BACKEND]
    correct.py                 # n-gram + beam-search correction               [BUILD_BACKEND]
    defense.py                 # acoustic masker + accuracy measurement        [BUILD_DEFENSE]
    server.py                  # FastAPI app + WebSocket, serves the UI        [BUILD_BACKEND]
    ui/
      index.html  app.js  trainer.html  trainer.js  style.css                 [BUILD_FRONTEND]
  scripts/
    collect.py  run_train.py  run_attack.py  serve.py
  tests/
    test_prompts.py  test_segment.py  test_features.py  test_dataset.py
    test_model.py  test_correct.py  test_calibrate.py  test_server.py
```

The bracket tags show which component plan fills each module. In the scaffold, create them all as clean-importing stubs.

---

## 8. Configuration (`config.py`, write this in full during scaffold)

```python
SEED = 42

# Audio
SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = "float32"
INPUT_DEVICE = None            # None = default; pin an index at the venue

# Keystroke window
WINDOW_MS = 200
PRE_ONSET_MS = 40
# WINDOW_SAMPLES = int(SAMPLE_RATE * WINDOW_MS / 1000) = 8820

# Log-Mel spectrogram
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 64
FMIN = 0
FMAX = 22050
# T (time frames) ~= WINDOW_SAMPLES / HOP_LENGTH ~= 35; fix once measured

# Onset detection (attack path)
ONSET_HP_CUTOFF_HZ = 1500
ONSET_FRAME_MS = 5
ONSET_K = 3.0
ONSET_MIN_GAP_MS = 60

# Key set (classes)
KEY_SET = list("abcdefghijklmnopqrstuvwxyz0123456789") + ["space"]

# Model
EMBED_DIM = 128
DROPOUT = 0.3

# Training
BATCH_SIZE = 64
EPOCHS = 60
LR = 1e-3
WEIGHT_DECAY = 1e-4
EARLY_STOP_PATIENCE = 8
VAL_SPLIT = 0.15

# Augmentation (train only)
AUG_NOISE_STD = 0.005
AUG_TIME_SHIFT_MS = 10
AUG_PITCH_SEMITONES = 1.0
SPECAUG_TIME_MASK = 6
SPECAUG_FREQ_MASK = 8

# Trainer (collection)
TRAINER_DEFAULT_LENGTH = 300
TRAINER_PACED_GAP_MS = 550

# Correction
NGRAM_ORDER = 5
BEAM_WIDTH = 8
USE_LLM_CORRECTION = False
LLM_MODEL = None

# Defense
MASKER_BAND_HZ = (1000, 10000)
MASKER_LEVEL = 0.3

# Paths
DATA_DIR = "data"
RECORDINGS_DIR = "data/recordings"
DATASETS_DIR = "data/datasets"
MODELS_DIR = "data/models"
CORPUS_DIR = "data/corpus"
```

---

## 9. Data formats on disk (the contract every plan shares)

**Recording session** at `data/recordings/<session_id>/`:
- `audio.wav`: mono, `SAMPLE_RATE`, float32.
- `events.json`:
```json
{
  "session_id": "2026-09-26T09-30-00_blue_akarsh",
  "sample_rate": 44100,
  "audio_start_perf": 12345.678,
  "keyboard_id": "blue",
  "typist": "akarsh",
  "mode": "paced",
  "events": [{"key": "a", "t_perf": 12346.101, "type": "press"}]
}
```
Alignment: `sample_index = round((t_perf - audio_start_perf) * sample_rate)`. Audio and events share one `perf_counter` clock. Only `press` events; keys not in `KEY_SET` are dropped at dataset-build time.

**Dataset cache** at `data/datasets/<name>.npz`: `X (N, N_MELS, T) float32`, `y (N,) int64`, `classes` (strings), `meta` (JSON string).

**Model** at `data/models/<name>/`: `model.pt`, `config.json`, `metrics.json`, `confusion_matrix.png`.

---

## 10. Documentation standards (follow in every plan)

- Numpydoc docstrings on every public function, class, and module: one-line summary, then Parameters, Returns, Raises, and a short example for non-trivial ones. Cite the paper in `segment.py`, `features.py`, `model.py`. Update docstrings when behavior changes.
- Type hints on all signatures.
- Comments explain why, not what. No commented-out code. Mark shortcuts with `TODO:` (what and why).
- README (intent, problem, install, a usage example per entry point, a dashboard screenshot, the ethics note, the paper link), CONTRIBUTING (style, setup, branching), pinned requirements, CHANGELOG (Keep a Changelog), VERSION (semver), LICENSE (MIT), CITATION.cff (the paper), docs/architecture.md.

---

## 11. Testing standards (follow in every plan)

Stack: pytest, pytest-cov, hypothesis, pytest-asyncio, httpx, numpy.testing. Use `assert_allclose` for arrays. Use Hypothesis for `segment.py`, `features.py`, `prompts.py`. Every test asserts real behavior. Do not train a real model in a test. `pyproject.toml` configures pytest so `pytest` alone runs everything with coverage.

---

## 12. THE TASK FOR THIS PLAN: scaffold the repository

Do exactly this, committing as you go. This is the only building this plan does.

1. **Create the tree** in section 7: all folders and every module as a clean-importing stub. Each stub module has its numpydoc module docstring and declares its public functions/classes with type-hinted signatures whose bodies `raise NotImplementedError("built in <PLAN>")`. Stubs must import without error so the test harness is green.
2. **Write `config.py`** exactly as section 8, and `config_types.py` with dataclasses mirroring it (so other modules can import typed config).
3. **Write the docs and metadata:** README (fill the intent, the ethics note, the paper link, and placeholders for install and screenshot), CONTRIBUTING, CHANGELOG (with an `Unreleased` section), VERSION (`0.1.0`), LICENSE (MIT), CITATION.cff (the 2023 paper), docs/architecture.md (put the section 2 mental model and the pipeline sketch here so the design is captured in-repo).
4. **Write `requirements.txt`** listing: torch, torchaudio, numpy, scipy, librosa, soundfile, sounddevice, pynput, fastapi, "uvicorn[standard]", websockets, httpx, pytest, pytest-cov, pytest-asyncio, hypothesis, matplotlib, nltk. After the environment installs, freeze exact versions back into this file.
5. **Write `pyproject.toml`** with pytest config:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   addopts = "-q --cov=clack --cov-report=term-missing"
   ```
6. **Write `.gitignore`**: `data/`, `plans/`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `.coverage`, `*.pt`, `*.npz`, `*.wav`. (`plans/` holds these build-plan markdown files, which are local working notes and are never committed.)
7. **Write `conftest.py`** with shared fixtures used later (a `tmp_session` factory that writes a tiny synthetic `audio.wav` + `events.json`, and a `device` fixture returning the detected torch device).
8. **Write one real passing test** (`tests/test_config.py`): assert every `clack` module imports, and assert `WINDOW_SAMPLES` and the computed `T` match the config formulas.
9. **Create the runtime data dirs** (`data/recordings`, `data/datasets`, `data/models`, `data/corpus`) with a `.gitkeep` in each so the structure exists, while `data/` contents stay gitignored.
10. **Initialize git**, make the first commit, then commit after each of the steps above (several small commits, not one).
11. **Verify:** run `python -c "import clack, clack.model, clack.server"` (all stubs import) and `pytest` (green). Print the detected compute device.

**DONE for this plan:** the full tree exists, every module imports with no error, `pytest` passes, docs and metadata are written, `config.py` is complete, the data dirs exist, and the work is committed in several small commits. At that point, stop and begin step 1 of the build order (BUILD_BACKEND.md, capture and trainer).

---

## 13. Guardrails (all plans)

- Record only the team's own keyboards and consenting typists.
- Never display an accuracy number that cannot be reproduced live.
- Claim search-space collapse for passwords, not always-exact recovery.
- The cross-keyboard reach never blocks the guaranteed same-keyboard demo.
- UI polish never touches the decode path.
- Never skip the defense. It is the half that wins the track.

## 14. Reference

J. Harrison, E. Toreini, M. Mehrnezhad. "A Practical Deep Learning-Based Acoustic Side Channel Attack on Keyboards." IEEE EuroS&PW 2023.
arXiv: https://arxiv.org/abs/2308.01074 . IEEE Xplore: https://ieeexplore.ieee.org/document/10190721
