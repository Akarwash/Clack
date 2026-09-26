"""Onset detection and onset-centered window cutting.

The single most important concept in Clack: both training and attack cut an
onset-centered window; only the label source differs. At training time a key
event gives the label and an approximate location, then a small band
(+/- ``config.ONSET_SEARCH_MS``) is searched for the real acoustic onset with the
SAME detector the attack uses, and the window is cut there. At attack time onsets
are found directly. Both paths call the identical :func:`cut_window`, so the two
cannot drift.

Reference: Harrison, Toreini, Mehrnezhad, "A Practical Deep Learning-Based
Acoustic Side Channel Attack on Keyboards," IEEE EuroS&PW 2023
(https://arxiv.org/abs/2308.01074), section on keystroke isolation (energy
onset detection).

Owner: BUILD_MODEL.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from scipy.signal import butter, sosfiltfilt

import config


def _highpass(audio: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    """High-pass filter to emphasize the click transient over room rumble."""
    if audio.size == 0:
        return audio
    nyq = 0.5 * sample_rate
    normalized = min(0.99, cutoff_hz / nyq)
    sos = butter(4, normalized, btype="highpass", output="sos")
    padlen = 3 * (sos.shape[0] + 1)
    if audio.shape[0] <= padlen:
        return audio.astype(np.float32, copy=False)
    return sosfiltfilt(sos, audio).astype(np.float32)


def _frame_energy(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    """Return non-overlapping short-time energy per frame and the frame length."""
    frame_len = max(1, int(sample_rate * config.ONSET_FRAME_MS / 1000.0))
    n_frames = audio.shape[0] // frame_len
    if n_frames == 0:
        return np.zeros(0, dtype=np.float64), frame_len
    trimmed = audio[: n_frames * frame_len].reshape(n_frames, frame_len)
    energy = np.sum(trimmed.astype(np.float64) ** 2, axis=1)
    return energy, frame_len


def detect_onsets(audio: np.ndarray, sample_rate: int, k: Optional[float] = None) -> np.ndarray:
    """Detect acoustic key-press onsets via the energy method.

    Parameters
    ----------
    audio : numpy.ndarray
        Mono float32 audio samples.
    sample_rate : int
        Sample rate in Hz.
    k : float or None, optional
        Threshold multiplier over the noise floor; defaults to ``config.ONSET_K``
        (ambient calibration overrides this at attack startup).

    Returns
    -------
    numpy.ndarray
        Integer sample indices of detected onsets, each at least
        ``config.ONSET_MIN_GAP_MS`` apart (one onset per physical press).
    """
    energy, frame_len, threshold = _energy_and_threshold(audio, sample_rate, k)
    if energy.size == 0:
        return np.zeros(0, dtype=np.int64)
    onsets, _ = _onsets_with_energy(energy, frame_len, sample_rate, threshold)
    return onsets


def _energy_and_threshold(
    audio: np.ndarray,
    sample_rate: int,
    k: Optional[float] = None,
) -> tuple[np.ndarray, int, float]:
    """Compute frame energy and the noise-relative onset threshold.

    The noise floor is estimated from the bottom 90% of frames: this excludes the
    loud click outliers (so they do not inflate the baseline) while keeping enough
    typical noise frames that the threshold clears the normal room level, not just
    the quietest samples. A lower percentile would put the threshold inside the
    noise and fire on every noisy frame.
    """
    threshold_k = config.ONSET_K if k is None else float(k)
    filtered = _highpass(audio, sample_rate, config.ONSET_HP_CUTOFF_HZ)
    energy, frame_len = _frame_energy(filtered, sample_rate)
    if energy.size == 0:
        return energy, frame_len, 0.0

    noise_cut = np.percentile(energy, 90)
    noise = energy[energy <= noise_cut]
    if noise.size == 0:
        noise = energy
    baseline_mean = float(np.mean(noise))
    baseline_std = float(np.std(noise))
    threshold = baseline_mean + threshold_k * baseline_std
    if threshold <= baseline_mean:
        threshold = baseline_mean + 1e-12
    return energy, frame_len, threshold


def _onsets_with_energy(
    energy: np.ndarray,
    frame_len: int,
    sample_rate: int,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Group frames above ``threshold`` into runs; return (onset_sample, run_peak).

    The onset is the rising edge (first frame) of each run; the run peak energy is
    used by :func:`find_onset_near` to pick the strongest (real) transient in a
    search band. Runs closer than ``config.ONSET_MIN_GAP_MS`` collapse to one.
    """
    above = energy > threshold
    min_gap = int(sample_rate * config.ONSET_MIN_GAP_MS / 1000.0)

    onsets: list[int] = []
    peaks: list[float] = []
    i = 0
    n = above.shape[0]
    while i < n:
        if above[i]:
            j = i
            while j < n and above[j]:
                j += 1
            onset_sample = i * frame_len
            run_peak = float(np.max(energy[i:j]))
            if onsets and onset_sample - onsets[-1] < min_gap:
                # Within debounce window: keep the stronger of the two.
                if run_peak > peaks[-1]:
                    onsets[-1] = onset_sample
                    peaks[-1] = run_peak
            else:
                onsets.append(onset_sample)
                peaks.append(run_peak)
            i = j
        else:
            i += 1
    return np.asarray(onsets, dtype=np.int64), np.asarray(peaks, dtype=np.float64)


def find_onset_near(
    audio: np.ndarray,
    approx_sample: int,
    sample_rate: int,
    k: Optional[float] = None,
) -> Optional[int]:
    """Snap an approximate event location to the nearest acoustic onset.

    Runs the SAME detector as :func:`detect_onsets` on the band
    ``[approx - S, approx + S]`` where ``S = ONSET_SEARCH_MS`` in samples, and
    returns the detected onset closest to ``approx_sample``.

    Parameters
    ----------
    audio : numpy.ndarray
        Mono float32 audio samples.
    approx_sample : int
        Approximate onset location from the key-event clock.
    sample_rate : int
        Sample rate in Hz.
    k : float or None, optional
        Threshold multiplier; defaults to ``config.ONSET_K``.

    Returns
    -------
    int or None
        The refined absolute onset sample index, or ``None`` if no clear onset is
        found in the band (silence or a missed press; the caller drops it rather
        than cutting at the raw timestamp).
    """
    search = int(sample_rate * config.ONSET_SEARCH_MS / 1000.0)
    lo = max(0, approx_sample - search)
    hi = min(audio.shape[0], approx_sample + search)
    if hi - lo <= 0:
        return None

    band = audio[lo:hi]
    energy, frame_len, threshold = _energy_and_threshold(band, sample_rate, k)
    if energy.size == 0:
        return None
    local, peaks = _onsets_with_energy(energy, frame_len, sample_rate, threshold)
    if local.size == 0:
        return None
    # The real key press dominates energy in the +/- ONSET_SEARCH_MS band, so pick
    # the strongest onset rather than the nearest (which could be a noise spike).
    strongest = local[int(np.argmax(peaks))]
    return int(strongest + lo)


def cut_window(audio: np.ndarray, onset_sample: int) -> np.ndarray:
    """Cut a fixed onset-centered window of ``config.WINDOW_SAMPLES`` samples.

    The window begins ``config.PRE_ONSET_MS`` before the onset. Windows that run
    off either edge are zero-padded to a constant length. This is the single cut
    helper both the training and attack paths call.

    Parameters
    ----------
    audio : numpy.ndarray
        Mono float32 audio samples.
    onset_sample : int
        The onset sample index to anchor on.

    Returns
    -------
    numpy.ndarray
        A 1-D array of exactly ``config.WINDOW_SAMPLES`` float32 samples.
    """
    pre = int(config.SAMPLE_RATE * config.PRE_ONSET_MS / 1000.0)
    start = int(onset_sample) - pre
    end = start + config.WINDOW_SAMPLES

    window = np.zeros(config.WINDOW_SAMPLES, dtype=np.float32)
    src_lo = max(0, start)
    src_hi = min(audio.shape[0], end)
    if src_hi > src_lo:
        dst_lo = src_lo - start
        dst_hi = dst_lo + (src_hi - src_lo)
        window[dst_lo:dst_hi] = audio[src_lo:src_hi].astype(np.float32, copy=False)
    return window


def windows_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    k: Optional[float] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Attack path: detect onsets and cut a window at each (no labels).

    Parameters
    ----------
    audio : numpy.ndarray
        Mono float32 audio samples.
    sample_rate : int
        Sample rate in Hz.
    k : float or None, optional
        Onset threshold multiplier; defaults to ``config.ONSET_K``.

    Returns
    -------
    tuple of numpy.ndarray
        ``(windows, onsets)`` where ``windows`` has shape
        ``(n_onsets, config.WINDOW_SAMPLES)`` and ``onsets`` holds the sample
        indices.
    """
    onsets = detect_onsets(audio, sample_rate, k=k)
    if onsets.size == 0:
        return np.zeros((0, config.WINDOW_SAMPLES), dtype=np.float32), onsets
    windows = np.stack([cut_window(audio, int(o)) for o in onsets], axis=0)
    return windows.astype(np.float32), onsets


def windows_from_events(
    audio: np.ndarray,
    events: list[dict],
    sample_rate: int,
    meta: dict,
) -> tuple[np.ndarray, list[str]]:
    """Training path: cut an onset-snapped window per key event (labels known).

    For each ``press`` event, compute the approximate sample from the clock
    mapping, snap to the real acoustic onset within +/- ``ONSET_SEARCH_MS`` with
    :func:`find_onset_near`, and cut the identical window with :func:`cut_window`.
    Events whose key is not in ``config.KEY_SET`` or whose onset cannot be found
    are dropped (never cut at the raw timestamp).

    Parameters
    ----------
    audio : numpy.ndarray
        Mono float32 audio samples.
    events : list of dict
        Press events with ``key`` and ``t_perf``.
    sample_rate : int
        Sample rate in Hz.
    meta : dict
        Session metadata with ``audio_start_perf`` and ``input_latency_s`` for the
        coarse clock mapping.

    Returns
    -------
    tuple
        ``(windows, labels)`` where ``windows`` has shape
        ``(n_kept, config.WINDOW_SAMPLES)`` and ``labels`` is the list of key
        names.
    """
    audio_start = float(meta.get("audio_start_perf", 0.0))
    latency = float(meta.get("input_latency_s", 0.0))

    windows: list[np.ndarray] = []
    labels: list[str] = []
    for event in events:
        if event.get("type", "press") != "press":
            continue
        key = event.get("key")
        if key not in config.KEY_SET:
            continue
        approx = round((float(event["t_perf"]) - audio_start - latency) * sample_rate)
        approx = max(0, int(approx))
        onset = find_onset_near(audio, approx, sample_rate)
        if onset is None:
            continue
        windows.append(cut_window(audio, onset))
        labels.append(key)

    if not windows:
        return np.zeros((0, config.WINDOW_SAMPLES), dtype=np.float32), labels
    return np.stack(windows, axis=0).astype(np.float32), labels
