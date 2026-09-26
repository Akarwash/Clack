"""Dataset assembly: (window, label) pairs, augmentation, caching, splitting.

Builds a labeled dataset from one or more recording sessions by cutting
onset-centered windows (labels from key events, via :mod:`clack.segment`),
extracting per-sample-normalized log-Mel features, and caching to ``.npz``
(contract in CLACK_BUILD_PLAN.md section 9, plus per-sample ``session_id`` and
``keyboard_id``). Splits are BY SESSION, never a random split of one session
(``config.SPLIT_BY_SESSION``): a random within-session split would share mic
position, room noise, gain, and typist state across train and val and inflate
accuracy.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import librosa
import numpy as np
import soundfile as sf

import config
from clack import features as _features
from clack import segment as _segment


@dataclass
class Dataset:
    """An in-memory labeled dataset.

    Attributes
    ----------
    X : numpy.ndarray
        Normalized log-Mel features, shape ``(N, N_MELS, SPEC_FRAMES)`` float32.
    y : numpy.ndarray
        Integer labels, shape ``(N,)`` int64.
    classes : list of str
        Class names indexed by label (``config.KEY_SET``).
    session_ids : numpy.ndarray
        Per-sample source session id, shape ``(N,)``.
    keyboard_ids : numpy.ndarray
        Per-sample source keyboard id, shape ``(N,)``.
    meta : dict
        Provenance metadata (source sessions, config snapshot).
    windows : numpy.ndarray or None
        Optional raw onset windows, shape ``(N, WINDOW_SAMPLES)``, kept in memory
        for on-the-fly waveform augmentation (not persisted to ``.npz``).
    """

    X: np.ndarray
    y: np.ndarray
    classes: list[str]
    session_ids: np.ndarray
    keyboard_ids: np.ndarray
    meta: dict = field(default_factory=dict)
    windows: Optional[np.ndarray] = None

    def __len__(self) -> int:
        return int(self.X.shape[0])


def featurize(window: np.ndarray, sample_rate: int) -> np.ndarray:
    """Window -> normalized log-Mel feature (the single feature path).

    Parameters
    ----------
    window : numpy.ndarray
        A raw onset window.
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    numpy.ndarray
        A ``(N_MELS, SPEC_FRAMES)`` normalized float32 feature.
    """
    return _features.normalize(_features.log_mel(window, sample_rate))


def build_dataset(session_dirs: list[str], augment: bool = False) -> Dataset:
    """Build a dataset from recording sessions.

    Parameters
    ----------
    session_dirs : list of str
        Paths to ``data/recordings/<session_id>/`` directories.
    augment : bool, optional
        Unused at build time; augmentation is applied on the fly at train time
        (kept for API symmetry). Default ``False``.

    Returns
    -------
    Dataset
        The assembled dataset (with raw windows retained in memory).

    Raises
    ------
    ValueError
        If no usable labeled windows are produced (fail loudly, never return an
        empty dataset silently).
    FileNotFoundError
        If a session directory is missing its files.
    """
    classes = list(config.KEY_SET)
    class_to_idx = {k: i for i, k in enumerate(classes)}

    all_windows: list[np.ndarray] = []
    ys: list[int] = []
    sids: list[str] = []
    kids: list[str] = []
    sources: list[str] = []

    for session_dir in session_dirs:
        wav_path = os.path.join(session_dir, "audio.wav")
        events_path = os.path.join(session_dir, "events.json")
        if not os.path.isfile(wav_path) or not os.path.isfile(events_path):
            raise FileNotFoundError(f"session missing audio.wav or events.json: {session_dir}")

        audio, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1).astype(np.float32)
        with open(events_path, encoding="utf-8") as fh:
            meta = json.load(fh)

        windows, labels = _segment.windows_from_events(audio, meta.get("events", []), int(sr), meta)
        for window, key in zip(windows, labels):
            all_windows.append(window)
            ys.append(class_to_idx[key])
            sids.append(meta.get("session_id", os.path.basename(session_dir)))
            kids.append(meta.get("keyboard_id", "unknown"))
        sources.append(meta.get("session_id", os.path.basename(session_dir)))

    if not all_windows:
        raise ValueError(
            "no usable labeled windows were produced from the given sessions; "
            "check onset detection and the event clock mapping (never training on "
            "an empty dataset)"
        )

    windows_arr = np.stack(all_windows, axis=0).astype(np.float32)
    X = np.stack([featurize(w, config.SAMPLE_RATE) for w in windows_arr], axis=0).astype(np.float32)
    y = np.asarray(ys, dtype=np.int64)
    return Dataset(
        X=X,
        y=y,
        classes=classes,
        session_ids=np.asarray(sids),
        keyboard_ids=np.asarray(kids),
        meta={"sources": sources, "sample_rate": config.SAMPLE_RATE},
        windows=windows_arr,
    )


def save_dataset(dataset: Dataset, path: str) -> None:
    """Cache a dataset's features to a ``.npz`` file (section 9 contract).

    Parameters
    ----------
    dataset : Dataset
        The dataset to persist.
    path : str
        Destination ``.npz`` path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    np.savez_compressed(
        path,
        X=dataset.X,
        y=dataset.y,
        classes=np.asarray(dataset.classes),
        session_ids=dataset.session_ids,
        keyboard_ids=dataset.keyboard_ids,
        meta=json.dumps(dataset.meta),
    )


def load_dataset(path: str) -> Dataset:
    """Load a cached ``.npz`` dataset.

    Parameters
    ----------
    path : str
        Path to a ``.npz`` produced by :func:`save_dataset`.

    Returns
    -------
    Dataset
        The loaded dataset (``windows`` is ``None``; features only).

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"dataset not found: {path}")
    with np.load(path, allow_pickle=False) as data:
        return Dataset(
            X=data["X"].astype(np.float32),
            y=data["y"].astype(np.int64),
            classes=[str(c) for c in data["classes"].tolist()],
            session_ids=data["session_ids"],
            keyboard_ids=data["keyboard_ids"],
            meta=json.loads(str(data["meta"])),
            windows=None,
        )


def split_by_session(
    dataset: Dataset,
    val_session_ids: Optional[list[str]] = None,
    val_fraction: float = 0.3,
) -> tuple[Dataset, Dataset]:
    """Split a dataset into train and val by WHOLE sessions (no leakage).

    Parameters
    ----------
    dataset : Dataset
        The dataset to split.
    val_session_ids : list of str or None, optional
        Sessions to hold out for validation. If ``None``, the last
        ``ceil(val_fraction * n_sessions)`` sessions (sorted) are held out.
    val_fraction : float, optional
        Fraction of sessions to hold out when ``val_session_ids`` is ``None``
        (default ``0.3``).

    Returns
    -------
    tuple of Dataset
        ``(train, val)``. No ``session_id`` appears in both.

    Raises
    ------
    ValueError
        If the split leaves either side empty.
    """
    unique = sorted(set(dataset.session_ids.tolist()))
    if val_session_ids is None:
        n_val = max(1, int(np.ceil(val_fraction * len(unique))))
        val_set = set(unique[-n_val:])
    else:
        val_set = set(val_session_ids)

    val_mask = np.isin(dataset.session_ids, list(val_set))
    train_mask = ~val_mask
    if train_mask.sum() == 0 or val_mask.sum() == 0:
        raise ValueError(
            f"session split left an empty side (train={int(train_mask.sum())}, "
            f"val={int(val_mask.sum())}); need at least two sessions"
        )

    def _subset(mask: np.ndarray) -> Dataset:
        return Dataset(
            X=dataset.X[mask],
            y=dataset.y[mask],
            classes=dataset.classes,
            session_ids=dataset.session_ids[mask],
            keyboard_ids=dataset.keyboard_ids[mask],
            meta=dataset.meta,
            windows=None if dataset.windows is None else dataset.windows[mask],
        )

    return _subset(train_mask), _subset(val_mask)


def augment_window(window: np.ndarray, sample_rate: int, seed: Optional[int] = None) -> np.ndarray:
    """Apply train-only waveform augmentation to one window.

    Additive Gaussian noise (``AUG_NOISE_STD``), a small time shift
    (``AUG_TIME_SHIFT_MS``), and a small pitch shift (``AUG_PITCH_SEMITONES``).
    Length is preserved.

    Parameters
    ----------
    window : numpy.ndarray
        A 1-D float32 window.
    sample_rate : int
        Sample rate in Hz.
    seed : int or None, optional
        RNG seed for reproducible augmentation.

    Returns
    -------
    numpy.ndarray
        The augmented window, same length, float32.
    """
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    out = np.asarray(window, dtype=np.float32).copy()

    # Time shift.
    max_shift = int(sample_rate * config.AUG_TIME_SHIFT_MS / 1000.0)
    if max_shift > 0:
        shift = int(rng.integers(-max_shift, max_shift + 1))
        out = np.roll(out, shift)

    # Pitch shift (helps cross-board robustness).
    semitones = float(rng.uniform(-config.AUG_PITCH_SEMITONES, config.AUG_PITCH_SEMITONES))
    if abs(semitones) > 1e-3:
        try:
            out = librosa.effects.pitch_shift(out, sr=sample_rate, n_steps=semitones).astype(np.float32)
        except Exception:  # pragma: no cover - librosa edge cases on tiny inputs
            pass

    # Additive Gaussian noise.
    out = out + rng.normal(0.0, config.AUG_NOISE_STD, size=out.shape).astype(np.float32)

    # Preserve exact length.
    if out.shape[0] < window.shape[0]:
        out = np.pad(out, (0, window.shape[0] - out.shape[0]))
    elif out.shape[0] > window.shape[0]:
        out = out[: window.shape[0]]
    return out.astype(np.float32)


def spec_augment(spec: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
    """Apply SpecAugment time and frequency masking to a spectrogram.

    Masks up to ``SPECAUG_TIME_MASK`` time frames and ``SPECAUG_FREQ_MASK`` Mel
    bands. Shape is preserved.

    Parameters
    ----------
    spec : numpy.ndarray
        A ``(N_MELS, SPEC_FRAMES)`` feature.
    seed : int or None, optional
        RNG seed.

    Returns
    -------
    numpy.ndarray
        The masked feature, same shape, float32.
    """
    rng = np.random.default_rng(config.SEED if seed is None else seed)
    out = np.asarray(spec, dtype=np.float32).copy()
    n_mels, n_frames = out.shape
    fill = float(out.min())

    t_width = int(rng.integers(0, config.SPECAUG_TIME_MASK + 1))
    if t_width > 0 and n_frames > t_width:
        t0 = int(rng.integers(0, n_frames - t_width))
        out[:, t0 : t0 + t_width] = fill

    f_width = int(rng.integers(0, config.SPECAUG_FREQ_MASK + 1))
    if f_width > 0 and n_mels > f_width:
        f0 = int(rng.integers(0, n_mels - f_width))
        out[f0 : f0 + f_width, :] = fill

    return out


def class_weights(y: np.ndarray, n_classes: int) -> np.ndarray:
    """Inverse-frequency class weights for a weighted cross-entropy loss.

    Parameters
    ----------
    y : numpy.ndarray
        Integer labels.
    n_classes : int
        Total number of classes.

    Returns
    -------
    numpy.ndarray
        Per-class weights of shape ``(n_classes,)`` float32 (mean 1.0). Absent
        classes get weight 0.
    """
    counts = np.bincount(y, minlength=n_classes).astype(np.float64)
    weights = np.zeros(n_classes, dtype=np.float64)
    present = counts > 0
    weights[present] = counts[present].sum() / (present.sum() * counts[present])
    return weights.astype(np.float32)
