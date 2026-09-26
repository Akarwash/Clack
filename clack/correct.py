"""Language-model correction: local n-gram beam search over the top-k lattice.

Turns the model's per-press top-k candidates into readable text using a local
character-level n-gram model (``config.NGRAM_ORDER``) and beam search
(``config.BEAM_WIDTH``). The corrector defaults to a bundled corpus shipped inside
the package (``clack/corpus/en.txt``), so there is no network dependency at demo
time; a user corpus under ``config.CORPUS_DIR`` is also loaded if present. An
external LLM is behind ``config.USE_LLM_CORRECTION`` and off by default, and it
must never be on the critical path.

RAW model output is always shown next to the corrected output so no one thinks the
language model did all the work.

Owner: BUILD_BACKEND (correction slice).
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from typing import Optional

import config

_PACKAGE_CORPUS = os.path.join(os.path.dirname(__file__), "corpus", "en.txt")
_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789 ")


def _key_to_char(key: str) -> str:
    """Map a class name to its character (``space`` becomes a literal space)."""
    return " " if key == "space" else key


def _clean_text(text: str) -> str:
    """Lowercase and keep only the modeled characters (letters, digits, space)."""
    return "".join(c for c in text.lower() if c in _ALLOWED)


class NgramCorrector:
    """Local n-gram beam-search corrector over a top-k candidate lattice.

    Parameters
    ----------
    corpus_path : str or None, optional
        Path to a corpus text file or directory; defaults to the bundled package
        corpus plus any files under ``config.CORPUS_DIR``.
    order : int or None, optional
        N-gram order; defaults to ``config.NGRAM_ORDER``.
    beam_width : int or None, optional
        Beam width; defaults to ``config.BEAM_WIDTH``.
    """

    def __init__(
        self,
        corpus_path: Optional[str] = None,
        order: Optional[int] = None,
        beam_width: Optional[int] = None,
    ) -> None:
        self.order = int(order or config.NGRAM_ORDER)
        self.beam_width = int(beam_width or config.BEAM_WIDTH)
        self._counts: list[dict] = [defaultdict(lambda: defaultdict(int)) for _ in range(self.order)]
        self._vocab: set[str] = set(" abcdefghijklmnopqrstuvwxyz0123456789")
        self._load_corpus(corpus_path)

    def _load_corpus(self, corpus_path: Optional[str]) -> None:
        texts: list[str] = []
        paths: list[str] = []
        if os.path.isfile(_PACKAGE_CORPUS):
            paths.append(_PACKAGE_CORPUS)
        if corpus_path:
            if os.path.isdir(corpus_path):
                paths.extend(
                    os.path.join(corpus_path, f) for f in sorted(os.listdir(corpus_path)) if f.endswith(".txt")
                )
            elif os.path.isfile(corpus_path):
                paths.append(corpus_path)
        elif os.path.isdir(config.CORPUS_DIR):
            paths.extend(
                os.path.join(config.CORPUS_DIR, f)
                for f in sorted(os.listdir(config.CORPUS_DIR))
                if f.endswith(".txt")
            )

        for path in paths:
            try:
                with open(path, encoding="utf-8") as fh:
                    texts.append(fh.read())
            except OSError:
                continue

        if not texts:
            raise FileNotFoundError(
                "no correction corpus found; expected the bundled corpus at "
                f"{_PACKAGE_CORPUS} (correction must run locally, no network)"
            )

        for text in texts:
            cleaned = _clean_text(text)
            self._vocab.update(cleaned)
            for n in range(1, self.order + 1):
                counts = self._counts[n - 1]
                for i in range(len(cleaned) - n + 1):
                    context = cleaned[i : i + n - 1]
                    nxt = cleaned[i + n - 1]
                    counts[context][nxt] += 1

    def _char_logprob(self, context: str, char: str) -> float:
        """Backoff character log-probability of ``char`` given a context."""
        vocab_size = len(self._vocab)
        for n in range(self.order, 0, -1):
            ctx = context[-(n - 1):] if n > 1 else ""
            counts = self._counts[n - 1].get(ctx)
            if counts:
                total = sum(counts.values())
                # Add-one smoothing over the observed vocabulary.
                return math.log((counts.get(char, 0) + 1) / (total + vocab_size))
        return math.log(1.0 / vocab_size)

    def correct(self, lattice: list[list[str]]) -> str:
        """Decode the most likely string from a per-press candidate lattice.

        Parameters
        ----------
        lattice : list of list of str
            Per-press ranked candidate keys (best first). ``space`` is a candidate.

        Returns
        -------
        str
            The corrected string (``space`` rendered as a space).
        """
        text, _ = self.correct_with_score(lattice)
        return text

    def correct_with_score(self, lattice: list[list[str]]) -> tuple[str, float]:
        """Beam-search decode returning the best string and its log-score.

        The score combines the n-gram language log-probability with a small rank
        prior (earlier candidates favored, a proxy for classifier confidence).

        Parameters
        ----------
        lattice : list of list of str
            Per-press ranked candidate keys.

        Returns
        -------
        tuple
            ``(best_text, score)``.
        """
        beams: list[tuple[str, float]] = [("", 0.0)]
        for position in lattice:
            candidates = [c for c in position[: self.beam_width] if c]
            if not candidates:
                continue
            new_beams: list[tuple[str, float]] = []
            for text, score in beams:
                for rank, key in enumerate(candidates):
                    char = _key_to_char(key)
                    lm = self._char_logprob(text, char)
                    rank_prior = -0.5 * rank  # favor higher-ranked classifier guesses
                    new_beams.append((text + char, score + lm + rank_prior))
            new_beams.sort(key=lambda tb: tb[1], reverse=True)
            beams = new_beams[: self.beam_width]

        if not beams:
            return "", 0.0
        return beams[0]
