"""Acoustic masker and before/after accuracy measurement (the payoff).

The defense is the product: Clack protects sensitive typing from acoustic
surveillance, and the attack exists to prove the threat and measure how well the
defense stops it. This module generates a band-limited masking sound plus fake
keystroke transients (so the attack's onset detector fires on phantom presses),
plays it through the default output device, and measures the recovery drop.

The guaranteed path is the Standard Shield: a continuous masker while armed, so no
identifying transient reaches the mic unmasked. A triggered "Smart Shield" is a
stretch and off by default (``config.MASKER_TRIGGERED``), because a triggered
masker can fire after the press onset has already been captured.

Owner: BUILD_DEFENSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
from scipy.signal import butter, sosfilt

import config


def generate_masker(
    duration_s: float,
    sample_rate: int,
    band_hz: Optional[tuple[int, int]] = None,
    level: Optional[float] = None,
    seed: Optional[int] = None,
    decoys: bool = True,
) -> np.ndarray:
    """Generate a band-limited masking signal with fake keystroke transients.

    Parameters
    ----------
    duration_s : float
        Length of the masker in seconds.
    sample_rate : int
        Sample rate in Hz.
    band_hz : tuple of int or None, optional
        Passband; defaults to ``config.MASKER_BAND_HZ`` (1 to 10 kHz, where laptop
        speakers are strong and keystroke energy lives).
    level : float or None, optional
        Amplitude scale; defaults to ``config.MASKER_LEVEL``.
    seed : int or None, optional
        RNG seed; defaults to ``config.SEED``.
    decoys : bool, optional
        Whether to inject fake keystroke transients (default ``True``).

    Returns
    -------
    numpy.ndarray
        Float32 masker samples in ``[-1, 1]``.
    """
    band = band_hz or config.MASKER_BAND_HZ
    amp = config.MASKER_LEVEL if level is None else float(level)
    rng = np.random.default_rng(config.SEED if seed is None else seed)

    n = max(1, int(duration_s * sample_rate))
    noise = rng.normal(0.0, 1.0, size=n).astype(np.float32)

    low, high = band
    nyq = 0.5 * sample_rate
    lo_n = max(1e-4, low / nyq)
    hi_n = min(0.999, high / nyq)
    sos = butter(4, [lo_n, hi_n], btype="bandpass", output="sos")
    filtered = sosfilt(sos, noise).astype(np.float32)

    peak = float(np.max(np.abs(filtered))) or 1.0
    masker = (filtered / peak * amp).astype(np.float32)

    if decoys:
        # Jittered fake keystroke transients (every 40 to 120 ms) so the attack's
        # onset detector fires on phantom presses.
        click_len = int(sample_rate * 0.006)
        env = np.exp(-np.linspace(0.0, 6.0, click_len)).astype(np.float32)
        pos = int(sample_rate * 0.05)
        while pos + click_len < n:
            transient = rng.normal(0.0, 1.0, size=click_len).astype(np.float32) * env * amp
            masker[pos : pos + click_len] += transient
            pos += int(sample_rate * rng.uniform(0.04, 0.12))
        masker = np.clip(masker, -1.0, 1.0)

    return masker.astype(np.float32)


def apply_masker(clean_audio: np.ndarray, masker: np.ndarray) -> np.ndarray:
    """Mix a masker into clean audio to simulate what the mic would capture.

    The masker is tiled or trimmed to the length of ``clean_audio``.

    Parameters
    ----------
    clean_audio : numpy.ndarray
        The clean recording.
    masker : numpy.ndarray
        The masking signal.

    Returns
    -------
    numpy.ndarray
        The masked (corrupted) audio, same length as ``clean_audio``.
    """
    clean = np.asarray(clean_audio, dtype=np.float32)
    m = np.asarray(masker, dtype=np.float32)
    if m.shape[0] < clean.shape[0]:
        reps = int(np.ceil(clean.shape[0] / m.shape[0]))
        m = np.tile(m, reps)
    m = m[: clean.shape[0]]
    return (clean + m).astype(np.float32)


def measure_keyboard_band(sample_audio: np.ndarray, sample_rate: int) -> tuple[int, int]:
    """Find the dominant keystroke energy band to tune the masker (D2).

    Parameters
    ----------
    sample_audio : numpy.ndarray
        A short recording of the keyboard.
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    tuple of int
        ``(low_hz, high_hz)`` covering the central mass of keystroke energy.
    """
    audio = np.asarray(sample_audio, dtype=np.float32)
    if audio.size == 0:
        return config.MASKER_BAND_HZ

    spectrum = np.abs(np.fft.rfft(audio)) ** 2
    freqs = np.fft.rfftfreq(audio.shape[0], d=1.0 / sample_rate)
    # Ignore low-frequency rumble below 300 Hz.
    mask = freqs >= 300
    spectrum = spectrum[mask]
    freqs = freqs[mask]
    if spectrum.sum() <= 0:
        return config.MASKER_BAND_HZ

    cumulative = np.cumsum(spectrum) / spectrum.sum()
    low = int(freqs[np.searchsorted(cumulative, 0.10)])
    high = int(freqs[min(len(freqs) - 1, np.searchsorted(cumulative, 0.90))])
    if high <= low:
        high = low + 1000
    return (low, high)


class Masker:
    """Standard Shield: a continuous band-limited masker while armed.

    The masker buffer is generated once and looped through a background output
    stream. The output stream is created by an injectable factory so the on/off
    state machine can be exercised without real audio hardware.

    Parameters
    ----------
    sample_rate : int or None, optional
        Output sample rate; defaults to ``config.SAMPLE_RATE``.
    band_hz : tuple of int or None, optional
        Masker passband; defaults to ``config.MASKER_BAND_HZ``.
    level : float or None, optional
        Masker level; defaults to ``config.MASKER_LEVEL``.
    stream_factory : callable or None, optional
        ``callback -> stream`` factory; defaults to a sounddevice OutputStream.
        Injected in tests to avoid opening real hardware.
    """

    def __init__(
        self,
        sample_rate: Optional[int] = None,
        band_hz: Optional[tuple[int, int]] = None,
        level: Optional[float] = None,
        stream_factory: Optional[Callable] = None,
    ) -> None:
        self.sample_rate = int(sample_rate or config.SAMPLE_RATE)
        self.band = band_hz or config.MASKER_BAND_HZ
        self.level = config.MASKER_LEVEL if level is None else float(level)
        self.triggered = config.MASKER_TRIGGERED
        self._stream_factory = stream_factory
        self._stream = None
        self._on = False
        self._buffer = self._make_buffer()
        self._pos = 0

    def _make_buffer(self) -> np.ndarray:
        return generate_masker(2.0, self.sample_rate, self.band, self.level)

    def _callback(self, outdata, frames, time_info, status) -> None:  # pragma: no cover - realtime
        buf = self._buffer
        idx = (self._pos + np.arange(frames)) % buf.shape[0]
        outdata[:, 0] = buf[idx]
        self._pos = int((self._pos + frames) % buf.shape[0])

    def _default_stream_factory(self, callback):  # pragma: no cover - requires a device
        import sounddevice as sd

        return sd.OutputStream(
            samplerate=self.sample_rate, channels=1, dtype=config.DTYPE, callback=callback
        )

    def start(self) -> None:
        """Begin playing the masker (continuous while armed)."""
        if self._on:
            return
        factory = self._stream_factory or self._default_stream_factory
        self._stream = factory(self._callback)
        if hasattr(self._stream, "start"):
            self._stream.start()
        self._on = True

    def stop(self) -> None:
        """Stop playing the masker."""
        if self._stream is not None:
            if hasattr(self._stream, "stop"):
                self._stream.stop()
            if hasattr(self._stream, "close"):
                self._stream.close()
            self._stream = None
        self._on = False

    def is_on(self) -> bool:
        """Return whether the masker is currently playing."""
        return self._on

    def set_level(self, value: float) -> None:
        """Set the masker level and regenerate the buffer."""
        self.level = float(value)
        self._buffer = self._make_buffer()

    def set_band(self, low: int, high: int) -> None:
        """Set the masker passband and regenerate the buffer."""
        self.band = (int(low), int(high))
        self._buffer = self._make_buffer()

    def set_trigger(self, enabled: bool) -> None:
        """Enable or disable Smart Shield triggering (stretch; default off)."""
        self.triggered = bool(enabled)


@dataclass
class MaskerResult:
    """A minimum-effective masker search outcome.

    Attributes
    ----------
    level : float
        The chosen masking level (lowest that meets the target).
    recovery : float
        Attack recovery achieved at that level.
    sweep : dict
        Recovery measured at each swept level.
    target : float
        The target recovery ceiling used.
    """

    level: float
    recovery: float
    sweep: dict
    target: float = field(default=0.0)


def measure(
    model: object,
    clean_audio: np.ndarray,
    true_keys: list[str],
    sample_rate: Optional[int] = None,
    level: Optional[float] = None,
    band_hz: Optional[tuple[int, int]] = None,
    true_samples: Optional[list[int]] = None,
) -> dict:
    """The honest before/after: recovery with the masker off vs on, same text.

    Uses :func:`clack.evaluate.evaluate_defense` for the actual metrics, so the
    numbers match everywhere. The same fixed ``true_keys`` (from a non-training
    session) are used both times.

    Parameters
    ----------
    model : object
        A fitted attack model.
    clean_audio : numpy.ndarray
        The clean recording of the fixed text (defense off).
    true_keys : list of str
        Ground-truth keys for that recording.
    sample_rate : int or None, optional
        Sample rate; defaults to ``config.SAMPLE_RATE``.
    level : float or None, optional
        Masker level; defaults to ``config.MASKER_LEVEL``.
    band_hz : tuple of int or None, optional
        Masker band; defaults to ``config.MASKER_BAND_HZ``.
    true_samples : list of int or None, optional
        Ground-truth onset sample positions; passed through so recovery is scored
        with onset alignment (see :func:`clack.evaluate.evaluate_defense`).

    Returns
    -------
    dict
        ``{off, on, delta, masker_key_ratio_db, cer_off, cer_on, level}``.
    """
    from clack import evaluate as _evaluate

    sr = int(sample_rate or config.SAMPLE_RATE)
    masker = generate_masker(len(clean_audio) / sr, sr, band_hz=band_hz, level=level)
    masked = apply_masker(clean_audio, masker)
    result = _evaluate.evaluate_defense(
        model, clean_audio, masked, sr, true_keys=true_keys, true_samples=true_samples
    )
    result["level"] = config.MASKER_LEVEL if level is None else float(level)
    return result


def measure_session(
    model: object,
    session_dir: str,
    level: Optional[float] = None,
    band_hz: Optional[tuple[int, int]] = None,
    auto_band: bool = True,
) -> dict:
    """Before/after defense measurement for a recorded session (backend entry).

    Reads the session's audio and ground-truth events, generates the masker
    (auto-tuned to the keyboard band by default), simulates the masked capture,
    and returns the onset-aligned recovery off vs on. This is the software path
    used by the ``/defense/measure`` endpoint so the defense result is
    reproducible without a live speaker-and-mic loop.

    Parameters
    ----------
    model : object
        A fitted attack model.
    session_dir : str
        A ``data/recordings/<id>/`` directory with ``audio.wav`` and
        ``events.json``.
    level : float or None, optional
        Masker level; defaults to ``config.MASKER_LEVEL``.
    band_hz : tuple of int or None, optional
        Masker band; overrides ``auto_band`` when given.
    auto_band : bool, optional
        Tune the masker band to the recording's measured keystroke band
        (default ``True``).

    Returns
    -------
    dict
        The :func:`measure` result plus ``band`` and ``n_keys``.
    """
    import json
    import os

    import soundfile as sf

    from clack import evaluate as _evaluate

    wav = os.path.join(session_dir, "audio.wav")
    events = os.path.join(session_dir, "events.json")
    if not os.path.isfile(wav) or not os.path.isfile(events):
        raise FileNotFoundError(f"session missing audio.wav or events.json: {session_dir}")
    audio, sr = sf.read(wav, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    with open(events, encoding="utf-8") as fh:
        meta = json.load(fh)
    true_samples, true_keys = _evaluate._true_samples_and_keys(meta, int(sr))

    band = band_hz
    if band is None and auto_band:
        band = measure_keyboard_band(audio[: int(sr) * 5], int(sr))

    result = measure(
        model, audio, true_keys, sample_rate=int(sr), level=level,
        band_hz=band, true_samples=true_samples,
    )
    result["band"] = list(band) if band else list(config.MASKER_BAND_HZ)
    result["n_keys"] = len(true_keys)
    return result


def find_min_effective_level(
    model: object,
    clean_audio: np.ndarray,
    sample_rate: Optional[int] = None,
    true_keys: Optional[list[str]] = None,
    target_recovery: Optional[float] = None,
    measure_fn: Optional[Callable[[float], float]] = None,
) -> MaskerResult:
    """Sweep masking levels for the lowest that hits the target recovery (D2).

    Parameters
    ----------
    model : object
        The trained attack model.
    clean_audio : numpy.ndarray
        Clean audio of the fixed text.
    sample_rate : int or None, optional
        Sample rate; defaults to ``config.SAMPLE_RATE``.
    true_keys : list of str or None, optional
        Ground-truth keys (used by the real measurement).
    target_recovery : float or None, optional
        Recovery ceiling; defaults to ``config.MASKER_TARGET_RECOVERY``.
    measure_fn : callable or None, optional
        ``level -> recovery`` override for testing against a synthetic recovery
        curve; when ``None`` the real attack-based measurement is used.

    Returns
    -------
    MaskerResult
        The lowest level meeting the target (or the strongest swept level if none
        does), its recovery, and the full sweep.
    """
    target = config.MASKER_TARGET_RECOVERY if target_recovery is None else float(target_recovery)
    sr = int(sample_rate or config.SAMPLE_RATE)

    def _real_measure(level: float) -> float:
        out = measure(model, clean_audio, true_keys or [], sample_rate=sr, level=level)
        on = out.get("on")
        return float(on) if on is not None else 1.0

    measurer = measure_fn or _real_measure
    sweep: dict[float, float] = {}
    chosen_level = config.MASKER_LEVEL_STEPS[-1]
    chosen_recovery = 1.0
    found = False
    for lvl in config.MASKER_LEVEL_STEPS:
        recovery = float(measurer(lvl))
        sweep[lvl] = recovery
        if not found and recovery <= target:
            chosen_level = lvl
            chosen_recovery = recovery
            found = True
    if not found:
        # None met the target: report the strongest level and its recovery.
        chosen_level = config.MASKER_LEVEL_STEPS[-1]
        chosen_recovery = sweep[chosen_level]
    return MaskerResult(level=chosen_level, recovery=chosen_recovery, sweep=sweep, target=target)
