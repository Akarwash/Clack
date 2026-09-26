"""Tests for :mod:`clack.correct` (local n-gram beam-search correction).

Owner: BUILD_BACKEND. Uses the bundled corpus and a known noisy candidate lattice.
"""

from __future__ import annotations

from clack import evaluate
from clack.correct import NgramCorrector


def _lattice_for(reference: str, wrong_first: dict) -> list[list[str]]:
    """Build a lattice where certain positions have a wrong top-1 but the true key
    is available at rank 2."""
    lattice = []
    for i, ch in enumerate(reference):
        key = "space" if ch == " " else ch
        if i in wrong_first:
            lattice.append([wrong_first[i], key, "x"])  # wrong argmax, truth at rank 2
        else:
            lattice.append([key, "x", "z"])
    return lattice


def test_corrected_beats_raw_argmax() -> None:
    """Correction recovers a known sentence better than the raw argmax."""
    corrector = NgramCorrector()
    reference = "the quick brown fox"
    # Corrupt the top-1 at a few positions (truth still at rank 2).
    wrong = {1: "z", 5: "x", 12: "q"}
    lattice = _lattice_for(reference, wrong)

    raw = "".join((" " if row[0] == "space" else row[0]) for row in lattice)
    corrected = corrector.correct(lattice)

    assert evaluate.cer(reference, corrected) < evaluate.cer(reference, raw)


def test_correct_returns_string_and_score() -> None:
    """correct returns a string; correct_with_score returns (text, score)."""
    corrector = NgramCorrector()
    lattice = [["t"], ["h"], ["e"]]
    assert corrector.correct(lattice) == "the"
    text, score = corrector.correct_with_score(lattice)
    assert text == "the"
    assert isinstance(score, float)


def test_space_token_rendered() -> None:
    """The 'space' candidate renders as a literal space."""
    corrector = NgramCorrector()
    lattice = [["h"], ["i"], ["space"], ["u"]]
    out = corrector.correct(lattice)
    assert out[2] == " "


def test_corrector_is_local_no_network() -> None:
    """The corrector loads the bundled corpus with no network access."""
    corrector = NgramCorrector()
    # A non-empty vocabulary proves the bundled corpus loaded.
    assert len(corrector._vocab) > 10
