"""FastAPI application: HTTP endpoints, WebSockets, and static UI.

The single integration surface. It wires the trainer routes, the live attack
WebSocket, the correction, the defense routes, preflight, and serves the
self-hosted UI (no CDN). This module is owned only by the orchestrator and wired
last (CLACK_BUILD_PLAN.md section 5A, Wave 2).

Owner: BUILD_BACKEND.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


def create_app() -> "FastAPI":
    """Build and return the configured FastAPI application.

    Ensures runtime directories exist, mounts the static UI, and registers every
    HTTP and WebSocket route (trainer, attack, defense, exposure, preflight).

    Returns
    -------
    fastapi.FastAPI
        The wired application instance.
    """
    raise NotImplementedError("built in BUILD_BACKEND")
