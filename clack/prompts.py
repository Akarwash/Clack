"""Balanced random-character prompt generation for the Clack Trainer.

Random characters (not words) give even coverage across every key: natural words
over-represent ``e`` and starve ``q`` and ``z``. The generator is coverage-driven
so collection continues until every key reaches its per-key quota.

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

from typing import Optional


def balanced_prompt(length: int, seed: Optional[int] = None) -> str:
    """Generate a balanced random-character prompt string.

    Parameters
    ----------
    length : int
        Number of characters to emit.
    seed : int or None, optional
        RNG seed; defaults to ``config.SEED`` for reproducibility.

    Returns
    -------
    str
        A string of ``length`` characters drawn from ``config.KEY_SET``
        (``space`` rendered as a literal space), with near-uniform key coverage.

    Raises
    ------
    ValueError
        If ``length`` is not positive.
    """
    raise NotImplementedError("built in BUILD_TRAINER")


def coverage_counts(text: str) -> dict[str, int]:
    """Count how many times each key appears in a prompt or transcript.

    Parameters
    ----------
    text : str
        Text whose per-key counts to tally.

    Returns
    -------
    dict of str to int
        Count for every key in ``config.KEY_SET`` (zero-filled).
    """
    raise NotImplementedError("built in BUILD_TRAINER")


def next_needed_keys(counts: dict[str, int], quota: int) -> list[str]:
    """Return keys still below the per-key quota, most-deficient first.

    Parameters
    ----------
    counts : dict of str to int
        Current per-key sample counts.
    quota : int
        Target samples per key.

    Returns
    -------
    list of str
        Keys whose count is below ``quota``, ordered by increasing count.
    """
    raise NotImplementedError("built in BUILD_TRAINER")
