"""Offline batch attack on held-out audio.

Given a trained model and a recording, detect onsets, cut windows, classify each
keystroke, and produce recovered text (top-k per press). This is the offline
counterpart to the live streaming decode in :mod:`clack.stream`; it is used by
the evaluation harness and by the exposure check.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class AttackResult:
    """The result of attacking one recording.

    Attributes
    ----------
    topk : numpy.ndarray
        Per-press ranked class indices of shape ``(n_presses, k)``.
    onsets : numpy.ndarray
        Detected onset sample indices.
    text : str
        The top-1 recovered string.
    meta : dict
        Provenance and timing metadata.
    """

    topk: np.ndarray
    onsets: np.ndarray
    text: str
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
        A fitted :class:`clack.model.ClackCNN` or
        :class:`clack.model.CentroidBaseline`.
    k : int, optional
        Number of ranked candidates per press (default ``5``).

    Returns
    -------
    AttackResult
        The recovered top-k, onsets, and top-1 text.

    Raises
    ------
    ValueError
        If no onsets are detected in the audio.
    """
    raise NotImplementedError("built in BUILD_MODEL")
