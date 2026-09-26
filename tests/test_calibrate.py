"""Tests for :mod:`clack.calibrate` (few-shot cross-keyboard prototypes).

Owner: BUILD_MODEL. Uses synthetic separable embedding clusters.
"""

from __future__ import annotations

import numpy as np

import config
from clack import calibrate


def test_build_prototypes_shape() -> None:
    """Prototypes have shape (n_classes, embed_dim); unseen classes are NaN."""
    n_classes = len(config.KEY_SET)
    rng = np.random.default_rng(0)
    emb = rng.normal(0, 1, size=(20, config.EMBED_DIM)).astype(np.float32)
    labels = rng.integers(0, 3, size=20).astype(np.int64)  # only classes 0..2 present
    protos = calibrate.build_prototypes(emb, labels, n_classes)
    assert protos.shape == (n_classes, config.EMBED_DIM)
    assert np.isnan(protos[10]).all()  # an absent class


def test_nearest_prototype_beats_chance() -> None:
    """Nearest-prototype classification separates well-clustered embeddings."""
    rng = np.random.default_rng(1)
    n_used = 5
    centers = rng.normal(0, 10, size=(n_used, config.EMBED_DIM)).astype(np.float32)

    emb, labels = [], []
    for c in range(n_used):
        for _ in range(4):
            emb.append(centers[c] + rng.normal(0, 0.1, size=config.EMBED_DIM).astype(np.float32))
            labels.append(c)
    emb = np.stack(emb)
    labels = np.asarray(labels)

    protos = calibrate.build_prototypes(emb, labels, len(config.KEY_SET))
    pred = calibrate.classify_by_prototype(emb, protos, k=1)[:, 0]
    acc = (pred == labels).mean()
    assert acc > 0.9  # far above 1/5 chance
