"""Microphone capture and device enumeration (sounddevice).

Records raw mono audio at ``config.SAMPLE_RATE`` with OS processing (echo
cancellation, noise suppression, auto gain) off, and records the PortAudio
stream timing needed to map the event clock onto the audio sample clock (see
CLACK_BUILD_PLAN.md section 9).

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioDevice:
    """A selectable input device.

    Attributes
    ----------
    index : int
        The sounddevice device index.
    name : str
        Human-readable device name.
    max_input_channels : int
        Number of input channels the device exposes.
    default_samplerate : float
        The device's default sample rate in Hz.
    """

    index: int
    name: str
    max_input_channels: int
    default_samplerate: float


def list_input_devices() -> list[AudioDevice]:
    """Enumerate available audio input devices.

    Returns
    -------
    list of AudioDevice
        Every device with at least one input channel.

    Raises
    ------
    RuntimeError
        If the audio backend cannot be queried.
    """
    raise NotImplementedError("built in BUILD_TRAINER")


class Recorder:
    """Streaming microphone recorder writing float32 mono audio.

    Parameters
    ----------
    sample_rate : int, optional
        Capture sample rate; defaults to ``config.SAMPLE_RATE``.
    device : int or None, optional
        Input device index; ``None`` uses the system default.
    """

    def __init__(self, sample_rate: Optional[int] = None, device: Optional[int] = None) -> None:
        raise NotImplementedError("built in BUILD_TRAINER")

    def start(self) -> None:
        """Open the stream and begin buffering audio.

        Raises
        ------
        RuntimeError
            If no input device is available or permission is denied.
        """
        raise NotImplementedError("built in BUILD_TRAINER")

    def stop(self) -> "object":
        """Stop the stream and return the captured audio and stream timing.

        Returns
        -------
        object
            The recorded samples plus stream-timing metadata.
        """
        raise NotImplementedError("built in BUILD_TRAINER")
