"""Balanced random-character prompt generation for the Clack Trainer.

Random characters (not words) give even coverage across every key: natural words
over-represent ``e`` and starve ``q`` and ``z``. The generator concatenates
shuffled copies of the key set, which guarantees per-key counts differ by at most
one shuffle cycle (unlike uniform random sampling, which leaves some keys
under-sampled by chance). Collection is coverage-driven: the session keeps
serving prompts until every key reaches its quota.

Owner: BUILD_TRAINER.
"""

from __future__ import annotations

import random
from typing import Optional, Sequence

import config


def balanced_sequence(
    key_set: Optional[Sequence[str]] = None,
    length: Optional[int] = None,
    seed: Optional[int] = None,
) -> list[str]:
    """Generate a balanced random sequence of key tokens.

    Repeatedly shuffles a copy of ``key_set`` and concatenates the shuffles, then
    trims to ``length``. Per-key counts therefore differ by at most one shuffle
    cycle.

    Parameters
    ----------
    key_set : sequence of str or None, optional
        The keys to draw from; defaults to ``config.KEY_SET``.
    length : int or None, optional
        Number of tokens to emit; defaults to
        ``config.TRAIN_SAMPLES_PER_KEY * len(key_set)`` so a full session covers
        the training quota for every key.
    seed : int or None, optional
        RNG seed; defaults to ``config.SEED``. Pass a fresh seed per session so
        typists do not memorize the order.

    Returns
    -------
    list of str
        A list of ``length`` key tokens (``"space"`` is one token, rendered as a
        glyph in the UI).

    Raises
    ------
    ValueError
        If ``key_set`` is empty or ``length`` is not positive.

    Examples
    --------
    >>> seq = balanced_sequence(key_set=["a", "b"], length=4, seed=0)
    >>> sorted(seq) == ["a", "a", "b", "b"]
    True
    """
    keys = list(config.KEY_SET if key_set is None else key_set)
    if not keys:
        raise ValueError("key_set must be non-empty")
    if length is None:
        length = config.TRAIN_SAMPLES_PER_KEY * len(keys)
    if length <= 0:
        raise ValueError(f"length must be positive, got {length}")

    rng = random.Random(config.SEED if seed is None else seed)
    out: list[str] = []
    while len(out) < length:
        cycle = keys[:]
        rng.shuffle(cycle)
        out.extend(cycle)
    return out[:length]


def coverage_counts(tokens: Sequence[str], key_set: Optional[Sequence[str]] = None) -> dict[str, int]:
    """Count how many times each key appears in a token sequence.

    Parameters
    ----------
    tokens : sequence of str
        Key tokens whose per-key counts to tally.
    key_set : sequence of str or None, optional
        The keys to report; defaults to ``config.KEY_SET`` (zero-filled).

    Returns
    -------
    dict of str to int
        Count for every key in ``key_set``.
    """
    keys = list(config.KEY_SET if key_set is None else key_set)
    counts = {k: 0 for k in keys}
    for token in tokens:
        if token in counts:
            counts[token] += 1
    return counts


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
    below = [(count, key) for key, count in counts.items() if count < quota]
    below.sort()
    return [key for _, key in below]
