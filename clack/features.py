"""Log-Mel spectrogram extraction and normalization.

Turns a fixed onset-centered window into the log-Mel "image" fed to the model
(``config.N_MELS`` x ``config.SPEC_FRAMES``). Normalization is per-feature and
must be identical in training and inference.

Reference: Harrison et al., IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074).

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import numpy as np


def log_mel(window: np.ndarray, sample_rate: int) -> np.ndarray:
    """Compute a log-Mel spectrogram for one keystroke window.

    Parameters
    ----------
    window : numpy.ndarray
        A 1-D float32 array of ``config.WINDOW_SAMPLES`` samples.
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    numpy.ndarray
        A ``(config.N_MELS, config.SPEC_FRAMES)`` float32 log-Mel spectrogram.

    Raises
    ------
    ValueError
        If ``window`` does not have ``config.WINDOW_SAMPLES`` samples.
    """
    raise NotImplementedError("built in BUILD_MODEL")


def normalize(spec: np.ndarray) -> np.ndarray:
    """Normalize a log-Mel spectrogram for model input.

    Parameters
    ----------
    spec : numpy.ndarray
        A log-Mel spectrogram.

    Returns
    -------
    numpy.ndarray
        The normalized spectrogram, same shape and dtype.
    """
    raise NotImplementedError("built in BUILD_MODEL")
