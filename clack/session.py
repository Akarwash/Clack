"""Collection session lifecycle: start/stop, write ``audio.wav`` + ``events.json``.

A session ties one microphone recording to one stream of key events on a single
``time.perf_counter()`` clock and persists them to
``data/recordings/<session_id>/`` in the on-disk contract from
CLACK_BUILD_PLAN.md section 9. The :class:`clack.capture.Recorder` and
:class:`clack.keylog.KeyLogger` are injectable so a session can be exercised with
synthetic data in tests (no microphone required).

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Optional

import numpy as np
import soundfile as sf

import config
from clack.capture import Recorder
from clack.keylog import KeyLogger, check_permission

VALID_PURPOSES = ("train", "eval", "demo")

# Registry of active sessions, keyed by session_id.
_ACTIVE: dict[str, dict] = {}


def _make_session_id(keyboard_id: str, typist: str, purpose: str) -> str:
    """Build a filesystem-safe session id ``<iso>_<keyboard>_<typist>_<purpose>``."""
    stamp = _dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    safe = lambda s: "".join(c if c.isalnum() else "-" for c in str(s))
    return f"{stamp}_{safe(keyboard_id)}_{safe(typist)}_{safe(purpose)}"


def start_session(
    keyboard_id: str,
    typist: str,
    purpose: str = "train",
    mode: str = "paced",
    recorder: Optional[Recorder] = None,
    keylogger: Optional[KeyLogger] = None,
    root: Optional[str] = None,
) -> str:
    """Start a collection session and return its id.

    Parameters
    ----------
    keyboard_id : str
        Physical keyboard identifier, for example ``"blue"`` or ``"c3equalz"``.
    typist : str
        Consenting typist identifier.
    purpose : str, optional
        One of ``train``, ``eval``, or ``demo`` (default ``train``).
    mode : str, optional
        Collection cadence, for example ``"paced"`` or ``"flow"`` (default
        ``"paced"``).
    recorder : clack.capture.Recorder or None, optional
        Injected recorder; a real :class:`Recorder` is created when ``None``.
    keylogger : clack.keylog.KeyLogger or None, optional
        Injected key logger; a real :class:`KeyLogger` is created when ``None``
        (which first calls :func:`clack.keylog.check_permission`).
    root : str or None, optional
        Recordings root; defaults to ``config.RECORDINGS_DIR``.

    Returns
    -------
    str
        The new session id.

    Raises
    ------
    ValueError
        If ``purpose`` is not one of the valid purposes.
    RuntimeError
        If a session is already active on the shared device.
    """
    if purpose not in VALID_PURPOSES:
        raise ValueError(f"purpose must be one of {VALID_PURPOSES}, got {purpose!r}")

    creating_real_device = recorder is None or keylogger is None
    if creating_real_device and _ACTIVE:
        raise RuntimeError(
            "a collection session is already active on this device; stop it "
            f"before starting another (active: {sorted(_ACTIVE)})"
        )

    if recorder is None:
        recorder = Recorder()
    if keylogger is None:
        check_permission()
        keylogger = KeyLogger()

    session_id = _make_session_id(keyboard_id, typist, purpose)
    recorder.start()
    keylogger.start()
    _ACTIVE[session_id] = {
        "recorder": recorder,
        "keylogger": keylogger,
        "keyboard_id": keyboard_id,
        "typist": typist,
        "purpose": purpose,
        "mode": mode,
        "root": root or config.RECORDINGS_DIR,
    }
    return session_id


def stop_session(session_id: str) -> dict:
    """Stop a session, write its files, and return a summary.

    Parameters
    ----------
    session_id : str
        The id returned by :func:`start_session`.

    Returns
    -------
    dict
        ``{session_id, n_events, duration_s, path}``.

    Raises
    ------
    KeyError
        If ``session_id`` is not an active session.
    RuntimeError
        If no audio was captured (fail loudly, never write an empty session).
    """
    if session_id not in _ACTIVE:
        raise KeyError(f"unknown session_id: {session_id!r}")

    state = _ACTIVE.pop(session_id)
    recorder: Recorder = state["recorder"]
    keylogger: KeyLogger = state["keylogger"]

    events = keylogger.stop()
    recorder.stop()
    audio = recorder.read_all()

    if audio is None or len(audio) == 0:
        raise RuntimeError(
            f"session {session_id!r} captured no audio; check the microphone and "
            "input device, then retry (never writing an empty session)"
        )

    sample_rate = int(getattr(recorder, "sample_rate", config.SAMPLE_RATE))
    kept = [
        {"key": e["key"], "t_perf": float(e["t_perf"]), "type": "press"}
        for e in events
        if e.get("type", "press") == "press" and e.get("key") in config.KEY_SET
    ]

    session_dir = os.path.join(state["root"], session_id)
    os.makedirs(session_dir, exist_ok=True)
    sf.write(
        os.path.join(session_dir, "audio.wav"),
        np.asarray(audio, dtype=np.float32),
        sample_rate,
        subtype="FLOAT",
    )

    meta = {
        "session_id": session_id,
        "sample_rate": sample_rate,
        "audio_start_perf": float(getattr(recorder, "audio_start_perf", 0.0) or 0.0),
        "input_latency_s": float(getattr(recorder, "input_latency_s", 0.0) or 0.0),
        "stream_time_origin": float(getattr(recorder, "stream_time_origin", 0.0) or 0.0),
        "keyboard_id": state["keyboard_id"],
        "typist": state["typist"],
        "purpose": state["purpose"],
        "mode": state["mode"],
        "events": kept,
    }
    with open(os.path.join(session_dir, "events.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    duration_s = len(audio) / float(sample_rate)
    return {
        "session_id": session_id,
        "n_events": len(kept),
        "duration_s": duration_s,
        "path": session_dir,
    }


def active_sessions() -> list[str]:
    """Return the ids of currently active sessions.

    Returns
    -------
    list of str
        Active session ids (empty if none).
    """
    return sorted(_ACTIVE)


def event_to_sample_index(event_t_perf: float, meta: dict) -> int:
    """Map a key event's perf-counter time to an approximate audio sample index.

    Implements the documented coarse mapping
    ``sample_index ~= round((t_perf - audio_start_perf - input_latency_s) * sr)``
    (CLACK_BUILD_PLAN.md section 9). The onset snap in :mod:`clack.segment`
    finishes the alignment.

    Parameters
    ----------
    event_t_perf : float
        The event's ``t_perf`` timestamp.
    meta : dict
        Session metadata containing ``audio_start_perf``, ``input_latency_s``,
        and ``sample_rate``.

    Returns
    -------
    int
        The approximate sample index (clamped at zero).
    """
    sr = int(meta["sample_rate"])
    start = float(meta.get("audio_start_perf", 0.0))
    latency = float(meta.get("input_latency_s", 0.0))
    idx = round((event_t_perf - start - latency) * sr)
    return max(0, int(idx))
