"""Tests for :mod:`clack.evaluate` (metrics harness).

Owner: BUILD_EVAL. Built against synthetic ground truth and mock models so it does
not wait on a trained model.
"""

from __future__ import annotations

import numpy as np

import config
from clack import evaluate


def test_onset_metrics_perfect() -> None:
    """Exactly matching onsets give recall and precision 1.0."""
    true = [1000, 5000, 9000]
    detected = [1005, 4995, 9010]
    m = evaluate.onset_metrics(detected, true, config.SAMPLE_RATE, tol_ms=30)
    assert m["recall"] == 1.0
    assert m["precision"] == 1.0
    assert m["matched"] == 3


def test_onset_metrics_shifted_beyond_tolerance() -> None:
    """Onsets shifted beyond tolerance are not matched."""
    true = [1000, 5000]
    detected = [3000]  # ~45 ms from each true onset, beyond the 30 ms tolerance
    m = evaluate.onset_metrics(detected, true, config.SAMPLE_RATE, tol_ms=30)
    assert m["recall"] == 0.0
    assert m["matched"] == 0


def test_onset_metrics_precision_catches_overfiring() -> None:
    """Extra detections lower precision without hurting recall."""
    true = [1000, 5000]
    detected = [1000, 5000, 7000, 8000]  # two false positives
    m = evaluate.onset_metrics(detected, true, config.SAMPLE_RATE, tol_ms=30)
    assert m["recall"] == 1.0
    assert abs(m["precision"] - 0.5) < 1e-9


def test_char_metrics_known_values() -> None:
    """A hand-computed pred/reference pair gives known top-1, top-3, and CER."""
    pred = [["a", "b", "c"], ["x", "e", "f"], ["c", "y", "z"]]
    true = ["a", "e", "c"]
    m = evaluate.char_metrics(pred, true)
    np.testing.assert_allclose(m["top1"], 2 / 3)  # positions 0 and 2 correct
    np.testing.assert_allclose(m["topk"][3], 1.0)  # all true keys within top-3
    np.testing.assert_allclose(m["topk"][1], 2 / 3)
    # top-1 sequence "axc" vs reference "aec": one substitution, CER = 1/3.
    np.testing.assert_allclose(m["cer"], 1 / 3)


def test_char_metrics_space_rendering() -> None:
    """The 'space' token is rendered as a space in the CER string."""
    pred = [["h"], ["space"], ["i"]]
    true = ["h", "space", "i"]
    m = evaluate.char_metrics(pred, true)
    assert m["cer"] == 0.0
    assert m["top1"] == 1.0


def test_cer_basic() -> None:
    """CER matches hand-computed edit distances."""
    np.testing.assert_allclose(evaluate.cer("hello", "hello"), 0.0)
    np.testing.assert_allclose(evaluate.cer("hello", "hallo"), 1 / 5)
    np.testing.assert_allclose(evaluate.cer("", ""), 0.0)
    np.testing.assert_allclose(evaluate.cer("", "x"), 1.0)


def test_latency_stats_known_list() -> None:
    """Median and p90 on a known list."""
    stats = evaluate.latency_stats([10, 20, 30, 40, 50])
    np.testing.assert_allclose(stats["median"], 30.0)
    np.testing.assert_allclose(stats["p90"], 46.0)
    empty = evaluate.latency_stats([])
    assert empty["median"] is None


def test_masker_ratio_db() -> None:
    """A 10x louder masker is +20 dB; equal levels are 0 dB."""
    np.testing.assert_allclose(evaluate.masker_ratio_db(1.0, 10.0), 20.0)
    np.testing.assert_allclose(evaluate.masker_ratio_db(1.0, 1.0), 0.0)


class _MockModel:
    """A mock model that always favors one fixed class (for ranking tests)."""

    def __init__(self, favored_key: str, strength: float) -> None:
        self.classes = list(config.KEY_SET)
        self._idx = self.classes.index(favored_key)
        self._strength = strength

    def scores(self, X: np.ndarray) -> np.ndarray:
        n = np.asarray(X).shape[0]
        s = np.zeros((n, len(self.classes)), dtype=np.float32)
        s[:, self._idx] = self._strength
        return s


def test_compare_models_ranks(tmp_session) -> None:
    """Two mock models with different accuracies rank correctly."""
    session_dir = tmp_session(keys=["a", "a", "a", "a"], keyboard_id="blue")
    good = _MockModel("a", strength=5.0)  # always predicts 'a' == the truth
    bad = _MockModel("z", strength=5.0)   # always predicts 'z'
    results = evaluate.compare_models({"good": good, "bad": bad}, session_dir)
    assert results["good"]["raw"]["top1"] > results["bad"]["raw"]["top1"]
    assert results["good"]["raw"]["top1"] == 1.0


def test_format_report_reports_not_measured() -> None:
    """format_report never fabricates a missing metric."""
    metrics = {
        "session_id": "s",
        "keyboard_id": "blue",
        "typist": "x",
        "onset": {"recall": 0.9, "precision": 0.8, "matched": 9, "n_true": 10, "n_detected": 11},
        "raw": {"top1": 0.8, "topk": {1: 0.8, 3: 0.95, 5: 0.99}, "cer": 0.2},
        "latency": {"median": None, "p90": None},
    }
    report = evaluate.format_report(metrics)
    assert "not measured" in report
    assert "onset recall" in report
