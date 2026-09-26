"""Offline batch attack on held-out audio.

Given a trained model and a recording, detect onsets, cut identical windows,
featurize, classify each keystroke, and produce recovered text (top-k per press
with confidences). This is the offline counterpart to the live streaming decode in
:mod:`clack.stream`; the evaluation harness and the exposure check call it. It
works with either :class:`clack.model.CentroidBaseline` or
:class:`clack.model.ClackCNN` through their shared ``scores`` interface.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

import config
from clack import dataset as _dataset
from clack import segment as _segment


def _softmax(scores: np.ndarray) -> np.ndarray:
    finite = np.where(np.isfinite(scores), scores, -np.inf)
    shifted = finite - np.max(finite, axis=1, keepdims=True)
    exp = np.exp(np.where(np.isfinite(shifted), shifted, -np.inf))
    total = exp.sum(axis=1, keepdims=True)
    total[total == 0] = 1.0
    return exp / total


def key_name(index: int, classes: list[str]) -> str:
    """Return the class name for a label index."""
    return classes[index]


def render_text(indices: list[int], classes: list[str]) -> str:
    """Render a sequence of label indices as text (``space`` becomes a space)."""
    out = []
    for i in indices:
        name = classes[i]
        out.append(" " if name == "space" else name)
    return "".join(out)


@dataclass
class AttackResult:
    """The result of attacking one recording.

    Attributes
    ----------
    topk : numpy.ndarray
        Per-press ranked class indices, shape ``(n_presses, k)``.
    probs : numpy.ndarray
        Per-press probabilities aligned with ``topk``, shape ``(n_presses, k)``.
    onsets : numpy.ndarray
        Detected onset sample indices.
    text : str
        The top-1 recovered string.
    per_key : list of dict
        One ``{index, topk: [(key, prob), ...], best: key}`` per press.
    classes : list of str
        The model's class names.
    meta : dict
        Provenance and timing metadata.
    """

    topk: np.ndarray
    probs: np.ndarray
    onsets: np.ndarray
    text: str
    per_key: list[dict]
    classes: list[str]
    meta: dict = field(default_factory=dict)


def attack_audio(audio: np.ndarray, sample_rate: int, model: object, k: int = 5) -> AttackResult:
    """Recover keystrokes from an audio signal using a trained model.

    Parameters
    ----------
    audio : numpy.ndarray
        Mono float32 audio samples.
    sample_rate : int
        Sample rate in Hz.
    model : object
        A fitted model exposing ``scores`` and ``classes``
        (:class:`clack.model.ClackCNN` or :class:`clack.model.CentroidBaseline`).
    k : int, optional
        Number of ranked candidates per press (default ``5``).

    Returns
    -------
    AttackResult
        The recovered top-k, probabilities, onsets, and top-1 text.

    Raises
    ------
    ValueError
        If no onsets are detected in the audio.
    """
    windows, onsets = _segment.windows_from_audio(audio, sample_rate)
    if windows.shape[0] == 0:
        raise ValueError(
            "no keystroke onsets detected in the audio; check the microphone, the "
            "onset threshold (ambient calibration), or that keys were actually typed"
        )

    X = np.stack([_dataset.featurize(w, sample_rate) for w in windows], axis=0)
    scores = model.scores(X)
    probs_full = _softmax(scores)
    classes = list(getattr(model, "classes", config.KEY_SET))

    kk = max(1, min(k, scores.shape[1]))
    topk = np.argsort(-scores, axis=1)[:, :kk].astype(np.int64)
    row = np.arange(topk.shape[0])[:, None]
    topk_probs = probs_full[row, topk]

    per_key: list[dict] = []
    best_indices: list[int] = []
    for i in range(topk.shape[0]):
        ranked = [(classes[int(c)], float(topk_probs[i, j])) for j, c in enumerate(topk[i])]
        best = int(topk[i, 0])
        best_indices.append(best)
        per_key.append({"index": i, "topk": ranked, "best": classes[best]})

    text = render_text(best_indices, classes)
    return AttackResult(
        topk=topk,
        probs=topk_probs.astype(np.float32),
        onsets=onsets,
        text=text,
        per_key=per_key,
        classes=classes,
        meta={"n_presses": int(topk.shape[0]), "sample_rate": int(sample_rate)},
    )


def attack_wav(path: str, model: object, k: int = 5) -> AttackResult:
    """Attack a WAV file on disk.

    Parameters
    ----------
    path : str
        Path to a mono WAV recording.
    model : object
        A fitted model (see :func:`attack_audio`).
    k : int, optional
        Number of ranked candidates per press (default ``5``).

    Returns
    -------
    AttackResult
        The recovery result.
    """
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    return attack_audio(audio, int(sr), model, k=k)


def password_search_space(topk: np.ndarray, top_n: int = 3) -> int:
    """Combined top-N-per-position search-space size for a password recovery.

    The honest password number: ``product over positions of min(top_n, k)``,
    framed as "we reduced the space from the full alphabet to N candidates", not
    guaranteed exact recovery.

    Parameters
    ----------
    topk : numpy.ndarray
        Per-press ranked class indices, shape ``(n_presses, k)``.
    top_n : int, optional
        Candidates kept per position (default ``3``).

    Returns
    -------
    int
        The size of the reduced search space (``1`` for an empty password).
    """
    space = 1
    for row in topk:
        space *= min(top_n, len(row))
    return int(space)
