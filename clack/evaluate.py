"""Metrics harness: onset recall/precision, top-k, CER, latency, defense deltas.

One module that turns the attack and defense into honest, reproducible numbers,
so every surface (dashboard, README Security Evaluation table, demo) reports the
same figures and no number is shown that cannot be reproduced. All functions are
pure given their inputs. ``format_report`` never invents a metric: a missing input
yields an explicit "not measured", never a fabricated number.

Owner: BUILD_EVAL. Consumed by BUILD_MODEL (offline eval), BUILD_DEFENSE
(before/after), and BUILD_FRONTEND (metrics panel).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import soundfile as sf

import config


# ---------------------------------------------------------------------------
# Pure metric primitives
# ---------------------------------------------------------------------------
def _levenshtein(a: list, b: list) -> int:
    """Edit distance between two sequences (insert/delete/substitute cost 1)."""
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m]


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate: edit distance divided by reference length.

    Parameters
    ----------
    reference : str
        Ground-truth text.
    hypothesis : str
        Recovered text.

    Returns
    -------
    float
        ``0.0`` is perfect. If the reference is empty, returns ``0.0`` when the
        hypothesis is also empty, else ``1.0``.
    """
    if len(reference) == 0:
        return 0.0 if len(hypothesis) == 0 else 1.0
    return _levenshtein(list(reference), list(hypothesis)) / len(reference)


def onset_metrics(
    detected_samples,
    true_samples,
    sr: int,
    tol_ms: float = 30.0,
) -> dict:
    """Greedy-match detected onsets to true event samples within a tolerance.

    Parameters
    ----------
    detected_samples : sequence of int
        Detected onset sample indices.
    true_samples : sequence of int
        Ground-truth key-event sample indices.
    sr : int
        Sample rate in Hz.
    tol_ms : float, optional
        Match tolerance in milliseconds (default ``30``).

    Returns
    -------
    dict
        ``{recall, precision, matched, n_true, n_detected}``.
    """
    detected = sorted(int(x) for x in detected_samples)
    true = sorted(int(x) for x in true_samples)
    tol = sr * tol_ms / 1000.0

    used = [False] * len(detected)
    matched = 0
    for t in true:
        best_j = -1
        best_d = tol
        for j, d in enumerate(detected):
            if used[j]:
                continue
            dist = abs(d - t)
            if dist <= best_d:
                best_d = dist
                best_j = j
        if best_j >= 0:
            used[best_j] = True
            matched += 1

    recall = matched / len(true) if true else 0.0
    precision = matched / len(detected) if detected else 0.0
    return {
        "recall": recall,
        "precision": precision,
        "matched": matched,
        "n_true": len(true),
        "n_detected": len(detected),
    }


def char_metrics(pred_keys: list[list[str]], true_keys: list[str]) -> dict:
    """Top-1, top-k recall, and CER for a decoded sequence.

    Parameters
    ----------
    pred_keys : list of list of str
        Per-position ranked candidate keys (top-1 first).
    true_keys : list of str
        The reference key sequence.

    Returns
    -------
    dict
        ``{top1, topk: {k: recall}, cer}`` where ``topk`` covers
        ``config.EVAL_TOPK``. CER is computed on the top-1 sequence vs the
        reference (as strings, with ``space`` rendered as a space).
    """
    n = min(len(pred_keys), len(true_keys))
    top1_hits = sum(1 for i in range(n) if pred_keys[i] and pred_keys[i][0] == true_keys[i])
    total = len(true_keys)
    top1 = top1_hits / total if total else 0.0

    topk: dict[int, float] = {}
    for k in config.EVAL_TOPK:
        hits = sum(1 for i in range(n) if true_keys[i] in pred_keys[i][:k])
        topk[k] = hits / total if total else 0.0

    def _render(keys: list[str]) -> str:
        return "".join(" " if key == "space" else key for key in keys)

    pred_top1_seq = _render([row[0] if row else "" for row in pred_keys])
    ref_seq = _render(true_keys)
    return {"top1": top1, "topk": topk, "cer": cer(ref_seq, pred_top1_seq)}


def latency_stats(latencies_ms) -> dict:
    """Median and p90 of a list of latencies.

    Parameters
    ----------
    latencies_ms : sequence of float
        Per-press latencies in milliseconds.

    Returns
    -------
    dict
        ``{median, p90}`` in milliseconds, or ``{median: None, p90: None}`` if
        empty (not measured).
    """
    arr = np.asarray(list(latencies_ms), dtype=np.float64)
    if arr.size == 0:
        return {"median": None, "p90": None}
    return {"median": float(np.median(arr)), "p90": float(np.percentile(arr, 90))}


def masker_ratio_db(clean_rms: float, masked_rms: float) -> float:
    """Ratio of masked-environment level to keystroke level, in dB.

    Parameters
    ----------
    clean_rms : float
        RMS of the clean keystroke signal at the mic.
    masked_rms : float
        RMS of the masked environment at the mic.

    Returns
    -------
    float
        ``20 * log10(masked_rms / clean_rms)`` (``+inf`` handled as a large value).
    """
    if clean_rms <= 0:
        return float("inf")
    ratio = max(masked_rms, 1e-12) / clean_rms
    return 20.0 * math.log10(ratio)


def _rms(audio: np.ndarray) -> float:
    audio = np.asarray(audio, dtype=np.float64)
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio**2)))


# ---------------------------------------------------------------------------
# Session-level evaluation
# ---------------------------------------------------------------------------
def _load_session(session_dir: str) -> tuple[np.ndarray, int, dict]:
    wav_path = os.path.join(session_dir, "audio.wav")
    events_path = os.path.join(session_dir, "events.json")
    if not os.path.isfile(wav_path) or not os.path.isfile(events_path):
        raise FileNotFoundError(f"session missing files: {session_dir}")
    audio, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    with open(events_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    return audio, int(sr), meta


def _true_samples_and_keys(meta: dict, sr: int) -> tuple[list[int], list[str]]:
    start = float(meta.get("audio_start_perf", 0.0))
    latency = float(meta.get("input_latency_s", 0.0))
    samples: list[int] = []
    keys: list[str] = []
    for e in meta.get("events", []):
        if e.get("type", "press") != "press" or e.get("key") not in config.KEY_SET:
            continue
        samples.append(max(0, int(round((float(e["t_perf"]) - start - latency) * sr))))
        keys.append(e["key"])
    return samples, keys


def evaluate_attack(
    model: object,
    session: str,
    correct_fn: Optional[Callable[[list[list[str]]], str]] = None,
    tol_ms: float = 30.0,
) -> dict:
    """Run the full attack on a held-out recording and return every metric.

    The recording must have ``events.json`` (for onset recall) and known text (for
    char metrics). Predicted presses are aligned to true events by nearest onset
    within ``tol_ms``; unmatched true events count as errors (honest recovery).

    Parameters
    ----------
    model : object
        A fitted model (see :mod:`clack.attack`).
    session : str
        A ``data/recordings/<session_id>/`` directory.
    correct_fn : callable or None, optional
        ``lattice -> corrected_str``; if given, corrected CER and accuracy are
        also returned so raw vs corrected is one call.
    tol_ms : float, optional
        Onset match tolerance in milliseconds.

    Returns
    -------
    dict
        Onset metrics, raw char metrics, optional corrected metrics, per-model
        counts, and the source session id.
    """
    from clack import attack as _attack

    audio, sr, meta = _load_session(session)
    true_samples, true_keys = _true_samples_and_keys(meta, sr)
    result = _attack.attack_audio(audio, sr, model, k=max(config.EVAL_TOPK))

    onset = onset_metrics(result.onsets.tolist(), true_samples, sr, tol_ms=tol_ms)

    # Align detected presses to true events (nearest onset within tolerance).
    detected = list(result.onsets.tolist())
    tol = sr * tol_ms / 1000.0
    aligned_pred: list[list[str]] = []
    for t in true_samples:
        best_j, best_d = -1, tol
        for j, d in enumerate(detected):
            dist = abs(d - t)
            if dist <= best_d:
                best_d, best_j = dist, j
        if best_j >= 0:
            aligned_pred.append([kk for kk, _ in result.per_key[best_j]["topk"]])
        else:
            aligned_pred.append([])  # onset miss counts as an error

    chars = char_metrics(aligned_pred, true_keys)
    out = {
        "session_id": meta.get("session_id", os.path.basename(session)),
        "keyboard_id": meta.get("keyboard_id", "unknown"),
        "typist": meta.get("typist", "unknown"),
        "onset": onset,
        "raw": chars,
        "latency": latency_stats([]),  # offline: latency is a live metric
        "n_presses": int(result.topk.shape[0]),
    }

    if correct_fn is not None:
        ref_seq = "".join(" " if k == "space" else k for k in true_keys)
        corrected = correct_fn(aligned_pred)
        pos_hits = sum(1 for a, b in zip(corrected, ref_seq) if a == b)
        out["corrected"] = {
            "cer": cer(ref_seq, corrected),
            "top1": pos_hits / len(ref_seq) if ref_seq else 0.0,
            "text": corrected,
        }
    return out


def evaluate_defense(
    model: object,
    clean_audio: np.ndarray,
    masked_audio: np.ndarray,
    sr: int,
    true_keys: Optional[list[str]] = None,
) -> dict:
    """Before/after recovery for the defense (the main Cyber result).

    Attacks the clean and masked audio and reports the recovery drop and the
    measured mic-level masker-to-key ratio in dB.

    Parameters
    ----------
    model : object
        A fitted attack model.
    clean_audio : numpy.ndarray
        The clean recording (defense off).
    masked_audio : numpy.ndarray
        The same content with the masker applied (defense on).
    sr : int
        Sample rate in Hz.
    true_keys : list of str or None, optional
        Ground-truth keys; if given, ``off``/``on`` are top-1 accuracy and CER is
        included, else recovery is the detected-press count ratio.

    Returns
    -------
    dict
        ``{off, on, delta, masker_key_ratio_db, ...}``.
    """
    from clack import attack as _attack

    def _recover(audio: np.ndarray) -> dict:
        try:
            res = _attack.attack_audio(audio, sr, model, k=max(config.EVAL_TOPK))
        except ValueError:
            return {"top1": 0.0, "cer": 1.0, "n_presses": 0, "pred": []}
        pred = [[kk for kk, _ in pk["topk"]] for pk in res.per_key]
        if true_keys is not None:
            cm = char_metrics(pred, true_keys)
            return {"top1": cm["top1"], "cer": cm["cer"], "n_presses": len(pred), "pred": pred}
        return {"top1": None, "cer": None, "n_presses": len(pred), "pred": pred}

    off = _recover(clean_audio)
    on = _recover(masked_audio)

    if true_keys is not None:
        off_val, on_val = off["top1"], on["top1"]
    else:
        # No ground truth: recovery proxied by relative detected-press count.
        base = max(1, off["n_presses"])
        off_val, on_val = 1.0, on["n_presses"] / base

    masker = np.asarray(masked_audio, dtype=np.float64) - np.asarray(clean_audio, dtype=np.float64)[: len(masked_audio)]
    ratio_db = masker_ratio_db(_rms(clean_audio), _rms(masker))

    return {
        "off": off_val,
        "on": on_val,
        "delta": (off_val - on_val) if (off_val is not None and on_val is not None) else None,
        "masker_key_ratio_db": ratio_db,
        "cer_off": off["cer"],
        "cer_on": on["cer"],
    }


def compare_models(models: dict, session: str) -> dict:
    """Run several models on the same session for a side-by-side.

    Parameters
    ----------
    models : dict
        ``{name: model}`` (for example centroid baseline vs CNN).
    session : str
        A held-out recording directory.

    Returns
    -------
    dict
        ``{name: evaluate_attack(...)}`` for each model.
    """
    return {name: evaluate_attack(model, session) for name, model in models.items()}


def cross_typist_eval(model: object, train_typists: list[str], test_session: str) -> dict:
    """Recovery on a held-out typist who gave zero training samples.

    Parameters
    ----------
    model : object
        The trained model.
    train_typists : list of str
        Typists represented in training (informational; recorded in the result).
    test_session : str
        A recording from a typist not in ``train_typists``.

    Returns
    -------
    dict
        The attack metrics plus the train/test typist annotation.
    """
    metrics = evaluate_attack(model, test_session)
    metrics["train_typists"] = list(train_typists)
    metrics["cross_typist"] = metrics.get("typist") not in set(train_typists)
    return metrics


# ---------------------------------------------------------------------------
# Reporting and the run_attack-friendly wrapper
# ---------------------------------------------------------------------------
@dataclass
class EvalReport:
    """A flattened evaluation report (convenience for scripts and the UI).

    Attributes
    ----------
    onset_recall : float
        Fraction of true presses matched by a detected onset.
    topk_recall : dict
        Recall at each k in ``config.EVAL_TOPK``.
    cer_raw : float
        Character error rate of raw model output.
    cer_corrected : float
        Character error rate after language-model correction (``nan`` if none).
    latency_ms : float
        Median per-press decode latency in milliseconds (``nan`` if not measured).
    extra : dict
        The full :func:`evaluate_attack` dictionary.
    """

    onset_recall: float
    topk_recall: dict
    cer_raw: float
    cer_corrected: float
    latency_ms: float
    extra: dict = field(default_factory=dict)


def evaluate_recording(session_dir: str, model: object, correct: bool = True) -> EvalReport:
    """Convenience wrapper around :func:`evaluate_attack` returning an EvalReport.

    Parameters
    ----------
    session_dir : str
        A recording directory with ground-truth events.
    model : object
        A trained model.
    correct : bool, optional
        Whether to also compute corrected CER via the local corrector if it is
        available (default ``True``).

    Returns
    -------
    EvalReport
        The flattened report.
    """
    correct_fn = None
    if correct:
        try:
            from clack.correct import NgramCorrector

            corrector = NgramCorrector()
            correct_fn = corrector.correct
        except Exception:
            correct_fn = None

    metrics = evaluate_attack(model, session_dir, correct_fn=correct_fn)
    median = metrics["latency"]["median"]
    return EvalReport(
        onset_recall=metrics["onset"]["recall"],
        topk_recall=metrics["raw"]["topk"],
        cer_raw=metrics["raw"]["cer"],
        cer_corrected=metrics.get("corrected", {}).get("cer", float("nan")),
        latency_ms=median if median is not None else float("nan"),
        extra=metrics,
    )


def format_report(metrics: dict) -> str:
    """Render a plain-text metric table (console, dashboard, README).

    Only values actually present are shown; anything missing is reported as
    "not measured", never fabricated.

    Parameters
    ----------
    metrics : dict
        A dict from :func:`evaluate_attack` (and optionally defense fields).

    Returns
    -------
    str
        A multi-line report.
    """
    lines: list[str] = ["Clack evaluation report", "=" * 32]

    def _fmt(v, pct: bool = False) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "not measured"
        if pct:
            return f"{v * 100:.1f}%"
        return f"{v:.3f}"

    if "session_id" in metrics:
        lines.append(f"session      : {metrics['session_id']}")
    if "keyboard_id" in metrics:
        lines.append(f"keyboard     : {metrics['keyboard_id']}  typist: {metrics.get('typist', '?')}")
    if "onset" in metrics:
        o = metrics["onset"]
        lines.append(f"onset recall : {_fmt(o['recall'], pct=True)}   precision: {_fmt(o['precision'], pct=True)}")
    if "raw" in metrics:
        r = metrics["raw"]
        lines.append(f"raw top-1    : {_fmt(r['top1'], pct=True)}")
        lines.append("top-k recall : " + "  ".join(f"top{k}={_fmt(v, pct=True)}" for k, v in r["topk"].items()))
        lines.append(f"CER (raw)    : {_fmt(r['cer'])}")
    if "corrected" in metrics:
        c = metrics["corrected"]
        lines.append(f"CER (corr.)  : {_fmt(c['cer'])}   corrected top-1: {_fmt(c['top1'], pct=True)}")
    if "latency" in metrics:
        lines.append(f"latency (ms) : median={_fmt(metrics['latency']['median'])}  p90={_fmt(metrics['latency']['p90'])}")
    # Defense fields, if present.
    if "delta" in metrics:
        lines.append("-" * 32)
        lines.append(f"defense off  : {_fmt(metrics.get('off'), pct=True)}")
        lines.append(f"defense on   : {_fmt(metrics.get('on'), pct=True)}")
        lines.append(f"delta        : {_fmt(metrics.get('delta'), pct=True)}")
        lines.append(f"masker/key dB: {_fmt(metrics.get('masker_key_ratio_db'))}")
    return "\n".join(lines)
