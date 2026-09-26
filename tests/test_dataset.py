"""Tests for :mod:`clack.dataset` (assembly, augmentation, session split).

Owner: BUILD_MODEL. Builds datasets from synthetic sessions (no microphone).
"""

from __future__ import annotations

import os

import numpy as np

import config
from clack import dataset


def test_build_dataset_shapes(tmp_session) -> None:
    """Built features have matching X/y lengths and the fixed feature shape."""
    d1 = tmp_session(keys=["a", "b", "c", "d", "e"], typist="one")
    ds = dataset.build_dataset([d1])
    assert ds.X.shape[0] == ds.y.shape[0]
    assert ds.X.shape[1:] == (config.N_MELS, config.SPEC_FRAMES)
    assert ds.classes == list(config.KEY_SET)
    assert len(ds) == ds.X.shape[0]


def test_split_by_session_no_leakage(tmp_session) -> None:
    """Whole sessions go to train or val, never both."""
    d1 = tmp_session(keys=["a", "b", "c"], typist="one")
    d2 = tmp_session(keys=["d", "e", "f"], typist="two")
    ds = dataset.build_dataset([d1, d2])
    train, val = dataset.split_by_session(ds)
    train_ids = set(train.session_ids.tolist())
    val_ids = set(val.session_ids.tolist())
    assert train_ids and val_ids
    assert train_ids.isdisjoint(val_ids)


def test_save_load_roundtrip(tmp_session, tmp_path) -> None:
    """A cached dataset round-trips through .npz."""
    d1 = tmp_session(keys=["a", "b", "c"], typist="one")
    ds = dataset.build_dataset([d1])
    path = os.path.join(str(tmp_path), "cache.npz")
    dataset.save_dataset(ds, path)
    loaded = dataset.load_dataset(path)
    np.testing.assert_allclose(loaded.X, ds.X)
    np.testing.assert_array_equal(loaded.y, ds.y)
    assert loaded.classes == ds.classes


def test_augment_window_preserves_length() -> None:
    """Waveform augmentation keeps the window length exactly."""
    rng = np.random.default_rng(0)
    window = rng.normal(0, 0.1, size=config.WINDOW_SAMPLES).astype(np.float32)
    aug = dataset.augment_window(window, config.SAMPLE_RATE, seed=1)
    assert aug.shape == window.shape
    assert aug.dtype == np.float32


def test_spec_augment_preserves_shape() -> None:
    """SpecAugment keeps the feature shape."""
    rng = np.random.default_rng(0)
    spec = rng.normal(0, 1, size=(config.N_MELS, config.SPEC_FRAMES)).astype(np.float32)
    out = dataset.spec_augment(spec, seed=2)
    assert out.shape == spec.shape


def test_class_weights_shape_and_zero_for_absent() -> None:
    """Class weights have one entry per class; absent classes get weight 0."""
    y = np.array([0, 0, 1, 2, 2, 2], dtype=np.int64)
    n = len(config.KEY_SET)
    w = dataset.class_weights(y, n)
    assert w.shape == (n,)
    assert w[3] == 0.0  # class 3 absent
    assert w[0] > 0 and w[1] > 0
