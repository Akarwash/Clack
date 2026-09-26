# Architecture

## What Clack is

Clack is an acoustic side-channel security auditor. It grades how exposed a
keyboard environment is to microphone-based keystroke inference, proves the
leakage live, applies an acoustic countermeasure, and measures the drop. The
whole product is one closed loop, and every plan, the pitch, and the demo use
this order:

```
AUDIT  ->  ATTACK SIMULATION  ->  DEFENSE  ->  VERIFY
(grade exposure) (prove leakage live) (apply masker) (measure the drop)
```

Clack is presented as a defensive auditing tool, not "an attack with a defense
bolted on." The attack step is how Clack proves and measures leakage so the
defense can be verified.

## Mental model: three bands, one classifier

```
ATTACK   (inference, no labels):   mic audio -> onset detection -> log-Mel spectrogram -> CNN -> top-k keys -> language-model correction -> recovered text
TRAINING (auto-labeled, on-site):  Clack Trainer shows random chars -> backend records audio + key events on one clock -> auto-labeled windows -> augment -> train CNN
DEFENSE  (the payoff):             acoustic masker corrupts the mic input -> attack accuracy craters -> before/after measured
```

## The segmentation split (the one bug that wastes time if missed)

Both training and attack cut an **onset-centered window**; the only difference is
where the label comes from.

Do not trust the audio driver's clock for the cut location. sounddevice/PortAudio
buffers input, so a callback's arrival time is not the sample-capture time, and
cutting at a raw event timestamp would train the model on consistently shifted
windows. Instead:

- **Training:** the keyboard event gives the **label** and an approximate
  location. Search a small band (+/- `ONSET_SEARCH_MS`, about 100 ms) around it
  for the actual acoustic onset and cut the window there.
- **Attack:** there is no event, so the acoustic onset is found directly.

Both paths cut the identical onset-centered window, tolerant of driver latency,
so the classifier sees the same distribution in training and inference. The clock
mapping on disk (`audio_start_perf`, `input_latency_s`, `stream_time_origin`)
only needs to be close; the onset snap finishes the alignment.

## The Clack Trainer

Data is collected with a monkeytype-style page that shows **random characters**,
not words. Random characters give even coverage across every key (words
over-represent "e" and starve "q" and "z") and remove linguistic bias. The
browser is only a teleprompter; the backend captures audio and key events in one
Python process on one clock (`time.perf_counter()`). Labels come from the actual
keys pressed (pynput), so a typo labels its own sound correctly.

## Cross-keyboard by embeddings (stretch)

The model exposes an `embed()` vector per keystroke. To attack a keyboard it
never trained on, type a short calibration string on that board, average the
embeddings per key into prototypes, and classify new keystrokes by nearest
prototype. No retraining on the day. Supporting the team's own boards is core
(one combined model on both); generalizing to an unseen board is the stretch.

## Mode separation (provably listening only)

Clack contains a pynput keylogger, but only for training. In attack mode the
pynput listener is never instantiated (`ATTACK_DISABLES_KEYLOGGER`), and the
dashboard shows `Microphone: ACTIVE, Keyboard Events: DISABLED`. A judge can see
that recovery uses sound alone.

## The floor model

Alongside the CNN, Clack keeps a trivial nearest-centroid baseline over
normalized log-Mel features (mean feature vector per key, classify by nearest
centroid). If CNN training breaks, the baseline still gives a working end-to-end
demo, and "CNN vs centroid" is itself a clean technical result. The baseline is
kept working at all times as the fallback.

## Pipeline sketch (modules)

```
capture.py   mic audio + stream timing        [BUILD_TRAINER]
keylog.py    key events (labels, train only)   [BUILD_TRAINER]
session.py   write audio.wav + events.json     [BUILD_TRAINER]
    |
segment.py   onset detect + onset-centered cut [BUILD_MODEL]
features.py  log-Mel spectrogram + normalize   [BUILD_MODEL]
dataset.py   (window,label), augment, cache    [BUILD_MODEL]
model.py     centroid baseline + CNN + embed   [BUILD_MODEL]
train.py     seed, device, train, log          [BUILD_MODEL]
    |
attack.py    offline batch attack              [BUILD_MODEL]
stream.py    live decode + ambient calibration [BUILD_BACKEND]
correct.py   local n-gram beam-search          [BUILD_BACKEND]
    |
evaluate.py  recall, CER, latency, deltas      [BUILD_EVAL]
defense.py   masker + before/after measure     [BUILD_DEFENSE]
exposure.py  Exposure Check risk grade         [BUILD_DEFENSE]
server.py    FastAPI + WebSocket + static UI   [BUILD_BACKEND]
```

## Tech stack and device detection

Python 3.11+, PyTorch and torchaudio for the model, sounddevice/soundfile for
audio I/O, numpy/scipy/librosa for DSP, pynput for key events, FastAPI/uvicorn/
websockets for the backend, and a single-page vanilla-JS UI with self-hosted
fonts and libraries (no CDN, no build step). The compute device is detected once
at startup (CUDA, else Apple MPS, else CPU) and logged.

## Model, features, and training

The attack is a per-keystroke image classifier (the paper's pipeline: isolate
keystrokes, convert each to a Mel spectrogram, classify the image).

- **Features (`features.py`).** `log_mel(window, sr)` produces a
  `(N_MELS, SPEC_FRAMES)` = `(64, ~35)` log-Mel spectrogram in dB, padding or
  trimming the time axis to `SPEC_FRAMES` so the shape is guaranteed. Normalization
  is per-sample z-score, so there is no cross-sample statistic and no train/val
  leakage.
- **Dataset (`dataset.py`).** `build_dataset` cuts onset-snapped windows per event,
  featurizes, and keeps a per-sample `session_id` and `keyboard_id`.
  `split_by_session` holds out WHOLE sessions for validation (never a random split
  of one session), which is what makes the before/after result defensible.
  Augmentation is train-only: waveform noise/time-shift/pitch (`augment_window`)
  and SpecAugment time/frequency masks (`spec_augment`). Class imbalance is handled
  with inverse-frequency `class_weights`.
- **Models (`model.py`).** Two share one prediction contract (`scores`,
  `predict_topk`): `CentroidBaseline` (the floor: mean flattened feature per class,
  nearest centroid) built first and always kept working, and `ClackCNN` (three conv
  blocks to an adaptive pool, a 128-d embedding head reused by calibration, then a
  dropout classifier). `ClackCNN.embed()` is the cross-keyboard fingerprint.
- **Training (`train.py`).** Seeds all RNGs from `config.SEED`, detects the device
  once (CUDA, else MPS, else CPU), fits the centroid floor first (saved even if the
  CNN step fails), then trains the CNN with class-weighted cross-entropy, a plateau
  scheduler, and early stopping, keeping the best weights. Saves `model.pt`,
  `config.json` (snapshot), `metrics.json` (overall/per-key/top-3 plus loss curve),
  and `confusion_matrix.png`.
- **Attack (`attack.py`).** `attack_audio`/`attack_wav` detect onsets, cut the
  identical window, featurize, classify, and return per-press top-k with
  confidences and the top-1 text. `password_search_space` reports the honest
  top-3-per-position search-space reduction (not guaranteed exact recovery). Works
  with either model via the shared interface. RAW output is always shown next to the
  language-corrected output.

## Multi-keyboard strategy

- **Known boards (core).** The team's boards (blue and C3 Equalz), all captured
  through the one mic, are in-distribution. Train ONE combined model on both boards'
  training sessions (the classes are just the keys, not board-key pairs), so it
  works on either board and enables the "swap keyboards, same model" demo. Per-board
  models are the fallback. Report per-board accuracy using the per-sample
  `keyboard_id`.
- **Unseen board (stretch, `calibrate.py`).** For a board with zero training data,
  type a short calibration string, average `embed()` vectors per key into
  prototypes, and classify new keystrokes by nearest prototype (cosine). No
  retraining. This never jeopardizes the guaranteed floor.

## Reference

J. Harrison, E. Toreini, M. Mehrnezhad. "A Practical Deep Learning-Based Acoustic
Side Channel Attack on Keyboards." IEEE EuroS&PW 2023.
arXiv: https://arxiv.org/abs/2308.01074 .
IEEE Xplore: https://ieeexplore.ieee.org/document/10190721
