"""Cross-keyboard few-shot calibration via embedding prototypes (stretch).

To attack a keyboard the model never trained on, type a short calibration string
on that board, average the CNN ``embed()`` vectors per key into prototypes, and
classify new keystrokes by nearest prototype (cosine distance). No retraining, so
calibration takes seconds on stage.

This is the cross-keyboard STRETCH (CLACK_BUILD_PLAN.md section 5; BUILD_MODEL
section 8, Tier A). It never jeopardizes the guaranteed floor.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import json
import os

import numpy as np
import soundfile as sf

import config
from clack import dataset as _dataset
from clack import segment as _segment


def build_prototypes(embeddings: np.ndarray, labels: np.ndarray, n_classes: int) -> np.ndarray:
    """Average per-key embeddings into class prototypes.

    Parameters
    ----------
    embeddings : numpy.ndarray
        Calibration embeddings of shape ``(N, embed_dim)``.
    labels : numpy.ndarray
        Integer labels of shape ``(N,)``.
    n_classes : int
        Total number of classes.

    Returns
    -------
    numpy.ndarray
        Prototypes of shape ``(n_classes, embed_dim)``; rows for unseen classes
        are filled with NaN.
    """
    embeddings = np.asarray(embeddings, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int64)
    dim = embeddings.shape[1]
    protos = np.full((n_classes, dim), np.nan, dtype=np.float32)
    for c in range(n_classes):
        mask = labels == c
        if mask.any():
            protos[c] = embeddings[mask].mean(axis=0)
    return protos


def classify_by_prototype(embeddings: np.ndarray, prototypes: np.ndarray, k: int = 1) -> np.ndarray:
    """Classify keystrokes by nearest prototype in cosine distance.

    Parameters
    ----------
    embeddings : numpy.ndarray
        Query embeddings of shape ``(N, embed_dim)``.
    prototypes : numpy.ndarray
        Prototypes of shape ``(n_classes, embed_dim)``; NaN rows are ignored.
    k : int, optional
        Number of ranked classes to return (default ``1``).

    Returns
    -------
    numpy.ndarray
        Ranked class indices of shape ``(N, k)``.
    """
    embeddings = np.asarray(embeddings, dtype=np.float32)
    protos = np.asarray(prototypes, dtype=np.float32)
    present = ~np.isnan(protos).any(axis=1)

    def _norm(a: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(a, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return a / n

    q = _norm(embeddings)
    p = _norm(np.nan_to_num(protos, nan=0.0))
    sim = q @ p.T  # cosine similarity; higher is closer
    sim[:, ~present] = -np.inf

    kk = max(1, min(k, int(present.sum()) if present.any() else 1))
    return np.argsort(-sim, axis=1)[:, :kk].astype(np.int64)


def prototypes_from_session(model: object, calib_session_dir: str) -> np.ndarray:
    """Build prototypes from a short calibration session on an unseen board.

    Parameters
    ----------
    model : object
        A model exposing ``embed`` (a :class:`clack.model.ClackCNN`).
    calib_session_dir : str
        A recording session with a known calibration string.

    Returns
    -------
    numpy.ndarray
        Prototypes of shape ``(len(KEY_SET), embed_dim)``.

    Raises
    ------
    FileNotFoundError
        If the session files are missing.
    ValueError
        If no calibration windows can be cut.
    """
    wav_path = os.path.join(calib_session_dir, "audio.wav")
    events_path = os.path.join(calib_session_dir, "events.json")
    if not os.path.isfile(wav_path) or not os.path.isfile(events_path):
        raise FileNotFoundError(f"calibration session missing files: {calib_session_dir}")

    audio, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    with open(events_path, encoding="utf-8") as fh:
        meta = json.load(fh)

    windows, labels = _segment.windows_from_events(audio, meta.get("events", []), int(sr), meta)
    if windows.shape[0] == 0:
        raise ValueError("no calibration windows found in the session")

    class_to_idx = {k: i for i, k in enumerate(config.KEY_SET)}
    X = np.stack([_dataset.featurize(w, int(sr)) for w in windows], axis=0)
    emb = model.embed(X)
    y = np.asarray([class_to_idx[k] for k in labels], dtype=np.int64)
    return build_prototypes(emb, y, len(config.KEY_SET))
