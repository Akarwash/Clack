"""Tests for :mod:`clack.session` (session lifecycle and on-disk contract).

Owner: BUILD_TRAINER. Runs a short synthetic session with injected fake
recorder/keylogger (no microphone), then asserts the written ``events.json``
matches the schema, timestamps are monotonic, and the event-to-sample alignment
is within tolerance of the injected onset positions.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

import config
from clack import session


class _FakeRecorder:
    """A recorder returning pre-baked audio and stream-timing fields."""

    def __init__(self, audio: np.ndarray, audio_start_perf: float) -> None:
        self._audio = np.asarray(audio, dtype=np.float32)
        self.sample_rate = config.SAMPLE_RATE
        self.audio_start_perf = audio_start_perf
        self.input_latency_s = 0.012
        self.stream_time_origin = 8402.101
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def read_all(self) -> np.ndarray:
        return self._audio


class _FakeKeyLogger:
    """A key logger returning pre-baked events."""

    def __init__(self, events: list[dict]) -> None:
        self._events = events
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> list[dict]:
        return list(self._events)


def _build_events(onsets, audio_start_perf, sample_rate, keys):
    """Build press events whose t_perf maps back to each onset sample index."""
    events = []
    for key, onset in zip(keys, onsets):
        t_perf = audio_start_perf + 0.012 + onset / sample_rate
        events.append({"key": key, "t_perf": t_perf, "type": "press"})
    return events


def test_synthetic_session_roundtrip(tmp_path, synthetic_audio) -> None:
    """A synthetic session writes valid files with aligned, monotonic events."""
    keys = ["a", "b", "c", "d", "e"]
    audio, onsets = synthetic_audio(n_clicks=len(keys), gap_ms=550)
    audio_start_perf = 1000.0
    events = _build_events(onsets, audio_start_perf, config.SAMPLE_RATE, keys)

    sid = session.start_session(
        keyboard_id="blue",
        typist="synthetic",
        purpose="train",
        mode="paced",
        recorder=_FakeRecorder(audio, audio_start_perf),
        keylogger=_FakeKeyLogger(events),
        root=str(tmp_path),
    )
    assert sid in session.active_sessions()

    summary = session.stop_session(sid)
    assert sid not in session.active_sessions()
    assert summary["n_events"] == len(keys)
    assert summary["duration_s"] > 0

    session_dir = summary["path"]
    assert os.path.isfile(os.path.join(session_dir, "audio.wav"))
    with open(os.path.join(session_dir, "events.json"), encoding="utf-8") as fh:
        meta = json.load(fh)

    # Schema
    for field in (
        "session_id",
        "sample_rate",
        "audio_start_perf",
        "input_latency_s",
        "stream_time_origin",
        "keyboard_id",
        "typist",
        "purpose",
        "mode",
        "events",
    ):
        assert field in meta
    assert meta["sample_rate"] == config.SAMPLE_RATE
    assert meta["keyboard_id"] == "blue"
    assert meta["purpose"] == "train"
    assert all(e["type"] == "press" for e in meta["events"])
    assert all(e["key"] in config.KEY_SET for e in meta["events"])

    # Monotonic timestamps
    times = [e["t_perf"] for e in meta["events"]]
    assert times == sorted(times)

    # Alignment within tolerance of the injected onsets (coarse map; onset snap
    # in BUILD_MODEL finishes it, so a few samples of slack is expected).
    tol = 2
    for event, onset in zip(meta["events"], onsets):
        idx = session.event_to_sample_index(event["t_perf"], meta)
        assert abs(idx - onset) <= tol


def test_stop_empty_audio_fails_loudly(tmp_path) -> None:
    """A session that captured no audio raises rather than writing empty data."""
    sid = session.start_session(
        keyboard_id="blue",
        typist="synthetic",
        purpose="eval",
        recorder=_FakeRecorder(np.zeros(0, dtype=np.float32), 1000.0),
        keylogger=_FakeKeyLogger([]),
        root=str(tmp_path),
    )
    with pytest.raises(RuntimeError):
        session.stop_session(sid)


def test_invalid_purpose_rejected(tmp_path) -> None:
    """An unknown purpose is rejected up front."""
    with pytest.raises(ValueError):
        session.start_session(
            keyboard_id="blue",
            typist="x",
            purpose="not-a-purpose",
            recorder=_FakeRecorder(np.ones(10, dtype=np.float32), 0.0),
            keylogger=_FakeKeyLogger([]),
            root=str(tmp_path),
        )


def test_unknown_session_stop_raises() -> None:
    """Stopping an unknown session id raises KeyError."""
    with pytest.raises(KeyError):
        session.stop_session("does-not-exist")


def test_session_level_reports_health(tmp_path, synthetic_audio) -> None:
    """session_level reports active state, and False for an unknown session."""
    assert session.session_level("nope") == {"active": False}
    audio, onsets = synthetic_audio(n_clicks=3)
    rec = _FakeRecorder(audio, 1000.0)
    rec.level_status = lambda: {"rms": 0.01, "silent_s": 0.05, "alive": True}
    sid = session.start_session(
        keyboard_id="blue", typist="t", purpose="train",
        recorder=rec, keylogger=_FakeKeyLogger([]), root=str(tmp_path),
    )
    lvl = session.session_level(sid)
    assert lvl["active"] is True and lvl["alive"] is True
    session.stop_session(sid)


def test_truncated_audio_warns(tmp_path) -> None:
    """A recording far shorter than the keypress span is flagged as truncated."""
    sr = config.SAMPLE_RATE
    audio_start = 1000.0
    short_audio = np.ones(sr // 2, dtype=np.float32)  # 0.5s of audio
    # Keypresses span ~20s (audio should be ~20s but is only 0.5s).
    events = [
        {"key": "a", "t_perf": audio_start + 0.1, "type": "press"},
        {"key": "b", "t_perf": audio_start + 10.0, "type": "press"},
        {"key": "c", "t_perf": audio_start + 20.0, "type": "press"},
    ]
    sid = session.start_session(
        keyboard_id="blue",
        typist="synthetic",
        purpose="eval",
        recorder=_FakeRecorder(short_audio, audio_start),
        keylogger=_FakeKeyLogger(events),
        root=str(tmp_path),
    )
    summary = session.stop_session(sid)
    assert "warning" in summary
    assert "TRUNCATED" in summary["warning"]
    assert summary["expected_duration_s"] > 15


def test_drops_keys_outside_key_set(tmp_path, synthetic_audio) -> None:
    """Events for keys outside KEY_SET are dropped at write time."""
    audio, onsets = synthetic_audio(n_clicks=3, gap_ms=550)
    events = [
        {"key": "a", "t_perf": 1000.1, "type": "press"},
        {"key": "ctrl", "t_perf": 1000.2, "type": "press"},  # not in KEY_SET
        {"key": "space", "t_perf": 1000.3, "type": "press"},
    ]
    sid = session.start_session(
        keyboard_id="c3equalz",
        typist="synthetic",
        purpose="demo",
        recorder=_FakeRecorder(audio, 1000.0),
        keylogger=_FakeKeyLogger(events),
        root=str(tmp_path),
    )
    summary = session.stop_session(sid)
    assert summary["n_events"] == 2  # ctrl dropped
