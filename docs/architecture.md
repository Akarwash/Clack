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

## Reference

J. Harrison, E. Toreini, M. Mehrnezhad. "A Practical Deep Learning-Based Acoustic
Side Channel Attack on Keyboards." IEEE EuroS&PW 2023.
arXiv: https://arxiv.org/abs/2308.01074 .
IEEE Xplore: https://ieeexplore.ieee.org/document/10190721
