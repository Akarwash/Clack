"""Live streaming decode and ambient calibration (attack path).

Consumes microphone audio in real time, calibrates the onset threshold against
``config.AMBIENT_CALIB_S`` seconds of the quiet room (the venue is noisy and the
whole attack begins with onset detection, so this is not optional), detects onsets
as they arrive, cuts the identical window, classifies, and emits live top-k
guesses. In this path the keylogger is NEVER instantiated
(``config.ATTACK_DISABLES_KEYLOGGER``): recovery is provably microphone-only.

The one exception is ``event_mode=True``, a deliberately operator-enabled
clean-run that uses key-event timestamps instead of acoustic onsets; it is the
only place ``stream`` touches key events, it is off by default, and the dashboard
labels it clearly.

Owner: BUILD_BACKEND.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

import config
from clack import dataset as _dataset
from clack import segment as _segment


@dataclass
class StreamGuess:
    """One live keystroke guess emitted by the stream.

    Attributes
    ----------
    key : str
        The top-1 predicted key.
    confidence : float
        The top-1 probability.
    topk : list of tuple
        Ranked ``(key, prob)`` candidates for this press.
    onset_sample : int
        Absolute sample index of the detected onset since stream start.
    t : float
        Wall-clock (``perf_counter``) time the guess was produced.
    latency_ms : float
        End-to-end latency from onset to emitted prediction.
    """

    key: str
    confidence: float
    topk: list[tuple[str, float]]
    onset_sample: int
    t: float
    latency_ms: float = 0.0

    def as_message(self, text: str) -> dict:
        """Render the WebSocket ``key`` message for the dashboard."""
        return {
            "type": "key",
            "key": self.key,
            "confidence": round(self.confidence, 4),
            "topk": [[k, round(p, 4)] for k, p in self.topk],
            "text": text,
            "t": self.t,
            "latency_ms": round(self.latency_ms, 1),
        }


def calibrate_ambient(noise_audio: np.ndarray, sample_rate: int) -> float:
    """Set an effective onset threshold multiplier from quiet-room noise.

    Measures the ambient frame-energy distribution and returns a ``k`` large
    enough to clear the loudest observed noise frame (plus a margin), never below
    ``config.ONSET_K``.

    Parameters
    ----------
    noise_audio : numpy.ndarray
        A recording of the quiet room (about ``config.AMBIENT_CALIB_S`` seconds).
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    float
        The calibrated threshold multiplier for :func:`clack.segment.detect_onsets`.
    """
    audio = np.asarray(noise_audio, dtype=np.float32)
    if audio.size == 0:
        return float(config.ONSET_K)
    filtered = _segment._highpass(audio, sample_rate, config.ONSET_HP_CUTOFF_HZ)
    energy, _ = _segment._frame_energy(filtered, sample_rate)
    if energy.size < 2:
        return float(config.ONSET_K)
    mean = float(np.mean(energy))
    std = float(np.std(energy)) or 1e-12
    z_max = (float(np.max(energy)) - mean) / std
    return float(max(config.ONSET_K, z_max + 1.0))


def decode_window(model: object, window: np.ndarray, sample_rate: int, k: int = 5) -> tuple[str, float, list[tuple[str, float]]]:
    """Classify one onset window into a top-k guess.

    Parameters
    ----------
    model : object
        A fitted model exposing ``scores`` and ``classes``.
    window : numpy.ndarray
        A raw onset-centered window.
    sample_rate : int
        Sample rate in Hz.
    k : int, optional
        Candidates to return (default ``5``).

    Returns
    -------
    tuple
        ``(best_key, best_prob, topk)`` where ``topk`` is a ranked
        ``(key, prob)`` list.
    """
    feats = _dataset.featurize(window, sample_rate)[None, :, :]
    scores = model.scores(feats)[0]
    finite = np.where(np.isfinite(scores), scores, -np.inf)
    shifted = finite - np.max(finite)
    exp = np.exp(np.where(np.isfinite(shifted), shifted, -np.inf))
    probs = exp / (exp.sum() or 1.0)
    classes = list(getattr(model, "classes", config.KEY_SET))
    order = np.argsort(-scores)[: max(1, k)]
    topk = [(classes[int(i)], float(probs[int(i)])) for i in order]
    return topk[0][0], topk[0][1], topk


class LiveDecoder:
    """Real-time keystroke decoder over a microphone stream.

    Parameters
    ----------
    model : object
        A trained model exposing ``scores`` and ``classes``.
    on_guess : callable or None, optional
        Callback invoked with each :class:`StreamGuess`.
    device : int or None, optional
        Input device index; ``None`` uses ``config.INPUT_DEVICE``.
    event_mode : bool, optional
        If ``True``, use key-event timestamps for one clean run (the only place
        the stream touches key events); off by default.
    """

    def __init__(
        self,
        model: object,
        on_guess: Optional[Callable[[StreamGuess], None]] = None,
        device: Optional[int] = None,
        event_mode: bool = False,
    ) -> None:
        from clack.capture import StreamReader

        self.model = model
        self.on_guess = on_guess
        self.device = config.INPUT_DEVICE if device is None else device
        self.event_mode = bool(event_mode)
        self.reader = StreamReader(seconds=5.0)
        self.calibrated = False
        self.calibrated_k = float(config.ONSET_K)
        self.noise_floor = 0.0
        self.text = ""
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_onset = -(10**9)

    def calibrate_ambient(self) -> float:  # pragma: no cover - requires a real mic
        """Record ``config.AMBIENT_CALIB_S`` of the room and set the threshold."""
        time.sleep(config.AMBIENT_CALIB_S)
        noise = self.reader.read_tail(config.AMBIENT_CALIB_S)
        self.calibrated_k = calibrate_ambient(noise, self.reader.sample_rate)
        self.noise_floor = float(np.sqrt(np.mean(noise**2))) if noise.size else 0.0
        self.calibrated = True
        return self.calibrated_k

    def _callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - realtime
        mono = indata[:, 0] if indata.ndim > 1 else indata
        self.reader.push(np.asarray(mono, dtype=np.float32))

    def start(self) -> None:  # pragma: no cover - requires a real mic
        """Open the mic, calibrate, and begin the decode loop.

        Raises
        ------
        RuntimeError
            If the microphone is unavailable.
        """
        if config.ATTACK_DISABLES_KEYLOGGER and not self.event_mode:
            # Provable mic-only: no pynput listener is created in this path.
            pass
        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
                dtype=config.DTYPE,
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            raise RuntimeError(f"could not open microphone for the live attack: {exc}") from exc

        self.calibrate_ambient()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:  # pragma: no cover - realtime
        window_s = 0.4
        while self._running:
            tail = self.reader.read_tail(window_s)
            if tail.size >= config.WINDOW_SAMPLES:
                onsets = _segment.detect_onsets(tail, self.reader.sample_rate, k=self.calibrated_k)
                base = self.reader.total_pushed - tail.shape[0]
                for local in onsets:
                    absolute = base + int(local)
                    if absolute - self._last_onset < int(config.SAMPLE_RATE * config.ONSET_MIN_GAP_MS / 1000.0):
                        continue
                    self._last_onset = absolute
                    t0 = time.perf_counter()
                    window = _segment.cut_window(tail, int(local))
                    key, prob, topk = decode_window(self.model, window, self.reader.sample_rate)
                    self.text += " " if key == "space" else key
                    guess = StreamGuess(
                        key=key,
                        confidence=prob,
                        topk=topk,
                        onset_sample=absolute,
                        t=time.perf_counter(),
                        latency_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                    if self.on_guess is not None:
                        self.on_guess(guess)
            time.sleep(0.05)

    def stop(self) -> None:
        """Stop decoding and release the microphone."""
        self._running = False
        if self._stream is not None:  # pragma: no cover - requires a real mic
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread is not None:  # pragma: no cover - realtime
            self._thread.join(timeout=1.0)
            self._thread = None
