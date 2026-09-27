"""FastAPI application: HTTP endpoints, the attack WebSocket, and the static UI.

The single integration surface. It wires the trainer routes, the live attack
WebSocket, the local correction, the defense and exposure and fleet routes,
preflight/status, and serves the self-hosted UI (no CDN). This module is owned by
the orchestrator and wired last (CLACK_BUILD_PLAN.md section 5A, Wave 2).

Owner: BUILD_BACKEND.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from clack import capture, exposure, prompts, session
from clack.config_types import ensure_dirs

_UI_DIR = os.path.join(os.path.dirname(__file__), "ui")


def _find_default_model() -> Optional[str]:
    """Return a model directory under MODELS_DIR, preferring a CNN over a floor."""
    root = config.MODELS_DIR
    if not os.path.isdir(root):
        return None
    candidates = [
        os.path.join(root, d)
        for d in sorted(os.listdir(root))
        if os.path.isfile(os.path.join(root, d, "config.json"))
    ]
    if not candidates:
        return None
    non_floor = [c for c in candidates if not c.endswith("-centroid")]
    return (non_floor or candidates)[0]


def _synthetic_frames() -> list[dict]:
    """A short synthetic key stream for wiring/tests (never presented as real)."""
    phrase = list("clack")
    frames = []
    text = ""
    for i, ch in enumerate(phrase):
        text += ch
        frames.append(
            {
                "type": "key",
                "key": ch,
                "confidence": 0.9,
                "topk": [[ch, 0.9], ["a", 0.05], ["s", 0.03]],
                "text": text,
                "t": time.perf_counter(),
                "latency_ms": 12.0,
                "synthetic": True,
            }
        )
    return frames


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Ensures runtime directories exist, registers every HTTP and WebSocket route
    (trainer, attack, defense, exposure, fleet, status), and mounts the static UI.

    Returns
    -------
    fastapi.FastAPI
        The wired application instance.
    """
    ensure_dirs()
    app = FastAPI(title="Clack", version="0.1.0")
    app.state.attack = {"running": False, "source": None, "queue": None, "task": None, "decoder": None, "event_mode": False, "text": ""}
    app.state.masker = None
    app.state.last_exposure = None
    app.state.last_defense = None
    app.state.corrector = None

    # ---- Pages ----------------------------------------------------------------
    @app.get("/")
    def index() -> "FileResponse":
        return FileResponse(os.path.join(_UI_DIR, "index.html"))

    @app.get("/trainer")
    def trainer_page() -> "FileResponse":
        return FileResponse(os.path.join(_UI_DIR, "trainer.html"))

    # ---- Trainer / collection -------------------------------------------------
    @app.get("/devices")
    def devices() -> "JSONResponse":
        try:
            return JSONResponse(capture.list_input_devices())
        except Exception as exc:  # pragma: no cover - host audio backend
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/trainer/prompt")
    def trainer_prompt(n: int = 200, mode: str = "paced") -> dict:
        if mode == "sequence":
            chars = prompts.sequence_prompt(length=max(1, int(n)))
        else:
            chars = prompts.balanced_sequence(length=max(1, int(n)))
        return {"chars": chars, "mode": mode}

    @app.post("/trainer/start")
    async def trainer_start(body: dict) -> "JSONResponse":
        try:
            sid = session.start_session(
                keyboard_id=body.get("keyboard_id", "blue"),
                typist=body.get("typist", "unknown"),
                purpose=body.get("purpose", "train"),
                mode=body.get("mode", "paced"),
            )
            return JSONResponse({"session_id": sid})
        except (PermissionError, RuntimeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/trainer/stop")
    async def trainer_stop(body: dict) -> "JSONResponse":
        try:
            return JSONResponse(session.stop_session(body["session_id"]))
        except (KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/trainer/level")
    def trainer_level(session_id: str) -> dict:
        return session.session_level(session_id)

    # ---- Attack (live) --------------------------------------------------------
    @app.post("/attack/start")
    async def attack_start(body: dict) -> "JSONResponse":
        source = body.get("source", "mic")
        event_mode = bool(body.get("event_mode", False))
        state = app.state.attack
        if state["running"]:
            return JSONResponse({"ok": False, "detail": "attack already running"}, status_code=400)

        queue: asyncio.Queue = asyncio.Queue()
        state.update({"running": True, "source": source, "queue": queue, "event_mode": event_mode, "text": ""})

        if source == "synthetic":
            async def _produce() -> None:
                for frame in _synthetic_frames():
                    await queue.put(frame)
                    await asyncio.sleep(0.05)
            state["task"] = asyncio.create_task(_produce())
            return JSONResponse({"ok": True, "source": "synthetic"})

        # Real microphone path.
        model_name = body.get("model_name")
        model_dir = os.path.join(config.MODELS_DIR, model_name) if model_name else _find_default_model()
        if not model_dir or not os.path.isdir(model_dir):
            state["running"] = False
            return JSONResponse({"ok": False, "detail": "no trained model available"}, status_code=400)

        try:  # pragma: no cover - requires a real mic and model
            from clack import model as _model
            from clack.stream import LiveDecoder

            loaded = _model.load_model(model_dir)
            loop = asyncio.get_event_loop()

            def _on_guess(guess) -> None:
                state["text"] = state.get("text", "") + (" " if guess.key == "space" else guess.key)
                loop.call_soon_threadsafe(queue.put_nowait, guess.as_message(state["text"]))

            decoder = LiveDecoder(loaded, on_guess=_on_guess, event_mode=event_mode)
            decoder.start()
            state["decoder"] = decoder
            return JSONResponse({"ok": True, "source": "mic", "model": os.path.basename(model_dir)})
        except Exception as exc:  # pragma: no cover
            state["running"] = False
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)

    @app.post("/attack/stop")
    async def attack_stop() -> dict:
        state = app.state.attack
        if state.get("decoder") is not None:  # pragma: no cover - requires a real mic
            state["decoder"].stop()
        if state.get("task") is not None:
            state["task"].cancel()
        app.state.attack = {"running": False, "source": None, "queue": None, "task": None, "decoder": None, "event_mode": False, "text": ""}
        return {"ok": True}

    @app.websocket("/ws/attack")
    async def ws_attack(ws: WebSocket) -> None:
        await ws.accept()
        state = app.state.attack
        keylogger_state = "ENABLED (event mode)" if state.get("event_mode") else "DISABLED"
        await ws.send_json(
            {
                "type": "status",
                "microphone": "ACTIVE" if state.get("source") == "mic" else (state.get("source") or "idle"),
                "keylogger": keylogger_state,
            }
        )
        queue = state.get("queue")
        try:
            while True:
                if queue is None:
                    await asyncio.sleep(0.1)
                    queue = app.state.attack.get("queue")
                    continue
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=0.5)
                    await ws.send_json(frame)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "heartbeat", "t": time.perf_counter()})
        except WebSocketDisconnect:
            return

    # ---- Defense --------------------------------------------------------------
    @app.post("/defense/on")
    async def defense_on(body: Optional[dict] = None) -> "JSONResponse":
        from clack.defense import Masker

        body = body or {}
        try:
            masker = app.state.masker or Masker()
            if body.get("level") is not None:
                masker.set_level(float(body["level"]))
            band = body.get("band")
            if band:
                masker.set_band(int(band[0]), int(band[1]))
            masker.start()
            app.state.masker = masker
            return JSONResponse({"ok": True, "on": masker.is_on(), "level": masker.level, "band": list(masker.band)})
        except Exception as exc:  # pragma: no cover - requires audio output
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)

    @app.post("/defense/off")
    async def defense_off() -> dict:
        if app.state.masker is not None:
            app.state.masker.stop()
        return {"ok": True, "on": False}

    @app.get("/defense/measure")
    def defense_measure() -> "JSONResponse":
        if app.state.last_defense is None:
            return JSONResponse({"ok": False, "detail": "no measurement yet; run a before/after measurement"}, status_code=404)
        return JSONResponse(app.state.last_defense)

    # ---- Exposure and fleet ---------------------------------------------------
    @app.post("/exposure/check")
    async def exposure_check(body: dict) -> "JSONResponse":
        session_id = body.get("session_id") or body.get("sample_id")
        endpoint = body.get("endpoint", "this-endpoint")
        if not session_id:
            return JSONResponse({"error": "session_id required"}, status_code=400)
        session_dir = os.path.join(config.RECORDINGS_DIR, session_id)
        model_dir = os.path.join(config.MODELS_DIR, body["model_name"]) if body.get("model_name") else _find_default_model()
        if not model_dir or not os.path.isdir(model_dir):
            return JSONResponse({"error": "no trained model available"}, status_code=400)
        try:
            from clack import model as _model

            loaded = _model.load_model(model_dir)
            report = exposure.run_exposure_check(session_dir, loaded, endpoint=endpoint, save=True)
            app.state.last_exposure = report.as_dict()
            return JSONResponse(app.state.last_exposure)
        except (FileNotFoundError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/exposure/last")
    def exposure_last() -> "JSONResponse":
        if app.state.last_exposure is None:
            return JSONResponse({"ok": False, "detail": "no exposure check yet"}, status_code=404)
        return JSONResponse(app.state.last_exposure)

    @app.get("/fleet")
    def fleet() -> "JSONResponse":
        return JSONResponse(exposure.load_fleet_reports())

    # ---- Correction (local, no network) ---------------------------------------
    @app.post("/correct")
    async def correct_route(body: dict) -> dict:
        lattice = body.get("lattice", [])
        if app.state.corrector is None:
            from clack.correct import NgramCorrector

            app.state.corrector = NgramCorrector()
        return {"text": app.state.corrector.correct(lattice)}

    # ---- Status / preflight ---------------------------------------------------
    @app.get("/status")
    def status() -> dict:
        return build_status(app)

    # ---- Static assets (mounted last so API routes take precedence) -----------
    app.mount("/", StaticFiles(directory=_UI_DIR, html=False), name="ui")
    return app


def build_status(app: object) -> dict:
    """Assemble the readiness report used by ``/status`` and preflight.

    Each item is ``{"ok": bool, ...detail}``. Failures are reported, never hidden.

    Parameters
    ----------
    app : object
        The FastAPI app (for the current attack/keylogger state).

    Returns
    -------
    dict
        The full readiness report.
    """
    report: dict = {}

    # Microphone.
    try:
        devices = capture.list_input_devices()
        report["microphone"] = {"ok": bool(devices), "name": devices[0]["name"] if devices else None}
    except Exception as exc:
        report["microphone"] = {"ok": False, "detail": str(exc)}

    report["sample_rate"] = {"ok": True, "value": config.SAMPLE_RATE}

    # Keyboard permission (best-effort; a failure is reported, not raised).
    try:
        from clack.keylog import check_permission

        check_permission()
        report["keyboard_permission"] = {"ok": True}
    except Exception as exc:
        report["keyboard_permission"] = {"ok": False, "detail": str(exc)}

    # Model.
    model_dir = _find_default_model()
    report["model"] = {"ok": bool(model_dir), "name": os.path.basename(model_dir) if model_dir else None}

    # Attack keylogger state (provably disabled unless event mode).
    attack = getattr(app.state, "attack", {}) if hasattr(app, "state") else {}
    state = "ENABLED (event mode)" if attack.get("event_mode") else "DISABLED"
    report["attack_keylogger"] = {"ok": state == "DISABLED", "state": state}

    # Speaker (best-effort output device query).
    try:
        import sounddevice as sd

        outs = [d for d in sd.query_devices() if int(d.get("max_output_channels", 0)) > 0]
        report["speaker"] = {"ok": bool(outs)}
    except Exception as exc:  # pragma: no cover - host audio backend
        report["speaker"] = {"ok": False, "detail": str(exc)}

    # Compute device.
    try:
        from clack.train import detect_device

        report["compute"] = {"ok": True, "device": detect_device()}
    except Exception as exc:  # pragma: no cover
        report["compute"] = {"ok": False, "detail": str(exc)}

    # Ambient calibration (from a running decoder, if any).
    decoder = attack.get("decoder")
    if decoder is not None and getattr(decoder, "calibrated", False):  # pragma: no cover - requires a mic
        report["ambient_calibration"] = {"ok": True, "noise_floor": decoder.noise_floor}
    else:
        report["ambient_calibration"] = {"ok": False, "detail": "not calibrated (starts at attack time)"}

    return report


# A module-level app for uvicorn ("clack.server:app").
app = create_app()
