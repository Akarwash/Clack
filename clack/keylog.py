"""Keyboard event capture (pynput) with permission checking.

Records ``press`` events with ``time.perf_counter()`` timestamps so each press
supplies a training LABEL and an approximate location. The exact window cut is
snapped to the acoustic onset later (see :mod:`clack.segment`).

Security note: this listener is used ONLY during training. In attack mode the
pynput listener is never instantiated (``config.ATTACK_DISABLES_KEYLOGGER``);
this is what makes the attack provably microphone-only.

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class KeyEvent:
    """A single keyboard press.

    Attributes
    ----------
    key : str
        The normalized key name (a member of ``config.KEY_SET`` where possible).
    t_perf : float
        ``time.perf_counter()`` timestamp of the press.
    type : str
        Event type; always ``"press"`` for collected events.
    """

    key: str
    t_perf: float
    type: str = "press"


def check_permission() -> bool:
    """Check whether keyboard monitoring is permitted by the OS.

    Returns
    -------
    bool
        ``True`` if a listener can be created.

    Raises
    ------
    PermissionError
        If accessibility/input-monitoring permission is denied.
    """
    raise NotImplementedError("built in BUILD_TRAINER")


class KeyLogger:
    """Collect keyboard press events on the shared performance clock.

    Parameters
    ----------
    on_event : callable or None, optional
        Optional callback invoked with each :class:`KeyEvent` as it arrives.
    """

    def __init__(self, on_event: Optional[Callable[[KeyEvent], None]] = None) -> None:
        raise NotImplementedError("built in BUILD_TRAINER")

    def start(self) -> None:
        """Start listening for key presses.

        Raises
        ------
        PermissionError
            If input monitoring permission is not granted.
        """
        raise NotImplementedError("built in BUILD_TRAINER")

    def stop(self) -> list[KeyEvent]:
        """Stop listening and return all collected events.

        Returns
        -------
        list of KeyEvent
            Every press captured between :meth:`start` and :meth:`stop`.
        """
        raise NotImplementedError("built in BUILD_TRAINER")
