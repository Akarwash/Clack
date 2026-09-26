"""Collection session lifecycle: start/stop, write ``audio.wav`` + ``events.json``.

A session ties one microphone recording to one stream of key events on a single
clock and persists them to ``data/recordings/<session_id>/`` in the on-disk
contract from CLACK_BUILD_PLAN.md section 9.

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionMeta:
    """Metadata describing one collection session.

    Attributes
    ----------
    session_id : str
        Unique id, for example ``2026-09-26T09-30-00_blue_akarsh``.
    keyboard_id : str
        Which physical keyboard, for example ``blue`` or ``c3equalz``.
    typist : str
        Consenting typist identifier.
    purpose : str
        One of ``train``, ``eval``, or ``demo``.
    mode : str
        Collection cadence, for example ``paced``.
    """

    session_id: str
    keyboard_id: str
    typist: str
    purpose: str
    mode: str = "paced"


@dataclass
class Session:
    """An in-progress collection session.

    Parameters
    ----------
    meta : SessionMeta
        Descriptive metadata for the session.
    root : str or None, optional
        Recordings root; defaults to ``config.RECORDINGS_DIR``.
    """

    meta: SessionMeta
    root: Optional[str] = None
    events: list = field(default_factory=list)

    def start(self) -> None:
        """Begin recording audio and collecting key events on one clock.

        Raises
        ------
        RuntimeError
            If capture or key logging cannot be started.
        """
        raise NotImplementedError("built in BUILD_TRAINER")

    def stop(self) -> str:
        """Stop capture and write ``audio.wav`` and ``events.json`` to disk.

        Returns
        -------
        str
            The path of the written session directory.

        Raises
        ------
        RuntimeError
            If no audio was captured (fail loudly, never write empty data).
        """
        raise NotImplementedError("built in BUILD_TRAINER")


def load_session(session_dir: str) -> tuple["object", SessionMeta]:
    """Load a persisted session's audio and metadata from disk.

    Parameters
    ----------
    session_dir : str
        Path to a ``data/recordings/<session_id>/`` directory.

    Returns
    -------
    tuple
        The loaded audio array and its :class:`SessionMeta`.

    Raises
    ------
    FileNotFoundError
        If the session directory or its files are missing.
    """
    raise NotImplementedError("built in BUILD_TRAINER")
