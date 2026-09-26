# Clack — BUILD_MODEL.md

The machine-learning component: turn keystroke audio into keys. Read `CLACK_BUILD_PLAN.md` first for the rules, layout, and `config.py` values. This file is the exact recipe for the model, grounded in Harrison, Toreini, Mehrnezhad (IEEE EuroS&PW 2023, https://arxiv.org/abs/2308.01074). Commit regularly.

Covers files: `features.py`, `dataset.py`, `model.py`, `train.py`, `attack.py`, `calibrate.py`, plus `scripts/run_train.py` and `scripts/run_attack.py`.

---

## 1. What the model does (and the paper's method)

The attack is a per-keystroke image classifier. Each key press produces a short sound. Convert that sound to a log-Mel spectrogram (an image), and classify the image into one of the keys. This is exactly the paper's pipeline: isolate keystrokes, convert each to a Mel spectrogram, train a deep image classifier, optionally correct with a language model. The paper reached 95% on phone-recorded keystrokes and 93% over Zoom, using a CoAtNet (convolution plus attention) classifier.

Two differences we make on purpose (see the master plan): we decode live rather than in batch, and we generalize across keyboards. Both sit on top of the same classifier this file builds.

Inputs to this component: recording sessions on disk (`data/recordings/<id>/audio.wav` + `events.json`, schema in the master plan).
Outputs: a trained model at `data/models/<name>/` (`model.pt`, `config.json`, `metrics.json`, `confusion_matrix.png`) and, at inference, top-k key predictions per keystroke with confidences.

---

## 2. Data requirements

- **Classes:** `KEY_SET` from config: `a-z`, `0-9`, and `space` (37 classes) to start.
- **Samples per key:** aim for at least 100 clean presses per key for the same-keyboard model (the paper used 25 per key on one board; more is better and the trainer makes it cheap). In paced mode at ~1 key/second, 100 presses per key across 37 keys is about one hour of typing, split across the team. Start collecting the moment the venue setup works.
- **Balance:** the trainer's balanced sequence keeps per-key counts even. Still compute and log per-key counts before training and warn on any key with fewer than 40 samples.
- **Multiple typists:** collect from two or three people so the model is not tuned to one person's hands. Note honestly that the on-stage typist should be represented in training for the strongest result.
- **Per board:** collect a separate dataset per physical keyboard (blue board, C3 Equalz board). The model learns a board's acoustic signature.

---

## 3. Preprocessing

### 3.1 Keystroke isolation (two paths, same output window)

The window shape must be identical for training and attack, or the classifier sees a distribution shift.

- **Training (labels known):** `windows_from_events(audio, events, sr)`. For each `press` event, compute `onset_sample = round((t_perf - audio_start_perf) * sr)`, then cut `[onset_sample - PRE, onset_sample - PRE + WINDOW_SAMPLES]` where `PRE = int(sr * PRE_ONSET_MS/1000)` and `WINDOW_SAMPLES = int(sr * WINDOW_MS/1000)` (8820 samples for 200 ms at 44.1 kHz). Drop events whose key is not in `KEY_SET`.
- **Attack (no labels):** `detect_onsets(audio, sr)` then `windows_from_audio(audio, sr)`. Onset detection (energy method, as in the paper):
  1. High-pass filter the audio at `ONSET_HP_CUTOFF_HZ` (1500 Hz) to emphasize the click transient over room rumble.
  2. Compute short-time energy: frame the signal into `ONSET_FRAME_MS` (5 ms) frames, energy = sum of squares per frame.
  3. Estimate a rolling baseline (mean and std over a trailing window). Mark a candidate onset where energy crosses `baseline_mean + ONSET_K * baseline_std` (K = 3.0) on a rising edge and is a local maximum.
  4. Debounce: reject any onset within `ONSET_MIN_GAP_MS` (60 ms) of the previous one, so one physical press yields one onset (push, not release).
  5. Cut the same `WINDOW_SAMPLES` window with the same `PRE` offset around each onset.

### 3.2 Features: log-Mel spectrogram

`features.log_mel(window, sr) -> np.ndarray`:
- `librosa.feature.melspectrogram` with `n_fft=N_FFT` (1024), `hop_length=HOP_LENGTH` (256), `n_mels=N_MELS` (64), `fmin=FMIN` (0), `fmax=FMAX` (22050).
- Convert to dB: `librosa.power_to_db(mel, ref=np.max)`.
- Fix time dimension: pad or trim to `T` frames (for an 8820-sample window at hop 256, `T ≈ 35`). Store `T` in config once computed.
- Per-sample normalization: z-score (subtract mean, divide by std over the whole image). This is what lets the model generalize across recording levels.
- Output shape `(N_MELS, T)` = `(64, 35)`, float32.

Tests (`test_features.py`): output is always `(64, T)`, finite, deterministic for a fixed input. Use Hypothesis over window lengths to confirm pad/trim always yields `T`.

---

## 4. Model architecture

Build the small CNN first. It trains in minutes and is enough for the same-keyboard result. Keep the paper's CoAtNet as a documented upgrade path only if you have GPU time to spare.

### 4.1 Primary: small CNN (`model.py`, class `ClackCNN`)

Input: `(batch, 1, 64, T)`.

```
Block1: Conv2d(1, 32, kernel=3, padding=1)  -> BatchNorm2d(32)  -> ReLU -> MaxPool2d(2)
Block2: Conv2d(32, 64, kernel=3, padding=1) -> BatchNorm2d(64)  -> ReLU -> MaxPool2d(2)
Block3: Conv2d(64, 128, kernel=3, padding=1)-> BatchNorm2d(128) -> ReLU -> AdaptiveAvgPool2d(1)
Flatten -> (batch, 128)
Embedding head: Linear(128, EMBED_DIM=128) -> ReLU      # reused by calibrate.py
Classifier: Dropout(DROPOUT=0.3) -> Linear(EMBED_DIM, num_classes)
```

Expose two methods:
- `forward(x) -> logits` of shape `(batch, num_classes)`.
- `embed(x) -> (batch, EMBED_DIM)`: everything up to and including the embedding head, before dropout and the classifier. This vector is the cross-keyboard feature.

Parameter count is well under 1M, so it trains fast on CPU and is a few MB on disk.

### 4.2 Upgrade path: CoAtNet (paper-faithful, optional)

If a CUDA GPU is available and the small CNN has converged with time to spare, swap in a CoAtNet-style hybrid (convolution stages followed by transformer blocks), matching the paper. Use `timm` (`coatnet_0` or a small variant) adapted to a single-channel spectrogram input and `num_classes` output. Keep the same `embed()` contract (take the pre-classifier features). Do not start here: it is heavier, slower to train, and only worth it once the floor works.

---

## 5. Dataset and augmentation (`dataset.py`)

- `build_dataset(session_dirs, name) -> path`: read each session, cut event windows, compute log-Mel, map keys to indices, cache to `data/datasets/<name>.npz` with `X (N,64,T) float32`, `y (N,) int64`, `classes`, and a `meta` JSON (source sessions, keyboard ids, config snapshot).
- A `torch.utils.data.Dataset` wrapping the npz, plus a deterministic seeded train/val split (`VAL_SPLIT=0.15`).
- **Augmentation, train split only, applied on the fly:**
  - Additive Gaussian noise, std `AUG_NOISE_STD` (0.005) on the raw window before the spectrogram, or on the spectrogram.
  - Small time shift up to `AUG_TIME_SHIFT_MS` (10 ms) of the window before featurizing.
  - Pitch shift up to `AUG_PITCH_SEMITONES` (1.0) via `librosa.effects.pitch_shift` (helps cross-board robustness).
  - SpecAugment: mask up to `SPECAUG_TIME_MASK` (6) time frames and `SPECAUG_FREQ_MASK` (8) Mel bands.
- **Class balancing:** either a `WeightedRandomSampler` or class-weighted cross-entropy from inverse class frequency. Prefer class-weighted loss for simplicity. Log per-class counts before training.

Tests (`test_dataset.py`): the npz has matching `X`/`y` lengths; augmentation preserves shape; the split is deterministic under a fixed seed.

---

## 6. Training (`train.py`, `scripts/run_train.py`)

Procedure, all seeded from `config.SEED`:
1. Load the dataset npz, build loaders (`BATCH_SIZE=64`).
2. Instantiate `ClackCNN(num_classes)`, move to the detected device (CUDA / MPS / CPU).
3. Optimizer: Adam(`lr=LR=1e-3`, `weight_decay=WEIGHT_DECAY=1e-4`).
4. Loss: cross-entropy with class weights.
5. Scheduler: `ReduceLROnPlateau` on val loss (factor 0.5, patience 3).
6. Train up to `EPOCHS=60` with early stopping (`EARLY_STOP_PATIENCE=8`) on val loss; keep the best weights.
7. After training, on the val split compute: overall accuracy, **per-key accuracy**, **top-3 accuracy**, and a confusion matrix.
8. Save to `data/models/<name>/`: `model.pt` (state dict), `config.json` (the snapshot), `metrics.json` (all of the above plus the loss curve), and `confusion_matrix.png`.
9. Print a one-screen summary: overall acc, top-3 acc, the five worst keys, and the loss curve length.

Tests (`test_model.py`): forward and embed return correct shapes on a synthetic batch; one optimizer step reduces loss on a tiny overfit batch. Never train a real model inside a test.

---

## 7. Inference and evaluation (`attack.py`, `scripts/run_attack.py`)

- `attack_wav(path, model) -> list[dict]`: run `detect_onsets`, cut windows, featurize, classify, return per keystroke `{index, topk: [(key, prob), ...], best: key}`.
- **Prose evaluation:** feed a held-out recording of a typed sentence; report exact-match character accuracy (raw), then accuracy after language-model correction (see BUILD_BACKEND for `correct.py`).
- **Password evaluation (the honest number):** for a typed password, report:
  - Exact full-string recovery rate over repeated trials.
  - The combined top-3-per-position search-space size, that is `product over positions of min(3, candidates)`, framed as "we reduced the space from X to N". At 95% per-key, a 12-char password is fully correct about 54% of the time; when it is not, top-3 per position collapses the space to a handful.
- Never display an accuracy number you cannot reproduce live.

---

## 8. Cross-keyboard (`calibrate.py`)

Goal: recover text from a board the model never trained on. Two tiers, Tier A is the floor.

### Tier A: few-shot prototype calibration (the floor, do this)
1. Train the model on one or more boards as usual. Its `embed()` output is a 128-d fingerprint of a keystroke's sound.
2. On the unseen board, collect a short calibration set via the trainer: a known string that hits each key a few times (say 3 to 5). Auto-labeled as usual.
3. For each key, compute the **prototype** = mean of `model.embed(window)` over that key's calibration samples.
4. Classify a new keystroke from the unseen board by nearest prototype in embedding space (cosine distance). Optionally k-NN over the calibration embeddings instead of prototypes.
5. No retraining, so calibration takes seconds on stage.

`calibrate.build_prototypes(model, calib_session) -> {key: vector}` and `calibrate.classify(model, window, prototypes) -> topk`.

### Tier B: zero-shot (stretch, clearly optional)
Train on several boards with strong augmentation and per-sample normalization so the model does not memorize one board, then attack the unseen board with no calibration, leaning on the language model to recover prose. This is a real research problem and may not converge in 24 hours. It never blocks Tier A, and the same-keyboard demo stays intact as the guaranteed result.

Tests (`test_calibrate.py`): prototypes have shape `(EMBED_DIM,)`; nearest-prototype beats chance on a synthetic embedding set with separable clusters.

---

## 9. Predicted model failures and fixes

| Problem | Fix |
|---|---|
| High val accuracy, poor live/attack accuracy | Distribution shift between event windows (train) and onset windows (attack). Make `windows_from_audio` cut the exact same window shape and offset as `windows_from_events`; verify on a recording that has both. |
| Low accuracy overall | Check per-key counts and class balance first, then window alignment, before touching the model. Read the confusion matrix: adjacent physical keys confused is expected and the LM fixes it for prose. |
| Onset detector misses fast typing | Collect the core dataset in paced mode; raise `ONSET_K` or lower `ONSET_MIN_GAP_MS` only against the synthetic test; keep the event-timestamp mode for a clean demo run. |
| Overfit to one typist or one session | More typists, more sessions, stronger augmentation; shuffle across sessions in the split. |
| Cross-board accuracy collapses | That is expected without calibration. Use Tier A prototypes; only attempt Tier B if time remains. |
| Training too slow | Small CNN, reduced `T`, fewer Mel bands, or fewer classes; use the GPU if present. Do not jump to CoAtNet on CPU. |

## 10. DONE for the model component

- `run_train.py` produces a same-keyboard model with strong per-key and top-3 accuracy, saved with metrics and a confusion matrix.
- `run_attack.py` recovers a held-out sentence (reported accuracy) and prints password top-k candidates, from audio only.
- `calibrate.py` recovers text on an unseen board after a short calibration string (Tier A). Tier B attempted and reported honestly, pass or fail.
