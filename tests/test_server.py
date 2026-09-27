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


def test_demo_page_serves(client) -> None:
    """The demo page returns 200."""
    assert client.get("/demo").status_code == 200


def test_models_route_shape(client) -> None:
    """/models returns a models list and a default field."""
    r = client.get("/models")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["models"], list)
    assert "default" in body


def test_decode_empty_body(client) -> None:
    """/decode rejects an empty upload rather than guessing."""
    r = client.post("/decode", content=b"", headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_decode_bad_audio(client) -> None:
    """/decode reports an unreadable audio upload loudly."""
    r = client.post("/decode?model=dak", content=b"not a wav", headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 400
    assert "could not read audio" in r.json()["detail"]


def test_decode_happy_path(client, monkeypatch, tmp_path) -> None:
    """/decode round-trips onsets -> top-k -> transcript with the model stubbed."""
    import io

    import numpy as np
    import soundfile as sf

    from clack import attack as _attack

    (tmp_path / "m1").mkdir()
    monkeypatch.setattr(server.config, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_load_cached_model", lambda app, d: object())

    class _R:
        text = "ab"
        classes = ["a", "b", "space"]
        topk = np.array([[0, 1], [1, 0]])
        per_key = [
            {"topk": [("a", 0.9), ("b", 0.1)]},
            {"topk": [("b", 0.8), ("a", 0.2)]},
        ]

    monkeypatch.setattr(_attack, "attack_audio", lambda *a, **k: _R())

    buf = io.BytesIO()
    sf.write(buf, np.zeros(1000, dtype="float32"), 44100, format="WAV", subtype="PCM_16")
    r = client.post(
        "/decode?model=m1&correct=false&top_n=3",
        content=buf.getvalue(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["n_presses"] == 2
    assert j["transcript"] == "ab"
    assert j["corrected"] is None
    assert j["per_key"][0][0][0] == "a"
    assert j["search_space_full"] == "9"


def test_defense_measure_run_and_read(client, monkeypatch, tmp_path) -> None:
    """POST /defense/measure runs the before/after and GET reads it back."""
    from clack import defense as _defense

    (tmp_path / "m1").mkdir()
    monkeypatch.setattr(server.config, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_load_cached_model", lambda app, d: object())
    canned = {
        "off": 0.78, "on": 0.03, "delta": 0.75,
        "masker_key_ratio_db": 21.0, "band": [884, 2865], "n_keys": 383, "level": 0.3,
    }
    monkeypatch.setattr(_defense, "measure_session", lambda *a, **k: dict(canned))

    r = client.post("/defense/measure", json={"session_id": "sX", "model_name": "m1", "level": 0.3})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["off"] == 0.78 and j["on"] == 0.03 and j["delta"] == 0.75

    g = client.get("/defense/measure")
    assert g.status_code == 200
    assert g.json()["delta"] == 0.75


def test_defense_measure_run_requires_session(client) -> None:
    """POST /defense/measure without a session_id fails loudly."""
    r = client.post("/defense/measure", json={"model_name": "dak"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
