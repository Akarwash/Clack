"""Digital noise and decoys sent only to a validated BlackHole route.

No suppression, recordings, keyboard listener, inference, or raw-input fallback.
"""
from __future__ import annotations
import queue
import threading
import time
from typing import Callable

import numpy as np
from scipy.signal import butter, sosfilt

import config
from clack.core_audio import CoreAudio, validate_bridge


def discover_devices() -> dict:
    """Discover routes without opening streams or changing system settings."""
    try:
        devices = CoreAudio().devices()
        routes = []
        for d in devices:
            if d.get("members") is not None:
                try:
                    routes.append({**validate_bridge(d["name"], devices), "ready": True})
                except ValueError as exc:
                    if d["name"] == config.VIRTUAL_MIC_BRIDGE:
                        routes.append({"bridge_device": d["name"], "ready": False, "detail": str(exc)})
        return {"available": any(r["ready"] for r in routes), "blackhole_installed": any(d["name"] == "BlackHole 2ch" for d in devices), "routes": routes}
    except (RuntimeError, OSError) as exc:
        return {"available": False, "blackhole_installed": False, "routes": [], "detail": str(exc)}


class MaskingGenerator:
    """Non-repeating band-limited noise with cross-block filter/click state."""
    def __init__(self, seed: int | None = None) -> None:
        self.rng = np.random.default_rng(seed)
        self.sr = config.SAMPLE_RATE
        self.sos = butter(4, config.MASKER_BAND_HZ, btype="bandpass", fs=self.sr, output="sos")
        self.zi = np.zeros((len(self.sos), 2))
        self.envelope = np.exp(-np.linspace(0, 6, int(self.sr * .006))).astype(np.float32)
        self.position = 0
        self.next_click = int(self.sr * .05)
        self.tail = np.empty(0, dtype=np.float32)

    def block(self, frames: int) -> np.ndarray:
        """Generate a unit-level block; seeded generation is for tests only."""
        noise, self.zi = sosfilt(self.sos, self.rng.normal(size=frames), zi=self.zi)
        result = (noise * .25).astype(np.float32)
        n = min(frames, len(self.tail))
        result[:n] += self.tail[:n]
        self.tail = self.tail[n:]
        while self.next_click < self.position + frames:
            start = self.next_click - self.position
            click = (self.rng.normal(size=len(self.envelope)) * self.envelope * .5).astype(np.float32)
            take = min(len(click), frames - start)
            result[start:start + take] += click[:take]
            if take < len(click):
                self.tail = click[take:]
            self.next_click += int(self.sr * self.rng.uniform(.04, .12))
        self.position += frames
        np.clip(result, -1, 1, out=result)
        return result


class VirtualMic:
    """Full-duplex bridge with fail-closed output and a background watchdog."""
    def __init__(self, stream_factory: Callable | None = None, validator: Callable | None = None) -> None:
        self._stream_factory = stream_factory
        self._validator = validator or (lambda name: validate_bridge(name, CoreAudio().devices()))
        self._stream = None
        self._stop = threading.Event()
        self._blocks: queue.Queue = queue.Queue(maxsize=32)
        self._thread = None
        self._worker_error = None
        self._control = threading.RLock()
        self.running = False
        self.error = None
        self.route: dict = {}
        self.level = config.MASKER_LEVEL
        self.frames = config.VIRTUAL_MIC_BLOCKSIZE
        self.last_callback = 0.0
        self.input_rms = self.output_rms = 0.0
        self.clipped_samples = self.total_samples = self.stream_errors = 0
        self.latency_ms = None
        self._last_route_check = 0.0
        self._scratch = np.empty(self.frames, dtype=np.float32)
        self._meter = np.empty(self.frames, dtype=np.float32)

    def set_level(self, level: float) -> None:
        """Set amplitude in [0.1, 1]; clean-microphone bypass is not supported."""
        value = float(level)
        if not np.isfinite(value) or not .1 <= value <= 1.0:
            raise ValueError("Masking level must be between 0.1 and 1.0")
        self.level = value

    def _produce(self) -> None:
        try:
            generator = MaskingGenerator()
            while not self._stop.is_set() and not self._worker_error:
                block = generator.block(self.frames)
                while not self._stop.is_set() and not self._worker_error:
                    try:
                        self._blocks.put(block, timeout=.05)
                        break
                    except queue.Full:
                        self._check_health()
                self._check_health()
        except Exception as exc:
            self._worker_error = f"Masking worker failed: {exc}"
        if self._worker_error and not self._stop.is_set():
            self.error = self._worker_error
            self.running = False
            self._stop.set()
            stream = self._stream
            if stream is not None:
                try:
                    stream.abort()
                finally:
                    stream.close()
                    if self._stream is stream:
                        self._stream = None

    def _check_health(self) -> None:
        """Detect device loss even if an aggregate keeps delivering silent input."""
        if not self.running:
            return
        now = time.monotonic()
        if self.last_callback and now - self.last_callback > 1:
            self._worker_error = "Audio callbacks stalled; bridge stopped"
        elif now - self._last_route_check > 1:
            self._last_route_check = now
            try:
                if self._validator(self.route["bridge_device"]) != self.route:
                    self._worker_error = "Audio routing changed; bridge stopped"
            except (ValueError, RuntimeError, OSError) as exc:
                self._worker_error = f"Audio device disconnected or routing invalid: {exc}"

    def _callback(self, indata, outdata, frames, time_info, status) -> None:
        outdata.fill(0)
        if self._stop.is_set() or self.error:
            return
        self.last_callback = time.monotonic()
        if status or frames != self.frames or not np.isfinite(indata[:, 0]).all():
            self.stream_errors += 1
            self.error = self._worker_error = "Audio stream error; output muted"
            return
        try:
            mask = self._blocks.get_nowait()
        except queue.Empty:
            self.error = self._worker_error = "Masking buffer exhausted; output muted"
            return
        mono = self._scratch
        np.multiply(indata[:, 0], config.VIRTUAL_MIC_GAIN, out=mono)
        np.multiply(mask, self.level, out=outdata[:, 0])
        np.add(mono, outdata[:, 0], out=mono)
        np.abs(mono, out=self._meter)
        self.clipped_samples += int(np.count_nonzero(self._meter > .98))
        self.total_samples += frames
        np.square(indata[:, 0], out=self._meter)
        self.input_rms = float(np.sqrt(np.mean(self._meter)))
        np.clip(mono, -.98, .98, out=outdata[:, 0])
        outdata[:, 1] = outdata[:, 0]
        np.square(outdata[:, 0], out=self._meter)
        self.output_rms = float(np.sqrt(np.mean(self._meter)))

    def start(self, bridge_device: str = config.VIRTUAL_MIC_BRIDGE, level: float = config.MASKER_LEVEL) -> dict:
        """Validate the route and prefill noise before opening the audio stream."""
        with self._control:
            if self.running:
                if bridge_device != self.route.get("bridge_device"):
                    raise ValueError("Stop the virtual mic before changing its device")
                self.set_level(level)
                return self.status()
            self.stop()
            self.set_level(level)
            self.route = self._validator(bridge_device)
            self.error = self._worker_error = None
            self._stop.clear()
            self.last_callback = 0
            self._last_route_check = time.monotonic()
            self.clipped_samples = self.total_samples = self.stream_errors = 0
            self._blocks = queue.Queue(maxsize=32)
            self._thread = threading.Thread(target=self._produce, daemon=True, name="clack-virtual-mic")
            self._thread.start()
            deadline = time.monotonic() + 2
            while self._blocks.qsize() < 8 and not self._worker_error and time.monotonic() < deadline:
                time.sleep(.005)
            try:
                if self._blocks.qsize() < 8:
                    raise RuntimeError(self._worker_error or "Could not prepare masking buffers")
                if self._stream_factory is None:
                    import sounddevice as sd
                    matches = [i for i, d in enumerate(sd.query_devices()) if d["name"] == bridge_device]
                    if len(matches) != 1:
                        raise RuntimeError("Aggregate unavailable in PortAudio; restart Clack after setup")
                    self._stream = sd.Stream(device=matches[0], channels=(1, 2), samplerate=config.SAMPLE_RATE,
                                             blocksize=self.frames, latency="low", dtype="float32", callback=self._callback)
                else:
                    self._stream = self._stream_factory(self._callback)
                self._stream.start()
                if self.error:
                    raise RuntimeError(self.error)
                self.running = True
                self.last_callback = time.monotonic()
                self.latency_ms = round(sum(getattr(self._stream, "latency", (0, 0))) * 1000, 2)
            except Exception as exc:
                self.error = str(exc)
                self.stop()
                raise RuntimeError(f"Could not start protected virtual mic: {exc}") from exc
            return self.status()

    def stop(self) -> None:
        """Release the stream; stopped output is silence, never clean audio."""
        with self._control:
            self.running = False
            self._stop.set()
            if self._stream is not None:
                try:
                    self._stream.abort()
                finally:
                    self._stream.close()
                    self._stream = None
            if self._thread is not None and self._thread is not threading.current_thread():
                self._thread.join(timeout=1)
            self._thread = None
            self.input_rms = self.output_rms = 0.0

    def status(self) -> dict:
        """Report health without claiming an external app selected this route."""
        if self.error and self._stream is not None:
            self.stop()
        if self.running and self.last_callback and time.monotonic() - self.last_callback > 1:
            self.error = "Audio callbacks stalled; bridge stopped"
            self.stop()
        return {"ok": self.error is None, "running": self.running, "error": self.error, **self.route,
                "level": self.level, "band": list(config.MASKER_BAND_HZ), "input_rms": self.input_rms,
                "output_rms": self.output_rms, "latency_ms": self.latency_ms,
                "limited_fraction": self.clipped_samples / max(1, self.total_samples), "stream_errors": self.stream_errors,
                "output_when_stopped": "silence", "processing": "noise + fake clicks (not suppression)"}
