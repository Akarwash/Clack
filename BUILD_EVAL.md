# Clack — BUILD_EVAL.md

The evaluation harness. One module, `clack/evaluate.py`, that turns the attack and defense into honest, reproducible numbers: the headline metrics for the dashboard, the README Security Evaluation table, and the demo. It exists so the team never shows a number it cannot reproduce, and so judges see rigor, not a single accuracy figure. Read `CLACK_BUILD_PLAN.md` first. Commit regularly.

Owns: `clack/evaluate.py`, `tests/test_eval.py`. Consumed by BUILD_MODEL (offline eval), BUILD_DEFENSE (before/after), and BUILD_FRONTEND (metrics panel).

Build this against a mock prediction interface and synthetic ground truth, so it does not wait on a trained model.

---

## 1. Why a dedicated eval module

Classification accuracy alone undersells the attack and oversells nothing. A richer, honest metric set is what makes the security claims credible and prevents two failure modes: over-claiming a number you cannot reproduce live, and letting the language model appear to do all the work. This module computes everything once, from the same inputs, so every surface reports the same figures.

---

## 2. The metrics (compute all of these)

| Metric | Definition | Why it matters |
|---|---|---|
| Onset recall | detected onsets that match a true key event within a tolerance / total events | proves the pipeline actually finds keystrokes; if this is low, nothing else matters |
| Onset precision | matched detections / total detections | catches an over-firing onset detector (noisy room) |
| Raw top-1 char accuracy | correct top-1 keys / total, before correction | pure classifier performance |
| Top-k recall | `EVAL_TOPK` = [1,3,5]: fraction where the true key is in the top-k | the honest password story: top-3 collapses the search space |
| Character error rate (CER) | edit distance / reference length over a full typed sequence | the right measure for whole phrases, not just per-key |
| Median inference latency | median ms from onset to emitted prediction | proves "live" means live |
| Raw vs corrected accuracy | top-1 accuracy before and after language-model correction | shows the classifier works and the LM is a boost, not the whole trick |
| Defense-on recovery | raw top-1 (or CER) with the masker on | the main Cyber result |
| Baseline vs defense delta | recovery off minus recovery on | the headline: "84% to 13%, a 71-point drop" |
| Masker-to-key ratio (dB) | keystroke RMS vs masked-environment RMS at the mic (dBFS) | makes the defense result physically reproducible, not just a digital amplitude |
| Cross-typist recovery | train on typists A/B, test on typist C (zero samples) | the real judge-demo condition and the biggest technical risk |
| Baseline model vs CNN | centroid baseline accuracy vs CNN accuracy | free technical result and floor proof |

---

## 3. Interfaces (`evaluate.py`)

- `onset_metrics(detected_samples, true_samples, sr, tol_ms=30) -> {recall, precision, matched}`: greedy match detected onsets to true event samples within `tol_ms`.
- `char_metrics(pred_keys, true_keys) -> {top1, topk: {1,3,5}, cer}`: `pred_keys` is a list of per-position top-k lists; `true_keys` is the reference. CER via Levenshtein on the top-1 sequence.
- `latency_stats(latencies_ms) -> {median, p90}`.
- `evaluate_attack(model, session, correct_fn=None) -> dict`: run the full attack on a held-out recording that has events (for onset recall) and known text (for char metrics); return every metric above; if `correct_fn` given, also return corrected accuracy so raw vs corrected is one call.
- `evaluate_defense(model, text, masker) -> {off, on, delta, masker_key_ratio_db}`: wraps `defense.measure`, adds CER off/on, and includes the measured mic-level masker-to-key ratio in dB.
- `compare_models(models: dict, session) -> {name: metrics}`: run several models (centroid baseline, CNN) on the same session for the side-by-side.
- `cross_typist_eval(model, train_typists, test_session) -> metrics`: report recovery on a held-out typist who gave zero training samples. This is the number that predicts the judge demo.
- `masker_ratio_db(clean_rms, masked_rms) -> float`: the dB ratio for the defense report.
- `format_report(metrics) -> str`: a plain-text table for the console, the dashboard, and the README Security Evaluation section. Only include values actually computed.

All functions are pure given their inputs, so they are easy to test and reuse.

---

## 4. Ground truth and honesty rules

- Onset recall needs true event samples, so evaluate on a held-out **trainer** recording (it has `events.json`). For a pure attack recording with no events, report the char metrics only and say so.
- Evaluate on a **separate session** from training (see `SPLIT_BY_SESSION`), and the demo phrase from yet another unseen recording. Same-session evaluation is not reported as a result.
- For passwords, report top-k recall and search-space reduction, not exact-match as if guaranteed.
- `format_report` never invents a metric; missing inputs produce an explicit "not measured", never a fabricated number.

---

## 5. Tests (`test_eval.py`)

- `onset_metrics`: synthetic detected/true arrays give known recall and precision; perfect input gives 1.0, shifted-beyond-tolerance gives lower.
- `char_metrics`: a known pred/reference pair gives the hand-computed top-1, top-3, and CER; `assert_allclose`.
- `latency_stats`: median and p90 on a known list.
- `compare_models`: two mock models with different accuracies rank correctly.

---

## 6. DONE

- `evaluate.py` computes every metric in section 2 from a held-out recording and a defense run, with a `format_report` table, and `test_eval.py` passes on synthetic inputs. The dashboard and README both pull their numbers from this module.
- `docs/evaluation.md` is written: the metric definitions and how to reproduce the before/after table.
