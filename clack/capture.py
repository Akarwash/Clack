"""Microphone capture and device enumeration (sounddevice).

Records raw mono audio at ``config.SAMPLE_RATE``. At the first stream callback the
recorder captures the PortAudio timing needed to map the event clock onto the
audio sample clock (``audio_start_perf``, ``input_latency_s``,
``stream_time_origin``); see CLACK_BUILD_PLAN.md section 9. The callback stays
light (it only appends frames to a queue), doing no processing inline.

OS-level audio processing (echo cancellation, noise suppression, auto gain)
should be disabled at the system level so the raw keystroke transients survive;
the demo Mac captures the raw built-in device.

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

import config


@dataclass
class DeviceInfo:
    """A selectable audio input device.

    Attributes
    ----------
    index : int
        The sounddevice device index.
    name : str
        Human-readable device name.
    channels : int
        Number of input channels the device exposes.
    default_samplerate : float
        The device's default sample rate in Hz.
    """

    index: int
    name: str
    channels: int
    default_samplerate: float

    def as_dict(self) -> dict:
        """Return a JSON-serializable dict for the device dropdown."""
        return {
            "index": self.index,
            "name": self.name,
            "channels": self.channels,
            "default_samplerate": self.default_samplerate,
        }


def list_input_devices() -> list[dict]:
    """Enumerate available audio input devices.

    Returns
    -------
    list of dict
        One dict per device with at least one input channel, each with keys
        ``index``, ``name``, ``channels``, and ``default_samplerate``.

    Raises
    ------
    RuntimeError
        If the audio backend cannot be queried.
    """
    try:
        import sounddevice as sd

        devices = sd.query_devices()
    except Exception as exc:  # pragma: no cover - depends on host audio backend
        raise RuntimeError(f"could not query audio devices: {exc}") from exc

    out: list[dict] = []
    for index, dev in enumerate(devices):
        if int(dev.get("max_input_channels", 0)) > 0:
            out.append(
                DeviceInfo(
                    index=index,
                    name=str(dev.get("name", f"device {index}")),
                    channels=int(dev["max_input_channels"]),
                    default_samplerate=float(dev.get("default_samplerate", config.SAMPLE_RATE)),
                ).as_dict()
            )
    return out


class Recorder:
    """Streaming microphone recorder writing float32 mono audio.

    Parameters
    ----------
    sr : int or None, optional
        Capture sample rate; defaults to ``config.SAMPLE_RATE``.
    device : int or None, optional
        Input device index; ``None`` uses the system default
        (``config.INPUT_DEVICE``).
    channels : int or None, optional
        Number of input channels; defaults to ``config.CHANNELS``.
    """

    def __init__(
        self,
        sr: Optional[int] = None,
        device: Optional[int] = None,
        channels: Optional[int] = None,
    ) -> None:
        self.sample_rate = int(sr or config.SAMPLE_RATE)
        self.device = config.INPUT_DEVICE if device is None else device
        self.channels = int(channels or config.CHANNELS)
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self.audio_start_perf: Optional[float] = None
        self.input_latency_s: float = 0.0
        self.stream_time_origin: Optional[float] = None
        self._first_callback = True

    def _callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - realtime
        """PortAudio callback: record timing on the first frame, then buffer."""
        if self._first_callback:
            self.audio_start_perf = time.perf_counter()
            self.stream_time_origin = getattr(time_info, "inputBufferAdcTime", 0.0)
            if self._stream is not None:
                self.input_latency_s = float(getattr(self._stream, "latency", 0.0) or 0.0)
            self._first_callback = False
        self._queue.put(indata.copy())

    def _open_stream(self) -> None:  # pragma: no cover - requires a real device
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=config.DTYPE,
            device=self.device,
            callback=self._callback,
        )
        self._first_callback = True
        self._stream.start()

    def start(self) -> None:
        """Open the input stream and begin buffering audio.

        If the first open fails, PortAudio's device list is refreshed once and the
        open retried: unplugging and replugging a USB microphone leaves PortAudio's
        cached device handles stale in a long-running process (PaErrorCode -9986),
        and a refresh recovers it without restarting the server.

        Raises
        ------
        RuntimeError
            If the input device cannot be opened even after refreshing.
        """
        try:  # pragma: no cover - requires a real device
            self._open_stream()
            return
        except Exception:
            pass
        try:  # pragma: no cover - requires a real device
            import sounddevice as sd

            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        try:  # pragma: no cover - requires a real device
            self._open_stream()
        except Exception as exc:
            raise RuntimeError(
                f"could not open input device {self.device!r}: {exc}. If you just "
                "unplugged and replugged the microphone, the refresh retry did not "
                "recover it; reseat the cable or restart the server."
            ) from exc

    def read_all(self) -> np.ndarray:
        """Drain the buffer into one float32 mono array.

        Returns
        -------
        numpy.ndarray
            The captured samples (empty if nothing was recorded). Multi-channel
            input is averaged to mono.
        """
        chunks: list[np.ndarray] = []
        while not self._queue.empty():
            chunks.append(self._queue.get())
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks, axis=0)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32, copy=False)

    def stop(self) -> None:
        """Stop and close the input stream."""
        if self._stream is not None:  # pragma: no cover - requires a real device
            self._stream.stop()
            self._stream.close()
            self._stream = None


class StreamReader:
    """A thread-safe rolling buffer of the last ``seconds`` of audio.

    Fed by a live input stream's callback (via :meth:`push`) and polled by the live
    decoder (via :meth:`read_tail`). Used by :mod:`clack.stream` for the live
    attack.

    Parameters
    ----------
    seconds : float, optional
        How much audio history to retain (default ``5.0``).
    sample_rate : int or None, optional
        Sample rate; defaults to ``config.SAMPLE_RATE``.
    """

    def __init__(self, seconds: float = 5.0, sample_rate: Optional[int] = None) -> None:
        import threading

        self.sample_rate = int(sample_rate or config.SAMPLE_RATE)
        self.capacity = int(seconds * self.sample_rate)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self.total_pushed = 0

    def push(self, frames: np.ndarray) -> None:
        """Append new frames, trimming to the retained window.

        Parameters
        ----------
        frames : numpy.ndarray
            New float32 mono samples.
        """
        chunk = np.asarray(frames, dtype=np.float32).reshape(-1)
        with self._lock:
            self._buffer = np.concatenate([self._buffer, chunk])
            if self._buffer.shape[0] > self.capacity:
                self._buffer = self._buffer[-self.capacity :]
            self.total_pushed += chunk.shape[0]

    def read_tail(self, seconds: float) -> np.ndarray:
        """Return a copy of the most recent ``seconds`` of audio.

        Parameters
        ----------
        seconds : float
            How much recent audio to return.

        Returns
        -------
        numpy.ndarray
            A float32 copy (possibly shorter than requested early on).
        """
        n = int(seconds * self.sample_rate)
        with self._lock:
            return self._buffer[-n:].copy()

    def read_all(self) -> np.ndarray:
        """Return a copy of the entire retained buffer."""
        with self._lock:
            return self._buffer.copy()
