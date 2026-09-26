"""Tests for :mod:`clack.features` (log-Mel extraction and normalization).

Owner: BUILD_MODEL. Asserts the ACTUAL output shape (not just the config formula)
and uses Hypothesis over window lengths to confirm pad/trim always yields
SPEC_FRAMES.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

import config
from clack import features


def test_log_mel_actual_shape() -> None:
    """The real output shape equals (N_MELS, SPEC_FRAMES)."""
    spec = features.log_mel(np.zeros(config.WINDOW_SAMPLES, dtype=np.float32), config.SAMPLE_RATE)
    assert spec.shape == (config.N_MELS, config.SPEC_FRAMES)


def test_log_mel_finite_and_deterministic() -> None:
    """Output is finite and identical for identical input."""
    rng = np.random.default_rng(0)
    window = rng.normal(0, 0.1, size=config.WINDOW_SAMPLES).astype(np.float32)
    a = features.log_mel(window, config.SAMPLE_RATE)
    b = features.log_mel(window, config.SAMPLE_RATE)
    assert np.all(np.isfinite(a))
    np.testing.assert_allclose(a, b)


@given(length=st.integers(min_value=1024, max_value=20000))
@settings(max_examples=20, deadline=None)
def test_log_mel_padtrim_always_spec_frames(length) -> None:
    """Any window length is padded/trimmed to SPEC_FRAMES frames."""
    window = np.zeros(length, dtype=np.float32)
    spec = features.log_mel(window, config.SAMPLE_RATE)
    assert spec.shape == (config.N_MELS, config.SPEC_FRAMES)


def test_normalize_zscore() -> None:
    """Per-sample z-score gives ~zero mean and ~unit std, shape preserved."""
    rng = np.random.default_rng(1)
    spec = rng.normal(3.0, 2.0, size=(config.N_MELS, config.SPEC_FRAMES)).astype(np.float32)
    norm = features.normalize(spec)
    assert norm.shape == spec.shape
    assert abs(float(norm.mean())) < 1e-4
    assert abs(float(norm.std()) - 1.0) < 1e-3


def test_normalize_constant_input_is_safe() -> None:
    """A constant spectrogram does not divide by zero."""
    spec = np.full((config.N_MELS, config.SPEC_FRAMES), 5.0, dtype=np.float32)
    norm = features.normalize(spec)
    assert np.all(np.isfinite(norm))
