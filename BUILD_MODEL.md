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
- **Samples per key:** collect until every key reaches `TARGET_SAMPLES_PER_KEY` (40; the paper used 25, so 40 is a safe floor). At the 550 ms paced interval, 40 x 37 is about 15 minutes of typing, split across the team. The trainer is coverage-driven and auto-stops when the target is met (see BUILD_TRAINER). Do not chase huge totals; 40 per key is enough to start, more helps the cross-keyboard stretch.
- **Balance:** the trainer's balanced sequence keeps per-key counts even. Still compute and log per-key counts before training and warn on any key with fewer than 40 samples.
- **Multiple typists:** collect from two or three people so the model is not tuned to one person's hands. Note honestly that the on-stage typist should be represented in training for the strongest result.
- **Per board:** collect a separate dataset per physical keyboard (blue board, C3 Equalz board). The model learns a board's acoustic signature.

---

## 3. Preprocessing

### 3.1 Keystroke isolation (both paths cut an onset-centered window; only the label source differs)

Critical, read carefully. **Do not cut the training window at the raw keyboard-event timestamp.** sounddevice/PortAudio buffers input, so the callback arrival time is not the sample capture time, and cutting at the event timestamp would train the model on windows shifted by an unknown, roughly constant driver latency, which the attack path (which finds onsets acoustically) would not share. The fix: the event gives the label and an approximate location, then you snap to the real acoustic onset.

- **Training (label known):** `windows_from_events(audio, events, sr)`. For each `press` event: compute the approximate sample `a = round((t_perf - audio_start_perf) * sr)`, search the band `[a - S, a + S]` where `S = int(sr * ONSET_SEARCH_MS/1000)` (about ±100 ms) for the actual acoustic onset (the same energy/spectral-flux peak the attack uses), then cut the identical onset-centered window used at attack time (`PRE = int(sr * PRE_ONSET_MS/1000)` before the onset, length `WINDOW_SAMPLES` = 8820). The key from the event is the label. Drop events whose key is not in `KEY_SET`. If no clear onset is found in the band (silence, missed press), drop that sample rather than cutting at the raw timestamp.
- **Attack (no labels):** `detect_onsets(audio, sr)` then `windows_from_audio(audio, sr)`. Onset detection (energy method, as in the paper):
  1. High-pass filter the audio at `ONSET_HP_CUTOFF_HZ` (1500 Hz) to emphasize the click transient over room rumble.
  2. Compute short-time energy: frame the signal into `ONSET_FRAME_MS` (5 ms) frames, energy = sum of squares per frame.
  3. Threshold at `baseline_mean + ONSET_K * baseline_std`. `ONSET_K` defaults to 3.0 but is set dynamically by the ambient calibration at attack startup (see BUILD_BACKEND). Mark a candidate onset on a rising edge that is a local maximum.
  4. Debounce: reject any onset within `ONSET_MIN_GAP_MS` (60 ms) of the previous one, so one physical press yields one onset (push, not release).
  5. Cut the same onset-centered `WINDOW_SAMPLES` window with the same `PRE` offset. This is the exact same cut helper the training path calls once it has found the onset, so the two paths cannot drift.

Factor the actual onset-finding and window-cutting into one shared helper (`find_onset_near`, `cut_window`) used by both paths, so "identical window" is guaranteed by construction, not by two parallel implementations.

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

Build the baseline first, then the CNN. The baseline is the guaranteed floor; the CNN is the primary model; CoAtNet is an optional upgrade only if you have GPU time to spare.

### 4.0 Floor: nearest-centroid baseline (`model.py`, class `CentroidBaseline`) — build this first

A trivial classifier that needs almost no machinery and guarantees a working end-to-end demo even if CNN training breaks.
- `fit(X, y)`: compute the mean normalized log-Mel vector (flattened) per class; store the 37 centroids.
- `predict(x) -> topk`: classify by nearest centroid (cosine or euclidean), return top-k.
- Same predict interface as the CNN so `attack.py`, `evaluate.py`, and `stream.py` can run against either model by a config switch.
Why: if the CNN does not converge at 3 AM, the baseline still recovers text live. And reporting "CNN 81% vs centroid 48%" is a clean, honest technical result on its own. Keep the baseline working at all times.

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

- `build_dataset(session_dirs, name) -> path`: read each session, cut onset-centered windows (section 3.1), compute log-Mel, map keys to indices, cache to `data/datasets/<name>.npz` with `X (N,64,T) float32`, `y (N,) int64`, `classes`, a per-sample `session_id`, and a `meta` JSON (source sessions, keyboard ids, config snapshot).
- **Split by session, never randomly (`SPLIT_BY_SESSION=True`).** Do NOT randomly split windows 85/15 when they come from the same recording: train and val would share the same mic position, room noise, gain, and typist state, which inflates validation accuracy. Instead, hold out one or more entire sessions for validation and test, and use different sessions for training. The final demo phrase must come from yet another recording the model never trained on. This is what makes the before/after result defensible. Keep the per-sample `session_id` so the split is by session.
- **Augmentation, train split only, applied on the fly:**
  - Additive Gaussian noise, std `AUG_NOISE_STD` (0.005) on the raw window before the spectrogram, or on the spectrogram.
  - Small time shift up to `AUG_TIME_SHIFT_MS` (10 ms) of the window before featurizing.
  - Pitch shift up to `AUG_PITCH_SEMITONES` (1.0) via `librosa.effects.pitch_shift` (helps cross-board robustness).
  - SpecAugment: mask up to `SPECAUG_TIME_MASK` (6) time frames and `SPECAUG_FREQ_MASK` (8) Mel bands.
- **Class balancing:** either a `WeightedRandomSampler` or class-weighted cross-entropy from inverse class frequency. Prefer class-weighted loss for simplicity. Log per-class counts before training.

Tests (`test_dataset.py`): the npz has matching `X`/`y` lengths; augmentation preserves shape; the split assigns whole sessions to train vs val (no `session_id` appears in both).

---

## 6. Training (`train.py`, `scripts/run_train.py`)

Procedure, all seeded from `config.SEED`:
1. Load the dataset npz, build loaders (`BATCH_SIZE=64`) with the session-level split from section 5. First fit `CentroidBaseline` on the train split and record its val accuracy: that is the floor, saved even if the CNN step fails.
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

- `attack_wav(path, model) -> list[dict]`: run `detect_onsets`, cut windows, featurize, classify, return per keystroke `{index, topk: [(key, prob), ...], best: key}`. Works with either `CentroidBaseline` or `ClackCNN` via the shared predict interface.
- **Metrics come from `evaluate.py` (BUILD_EVAL).** Do not hand-roll metrics here. `run_attack.py` calls `evaluate.evaluate_attack` on a held-out session (different from training) and prints the full report: onset recall, raw top-1, top-k recall, CER, median latency, and raw vs language-corrected. Also run `evaluate.compare_models` for the baseline-vs-CNN line.
- **Password evaluation (the honest number):** report top-k recall and the combined top-3-per-position search-space size (`product over positions of min(3, candidates)`), framed as "we reduced the space from X to N", not guaranteed exact recovery. At 95% per-key a 12-char password is fully correct about 54% of the time; when it is not, top-3 per position collapses the space to a handful.
- Never display an accuracy number you cannot reproduce live, and always show raw next to corrected so no one thinks the language model did all the work.

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
