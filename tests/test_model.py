"""Tests for :mod:`clack.model` (centroid floor + CNN with embedding head).

Owner: BUILD_MODEL. Asserts shapes on synthetic batches and that one optimizer
step reduces loss on a tiny overfit batch. Never trains a real model.
"""

from __future__ import annotations

import numpy as np
import torch

import config
from clack import model as _model


def _synthetic_features(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, size=(n, config.N_MELS, config.SPEC_FRAMES)).astype(np.float32)
    y = rng.integers(0, len(config.KEY_SET), size=n).astype(np.int64)
    return X, y


def test_centroid_baseline_separable() -> None:
    """The floor classifies clearly separable classes correctly."""
    n_classes = len(config.KEY_SET)
    rng = np.random.default_rng(0)
    centers = rng.normal(0, 5, size=(n_classes, config.N_MELS, config.SPEC_FRAMES)).astype(np.float32)
    X, y = [], []
    for c in range(n_classes):
        for _ in range(3):
            X.append(centers[c] + rng.normal(0, 0.01, size=centers[c].shape).astype(np.float32))
            y.append(c)
    X = np.stack(X)
    y = np.asarray(y)
    clf = _model.CentroidBaseline().fit(X, y)
    top1 = clf.predict_topk(X, k=1)[:, 0]
    assert (top1 == y).mean() > 0.95


def test_cnn_shapes() -> None:
    """forward, embed, and predict_topk return the right shapes."""
    net = _model.ClackCNN(len(config.KEY_SET))
    x = torch.zeros(4, 1, config.N_MELS, config.SPEC_FRAMES)
    logits = net(x)
    assert logits.shape == (4, len(config.KEY_SET))

    X, _ = _synthetic_features(4)
    assert net.embed(X).shape == (4, config.EMBED_DIM)
    assert net.predict_topk(X, k=3).shape == (4, 3)


def test_cnn_one_step_reduces_loss() -> None:
    """A few optimizer steps reduce loss on a tiny overfit batch."""
    torch.manual_seed(config.SEED)
    net = _model.ClackCNN(len(config.KEY_SET))
    X, y = _synthetic_features(8, seed=3)
    xb = torch.from_numpy(X[:, None, :, :])
    yb = torch.from_numpy(y)
    opt = torch.optim.Adam(net.parameters(), lr=1e-2)
    crit = torch.nn.CrossEntropyLoss()

    net.train()
    with torch.no_grad():
        first = float(crit(net(xb), yb).item())
    for _ in range(15):
        opt.zero_grad()
        loss = crit(net(xb), yb)
        loss.backward()
        opt.step()
    with torch.no_grad():
        last = float(crit(net(xb), yb).item())
    assert last < first


def test_save_load_roundtrip_cnn(tmp_path) -> None:
    """A CNN round-trips through save_model/load_model with matching scores."""
    net = _model.ClackCNN(len(config.KEY_SET))
    X, _ = _synthetic_features(3, seed=5)
    before = net.scores(X)
    model_dir = str(tmp_path / "cnn")
    _model.save_model(net, model_dir, metrics={"val_accuracy": 0.5})
    loaded = _model.load_model(model_dir)
    after = loaded.scores(X)
    np.testing.assert_allclose(before, after, atol=1e-4)


def test_save_load_roundtrip_centroid(tmp_path) -> None:
    """The centroid floor round-trips through save_model/load_model."""
    X, y = _synthetic_features(40, seed=7)
    clf = _model.CentroidBaseline().fit(X, y)
    before = clf.predict_topk(X, k=1)
    model_dir = str(tmp_path / "centroid")
    _model.save_model(clf, model_dir)
    loaded = _model.load_model(model_dir)
    after = loaded.predict_topk(X, k=1)
    np.testing.assert_array_equal(before, after)
