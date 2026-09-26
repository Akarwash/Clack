"""Shared pytest fixtures and synthetic data for Clack.

These fixtures let every component be built and tested against synthetic audio
and sessions without any real recordings, microphone, or trained model
(CLACK_BUILD_PLAN.md sections 5A and 11). Real training and real data collection
are the on-site human step; nothing here fabricates accuracy results.

Fixtures
--------
device
    The detected torch compute device (CUDA, else MPS, else CPU).
rng
    A seeded numpy random generator (``config.SEED``).
synthetic_audio
    A factory producing mono float32 audio with click transients at known
    onset sample indices.
tmp_session
    A factory writing a tiny synthetic recording session (``audio.wav`` +
    ``events.json``) to a temporary directory in the section 9 on-disk format.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional

import numpy as np
import pytest
import soundfile as sf

import config


@pytest.fixture
def device() -> str:
    """Return the detected torch compute device as a string.

    Returns
    -------
    str
        ``"cuda"`` if available, else ``"mps"`` if available, else ``"cpu"``.
    """
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@pytest.fixture
def rng() -> np.random.Generator:
    """Return a numpy random generator seeded from ``config.SEED``."""
    return np.random.default_rng(config.SEED)


@pytest.fixture
def synthetic_audio() -> Callable[..., tuple[np.ndarray, list[int]]]:
    """Return a factory for synthetic audio with known keystroke onsets.

    The factory signature is ``make(n_clicks=5, gap_ms=550, sample_rate=None,
    noise_std=0.001, seed=None) -> (audio, onset_samples)``. Each "click" is a
    short decaying broadband transient standing in for a key press, so onset
    detection and windowing can be tested against ground-truth positions.

    Returns
    -------
    callable
        A function producing ``(audio, onset_samples)``.
    """

    def make(
        n_clicks: int = 5,
        gap_ms: float = 550.0,
        sample_rate: Optional[int] = None,
        noise_std: float = 0.001,
        seed: Optional[int] = None,
    ) -> tuple[np.ndarray, list[int]]:
        sr = sample_rate or config.SAMPLE_RATE
        gen = np.random.default_rng(config.SEED if seed is None else seed)
        gap = int(sr * gap_ms / 1000.0)
        lead = int(sr * 0.1)
        total = lead + gap * n_clicks + int(sr * 0.1)
        audio = gen.normal(0.0, noise_std, size=total).astype(np.float32)

        click_len = int(sr * 0.01)  # 10 ms transient
        env = np.exp(-np.linspace(0.0, 8.0, click_len)).astype(np.float32)
        onsets: list[int] = []
        for i in range(n_clicks):
            start = lead + i * gap
            transient = (gen.normal(0.0, 1.0, size=click_len).astype(np.float32) * env * 0.5)
            audio[start : start + click_len] += transient
            onsets.append(start)
        peak = float(np.max(np.abs(audio))) or 1.0
        audio = (audio / peak * 0.9).astype(np.float32)
        return audio, onsets

    return make


@pytest.fixture
def tmp_session(tmp_path, synthetic_audio) -> Callable[..., str]:
    """Return a factory that writes a synthetic recording session to disk.

    The factory signature is ``make(keys=None, keyboard_id="blue",
    typist="synthetic", purpose="train", gap_ms=550) -> session_dir``. It writes
    ``audio.wav`` (mono float32 at ``config.SAMPLE_RATE``) and ``events.json`` in
    the CLACK_BUILD_PLAN.md section 9 format, with one press event per key placed
    at each synthetic onset (mapped through the documented clock relation).

    Returns
    -------
    callable
        A function returning the written session directory path.
    """

    def make(
        keys: Optional[list[str]] = None,
        keyboard_id: str = "blue",
        typist: str = "synthetic",
        purpose: str = "train",
        gap_ms: float = 550.0,
    ) -> str:
        keys = keys or ["a", "b", "c", "d", "e"]
        sr = config.SAMPLE_RATE
        audio, onsets = synthetic_audio(n_clicks=len(keys), gap_ms=gap_ms, sample_rate=sr)

        session_id = f"2026-09-26T09-30-00_{keyboard_id}_{typist}"
        session_dir = os.path.join(str(tmp_path), session_id)
        os.makedirs(session_dir, exist_ok=True)
        sf.write(os.path.join(session_dir, "audio.wav"), audio, sr, subtype="FLOAT")

        audio_start_perf = 1000.0
        input_latency_s = 0.0
        stream_time_origin = 0.0
        events = []
        for key, onset in zip(keys, onsets):
            # Inverse of the documented mapping so a reader recovers ~onset:
            # sample_index ~= round((t_perf - audio_start_perf - input_latency_s) * sr)
            t_perf = audio_start_perf + input_latency_s + onset / sr
            events.append({"key": key, "t_perf": t_perf, "type": "press"})

        meta = {
            "session_id": session_id,
            "sample_rate": sr,
            "audio_start_perf": audio_start_perf,
            "input_latency_s": input_latency_s,
            "stream_time_origin": stream_time_origin,
            "keyboard_id": keyboard_id,
            "typist": typist,
            "purpose": purpose,
            "mode": "paced",
            "events": events,
        }
        with open(os.path.join(session_dir, "events.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        return session_dir

    return make
