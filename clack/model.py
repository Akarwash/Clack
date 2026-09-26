"""Classifiers: nearest-centroid baseline (floor) and CNN with embedding head.

Two models share one prediction contract so :mod:`clack.attack`,
:mod:`clack.evaluate`, :mod:`clack.stream`, and the defense can run against either
by a config switch:

- ``scores(X) -> (N, n_classes)``: higher means more likely.
- ``predict_topk(X, k) -> (N, k)``: ranked class indices.

- :class:`CentroidBaseline`: a trivial nearest-centroid classifier over
  normalized log-Mel features. It needs almost no machinery and is the guaranteed
  fallback if CNN training breaks (golden rule: keep the floor working).
- :class:`ClackCNN`: a small convolutional classifier that also exposes an
  ``embed()`` vector per keystroke for cross-keyboard calibration.

Reference: Harrison et al., IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074).

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

import config


def _topk_from_scores(scores: np.ndarray, k: int) -> np.ndarray:
    """Return the top-k class indices per row from a score matrix."""
    k = max(1, min(k, scores.shape[1]))
    idx = np.argpartition(-scores, kth=k - 1, axis=1)[:, :k]
    # Order the k columns by descending score.
    row = np.arange(scores.shape[0])[:, None]
    order = np.argsort(-scores[row, idx], axis=1)
    return idx[row, order].astype(np.int64)


class CentroidBaseline:
    """Nearest-centroid classifier over normalized log-Mel features.

    The floor model: one mean flattened feature vector per class; classify by
    nearest centroid (Euclidean). Always kept working as the fallback.
    """

    def __init__(self) -> None:
        self.centroids: Optional[np.ndarray] = None
        self.classes: list[str] = list(config.KEY_SET)
        self._feature_shape: Optional[tuple[int, int]] = None

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

        Raises
        ------
        ValueError
            If ``X`` is empty.
        """
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int64)
        if X.shape[0] == 0:
            raise ValueError("cannot fit CentroidBaseline on an empty dataset")
        self._feature_shape = X.shape[1:]
        flat = X.reshape(X.shape[0], -1)
        n_classes = len(self.classes)
        dim = flat.shape[1]
        centroids = np.full((n_classes, dim), np.nan, dtype=np.float32)
        for c in range(n_classes):
            mask = y == c
            if mask.any():
                centroids[c] = flat[mask].mean(axis=0)
        self.centroids = centroids
        return self

    def scores(self, X: np.ndarray) -> np.ndarray:
        """Return negative distances to each centroid (higher is closer).

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.

        Returns
        -------
        numpy.ndarray
            Scores of shape ``(N, n_classes)``; absent classes score ``-inf``.
        """
        if self.centroids is None:
            raise RuntimeError("CentroidBaseline is not fitted")
        flat = np.asarray(X, dtype=np.float32).reshape(np.asarray(X).shape[0], -1)
        present = ~np.isnan(self.centroids).any(axis=1)
        cent = np.nan_to_num(self.centroids, nan=0.0)
        # Squared Euclidean distance, vectorized.
        dists = (
            (flat**2).sum(axis=1)[:, None]
            - 2.0 * flat @ cent.T
            + (cent**2).sum(axis=1)[None, :]
        )
        scores = -dists
        scores[:, ~present] = -np.inf
        return scores.astype(np.float32)

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
        return _topk_from_scores(self.scores(X), k)


class ClackCNN(nn.Module):
    """Small CNN keystroke classifier with an embedding head.

    Input shape ``(batch, 1, N_MELS, T)``. Parameter count is well under 1M, so it
    trains fast on CPU/MPS and is a few MB on disk.

    Parameters
    ----------
    n_classes : int
        Number of output classes (``len(config.KEY_SET)``).
    embed_dim : int, optional
        Embedding dimension; defaults to ``config.EMBED_DIM``.
    dropout : float, optional
        Dropout probability; defaults to ``config.DROPOUT``.
    """

    def __init__(
        self,
        n_classes: int,
        embed_dim: Optional[int] = None,
        dropout: Optional[float] = None,
    ) -> None:
        super().__init__()
        self.n_classes = int(n_classes)
        self.embed_dim = int(embed_dim or config.EMBED_DIM)
        self.dropout_p = float(config.DROPOUT if dropout is None else dropout)
        self.classes: list[str] = list(config.KEY_SET)

        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        self.embed_head = nn.Sequential(nn.Linear(128, self.embed_dim), nn.ReLU(inplace=True))
        self.classifier = nn.Sequential(
            nn.Dropout(self.dropout_p), nn.Linear(self.embed_dim, self.n_classes)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return classification logits.

        Parameters
        ----------
        x : torch.Tensor
            Input of shape ``(batch, 1, N_MELS, T)``.

        Returns
        -------
        torch.Tensor
            Logits of shape ``(batch, n_classes)``.
        """
        z = self.embed_features(x)
        return self.classifier(z)

    def embed_features(self, x: torch.Tensor) -> torch.Tensor:
        """Return the pre-classifier embedding tensor ``(batch, embed_dim)``."""
        h = self.features(x)
        h = torch.flatten(h, 1)
        return self.embed_head(h)

    def _as_input(self, X: np.ndarray) -> torch.Tensor:
        arr = np.asarray(X, dtype=np.float32)
        if arr.ndim == 3:  # (N, n_mels, T) -> (N, 1, n_mels, T)
            arr = arr[:, None, :, :]
        device = next(self.parameters()).device
        return torch.from_numpy(arr).to(device)

    def embed(self, X: np.ndarray) -> np.ndarray:
        """Return per-keystroke embedding vectors (the cross-keyboard feature).

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.

        Returns
        -------
        numpy.ndarray
            Embeddings of shape ``(N, embed_dim)``.
        """
        self.eval()
        with torch.no_grad():
            return self.embed_features(self._as_input(X)).cpu().numpy()

    def scores(self, X: np.ndarray) -> np.ndarray:
        """Return classification logits as a numpy score matrix.

        Parameters
        ----------
        X : numpy.ndarray
            Features of shape ``(N, n_mels, T)``.

        Returns
        -------
        numpy.ndarray
            Logits of shape ``(N, n_classes)``.
        """
        self.eval()
        with torch.no_grad():
            return self.forward(self._as_input(X)).cpu().numpy()

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
        return _topk_from_scores(self.scores(X), k)


def _config_snapshot() -> dict:
    """A JSON-serializable snapshot of the config values the model depends on."""
    return {
        "sample_rate": config.SAMPLE_RATE,
        "window_samples": config.WINDOW_SAMPLES,
        "n_mels": config.N_MELS,
        "spec_frames": config.SPEC_FRAMES,
        "n_fft": config.N_FFT,
        "hop_length": config.HOP_LENGTH,
        "embed_dim": config.EMBED_DIM,
        "dropout": config.DROPOUT,
        "key_set": list(config.KEY_SET),
        "seed": config.SEED,
    }


def save_model(model: object, model_dir: str, metrics: Optional[dict] = None) -> None:
    """Persist a model, its config snapshot, and metrics.

    Parameters
    ----------
    model : object
        A fitted :class:`ClackCNN` or :class:`CentroidBaseline`.
    model_dir : str
        Destination ``data/models/<name>/`` directory.
    metrics : dict or None, optional
        Metrics to store in ``metrics.json``.
    """
    os.makedirs(model_dir, exist_ok=True)
    if isinstance(model, ClackCNN):
        model_type = "cnn"
        torch.save(model.state_dict(), os.path.join(model_dir, "model.pt"))
        extra = {"n_classes": model.n_classes, "embed_dim": model.embed_dim, "dropout": model.dropout_p}
    elif isinstance(model, CentroidBaseline):
        model_type = "centroid"
        np.savez_compressed(os.path.join(model_dir, "centroids.npz"), centroids=model.centroids)
        extra = {"n_classes": len(model.classes)}
    else:
        raise TypeError(f"unknown model type: {type(model)!r}")

    cfg = {"type": model_type, "classes": list(getattr(model, "classes", config.KEY_SET)), **extra,
           "config": _config_snapshot()}
    with open(os.path.join(model_dir, "config.json"), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    with open(os.path.join(model_dir, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics or {}, fh, indent=2)


def load_model(model_dir: str) -> object:
    """Load a persisted model from a model directory.

    Parameters
    ----------
    model_dir : str
        A ``data/models/<name>/`` directory.

    Returns
    -------
    object
        The loaded :class:`ClackCNN` or :class:`CentroidBaseline`.

    Raises
    ------
    FileNotFoundError
        If the model directory is missing required files.
    """
    cfg_path = os.path.join(model_dir, "config.json")
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f"model config not found: {cfg_path}")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)

    if cfg["type"] == "cnn":
        model = ClackCNN(cfg["n_classes"], embed_dim=cfg.get("embed_dim"), dropout=cfg.get("dropout"))
        state = torch.load(os.path.join(model_dir, "model.pt"), map_location="cpu")
        model.load_state_dict(state)
        model.classes = list(cfg.get("classes", config.KEY_SET))
        model.eval()
        return model
    if cfg["type"] == "centroid":
        model = CentroidBaseline()
        with np.load(os.path.join(model_dir, "centroids.npz")) as data:
            model.centroids = data["centroids"].astype(np.float32)
        model.classes = list(cfg.get("classes", config.KEY_SET))
        return model
    raise ValueError(f"unknown model type in config: {cfg.get('type')!r}")
