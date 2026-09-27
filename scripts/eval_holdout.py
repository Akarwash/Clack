"""Held-out attack evaluation: real recovery numbers on a recording.

Runs :func:`clack.evaluate.evaluate_attack` for one or more trained models against
a held-out recording session (with ground-truth ``events.json``) and persists a
JSON report per model under ``config.REPORTS_DIR``. Reports carry the honest
end-to-end numbers: onset recall/precision, raw top-k recovery, CER, and the
per-window decode latency (featurize + classify, the same work the live decoder
times in :mod:`clack.stream`; onset detection is a batch step and is excluded, as
it is in the live latency figure).

This is the "no number is shown that cannot be reproduced" tool: re-run it and the
reports regenerate. It never trains and never touches the microphone.

Usage
-----
    python scripts/eval_holdout.py \
        --session 2026-09-26T20-54-04_dak-keyboard_aditya_eval \
        --models dak dak-aditya dak-cold
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from clack import dataset as _dataset  # noqa: E402
from clack import evaluate as _evaluate  # noqa: E402
from clack import model as _model  # noqa: E402
from clack import segment as _segment  # noqa: E402

# How each model relates to the audited typist, for an honest label in the report.
HELD_OUT_KIND = {
    "dak": "same-typist held-out (all 3 typists in training incl. aditya)",
    "dak-aditya": "same-typist, single-typist model (trained on aditya only)",
    "dak-cold": "TRUE cross-typist held-out (trained on josh+vishal; never heard aditya)",
}


def _decode_latency_ms(model: object, audio: np.ndarray, sr: int) -> dict:
    """Per-window decode latency: featurize + classify one window at a time.

    Mirrors what :class:`clack.stream.LiveDecoder` reports as ``latency_ms`` (the
    onset detector runs once over the buffer, so it is excluded here too). A warm-up
    inference is discarded so lazy graph/kernel init does not skew the median.
    """
    windows, _onsets = _segment.windows_from_audio(audio, sr)
    if windows.shape[0] == 0:
        return {"median": None, "p90": None, "n": 0}
    # Warm-up (first inference pays lazy-init costs).
    model.scores(_dataset.featurize(windows[0], sr)[None, :, :])
    lat: list[float] = []
    for w in windows:
        t0 = time.perf_counter()
        feats = _dataset.featurize(w, sr)[None, :, :]
        model.scores(feats)
        lat.append((time.perf_counter() - t0) * 1000.0)
    arr = np.asarray(lat, dtype=np.float64)
    return {
        "median": float(np.median(arr)),
        "p90": float(np.percentile(arr, 90)),
        "n": int(arr.size),
    }


def evaluate_one(model_name: str, session_dir: str) -> dict:
    """Evaluate one model on one session and return the full report dict."""
    model_dir = os.path.join(config.MODELS_DIR, model_name)
    model = _model.load_model(model_dir)

    metrics = _evaluate.evaluate_attack(model, session_dir)

    audio, sr = sf.read(os.path.join(session_dir, "audio.wav"), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    latency = _decode_latency_ms(model, audio, int(sr))

    onset = metrics["onset"]
    raw = metrics["raw"]
    return {
        "model": model_name,
        "model_dir": model_dir,
        "model_is_trainfit_headline": _trainfit_flag(model_dir),
        "session_id": metrics.get("session_id"),
        "typist": metrics.get("typist"),
        "keyboard_id": metrics.get("keyboard_id"),
        "held_out_kind": HELD_OUT_KIND.get(model_name, "unspecified"),
        "tol_ms": float(config.ONSET_SEARCH_MS),
        "n_true_presses": onset["n_true"],
        "n_detected_presses": onset["n_detected"],
        "onset_recall": onset["recall"],
        "onset_precision": onset["precision"],
        "top1": raw["top1"],
        "top3": raw["topk"].get(3),
        "top5": raw["topk"].get(5),
        "cer_raw": raw["cer"],
        "decode_latency_ms": latency,
        "corrected": None,
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "note": (
            "End-to-end attack recovery on held-out audio (onset detect + classify + "
            "onset-aligned scoring). Raw model output, no language-model correction. "
            "Onset recall is the fraction of true presses matched by a detected onset "
            f"within +/-{config.ONSET_SEARCH_MS} ms."
        ),
    }


def _trainfit_flag(model_dir: str) -> bool:
    """Read whether the model's stored training metrics were train-fit."""
    path = os.path.join(model_dir, "metrics.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(json.load(fh).get("val_is_trainfit", False))
    except (OSError, ValueError):
        return False


def _write_report(report: dict) -> str:
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    session_short = str(report.get("session_id", "session")).split("_", 1)[-1]
    fname = f"holdout_{report['model']}_on_{session_short}.json"
    path = os.path.join(config.REPORTS_DIR, fname)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return path


def _pct(v) -> str:
    return "  n/a" if v is None else f"{v * 100:5.1f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Held-out attack evaluation.")
    parser.add_argument("--session", required=True, help="session id under RECORDINGS_DIR")
    parser.add_argument("--models", nargs="+", required=True, help="model names under MODELS_DIR")
    args = parser.parse_args(argv)

    session_dir = os.path.join(config.RECORDINGS_DIR, args.session)
    if not os.path.isdir(session_dir):
        print(f"session not found: {session_dir}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for name in args.models:
        print(f"[eval] {name} on {args.session} ...", flush=True)
        report = evaluate_one(name, session_dir)
        path = _write_report(report)
        print(f"[eval]   wrote {path}", flush=True)
        rows.append(report)

    # Clean table.
    print()
    print(f"Held-out evaluation on: {args.session}")
    print("=" * 78)
    print(f"{'model':<12} | {'top-1':>7} | {'top-3':>7} | {'onset recall':>13} | {'latency (ms)':>14}")
    print("-" * 78)
    for r in rows:
        lat = r["decode_latency_ms"]
        lat_str = "n/a" if lat["median"] is None else f"{lat['median']:.2f} (p90 {lat['p90']:.2f})"
        print(f"{r['model']:<12} | {_pct(r['top1'])} | {_pct(r['top3'])} | {_pct(r['onset_recall']):>13} | {lat_str:>14}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
