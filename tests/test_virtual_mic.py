"""Routing, actual mixing, and fail-closed bridge lifecycle without hardware."""
import copy
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from clack.core_audio import validate_bridge
from clack.virtual_mic import MaskingGenerator, VirtualMic
from clack import server


@pytest.fixture
def devices():
    return [
        {"name": "HyperX SoloCast", "uid": "mic", "inputs": 2, "outputs": 0, "sample_rate": 44100, "members": None},
        {"name": "BlackHole 2ch", "uid": "bh", "inputs": 2, "outputs": 2, "sample_rate": 44100, "members": None},
        {"name": config.VIRTUAL_MIC_BRIDGE, "uid": "aggregate", "inputs": 4, "outputs": 2, "sample_rate": 44100,
         "members": ["mic", "bh"], "clock_uid": "mic", "drift": {"bh": True}},
    ]


def test_valid_route(devices):
    assert validate_bridge(config.VIRTUAL_MIC_BRIDGE, devices)["input_device"] == "HyperX SoloCast"


@pytest.mark.parametrize("change", ["order", "speakers", "extra", "missing", "rate", "clock", "drift", "channels", "unknown"])
def test_unsafe_routes_rejected(devices, change):
    if change == "order": devices[2]["members"].reverse()
    elif change == "speakers": devices[0]["outputs"] = 2
    elif change == "extra": devices[2]["members"].append("speaker")
    elif change == "missing": devices.pop(0)
    elif change == "rate": devices[1]["sample_rate"] = 48000
    elif change == "clock": devices[2]["clock_uid"] = "bh"
    elif change == "drift": devices[2]["drift"]["bh"] = False
    elif change == "channels": devices[2]["outputs"] = 4
    elif change == "unknown": devices[2]["members"] = None
    with pytest.raises(ValueError): validate_bridge(config.VIRTUAL_MIC_BRIDGE, devices)


def test_generator_continuity_and_freshness():
    split = MaskingGenerator(seed=7)
    blocks = np.concatenate([split.block(512) for _ in range(12)])
    whole = MaskingGenerator(seed=7)
    # Verify deterministic chunks, persistent filter state and no repeated loop.
    other = np.concatenate([whole.block(512) for _ in range(12)])
    np.testing.assert_array_equal(blocks, other)
    assert np.isfinite(blocks).all() and np.abs(blocks).max() <= 1
    assert not np.array_equal(blocks[:512], blocks[512:1024])
    assert split.position == 6144 and split.next_click > 6144


class FakeStream:
    latency = (.01, .01)
    def __init__(self, callback): self.callback = callback; self.closed = False; self.aborted = False
    def start(self): pass
    def abort(self): self.aborted = True
    def close(self): self.closed = True


@pytest.fixture
def bridge(devices):
    obj = VirtualMic(stream_factory=FakeStream, validator=lambda name: validate_bridge(name, devices))
    yield obj
    obj.stop()


def test_lifecycle_idempotence_and_device_change(bridge):
    assert bridge.start()["running"]
    stream = bridge._stream
    bridge.start(level=.5)
    assert bridge._stream is stream and bridge.level == .5
    with pytest.raises(ValueError): bridge.start("another bridge")
    bridge.stop(); bridge.stop()
    assert stream.closed and not bridge.running


def test_mic_preserved_identical_channels_and_limiting(bridge):
    # Known masker blocks isolate the actual mixing from random generation.
    bridge._blocks.put(np.full(512, .2, np.float32))
    x = np.full((512, 1), .1, np.float32)
    y = np.empty((512, 2), np.float32)
    bridge._callback(x, y, 512, None, False)
    np.testing.assert_allclose(y, .1 * config.VIRTUAL_MIC_GAIN + .2 * bridge.level)
    bridge._blocks.put(np.ones(512, np.float32))
    bridge._callback(np.full_like(x, 2), y, 512, None, False)
    assert np.isfinite(y).all() and np.abs(y).max() <= .98
    np.testing.assert_array_equal(y[:, 0], y[:, 1])
    assert bridge.clipped_samples == 512


@pytest.mark.parametrize("failure", ["empty", "stream", "nan", "size", "stopped"])
def test_failures_never_emit_clean_audio(bridge, failure):
    x = np.ones((512, 1), np.float32); y = np.ones((512, 2), np.float32)
    if failure != "empty": bridge._blocks.put(np.zeros(512, np.float32))
    if failure == "nan": x[0, 0] = np.nan
    if failure == "stopped": bridge.stop()
    bridge._callback(x, y, 511 if failure == "size" else 512, None, failure == "stream")
    assert np.all(y == 0)


def test_stall_stops_and_closes(bridge):
    bridge.start()
    stream = bridge._stream
    bridge.last_callback = time.monotonic() - 2
    report = bridge.status()
    assert not report["running"] and "stalled" in report["error"]
    assert stream.closed


def test_device_loss_even_with_live_callbacks(bridge):
    bridge.start()
    bridge._last_route_check = time.monotonic() - 2
    def missing(name): raise ValueError("microphone unplugged")
    bridge._validator = missing
    bridge._check_health()
    assert "disconnected" in bridge._worker_error


@pytest.mark.parametrize("level", [0, -.1, 1.1, float("nan"), float("inf")])
def test_level_cannot_bypass_masking(bridge, level):
    with pytest.raises(ValueError): bridge.set_level(level)


def test_bad_validation_never_opens_stream(devices):
    calls = []
    invalid = copy.deepcopy(devices); invalid[0]["outputs"] = 2
    obj = VirtualMic(stream_factory=lambda cb: calls.append(cb), validator=lambda n: validate_bridge(n, invalid))
    with pytest.raises(ValueError): obj.start()
    assert calls == []


def test_routes_settings_conflicts_shutdown(monkeypatch, bridge):
    app = server.create_app(); app.state.virtual_mic = bridge
    monkeypatch.setattr(server.session, "active_sessions", lambda: [])
    monkeypatch.setattr(server, "discover_devices", lambda: {"available": True, "routes": []})
    with TestClient(app) as client:
        assert client.get("/virtual-mic/devices").json()["available"]
        assert client.post("/virtual-mic/start", json={}).json()["running"]
        assert client.post("/virtual-mic/settings", json={"level": .5}).json()["level"] == .5
        assert client.post("/virtual-mic/settings", json={"level": 0}).status_code == 422
        assert client.post("/defense/on", json={}).status_code == 409
        assert client.post("/trainer/start", json={}).status_code == 409
        assert client.post("/attack/start", json={"input_device": "HyperX SoloCast"}).status_code == 409
        assert not client.post("/virtual-mic/stop", json={}).json()["running"]
        assert client.post("/virtual-mic/start", json={}).json()["running"]
        stream = bridge._stream
    assert stream.closed


def test_start_conflicts_with_speaker_training_and_attack(monkeypatch, bridge):
    app = server.create_app(); app.state.virtual_mic = bridge
    with TestClient(app) as client:
        monkeypatch.setattr(server.session, "active_sessions", lambda: ["session"])
        assert client.post("/virtual-mic/start", json={}).status_code == 409

        monkeypatch.setattr(server.session, "active_sessions", lambda: [])
        app.state.attack.update(running=True, source="mic", input_device="HyperX SoloCast")
        assert client.post("/virtual-mic/start", json={}).status_code == 409
        app.state.attack["running"] = False
        class Speaker:
            def is_on(self): return True
            def stop(self): pass
        app.state.masker = Speaker()
        assert client.post("/virtual-mic/start", json={}).status_code == 409


def test_live_attack_can_select_blackhole(monkeypatch, bridge, tmp_path):
    from clack import model, stream
    app = server.create_app(); app.state.virtual_mic = bridge
    monkeypatch.setattr(server.session, "active_sessions", lambda: [])
    monkeypatch.setattr(server, "_find_default_model", lambda: str(tmp_path))
    monkeypatch.setattr(model, "load_model", lambda path: object())
    selected = []
    class Decoder:
        def __init__(self, model, **kw): selected.append(kw["device"])
        def start(self): pass
        def stop(self): pass
    monkeypatch.setattr(stream, "LiveDecoder", Decoder)
    with TestClient(app) as client:
        bridge.start()
        response = client.post("/attack/start", json={"input_device": "BlackHole 2ch"})
        assert response.status_code == 200 and response.json()["ok"]
        assert selected == ["BlackHole 2ch"]
        monkeypatch.setattr(server.capture, "list_input_devices", lambda: [{"name": "HyperX SoloCast"}, {"name": "BlackHole 2ch"}])
        assert server.build_status(app)["microphone"]["name"] == "BlackHole 2ch"


def test_mac_permission_check_does_not_create_listener(monkeypatch):
    from clack import keylog
    from unittest.mock import Mock
    library = Mock()
    library.AXIsProcessTrusted.return_value = True
    library.CGPreflightListenEventAccess.return_value = True
    monkeypatch.setattr(keylog.sys, "platform", "darwin")
    monkeypatch.setattr(keylog.ctypes, "CDLL", lambda name: library)
    keylog.check_permission()
    library.AXIsProcessTrusted.assert_called_once()
    library.CGPreflightListenEventAccess.assert_called_once()
    library.CGPreflightListenEventAccess.return_value = False
    with pytest.raises(PermissionError): keylog.check_permission()
