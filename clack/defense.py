"""Acoustic masker and before/after accuracy measurement (the payoff).

Generates a band-limited masking sound (``config.MASKER_BAND_HZ``) that corrupts
the microphone input so the attack accuracy craters, and measures the recovery
before vs after. The guaranteed path is the Standard Shield: a continuous masker
while armed. A triggered "Smart Shield" is a stretch and off by default, because
a triggered masker can fire after the identifying transient already reached the
mic (``config.MASKER_TRIGGERED``).

Owner: BUILD_DEFENSE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class MaskerResult:
    """A minimum-effective masker search outcome.

    Attributes
    ----------
    level : float
        The chosen masking level.
    recovery : float
        Attack recovery achieved at that level.
    sweep : dict
        Recovery measured at each swept level.
    """

    level: float
    recovery: float
    sweep: dict


def generate_masker(duration_s: float, sample_rate: int, band_hz: Optional[tuple[int, int]] = None, level: Optional[float] = None) -> np.ndarray:
    """Generate a band-limited acoustic masking signal.

    Parameters
    ----------
    duration_s : float
        Length of the masker in seconds.
    sample_rate : int
        Sample rate in Hz.
    band_hz : tuple of int or None, optional
        Passband; defaults to ``config.MASKER_BAND_HZ``.
    level : float or None, optional
        Amplitude scale; defaults to ``config.MASKER_LEVEL``.

    Returns
    -------
    numpy.ndarray
        Float32 masker samples in ``[-1, 1]``.
    """
    raise NotImplementedError("built in BUILD_DEFENSE")


def apply_masker(clean_audio: np.ndarray, masker: np.ndarray) -> np.ndarray:
    """Mix a masker into clean audio to simulate what the mic would capture.

    Parameters
    ----------
    clean_audio : numpy.ndarray
        The clean recording.
    masker : numpy.ndarray
        The masking signal.

    Returns
    -------
    numpy.ndarray
        The masked (corrupted) audio.
    """
    raise NotImplementedError("built in BUILD_DEFENSE")


def find_min_effective_level(audio: np.ndarray, sample_rate: int, model: object, target_recovery: Optional[float] = None) -> MaskerResult:
    """Sweep masking levels for the lowest that hits the target recovery (D2).

    Parameters
    ----------
    audio : numpy.ndarray
        Clean audio to attack under masking.
    sample_rate : int
        Sample rate in Hz.
    model : object
        The trained attack model.
    target_recovery : float or None, optional
        Recovery ceiling; defaults to ``config.MASKER_TARGET_RECOVERY``.

    Returns
    -------
    MaskerResult
        The minimum-effective level and its sweep.
    """
    raise NotImplementedError("built in BUILD_DEFENSE")
