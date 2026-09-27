"""Tests for :mod:`clack.prompts` (balanced random-character generation).

Owner: BUILD_TRAINER. Uses Hypothesis per CLACK_BUILD_PLAN.md section 11.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given
from hypothesis import strategies as st

import config
from clack import prompts

_ALPHABET = st.sampled_from(list(string.ascii_lowercase + string.digits) + ["space"])


@given(
    key_set=st.lists(_ALPHABET, min_size=1, max_size=20, unique=True),
    length=st.integers(min_value=1, max_value=500),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_balanced_sequence_properties(key_set, length, seed) -> None:
    """Exact length, every token in the set, per-key spread at most one cycle."""
    seq = prompts.balanced_sequence(key_set=key_set, length=length, seed=seed)
    assert len(seq) == length
    assert all(token in key_set for token in seq)

    counts = {k: 0 for k in key_set}
    for token in seq:
        counts[token] += 1
    spread = max(counts.values()) - min(counts.values())
    assert spread <= 1


def test_balanced_sequence_defaults_cover_train_quota() -> None:
    """The default length covers the training quota for every key."""
    seq = prompts.balanced_sequence(seed=1)
    assert len(seq) == config.TRAIN_SAMPLES_PER_KEY * len(config.KEY_SET)
    counts = prompts.coverage_counts(seq)
    assert min(counts.values()) >= config.TRAIN_SAMPLES_PER_KEY - 1


def test_balanced_sequence_is_seeded() -> None:
    """The same seed reproduces the same sequence; a fresh seed differs."""
    a = prompts.balanced_sequence(length=100, seed=7)
    b = prompts.balanced_sequence(length=100, seed=7)
    c = prompts.balanced_sequence(length=100, seed=8)
    assert a == b
    assert a != c


def test_balanced_sequence_rejects_bad_input() -> None:
    """Empty key set or non-positive length raises ValueError."""
    with pytest.raises(ValueError):
        prompts.balanced_sequence(key_set=[], length=10)
    with pytest.raises(ValueError):
        prompts.balanced_sequence(length=0)


def test_sequence_prompt_even_coverage() -> None:
    """A whole number of passes covers every key equally."""
    order = prompts.DEFAULT_SEQUENCE_ORDER
    seq = prompts.sequence_prompt(length=len(order) * 5)
    counts = prompts.coverage_counts(seq)
    present = [c for c in counts.values() if c > 0]
    assert min(present) == max(present) == 5  # exactly 5 passes -> 5 per key
    assert all(t in config.KEY_SET for t in seq)


def test_sequence_prompt_is_fixed_order() -> None:
    """The sequence repeats the fixed order (not random)."""
    order = prompts.DEFAULT_SEQUENCE_ORDER
    seq = prompts.sequence_prompt(length=len(order) * 2)
    assert seq[: len(order)] == list(order)
    assert seq[len(order) : 2 * len(order)] == list(order)


def test_sequence_prompt_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        prompts.sequence_prompt(length=0)
    with pytest.raises(ValueError):
        prompts.sequence_prompt(order=[])


def test_next_needed_keys_orders_by_deficit() -> None:
    """Keys below quota are returned most-deficient first; met keys are omitted."""
    counts = {"a": 40, "b": 10, "c": 25, "d": 0}
    needed = prompts.next_needed_keys(counts, quota=40)
    assert needed == ["d", "b", "c"]
    assert prompts.next_needed_keys({"a": 40}, quota=40) == []
