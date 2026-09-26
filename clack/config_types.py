"""Typed views over ``config.py`` plus the runtime-directory helper.

This module mirrors the flat values in the top-level :mod:`config` module as
frozen dataclasses so other modules can import a typed, grouped configuration
object instead of reaching into module-level globals. It also owns
:func:`ensure_dirs`, which creates the gitignored ``data/`` subtree at runtime
(the directories are never tracked in git; see CLACK_BUILD_PLAN.md section 12).

Examples
--------
>>> from clack.config_types import load_config
>>> cfg = load_config()
>>> cfg.audio.sample_rate
44100
>>> cfg.window.window_samples
8820
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import config as _config


@dataclass(frozen=True)
class AudioConfig:
    """Microphone capture settings."""

    sample_rate: int
    channels: int
    dtype: str
    input_device: Optional[int]


@dataclass(frozen=True)
class WindowConfig:
    """Fixed per-keystroke audio window geometry."""

    window_ms: int
    pre_onset_ms: int
    window_samples: int
    onset_search_ms: int


@dataclass(frozen=True)
class SpectrogramConfig:
    """Log-Mel spectrogram parameters."""

    n_fft: int
    hop_length: int
    n_mels: int
    fmin: int
    fmax: int
    spec_frames: int


@dataclass(frozen=True)
class OnsetConfig:
    """Acoustic onset detection parameters (attack path)."""

    hp_cutoff_hz: float
    frame_ms: float
    k: float
    min_gap_ms: float
    ambient_calib_s: float


@dataclass(frozen=True)
class ModelConfig:
    """Classifier architecture and training hyperparameters."""

    embed_dim: int
    dropout: float
    batch_size: int
    epochs: int
    lr: float
    weight_decay: float
    early_stop_patience: int
    split_by_session: bool


@dataclass(frozen=True)
class DefenseConfig:
    """Acoustic masker and exposure-grading parameters."""

    band_hz: tuple[int, int]
    level: float
    level_steps: list[float]
    target_recovery: float
    triggered: bool
    grade_bands: dict[str, float]
    reports_dir: str


@dataclass(frozen=True)
class Paths:
    """Filesystem locations for runtime artifacts (all under ``data/``)."""

    data_dir: str
    recordings_dir: str
    datasets_dir: str
    models_dir: str
    corpus_dir: str
    reports_dir: str


@dataclass(frozen=True)
class ClackConfig:
    """Aggregate typed configuration assembled from :mod:`config`."""

    seed: int
    audio: AudioConfig
    window: WindowConfig
    spectrogram: SpectrogramConfig
    onset: OnsetConfig
    model: ModelConfig
    defense: DefenseConfig
    paths: Paths
    key_set: list[str] = field(default_factory=list)


def load_config() -> ClackConfig:
    """Build a typed :class:`ClackConfig` snapshot from :mod:`config`.

    Returns
    -------
    ClackConfig
        A frozen, grouped view of the current values in ``config.py``.
    """
    return ClackConfig(
        seed=_config.SEED,
        audio=AudioConfig(
            sample_rate=_config.SAMPLE_RATE,
            channels=_config.CHANNELS,
            dtype=_config.DTYPE,
            input_device=_config.INPUT_DEVICE,
        ),
        window=WindowConfig(
            window_ms=_config.WINDOW_MS,
            pre_onset_ms=_config.PRE_ONSET_MS,
            window_samples=_config.WINDOW_SAMPLES,
            onset_search_ms=_config.ONSET_SEARCH_MS,
        ),
        spectrogram=SpectrogramConfig(
            n_fft=_config.N_FFT,
            hop_length=_config.HOP_LENGTH,
            n_mels=_config.N_MELS,
            fmin=_config.FMIN,
            fmax=_config.FMAX,
            spec_frames=_config.SPEC_FRAMES,
        ),
        onset=OnsetConfig(
            hp_cutoff_hz=_config.ONSET_HP_CUTOFF_HZ,
            frame_ms=_config.ONSET_FRAME_MS,
            k=_config.ONSET_K,
            min_gap_ms=_config.ONSET_MIN_GAP_MS,
            ambient_calib_s=_config.AMBIENT_CALIB_S,
        ),
        model=ModelConfig(
            embed_dim=_config.EMBED_DIM,
            dropout=_config.DROPOUT,
            batch_size=_config.BATCH_SIZE,
            epochs=_config.EPOCHS,
            lr=_config.LR,
            weight_decay=_config.WEIGHT_DECAY,
            early_stop_patience=_config.EARLY_STOP_PATIENCE,
            split_by_session=_config.SPLIT_BY_SESSION,
        ),
        defense=DefenseConfig(
            band_hz=_config.MASKER_BAND_HZ,
            level=_config.MASKER_LEVEL,
            level_steps=list(_config.MASKER_LEVEL_STEPS),
            target_recovery=_config.MASKER_TARGET_RECOVERY,
            triggered=_config.MASKER_TRIGGERED,
            grade_bands=dict(_config.EXPOSURE_GRADE_BANDS),
            reports_dir=_config.FLEET_REPORTS_DIR,
        ),
        paths=Paths(
            data_dir=_config.DATA_DIR,
            recordings_dir=_config.RECORDINGS_DIR,
            datasets_dir=_config.DATASETS_DIR,
            models_dir=_config.MODELS_DIR,
            corpus_dir=_config.CORPUS_DIR,
            reports_dir=_config.REPORTS_DIR,
        ),
        key_set=list(_config.KEY_SET),
    )


def ensure_dirs() -> None:
    """Create the runtime ``data/`` subtree if it does not exist.

    Invoked at startup by the server and the scripts. The directories are never
    tracked in git (see ``.gitignore``); they are materialized on first run.
    Idempotent: safe to call repeatedly.

    Returns
    -------
    None
    """
    for path in (
        _config.RECORDINGS_DIR,
        _config.DATASETS_DIR,
        _config.MODELS_DIR,
        _config.CORPUS_DIR,
        _config.REPORTS_DIR,
    ):
        os.makedirs(path, exist_ok=True)
