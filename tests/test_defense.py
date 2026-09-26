"""Tests for :mod:`clack.defense` (masker generation, state, min-effective sweep).

Owner: BUILD_DEFENSE. Uses a fake output-stream factory so the on/off state
machine is exercised without real audio hardware.
"""

from __future__ import annotations

import numpy as np

import config
from clack import defense


def test_generate_masker_band_content() -> None:
    """Most masker energy sits inside the requested band."""
    sr = config.SAMPLE_RATE
    band = (1000, 10000)
    masker = defense.generate_masker(1.0, sr, band_hz=band, level=0.3, decoys=False)
    spectrum = np.abs(np.fft.rfft(masker)) ** 2
    freqs = np.fft.rfftfreq(masker.shape[0], d=1.0 / sr)
    in_band = spectrum[(freqs >= band[0]) & (freqs <= band[1])].sum()
    total = spectrum.sum()
    assert in_band / total > 0.9


def test_generate_masker_level_scales() -> None:
    """A higher level yields a larger amplitude, bounded to [-1, 1]."""
    sr = config.SAMPLE_RATE
    quiet = defense.generate_masker(0.5, sr, level=0.1, decoys=False)
    loud = defense.generate_masker(0.5, sr, level=0.5, decoys=False)
    assert np.max(np.abs(loud)) > np.max(np.abs(quiet))
    assert np.max(np.abs(loud)) <= 1.0 + 1e-6


def test_apply_masker_mixes_and_matches_length() -> None:
    """Applying the masker preserves length and changes the signal."""
    clean = np.zeros(config.SAMPLE_RATE, dtype=np.float32)
    masker = defense.generate_masker(0.2, config.SAMPLE_RATE, level=0.3)
    masked = defense.apply_masker(clean, masker)
    assert masked.shape == clean.shape
    assert np.any(masked != clean)


class _FakeStream:
    """A stand-in output stream that records start/stop without audio."""

    def __init__(self, callback) -> None:
        self.callback = callback
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def close(self) -> None:
        self.running = False


def test_masker_standard_shield_continuous_while_armed() -> None:
    """Standard Shield is on continuously between start and stop."""
    created = []

    def factory(callback):
        s = _FakeStream(callback)
        created.append(s)
        return s

    masker = defense.Masker(stream_factory=factory)
    assert masker.is_on() is False
    masker.start()
    assert masker.is_on() is True
    assert created[0].running is True
    masker.start()  # idempotent, no second stream
    assert len(created) == 1
    masker.stop()
    assert masker.is_on() is False
    assert created[0].running is False


def test_masker_set_level_and_band_regenerate() -> None:
    """Setting level/band updates state and regenerates the buffer."""
    masker = defense.Masker(stream_factory=lambda cb: _FakeStream(cb))
    masker.set_level(0.5)
    assert masker.level == 0.5
    masker.set_band(2000, 8000)
    assert masker.band == (2000, 8000)
    # Trigger defaults off (Smart Shield is a stretch).
    assert masker.triggered is False
    masker.set_trigger(True)
    assert masker.triggered is True


def test_measure_keyboard_band_covers_energy() -> None:
    """The tuned band overlaps a synthetic band-limited signal's energy."""
    sr = config.SAMPLE_RATE
    # Band-limited noise at 3 to 5 kHz.
    signal = defense.generate_masker(1.0, sr, band_hz=(3000, 5000), level=0.5, decoys=False)
    low, high = defense.measure_keyboard_band(signal, sr)
    assert low < 5000 and high > 3000  # the returned band overlaps 3 to 5 kHz


def test_find_min_effective_level_picks_lowest_meeting_target() -> None:
    """The sweep picks the lowest level whose recovery meets the target."""
    # Synthetic recovery curve: recovery falls as level rises.
    curve = {0.1: 0.60, 0.2: 0.30, 0.3: 0.15, 0.5: 0.05}
    result = defense.find_min_effective_level(
        model=None,
        clean_audio=np.zeros(10, dtype=np.float32),
        true_keys=[],
        target_recovery=0.20,
        measure_fn=lambda lvl: curve[lvl],
    )
    assert result.level == 0.3  # lowest level with recovery <= 0.20
    assert result.recovery == 0.15
    assert result.sweep == curve


def test_find_min_effective_level_none_meets_target() -> None:
    """If no level meets the target, the strongest level is reported."""
    curve = {0.1: 0.9, 0.2: 0.8, 0.3: 0.7, 0.5: 0.6}
    result = defense.find_min_effective_level(
        model=None,
        clean_audio=np.zeros(10, dtype=np.float32),
        true_keys=[],
        target_recovery=0.20,
        measure_fn=lambda lvl: curve[lvl],
    )
    assert result.level == config.MASKER_LEVEL_STEPS[-1]
    assert result.recovery == 0.6
