"""Metrics harness: onset recall, top-k, CER, latency, and defense deltas.

Reports every metric on a held-out recording: onset detection recall, top-k
keystroke recall (``config.EVAL_TOPK``), character error rate raw vs corrected,
per-press latency, and the baseline-vs-defense recovery delta that proves the
mitigation works.

Owner: BUILD_EVAL.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalReport:
    """A full evaluation report for one held-out recording.

    Attributes
    ----------
    onset_recall : float
        Fraction of true presses matched by a detected onset.
    topk_recall : dict
        Recall at each k in ``config.EVAL_TOPK``.
    cer_raw : float
        Character error rate of raw model output.
    cer_corrected : float
        Character error rate after language-model correction.
    latency_ms : float
        Median per-press decode latency in milliseconds.
    extra : dict
        Any additional metrics (for example defense deltas).
    """

    onset_recall: float
    topk_recall: dict
    cer_raw: float
    cer_corrected: float
    latency_ms: float
    extra: dict = field(default_factory=dict)


def onset_recall(true_onsets: list[int], detected_onsets: list[int], tolerance_samples: int) -> float:
    """Compute onset detection recall within a sample tolerance.

    Parameters
    ----------
    true_onsets : list of int
        Ground-truth onset sample indices.
    detected_onsets : list of int
        Detected onset sample indices.
    tolerance_samples : int
        Maximum distance for a detection to count as a match.

    Returns
    -------
    float
        Recall in ``[0, 1]``.
    """
    raise NotImplementedError("built in BUILD_EVAL")


def topk_recall(pred_topk: list[list[int]], true_labels: list[int], k: int) -> float:
    """Compute top-k keystroke recall.

    Parameters
    ----------
    pred_topk : list of list of int
        Per-press ranked predicted labels.
    true_labels : list of int
        Ground-truth labels.
    k : int
        Cutoff rank.

    Returns
    -------
    float
        Fraction of presses whose true label is within the top ``k``.
    """
    raise NotImplementedError("built in BUILD_EVAL")


def cer(reference: str, hypothesis: str) -> float:
    """Compute character error rate (Levenshtein distance / reference length).

    Parameters
    ----------
    reference : str
        Ground-truth text.
    hypothesis : str
        Recovered text.

    Returns
    -------
    float
        Character error rate (``0`` is perfect; can exceed ``1``).
    """
    raise NotImplementedError("built in BUILD_EVAL")


def evaluate_recording(session_dir: str, model: object, correct: bool = True) -> EvalReport:
    """Run the full metric suite on one held-out recording.

    Parameters
    ----------
    session_dir : str
        A ``data/recordings/<session_id>/`` directory with ground-truth events.
    model : object
        A trained model to evaluate.
    correct : bool, optional
        Whether to also report corrected CER (default ``True``).

    Returns
    -------
    EvalReport
        The assembled metrics.
    """
    raise NotImplementedError("built in BUILD_EVAL")
