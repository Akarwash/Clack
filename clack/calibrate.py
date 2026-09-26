"""Cross-keyboard few-shot calibration via embedding prototypes (stretch).

To attack a keyboard the model never trained on, type a short calibration string
on that board, average the CNN embeddings per key into prototypes, and classify
new keystrokes by nearest prototype. No retraining on the day.

This is the cross-keyboard STRETCH (CLACK_BUILD_PLAN.md section 5): it never
jeopardizes the guaranteed floor.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import numpy as np


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
    raise NotImplementedError("built in BUILD_MODEL")


def classify_by_prototype(embeddings: np.ndarray, prototypes: np.ndarray, k: int = 1) -> np.ndarray:
    """Classify keystrokes by nearest prototype.

    Parameters
    ----------
    embeddings : numpy.ndarray
        Query embeddings of shape ``(N, embed_dim)``.
    prototypes : numpy.ndarray
        Prototypes of shape ``(n_classes, embed_dim)``.
    k : int, optional
        Number of ranked classes to return (default ``1``).

    Returns
    -------
    numpy.ndarray
        Ranked class indices of shape ``(N, k)``.
    """
    raise NotImplementedError("built in BUILD_MODEL")
