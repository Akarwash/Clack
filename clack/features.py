"""Log-Mel spectrogram extraction and per-sample normalization.

Turns an onset-centered window into the log-Mel "image" fed to the model,
``(config.N_MELS, config.SPEC_FRAMES)``. The time dimension is padded or trimmed
to exactly ``config.SPEC_FRAMES`` so the output shape is guaranteed regardless of
the STFT's centering behavior. Normalization is per-sample z-score: because it
uses only that single image's statistics, there is no cross-sample leakage
between the train and validation splits.

Reference: Harrison et al., IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074).

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import librosa
import numpy as np

import config


def log_mel(window: np.ndarray, sample_rate: int) -> np.ndarray:
    """Compute a log-Mel spectrogram for one keystroke window.

    Parameters
    ----------
    window : numpy.ndarray
        A 1-D float32 window (any length; typically ``config.WINDOW_SAMPLES``).
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    numpy.ndarray
        A ``(config.N_MELS, config.SPEC_FRAMES)`` float32 log-Mel spectrogram in
        dB, padded or trimmed on the time axis to the fixed frame count.

    Examples
    --------
    >>> import numpy as np, config
    >>> spec = log_mel(np.zeros(config.WINDOW_SAMPLES, dtype=np.float32), config.SAMPLE_RATE)
    >>> spec.shape == (config.N_MELS, config.SPEC_FRAMES)
    True
    """
    signal = np.asarray(window, dtype=np.float32)
    mel = librosa.feature.melspectrogram(
        y=signal,
        sr=sample_rate,
        n_fft=config.N_FFT,
        hop_length=config.HOP_LENGTH,
        n_mels=config.N_MELS,
        fmin=config.FMIN,
        fmax=config.FMAX,
        power=2.0,
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # Fix the time dimension to SPEC_FRAMES (pad with the floor value, or trim).
    frames = mel_db.shape[1]
    target = config.SPEC_FRAMES
    if frames < target:
        pad = target - frames
        mel_db = np.pad(mel_db, ((0, 0), (0, pad)), mode="constant", constant_values=float(mel_db.min()))
    elif frames > target:
        mel_db = mel_db[:, :target]
    return mel_db.astype(np.float32)


def normalize(spec: np.ndarray) -> np.ndarray:
    """Per-sample z-score normalization of a log-Mel spectrogram.

    Subtracts the mean and divides by the standard deviation of that single
    image. No cross-sample statistics are used, so there is no train/val leakage.

    Parameters
    ----------
    spec : numpy.ndarray
        A log-Mel spectrogram.

    Returns
    -------
    numpy.ndarray
        The normalized spectrogram, same shape, float32.
    """
    arr = np.asarray(spec, dtype=np.float32)
    mean = float(arr.mean())
    std = float(arr.std())
    if std < 1e-8:
        return (arr - mean).astype(np.float32)
    return ((arr - mean) / std).astype(np.float32)
