# Clack — Plan 00: Start Here (orientation + scaffold)

**This is the first plan. Read it fully before touching any other file.** Its two jobs:
1. Give you (the executor) a complete understanding of what Clack is, how it works, and the conventions every later plan assumes.
2. Have you scaffold the entire repository: every folder, every placeholder module, config, docs, dependencies, and a green test harness, committed to git.

When this plan's DONE is met, stop. Then build the project by running the six component plans (BUILD_TRAINER, BUILD_MODEL, BUILD_EVAL, BUILD_BACKEND, BUILD_FRONTEND, BUILD_DEFENSE) in the order given in section 5. Do not start writing component logic in this plan. This plan only sets up and orients. (Submission and Devpost logistics are handled later, near the deadline, not now.)

**App:** Clack. **Event:** hackUMBC 2026 (24 hours). **Track:** Cyber, positioned for the overall grand prize.
**Builds on:** Harrison, Toreini, Mehrnezhad, "A Practical Deep Learning-Based Acoustic Side Channel Attack on Keyboards," IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074).

---

## 0A. Hackathon compliance (read before your first commit)

This can disqualify the team if mishandled, so it comes first.

- **Commit window.** All GitHub commits for the submission must fall inside the hackathon window: 12:00 PM Saturday Sept 26 to 11:45 AM Sunday Sept 27. Do not commit before noon Saturday.
- **Write it during the event.** All submission code is written during the event. Use the 2023 paper as a methodology reference; do NOT copy an existing implementation of it (for example a public DeepKeyAttack repo) into the submission. Write Clack's implementation fresh.
- **No pre-event scaffold.** If any implementation code or scaffold was created before noon Saturday, do not silently reuse or commit it. Re-create it inside the window. If there is any ambiguity, ask a hackUMBC organizer.
- **The `plans/` folder is fine.** These build-plan markdown files are personal working notes, gitignored (section 12, step 6), and are not submission code.

The rest of the submission logistics (Devpost, demo video, pitch, deadlines) are deferred and handled later, near the deadline. This section is only the commit hygiene that has to be right from the first commit.

---

## 1. What Clack is

**Clack is an acoustic side-channel security auditor.** It measures how vulnerable a keyboard environment is to microphone-based keystroke inference, demonstrates the leakage live, applies an acoustic countermeasure designed to reduce recoverability through nearby microphones, and quantitatively verifies the reduction. Claim what the experiments support ("under our test setup, Clack reduced recovery from X% to Y%"), not that typing is made unrecoverable in general: a more robust attacker could exist, so the honest claim is measured reduction against Clack's own attack in the tested environment.

The product is a closed loop, and every plan and the pitch use this order:

```
AUDIT  ->  ATTACK SIMULATION  ->  DEFENSE  ->  VERIFY
(grade exposure) (prove leakage live) (apply masker) (measure the drop)
```

This framing matters for judging. Do not present Clack as "an attack with a defense bolted on"; present it as a defensive auditing tool whose attack step is how it proves and measures leakage. Lead with the audit and the defense in the README, the pitch, and the demo.

The creativity claim is NOT that acoustic keystroke inference is novel: it is not (the 2023 paper hit 95% with a nearby mic, and public projects already implement the attack). The claim is the closed loop: **existing work shows the attack; Clack turns it into a defensive tool that audits vulnerability, performs the attack live, applies mitigation, and quantitatively verifies that mitigation.** State it that way.

Why it fits the rubric (see section 1B): the Cyber rubric rewards a real cybersecurity function that an organization would use and deploy, so the audit (Exposure Check) plus the adaptive masker, deployed across endpoints, earn the 30% Security Improvement. The closed loop earns Creativity, and the live leakage is what makes the whole thing legible to general judges in three minutes, which competes for the overall prizes. Grounded in published research, extended into a defensive audit-and-verify tool.

---

## 1B. The judging rubric and how Clack targets it

The Cyber track is scored on four criteria. Build toward them deliberately.

| Criterion | Weight | How Clack scores |
|---|---|---|
| Creativity | 20% | Not "we built the attack" (that exists). The novelty is the closed loop: audit exposure, prove leakage live, apply mitigation, verify the drop. Frame it that way. |
| Execution | 20% | Readable, technically sound docs (the QA standards in section 10), edge cases covered (the failure tables in each plan), a high-quality dashboard. |
| Functionality | 30% | The applicable clause is "the app itself has full functionality, all planned elements work without bugs." Hitting this depends on a bug-free live demo, which is why demo hardening is a phase, not an afterthought. |
| Security Improvement | 30% | Earned by the **defense**: the Exposure Check is a real assessment any org runs per endpoint; the adaptive masker is a deployable protection; the fleet view shows it across machines. The attack alone would not score here. |

The one sub-point Clack cannot fully win is "scalable for large organizations or high levels of traffic/requests." No acoustic tool is a high-throughput service. The honest substitute is deployment across many endpoints (D3, the fleet view). Do not fake a throughput story; lean on the endpoint-scale story instead.

Consequence for the build: the defense and the audit are co-primary with the attack, not bolt-ons. The demo spends about two of its three minutes on the audit, defense, and verification.

**Tracks to enter** (hackUMBC allows entering as many as genuinely fit): Cybersecurity Application (primary), Most Engaging Demo (the judge-types-it-collapses moment is tailor-made), and Best Entrepreneurial Idea (position as an acoustic-leakage assessment tool for security teams). Also First Overall / Second Overall as general-judge contenders. Enter Best First Time Hack only if every team member qualifies. Do not distort the project to chase sponsor prizes (Gemini, DigitalOcean, Snowflake, etc.); the one that could fit later, only if the core is done, is a data/telemetry sponsor via the audit-history layer.

**Ethics and scope (non-negotiable):** this is a defensive auditing tool. It only records the team's own keyboards and consenting typists. It exploits no software and targets no person. The point judges should take away is the audit and the defense.

---

## 1C. The two biggest technical risks (decide these before building the demo)

1. **The judge is a different typist.** The model is trained on the team's keystrokes; a judge strikes with different force, duration, and rhythm, which can wreck accuracy. Mitigations, in order: collect training data from 2 to 3 teammates (`TRAINER_MIN_TYPISTS`) on the floor keyboard; explicitly evaluate train-on-two-teammates, test-on-a-third-who-gave-zero-samples (BUILD_MODEL, BUILD_EVAL); and keep a **guaranteed demo fallback: the judge chooses the phrase, a team member types it.** That still proves a microphone-only attack because the judge controls the unknown text. Test the cross-typist case today; do not discover it at judging.
2. **Paced training vs natural typing.** Collection is paced at 550 ms for clean isolation, but fast typing overlaps the 200 ms windows. State the guaranteed promise: **MVP threat model is typing at >= `DEMO_MIN_GAP_MS` (250 ms, about 3 to 4 keys/sec).** Show a small pace indicator or ask the judge to "type naturally, about 3 to 4 keys per second." Faster unrestricted entry is a stretch, only claimed if demonstrated.

---

## 2. Mental model (understand this before building anything)

Think of the system as three bands that share one classifier.

```
ATTACK   (inference, no labels):   mic audio -> onset detection -> log-Mel spectrogram -> CNN -> top-k keys -> language-model correction -> recovered text
TRAINING (auto-labeled, on-site):  Clack Trainer shows random chars -> backend records audio + key events on one clock -> auto-labeled windows -> augment -> train CNN
DEFENSE  (the payoff):             acoustic masker corrupts the mic input -> attack accuracy craters -> before/after measured
```

The single most important concept, the one bug that will waste your time if you miss it:

> **Both training and attack cut an onset-centered window; the only difference is where the label comes from.** Do not trust the audio driver's clock for the cut location: sounddevice/PortAudio buffers input, so callback arrival time is not the sample capture time, and cutting at a raw event timestamp would train the model on consistently shifted windows. Instead, at training time the keyboard event gives the **label** and an approximate location, then you search a small band (about plus or minus 100 ms, `ONSET_SEARCH_MS`) around it for the actual acoustic onset and cut the window there. At attack time there is no event, so the acoustic onset is found directly. Both paths cut the identical onset-centered window, tolerant of driver latency, and the classifier sees the same distribution in training and inference.

Second key idea: **the Clack Trainer.** Data is collected with a monkeytype-style page that shows **random characters** (not words). Random characters give even coverage across every key (words over-represent "e" and starve "q" and "z") and remove linguistic bias from the training signal. The browser is only a teleprompter; the backend captures audio and key events in one Python process on one clock (`time.perf_counter()`). The event clock assigns the correct **label** and locates each press approximately; the exact cut is then snapped to the acoustic onset (see the segmentation note above), so audio-driver latency never shifts the training windows. Labels come from the actual keys pressed (pynput), so a typo labels its own sound correctly.

Third key idea: **cross-keyboard by embeddings.** The model exposes an `embed()` vector per keystroke. To attack a keyboard it never trained on, type a short calibration string on that board, average the embeddings per key into prototypes, and classify new keystrokes by nearest prototype. No retraining on the day.

Fourth key idea: **prove it is only listening.** The app contains a pynput keylogger, but only for training. In attack mode the pynput listener is never instantiated, and the dashboard shows `Microphone: ACTIVE, Keyboard Events: DISABLED`. A judge must be able to see that recovery uses sound alone. This is correct engineering and the answer to the obvious "how do I know you are not reading the keyboard" question.

Fifth key idea: **a floor model.** Alongside the CNN, build a trivial nearest-centroid baseline over normalized log-Mel features (mean feature vector per key, classify by nearest centroid). It needs almost no machinery. If CNN training breaks at 3 AM you still have a working end-to-end demo, and "CNN 81% vs centroid 48%" is itself a clean technical result. Hackathon plans need a floor.

Vocabulary used across all plans: **window** (the fixed audio slice around one press), **onset** (a detected press in the audio), **log-Mel** (the spectrogram image fed to the model), **top-k** (the k most likely keys for one press), **prototype** (a per-key mean embedding for calibration), **masker** (the defense sound), **baseline** (the nearest-centroid floor model).

---

## 3. Golden rules (apply in every plan)

1. **Commit regularly.** Commit after every working sub-step, not once at the end, with clear messages (for example `phase 1: sounddevice capture + device enumeration`). Never leave the tree uncommitted between sub-steps.
2. **One codebase, one plan set.** Backend and UI live in the same repo and are built together, not as separate efforts.
3. **Everything runs on localhost.** No cloud dependency to collect, train, attack, or serve.
4. **No live network call anywhere at demo time.** Correction defaults to a local model (any external API is behind a config flag, off by default), and the UI loads with no network: fonts and libraries are self-hosted in the repo, not pulled from a CDN. Venue wifi must never be able to break the demo.
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
| Frontend | single page, vanilla JS + canvas, self-hosted fonts and libs (no CDN), no build step |
| Correction | local n-gram (nltk or bundled corpus); LLM API optional, off by default |
| Testing | pytest, pytest-cov, hypothesis, pytest-asyncio, httpx, numpy.testing |

Detect the compute device once at startup: CUDA if available, else Apple MPS, else CPU. Log which one.

---

## 5. The build order (how the six component plans fit)

After this scaffold plan, build in this order. Each component plan is self-contained and states its own DONE.

| Step | Plan | Builds | Depends on | One-line DONE |
|---|---|---|---|---|
| 1 | **BUILD_TRAINER.md** | the monkeytype-style collector: capture, keylog, sessions, prompts, trainer endpoints and page | scaffold | trainer collects auto-labeled sessions to disk, coverage-driven |
| 2 | **BUILD_MODEL.md** | features, dataset, the nearest-centroid baseline (floor), the CNN, one combined model across both boards, training, offline attack | recordings from step 1 (both boards, one mic) | baseline and CNN recover a held-out sentence (session-split); the combined model works on both boards |
| 3 | **BUILD_EVAL.md** | the metrics harness: onset recall, top-k, CER, latency, raw vs corrected, baseline vs defense delta | a model + attack | evaluate.py reports every metric on a held-out recording |
| 4 | **BUILD_BACKEND.md** (live part) | live streaming decode, ambient calibration, attack-mode keylogger-off, correction, attack WebSocket, preflight, wiring all routes | a trained model | typing into the mic streams live guesses over the socket, keylogger provably off |
| 5 | **BUILD_FRONTEND.md** | the editorial-minimal dashboard, the five hero visuals, RAW-vs-corrected, input-source and calibration indicators, metrics panel | the endpoints and socket | dashboard shows live recovery, metrics, and the input-source state |
| 6 | **BUILD_DEFENSE.md** | the defense: masker + measurement, D1 Exposure Check (the audit), D2 minimum-effective adaptive masker, D3 report + fleet | a working attack + eval | exposure grades a setup, masker craters accuracy at minimum level, fleet view shows it across machines |

| stretch | cross-keyboard to an UNSEEN board (from BUILD_MODEL section 8, Tier A/B) | recover on a board with zero training data | a solid core | attempted only after step 6; never risks the floor. (Supporting the team's OWN boards is core, done via the combined model in step 2.) |

Submission and Devpost logistics (freeze, demo video, pitch rehearsal) are deferred to near the deadline and are not a build plan here.

Note: the Clack Trainer is built first because nothing downstream can be tested without data. Steps 2 and 3 can overlap (eval builds against the model contract). BUILD_BACKEND wires the trainer and defense routes into the full server; BUILD_FRONTEND owns only the dashboard.

Order priority: **lock the floor first** (steps 1 to 5: same-board live attack with the baseline as the guaranteed floor model, plus the dashboard). Then **the audit and defense** (step 6, where the 30% Security Improvement is won; D1 Exposure Check is the must-have, D2 and D3 follow if time allows). **Multiple keyboards, know the difference:** supporting the team's OWN boards (blue and C3 Equalz), all captured through the one mic, is CORE work, done by training one combined model on both boards (they are in-distribution, so this is reliable; see BUILD_MODEL 8A). Generalizing to a board with ZERO training data is the separate cross-keyboard STRETCH (BUILD_MODEL section 8), uncertain because embedding geometry does not automatically transfer, and it never jeopardizes the floor. Rules that never move: the unseen-board reach never risks the guaranteed demo, UI polish never touches the decode path, the defense features never break the working attack-plus-basic-masker demo, and the baseline model is always kept working as the fallback.

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
| ML | `segment.py`, `features.py`, `dataset.py`, `model.py` (centroid baseline + CNN), `train.py`, `attack.py`, `calibrate.py`, `scripts/run_train.py`, `scripts/run_attack.py` + tests | BUILD_MODEL | the `conftest` synthetic fixtures; real training waits for real data |
| EVAL | `evaluate.py` + `test_eval.py` | BUILD_EVAL | synthetic predictions and ground truth (a mock prediction interface) |
| CORRECT | `correct.py` + test, plus a small bundled corpus | BUILD_BACKEND (correction) | a known noisy candidate lattice |
| FRONTEND | `ui/index.html`, `ui/app.js`, `ui/style.css` (the design system and dashboard) | BUILD_FRONTEND | the documented endpoint and WebSocket contracts, using a mock socket and mock data |
| DEFENSE | `defense.py`, `exposure.py` + tests (`test_defense`, `test_exposure`) | BUILD_DEFENSE | its own unit tests (band content, on/off, exposure grading); the dashboard defense panel is built by FRONTEND against these contracts |

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
- **One mic for everything.** All audio, both boards, every session, is captured through the one microphone in the same spot with the same geometry. No cross-microphone concern.
- **Both boards are core.** Collect on blue and C3 Equalz and train ONE combined model on both (BUILD_MODEL 8A), so Clack works across both boards and you can demo swapping keyboards with the same model. Per-board models are the fallback; an unseen board is the separate stretch.
- **One machine for mic and speaker.** Co-located mic and speaker make the defense stronger (the masker easily swamps the mic). Keep the keyboard directly in front of the Mac.
- **Capture raw audio with OS processing off** (no echo cancellation, noise suppression, auto gain).

---

## 7. Repository layout (create all of this in the scaffold)

```
clack/
  README.md  CONTRIBUTING.md  CHANGELOG.md  VERSION  LICENSE  CITATION.cff
  requirements.txt  pyproject.toml  .gitignore  conftest.py
  config.py                    # all tunables in one place
  docs/                        # project documentation, kept current as the app is built
    architecture.md            # system design, the AUDIT->VERIFY loop, pipeline, train-vs-attack, mode separation
    data-collection.md         # the physical operator protocol (mic placement, key-press technique, multi-keyboard) from BUILD_TRAINER 11A
    threat-model.md            # what Clack defends against and explicitly what it does not
    evaluation.md              # the metrics and how to reproduce the before/after table
    runbook.md                 # demo-day operations: preflight, demo order, fallbacks, troubleshooting
    api.md                     # HTTP + WebSocket endpoints and message formats
  data/                        # gitignored, created at runtime
    recordings/  datasets/  models/  corpus/  reports/
  clack/
    __init__.py
    config_types.py            # dataclasses mirroring config.py
    capture.py                 # sounddevice recording + device enumeration   [BUILD_TRAINER]
    keylog.py                  # pynput event capture + permission check       [BUILD_TRAINER]
    prompts.py                 # balanced random-character generator           [BUILD_TRAINER]
    session.py                 # start/stop a collection session, write files  [BUILD_TRAINER]
    segment.py                 # onset detection + event-window cut            [BUILD_MODEL]
    features.py                # log-Mel spectrogram + normalization           [BUILD_MODEL]
    dataset.py                 # (window,label) pairs, augmentation, loaders   [BUILD_MODEL]
    model.py                   # CNN classifier + embedding head + centroid baseline [BUILD_MODEL]
    train.py                   # training loop, seeding, run logging           [BUILD_MODEL]
    attack.py                  # offline batch attack on held-out audio        [BUILD_MODEL]
    calibrate.py               # cross-keyboard few-shot prototypes (stretch)  [BUILD_MODEL]
    evaluate.py                # metrics harness: recall, CER, latency, deltas [BUILD_EVAL]
    stream.py                  # live streaming decode + ambient calibration   [BUILD_BACKEND]
    correct.py                 # n-gram + beam-search correction               [BUILD_BACKEND]
    defense.py                 # adaptive masker + accuracy measurement        [BUILD_DEFENSE]
    exposure.py                # Exposure Check: risk grade via the attack     [BUILD_DEFENSE]
    server.py                  # FastAPI app + WebSocket, serves the UI        [BUILD_BACKEND]
    ui/
      index.html  app.js  style.css                                          [BUILD_FRONTEND]
      trainer.html  trainer.js                                               [BUILD_TRAINER]
      fonts/  vendor/           # self-hosted fonts and JS libs, no CDN       [BUILD_FRONTEND]
  scripts/
    collect.py  run_train.py  run_attack.py  serve.py  preflight.py
  tests/
    test_config.py  test_prompts.py  test_session.py  test_segment.py
    test_features.py  test_dataset.py  test_model.py  test_correct.py
    test_calibrate.py  test_server.py  test_defense.py  test_exposure.py
    test_eval.py
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
WINDOW_SAMPLES = int(SAMPLE_RATE * WINDOW_MS / 1000)   # 8820, defined (not a comment): test_config asserts it
ONSET_SEARCH_MS = 100          # training: search this far each side of a key event for the real acoustic onset

# Log-Mel spectrogram
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 64
FMIN = 0
FMAX = 22050
SPEC_FRAMES = WINDOW_SAMPLES // HOP_LENGTH + 1          # T, the fixed time dimension; test_config asserts it

# Onset detection (attack path)
ONSET_HP_CUTOFF_HZ = 1500
ONSET_FRAME_MS = 5
ONSET_K = 3.0                  # default; ambient calibration overrides this at attack startup
ONSET_MIN_GAP_MS = 60
AMBIENT_CALIB_S = 2            # quiet room calibration at attack start to set the onset threshold dynamically

# Modes
ATTACK_DISABLES_KEYLOGGER = True   # in attack mode the pynput listener is never instantiated (provable mic-only)

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
SPLIT_BY_SESSION = True         # validate on a SEPARATE recording session, never a random split of one session

# Augmentation (train only)
AUG_NOISE_STD = 0.005
AUG_TIME_SHIFT_MS = 10
AUG_PITCH_SEMITONES = 1.0
SPECAUG_TIME_MASK = 6
SPECAUG_FREQ_MASK = 8

# Trainer (collection): two independent quotas for two separate sessions
TRAIN_SAMPLES_PER_KEY = 40      # Session A (training): collect until every key hits this
EVAL_SAMPLES_PER_KEY = 10       # Session B (held-out eval): a SEPARATE recording, ideally a different typist
TRAINER_PACED_GAP_MS = 550      # paced isolation for collection; the demo cadence is different (see MVP cadence)
TRAINER_MIN_TYPISTS = 2         # collect from 2-3 people so the model is not tuned to one pair of hands
DEMO_MIN_GAP_MS = 250           # MVP threat model: the guaranteed demo promises typing at >= this gap (~3-4 keys/sec)

# Correction
NGRAM_ORDER = 5
BEAM_WIDTH = 8
USE_LLM_CORRECTION = False
LLM_MODEL = None

# Defense
MASKER_BAND_HZ = (1000, 10000)   # default band; D2 tunes this to the measured keyboard
MASKER_LEVEL = 0.3               # default; D2 sweeps to find the minimum effective level
MASKER_LEVEL_STEPS = [0.1, 0.2, 0.3, 0.5]   # D2 sweep: pick the lowest that hits the target
MASKER_TARGET_RECOVERY = 0.20    # D2: lowest masking level that pushes recovery below this
MASKER_TRIGGERED = False         # Standard Shield = continuous while armed (guaranteed demo path). Triggered "Smart Shield" is a stretch, off by default (a triggered masker can fire after the identifying transient already reached the mic)
EXPOSURE_GRADE_BANDS = {"A": 0.15, "B": 0.25, "C": 0.40, "D": 0.60}  # Clack heuristic grade by recovery R; above D = F. A project heuristic, not an industry standard
FLEET_REPORTS_DIR = "data/reports"  # D3: each endpoint SAVES an audit report here; the dashboard reads saved reports (no live heartbeat infrastructure)

# Evaluation (see BUILD_EVAL.md)
EVAL_TOPK = [1, 3, 5]            # top-k recall levels to report

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
  "input_latency_s": 0.012,
  "stream_time_origin": 8402.101,
  "keyboard_id": "blue",
  "typist": "akarsh",
  "purpose": "train",
  "mode": "paced",
  "events": [{"key": "a", "t_perf": 12346.101, "type": "press"}]
}
```
Clock mapping: do NOT assume `audio_start_perf` identifies sample zero. Record the PortAudio stream timing at start (`input_latency_s` from the stream, and `stream_time_origin`, the stream's `time` at the first callback) so the event clock can be mapped to the audio sample clock, roughly `sample_index ≈ round((t_perf - audio_start_perf - input_latency_s) * sample_rate)`. This only needs to be close: the ±`ONSET_SEARCH_MS` onset snap (BUILD_MODEL) finishes the alignment. `purpose` is `train`, `eval`, or `demo` (the three sessions). Only `press` events; keys not in `KEY_SET` are dropped at dataset-build time.

**Dataset cache** at `data/datasets/<name>.npz`: `X (N, N_MELS, T) float32`, `y (N,) int64`, `classes` (strings), `meta` (JSON string).

**Model** at `data/models/<name>/`: `model.pt`, `config.json`, `metrics.json`, `confusion_matrix.png`.

---

## 10. Documentation standards (follow in every plan)

Documentation is a first-class deliverable (CyberDawgs weights it), and it lives in the `docs/` folder plus docstrings, kept current as each component is built (not written at the end). Every component plan updates the relevant `docs/` file as part of its DONE.

Priority: the rubric rewards security-specific documentation over academically perfect docstrings. Spend doc time on the README security sections and the `docs/` files below first, then on docstrings.

**The `docs/` folder (create the skeletons in scaffold, fill as you build):**
- `docs/architecture.md` — system design, the AUDIT to VERIFY loop, the pipeline, the train-vs-attack segmentation split, mode separation.
- `docs/data-collection.md` — the physical operator protocol from BUILD_TRAINER section 11A: exact mic placement, key-press technique, environment, per-typist and multi-keyboard workflow, the three sessions. This is what the team follows every collection session.
- `docs/threat-model.md` — what Clack defends against (passive nearby mic, keystrokes over a voice channel) and explicitly what it does not (a compromised endpoint).
- `docs/evaluation.md` — the metric definitions and how to reproduce the before/after table (from BUILD_EVAL).
- `docs/runbook.md` — demo-day operations: run preflight, the demo order, the fallbacks (event-mode clean run, judge-picks-teammate-types), and troubleshooting.
- `docs/api.md` — every HTTP and WebSocket endpoint with its request/response and message formats.

Who fills which doc (part of each component's DONE): BUILD_TRAINER writes `data-collection.md`; BUILD_MODEL keeps `architecture.md` current for the model and segmentation; BUILD_EVAL writes `evaluation.md`; BUILD_BACKEND writes `api.md` and the preflight part of `runbook.md`; BUILD_DEFENSE writes `threat-model.md` and the before/after in `evaluation.md`; BUILD_FRONTEND adds the dashboard screenshot to the README and the demo order to `runbook.md`.

- **README, security-first.** Beyond intent, install, and usage per entry point, include these sections (they attack the rubric directly): **Threat Model** (passive mic near a keyboard, or keystrokes over a voice channel; and explicitly what Clack does NOT defend against, such as a compromised endpoint that can disable the defense or read keyboard events); **User Controls** (mic choice, keyboard profile, calibration, defense toggle, masker intensity, local correction, save/delete recordings); **Data and Privacy** (everything local, where raw audio lives, attack text not persisted by default, how to wipe a session); **Known Limitations** (keyboard-specific acoustics, noisy rooms, distance, mic differences, unsupported punctuation, typist variability, fast overlapping keystrokes); **Security Evaluation** (a reproducible before/after table); **Why This Is Defensive** (consent-only training, no third-party target collection, attack used as validation); **Research Attribution** (Harrison et al., what was borrowed conceptually and what Clack adds). Plus a dashboard screenshot.
- **CITATION.cff describes Clack itself** (the project, authors, year), not the paper. The Harrison et al. paper goes in the README Research Attribution section and `docs/architecture.md`, not in CITATION.cff.
- Numpydoc docstrings on every public function, class, and module: one-line summary, then Parameters, Returns, Raises, and a short example for non-trivial ones. Reference the paper in `segment.py`, `features.py`, `model.py`. Update docstrings when behavior changes.
- Type hints on all signatures. Comments explain why, not what. No commented-out code. Mark shortcuts with `TODO:` (what and why).
- CONTRIBUTING (style, setup, branching), pinned requirements, CHANGELOG (Keep a Changelog), VERSION (semver), LICENSE (MIT), docs/architecture.md.

---

## 11. Testing standards (follow in every plan)

Stack: pytest, pytest-cov, hypothesis, pytest-asyncio, httpx, numpy.testing. Use `assert_allclose` for arrays. Use Hypothesis for `segment.py`, `features.py`, `prompts.py`. Every test asserts real behavior. Do not train a real model in a test. `pyproject.toml` configures pytest so `pytest` alone runs everything with coverage.

---

## 12. THE TASK FOR THIS PLAN: scaffold the repository

Do exactly this, committing as you go. This is the only building this plan does.

1. **Create the tree** in section 7: all folders and every module as a clean-importing stub. Each stub module has its numpydoc module docstring and declares its public functions/classes with type-hinted signatures whose bodies `raise NotImplementedError("built in <PLAN>")`. Stubs must import without error so the test harness is green.
2. **Write `config.py`** exactly as section 8, and `config_types.py` with dataclasses mirroring it (so other modules can import typed config).
3. **Write the docs and metadata:** README (intent, the security sections from section 10 as headed placeholders, the ethics note, install and screenshot placeholders, and links to the `docs/` files), CONTRIBUTING, CHANGELOG (with an `Unreleased` section), VERSION (`0.1.0`), LICENSE (MIT), CITATION.cff describing **Clack itself** (not the paper; the paper goes in the README Research Attribution section). Create the full `docs/` folder with headed skeletons for every file listed in section 10 (`architecture.md`, `data-collection.md`, `threat-model.md`, `evaluation.md`, `runbook.md`, `api.md`); put the section 2 mental model, the AUDIT to VERIFY loop, and the pipeline sketch into `architecture.md` now, and leave the others as headed stubs the component plans fill.
4. **Write `requirements.txt`** listing: torch, torchaudio, numpy, scipy, librosa, soundfile, sounddevice, pynput, fastapi, "uvicorn[standard]", websockets, httpx, pytest, pytest-cov, pytest-asyncio, hypothesis, matplotlib, nltk. After the environment installs, freeze exact versions back into this file. Also vendor the frontend fonts and any JS libs into `clack/ui/fonts/` and `clack/ui/vendor/` (download once now) so the UI needs no network at demo time.
5. **Write `pyproject.toml`** with pytest config:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   addopts = "-q --cov=clack --cov-report=term-missing"
   ```
6. **Write `.gitignore`**: `data/`, `plans/`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `.coverage`, `*.pt`, `*.npz`, `*.wav`. (`plans/` holds these build-plan markdown files, local working notes, never committed.) Do NOT use `.gitkeep` files inside `data/`, they conflict with this ignore rule.
7. **Create the runtime data dirs at runtime, not in git.** A helper `ensure_dirs()` (in `config_types.py`), invoked at startup by the server and the scripts, runs `os.makedirs(..., exist_ok=True)` for `data/recordings`, `data/datasets`, `data/models`, `data/corpus`, `data/reports`. The dirs are never tracked; they are created when the app runs. This resolves the gitignore conflict cleanly.
8. **Write `conftest.py`** with shared fixtures (a `tmp_session` factory that writes a tiny synthetic `audio.wav` + `events.json`, and a `device` fixture returning the detected torch device).
9. **Write one real passing test** (`tests/test_config.py`): assert every `clack` module imports, and assert `config.WINDOW_SAMPLES == 8820` and `config.SPEC_FRAMES` matches `WINDOW_SAMPLES // HOP_LENGTH + 1` (both are real attributes, not comments).
10. **Initialize git**, make the first commit, then commit after each step above (several small commits, not one). All commits must fall inside the hackathon window (see section 0A).
11. **Verify:** run `python -c "import clack, clack.model, clack.server, clack.evaluate"` (all stubs import) and `pytest` (green). Print the detected compute device.

**DONE for this plan:** the full tree exists, every module imports with no error, `pytest` passes, docs and metadata are written, `config.py` is complete, the runtime-dir helper exists, and the work is committed in several small commits inside the hackathon window. At that point, stop and begin step 1 of the build order (BUILD_TRAINER.md).

---

## 13. Guardrails (all plans)

- All commits fall inside the hackathon window; implementation is written during the event (section 0A).
- Record only the team's own keyboards and consenting typists.
- **Attack mode is provably keyboard-event-free:** the pynput listener is never instantiated in attack mode, and the dashboard shows `Keyboard Events: DISABLED`.
- Never display an accuracy number that cannot be reproduced live.
- Show RAW model output next to the language-corrected output, so no one thinks the language model did all the work.
- Claim search-space collapse for passwords, not always-exact recovery.
- Validate and demo on a SEPARATE recording session from training (never a random split of one session).
- Keep the nearest-centroid baseline working at all times as the fallback model.
- **Standard Shield (continuous masker while armed) is the guaranteed defense;** the triggered "Smart Shield" is a stretch, because a triggered masker can fire after the identifying transient already reached the mic.
- Test the cross-typist case (train on two teammates, test on a third) before relying on "judge types it live"; the guaranteed fallback is the judge picks the phrase and a teammate types it.
- State the MVP cadence (typing at >= 250 ms gaps); do not claim unrestricted fast typing unless demonstrated.
- Exposure grades are a labeled Clack heuristic, not an industry standard.
- Supporting the team's own keyboards (one combined model on both, one mic) is core; only generalizing to an UNSEEN board is the stretch, and it never blocks the guaranteed demo.
- D3 (multi-endpoint view) reads saved audit reports, not live heartbeats, and is the first thing to cut if behind.
- UI polish never touches the decode path.
- Never skip the audit and defense. They win the 30% Security Improvement.

## 14. Reference

J. Harrison, E. Toreini, M. Mehrnezhad. "A Practical Deep Learning-Based Acoustic Side Channel Attack on Keyboards." IEEE EuroS&PW 2023.
arXiv: https://arxiv.org/abs/2308.01074 . IEEE Xplore: https://ieeexplore.ieee.org/document/10190721
