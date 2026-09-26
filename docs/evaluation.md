# Evaluation

Owner: BUILD_EVAL (metric definitions and harness) with the before/after table
reproduced against BUILD_DEFENSE. Every number Clack shows comes from
`clack/evaluate.py`, so the dashboard, this document, and the README report the
same figures. The harness never invents a metric: a missing input is reported as
"not measured", never fabricated, and no number is shown that cannot be reproduced
live.

## Metrics

| Metric | Definition | Why it matters |
|---|---|---|
| Onset recall | detected onsets matched to a true key event within tolerance / total events | proves the pipeline finds keystrokes; if low, nothing else matters |
| Onset precision | matched detections / total detections | catches an over-firing detector in a noisy room |
| Raw top-1 char accuracy | correct top-1 keys / total, before correction | pure classifier performance |
| Top-k recall | `EVAL_TOPK` = [1, 3, 5]: fraction where the true key is in the top-k | the honest password story: top-3 collapses the search space |
| Character error rate (CER) | edit distance / reference length over a full sequence | the right measure for whole phrases |
| Median inference latency | median ms from onset to emitted prediction | proves "live" means live (a live-path metric) |
| Raw vs corrected accuracy | top-1 before and after language correction | the classifier works; the LM is a boost, not the whole trick |
| Defense-on recovery | recovery with the masker on | the main Cyber result |
| Baseline vs defense delta | recovery off minus recovery on | the headline drop |
| Masker-to-key ratio (dB) | masked-environment RMS vs keystroke RMS at the mic | makes the defense result physically reproducible |
| Cross-typist recovery | train on typists A/B, test on typist C (zero samples) | the real judge-demo condition and the biggest risk |
| Baseline model vs CNN | centroid floor accuracy vs CNN accuracy | free technical result and floor proof |

## Interfaces (`clack/evaluate.py`)

- `onset_metrics(detected_samples, true_samples, sr, tol_ms=30)` returns recall,
  precision, and matched count (greedy match within tolerance).
- `char_metrics(pred_keys, true_keys)` returns top-1, top-k recall over
  `EVAL_TOPK`, and CER on the top-1 sequence.
- `latency_stats(latencies_ms)` returns median and p90 (a live-path metric; the
  offline attack reports it as not measured).
- `evaluate_attack(model, session, correct_fn=None)` runs the full attack on a
  held-out recording with events and known text and returns every metric; with a
  `correct_fn` it also returns corrected CER and accuracy.
- `evaluate_defense(model, clean_audio, masked_audio, sr, true_keys)` returns the
  before/after recovery, the delta, and the mic-level masker-to-key ratio in dB.
- `compare_models({name: model}, session)` runs several models side by side
  (centroid floor vs CNN).
- `cross_typist_eval(model, train_typists, test_session)` reports recovery on a
  held-out typist who gave zero training samples.
- `format_report(metrics)` renders the plain-text table used by the console, the
  dashboard, and the README.

## Honesty rules

- Onset recall needs true event samples, so evaluate on a held-out trainer
  recording (it has `events.json`). A pure attack recording with no events reports
  char metrics only, and says so.
- Evaluate on a SEPARATE session from training (`SPLIT_BY_SESSION`), and the demo
  phrase from yet another unseen recording. Same-session evaluation is never
  reported as a result.
- For passwords, report top-k recall and the search-space reduction (from
  `attack.password_search_space`), not exact match as if guaranteed.

## Reproducing the results

Same-keyboard attack, held-out session:

```bash
python scripts/run_attack.py --model data/models/combined --session <held_out_session>
```

This prints onset recall, raw top-1, top-k recall, CER (raw and corrected), and
the password search-space reduction, all from `evaluate.py`.

Baseline vs CNN (the floor proof), on the same held-out session:

```python
from clack import evaluate, model
models = {"centroid": model.load_model("data/models/combined-centroid"),
          "cnn": model.load_model("data/models/combined")}
print(evaluate.compare_models(models, "<held_out_session>"))
```

Cross-typist (the judge condition), on a session typed by someone who gave zero
training samples:

```python
evaluate.cross_typist_eval(cnn, train_typists=["akarsh", "sam"], test_session="<typist_c_session>")
```

## The before/after defense table

The headline Cyber result is the recovery drop when the acoustic masker is armed.
It is reproduced on a fixed held-out phrase recorded once (defense off) and with
the masker mixed in at the measured mic level (defense on):

```python
from clack import evaluate, defense, model
import soundfile as sf
cnn = model.load_model("data/models/combined")
clean, sr = sf.read("<demo_session>/audio.wav", dtype="float32")
masker = defense.generate_masker(len(clean) / sr, sr)
masked = defense.apply_masker(clean, masker)
true_keys = [...]  # from the demo session events.json
print(evaluate.evaluate_defense(cnn, clean, masked, sr, true_keys))
```

`evaluate_defense` returns `off`, `on`, `delta`, and `masker_key_ratio_db`. Report
the drop as "under our test setup, recovery fell from X% to Y%", the measured
masker-to-key ratio in dB, and the minimum effective masking level found by
`defense.find_min_effective_level`. See [threat-model.md](threat-model.md) for
what this does and does not claim.
