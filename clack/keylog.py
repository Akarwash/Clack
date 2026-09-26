"""Keyboard event capture (pynput) with permission checking.

Records ``press`` events with ``time.perf_counter()`` timestamps so each press
supplies a training LABEL and an approximate location. The exact window cut is
snapped to the acoustic onset later (see :mod:`clack.segment`).

Security note: this listener is used ONLY during training. In attack mode the
pynput listener is never instantiated (``config.ATTACK_DISABLES_KEYLOGGER``);
that is what makes the attack provably microphone-only.

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

import time
from typing import Optional

import config


def _normalize_key(key: object) -> Optional[str]:
    """Map a pynput key object to a member of ``config.KEY_SET``, or ``None``.

    Parameters
    ----------
    key : object
        A ``pynput.keyboard.KeyCode`` or ``Key`` instance.

    Returns
    -------
    str or None
        The normalized key name if it is in ``config.KEY_SET``, else ``None``.
    """
    # Letters and digits arrive as KeyCode with a .char attribute.
    char = getattr(key, "char", None)
    if char is not None:
        lowered = char.lower()
        if lowered in config.KEY_SET:
            return lowered
        return None
    # Special keys arrive as Key.<name>; only space is in the key set.
    name = getattr(key, "name", None)
    if name == "space" and "space" in config.KEY_SET:
        return "space"
    return None


def check_permission() -> None:
    """Verify OS input-monitoring permission is granted.

    Returns
    -------
    None

    Raises
    ------
    PermissionError
        If a keyboard listener cannot be created. The message states the exact
        fix (macOS: System Settings, Privacy and Security, enable Input
        Monitoring and Accessibility for the terminal or app).
    """
    try:  # pragma: no cover - depends on host OS permissions
        from pynput import keyboard

        listener = keyboard.Listener(on_press=lambda _k: None)
        listener.start()
        listener.stop()
    except Exception as exc:  # pragma: no cover - depends on host OS permissions
        raise PermissionError(
            "keyboard input monitoring is not permitted. On macOS, open System "
            "Settings > Privacy and Security and enable both Input Monitoring and "
            "Accessibility for your terminal or app, then restart it. "
            f"(underlying error: {exc})"
        ) from exc


class KeyLogger:
    """Collect keyboard press events on the shared performance clock.

    Only keys in ``config.KEY_SET`` are recorded; letters and digits are
    lowercased and the spacebar is mapped to ``"space"``. Everything else
    (shift, backspace, modifiers) is ignored.
    """

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._listener = None

    def _on_press(self, key: object) -> None:  # pragma: no cover - realtime
        """Record a normalized press with a perf-counter timestamp."""
        normalized = _normalize_key(key)
        if normalized is not None:
            self._events.append(
                {"key": normalized, "t_perf": time.perf_counter(), "type": "press"}
            )

    def start(self) -> None:
        """Start listening for key presses.

        Raises
        ------
        PermissionError
            If input monitoring permission is not granted.
        """
        try:  # pragma: no cover - requires a real listener
            from pynput import keyboard

            self._events = []
            self._listener = keyboard.Listener(on_press=self._on_press)
            self._listener.start()
        except Exception as exc:  # pragma: no cover
            raise PermissionError(
                "could not start keyboard listener; grant Input Monitoring "
                f"permission and retry (underlying error: {exc})"
            ) from exc

    def stop(self) -> list[dict]:
        """Stop listening and return all collected press events.

        Returns
        -------
        list of dict
            Each event has ``key``, ``t_perf``, and ``type`` keys.
        """
        if self._listener is not None:  # pragma: no cover - requires a real listener
            self._listener.stop()
            self._listener = None
        return list(self._events)
