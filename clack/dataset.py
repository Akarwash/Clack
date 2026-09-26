"""Dataset assembly: (window, label) pairs, augmentation, caching, loaders.

Builds a labeled dataset from one or more recording sessions by cutting
onset-centered windows (labels from key events), extracting log-Mel features,
optionally augmenting (train only), and caching to a ``.npz`` (contract in
CLACK_BUILD_PLAN.md section 9). Splits are by session, never a random split of
one session (``config.SPLIT_BY_SESSION``).

Owner: BUILD_MODEL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Dataset:
    """An in-memory labeled dataset.

    Attributes
    ----------
    X : numpy.ndarray
        Features of shape ``(N, config.N_MELS, config.SPEC_FRAMES)`` float32.
    y : numpy.ndarray
        Integer labels of shape ``(N,)``.
    classes : list of str
        Class names indexed by label.
    meta : dict
        Provenance metadata (sessions, keyboards, typists).
    """

    X: np.ndarray
    y: np.ndarray
    classes: list[str]
    meta: dict


def build_dataset(session_dirs: list[str], augment: bool = False) -> Dataset:
    """Build a dataset from recording sessions.

    Parameters
    ----------
    session_dirs : list of str
        Paths to ``data/recordings/<session_id>/`` directories.
    augment : bool, optional
        Whether to apply training-time augmentation (default ``False``).

    Returns
    -------
    Dataset
        The assembled dataset.

    Raises
    ------
    ValueError
        If no usable labeled windows are produced (fail loudly, never return
        an empty dataset silently).
    """
    raise NotImplementedError("built in BUILD_MODEL")


def save_dataset(dataset: Dataset, path: str) -> None:
    """Cache a dataset to a ``.npz`` file.

    Parameters
    ----------
    dataset : Dataset
        The dataset to persist.
    path : str
        Destination ``.npz`` path.
    """
    raise NotImplementedError("built in BUILD_MODEL")


def load_dataset(path: str) -> Dataset:
    """Load a cached ``.npz`` dataset.

    Parameters
    ----------
    path : str
        Path to a ``.npz`` produced by :func:`save_dataset`.

    Returns
    -------
    Dataset
        The loaded dataset.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    """
    raise NotImplementedError("built in BUILD_MODEL")


def augment_window(window: np.ndarray, sample_rate: int, seed: Optional[int] = None) -> np.ndarray:
    """Apply train-only waveform augmentation to one window.

    Parameters
    ----------
    window : numpy.ndarray
        A 1-D float32 window.
    sample_rate : int
        Sample rate in Hz.
    seed : int or None, optional
        RNG seed for reproducible augmentation.

    Returns
    -------
    numpy.ndarray
        The augmented window, same length.
    """
    raise NotImplementedError("built in BUILD_MODEL")
