"""Language-model correction: local n-gram beam search over the top-k lattice.

Turns the model's per-press top-k candidates into readable text using a local
n-gram model (``config.NGRAM_ORDER``) and beam search (``config.BEAM_WIDTH``).
Defaults to a fully local corpus with no network call; an external LLM is behind
``config.USE_LLM_CORRECTION`` and off by default (golden rule: no network at
demo time). RAW output is always shown next to corrected output.

Owner: BUILD_BACKEND (correction slice).
"""

from __future__ import annotations

from typing import Optional


class NgramCorrector:
    """Local n-gram beam-search corrector over a top-k candidate lattice.

    Parameters
    ----------
    corpus_path : str or None, optional
        Path to a bundled local corpus; defaults to ``config.CORPUS_DIR``.
    order : int or None, optional
        N-gram order; defaults to ``config.NGRAM_ORDER``.
    beam_width : int or None, optional
        Beam width; defaults to ``config.BEAM_WIDTH``.
    """

    def __init__(self, corpus_path: Optional[str] = None, order: Optional[int] = None, beam_width: Optional[int] = None) -> None:
        raise NotImplementedError("built in BUILD_BACKEND")

    def correct(self, lattice: list[list[str]]) -> str:
        """Decode the most likely string from a per-press candidate lattice.

        Parameters
        ----------
        lattice : list of list of str
            Per-press ranked candidate keys.

        Returns
        -------
        str
            The corrected string.
        """
        raise NotImplementedError("built in BUILD_BACKEND")
