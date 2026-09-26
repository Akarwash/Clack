"""Tests for :mod:`clack.server` (routes, status, attack WebSocket).

Owner: BUILD_BACKEND. Hardware-touching calls (session capture, keyboard
permission) are monkeypatched so the tests are hermetic; the attack WebSocket is
exercised with the synthetic source.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clack import server


@pytest.fixture
def client(monkeypatch):
    """A TestClient over a fresh app with hardware calls stubbed out."""
    app = server.create_app()

    # Avoid touching the real microphone / keyboard permission in trainer + status.
    monkeypatch.setattr(server.session, "start_session", lambda **kw: "sid-test")
    monkeypatch.setattr(
        server.session,
        "stop_session",
        lambda sid: {"session_id": sid, "n_events": 3, "duration_s": 1.5, "path": "data/recordings/sid-test"},
    )
    with TestClient(app) as c:
        yield c


def test_pages_serve(client) -> None:
    """The dashboard and trainer pages return 200."""
    assert client.get("/").status_code == 200
    assert client.get("/trainer").status_code == 200


def test_trainer_prompt_count(client) -> None:
    """The prompt endpoint returns the requested number of characters."""
    r = client.get("/trainer/prompt", params={"n": 12, "mode": "paced"})
    assert r.status_code == 200
    assert len(r.json()["chars"]) == 12


def test_trainer_start_stop_roundtrip(client) -> None:
    """Trainer start then stop round-trips a session summary."""
    start = client.post("/trainer/start", json={"keyboard_id": "blue", "typist": "t", "purpose": "train"})
    assert start.status_code == 200
    sid = start.json()["session_id"]
    stop = client.post("/trainer/stop", json={"session_id": sid})
    assert stop.status_code == 200
    assert stop.json()["n_events"] == 3


def test_status_reports_every_item_and_keylogger_disabled(client) -> None:
    """/status reports each readiness item and shows the attack keylogger DISABLED."""
    report = client.get("/status").json()
    for key in (
        "microphone",
        "sample_rate",
        "keyboard_permission",
        "model",
        "attack_keylogger",
        "speaker",
        "compute",
        "ambient_calibration",
    ):
        assert key in report
        assert "ok" in report[key]
    assert report["attack_keylogger"]["state"] == "DISABLED"
    assert report["sample_rate"]["value"] == 44100


def test_attack_ws_forwards_synthetic_key(client) -> None:
    """The attack WebSocket handshakes and forwards a synthetic key message."""
    r = client.post("/attack/start", json={"source": "synthetic"})
    assert r.json()["ok"] is True
    with client.websocket_connect("/ws/attack") as ws:
        first = ws.receive_json()
        assert first["type"] == "status"
        assert first["keylogger"] == "DISABLED"
        # Read frames until a key message arrives (skip heartbeats).
        key_msg = None
        for _ in range(20):
            msg = ws.receive_json()
            if msg["type"] == "key":
                key_msg = msg
                break
        assert key_msg is not None
        assert "topk" in key_msg
        assert "text" in key_msg


def test_fleet_empty_ok(client) -> None:
    """/fleet returns a list (possibly empty) without error."""
    r = client.get("/fleet")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_defense_measure_not_yet(client) -> None:
    """/defense/measure reports nothing measured yet rather than fabricating."""
    r = client.get("/defense/measure")
    assert r.status_code == 404
    assert r.json()["ok"] is False
