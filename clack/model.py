"""Classifiers: nearest-centroid baseline (floor) and CNN with embedding head.

Two models share the same feature contract:

- :class:`CentroidBaseline`: a trivial nearest-centroid classifier over
  normalized log-Mel features. It needs almost no machinery and is the
  guaranteed fallback if CNN training breaks (golden rule: keep the floor).
- :class:`ClackCNN`: a convolutional classifier that also exposes an
  ``embed()`` vector per keystroke for cross-keyboard calibration.

Reference: Harrison et al., IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074).

Owner: BUILD_MODEL.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


class CentroidBaseline:
    """Nearest-centroid classifier over normalized log-Mel features.

    The floor model: one mean feature vector per key; classify by nearest
    centroid. Always kept working as the fallback.
    """

    def __init__(self) -> None:
        raise NotImplementedError("built in BUILD_MODEL")

    def fit(self, X: np.ndarray, y: np.ndarray) -> "CentroidBaseline":
        """Fit per-class centroids.

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.
        y : numpy.ndarray
            Integer labels of shape ``(N,)``.

        Returns
        -------
        CentroidBaseline
            The fitted model (for chaining).
        """
        raise NotImplementedError("built in BUILD_MODEL")

    def predict_topk(self, X: np.ndarray, k: int = 1) -> np.ndarray:
        """Predict the top-k nearest classes per sample.

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.
        k : int, optional
            Number of ranked classes to return (default ``1``).

        Returns
        -------
        numpy.ndarray
            Integer label ranks of shape ``(N, k)``.
        """
        raise NotImplementedError("built in BUILD_MODEL")


class ClackCNN:
    """CNN keystroke classifier with an embedding head.

    Parameters
    ----------
    n_classes : int
        Number of output classes (``len(config.KEY_SET)``).
    embed_dim : int, optional
        Embedding dimension; defaults to ``config.EMBED_DIM``.
    dropout : float, optional
        Dropout probability; defaults to ``config.DROPOUT``.
    """

    def __init__(self, n_classes: int, embed_dim: Optional[int] = None, dropout: Optional[float] = None) -> None:
        raise NotImplementedError("built in BUILD_MODEL")

    def embed(self, X: np.ndarray) -> np.ndarray:
        """Return the per-keystroke embedding vectors.

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.

        Returns
        -------
        numpy.ndarray
            Embeddings of shape ``(N, embed_dim)``.
        """
        raise NotImplementedError("built in BUILD_MODEL")

    def predict_topk(self, X: np.ndarray, k: int = 1) -> np.ndarray:
        """Predict the top-k most likely classes per sample.

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.
        k : int, optional
            Number of ranked classes to return (default ``1``).

        Returns
        -------
        numpy.ndarray
            Integer label ranks of shape ``(N, k)``.
        """
        raise NotImplementedError("built in BUILD_MODEL")


def save_model(model: object, model_dir: str, config_snapshot: dict, metrics: dict) -> None:
    """Persist a model, its config snapshot, and metrics.

    Parameters
    ----------
    model : object
        A fitted :class:`ClackCNN` or :class:`CentroidBaseline`.
    model_dir : str
        Destination ``data/models/<name>/`` directory.
    config_snapshot : dict
        The config used for the run (deterministic-run logging).
    metrics : dict
        Metrics to store alongside the model.
    """
    raise NotImplementedError("built in BUILD_MODEL")


def load_model(model_dir: str) -> object:
    """Load a persisted model from a model directory.

    Parameters
    ----------
    model_dir : str
        A ``data/models/<name>/`` directory.

    Returns
    -------
    object
        The loaded model.

    Raises
    ------
    FileNotFoundError
        If the model directory is missing required files.
    """
    raise NotImplementedError("built in BUILD_MODEL")
