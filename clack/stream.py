"""Live streaming decode and ambient calibration (attack path).

Consumes microphone audio in real time, calibrates the onset threshold against
``config.AMBIENT_CALIB_S`` seconds of the quiet room, detects onsets as they
arrive, cuts windows, classifies, and emits live top-k guesses over the attack
WebSocket. In this path the keylogger is NEVER instantiated
(``config.ATTACK_DISABLES_KEYLOGGER``): recovery is provably microphone-only.

Owner: BUILD_BACKEND.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class StreamGuess:
    """One live keystroke guess emitted by the stream.

    Attributes
    ----------
    topk : list of str
        Ranked candidate keys for this press.
    onset_sample : int
        Sample index of the detected onset (relative to stream start).
    t_perf : float
        Wall-clock time the guess was produced.
    """

    topk: list[str]
    onset_sample: int
    t_perf: float


class LiveDecoder:
    """Real-time keystroke decoder over a microphone stream.

    Parameters
    ----------
    model : object
        A trained model exposing ``predict_topk``.
    on_guess : callable or None, optional
        Callback invoked with each :class:`StreamGuess`.
    device : int or None, optional
        Input device index; ``None`` uses the system default.
    """

    def __init__(self, model: object, on_guess: Optional[Callable[[StreamGuess], None]] = None, device: Optional[int] = None) -> None:
        raise NotImplementedError("built in BUILD_BACKEND")

    def calibrate_ambient(self) -> float:
        """Measure the ambient noise floor to set the onset threshold.

        Returns
        -------
        float
            The calibrated onset threshold multiplier.

        Raises
        ------
        RuntimeError
            If the microphone is unavailable.
        """
        raise NotImplementedError("built in BUILD_BACKEND")

    def start(self) -> None:
        """Begin live decoding.

        Raises
        ------
        RuntimeError
            If capture cannot be started.
        """
        raise NotImplementedError("built in BUILD_BACKEND")

    def stop(self) -> None:
        """Stop live decoding and release the microphone."""
        raise NotImplementedError("built in BUILD_BACKEND")
