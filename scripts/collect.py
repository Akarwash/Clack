"""Terminal fallback for on-site data collection.

Runs a paced, coverage-driven collection session from the terminal when the
trainer web page is not yet wired (CLACK_BUILD_PLAN.md section 5). Writes a
recording session to ``data/recordings/`` per the section 9 contract.

Owner: BUILD_TRAINER.

Usage
-----
    python scripts/collect.py --keyboard blue --typist akarsh --purpose train
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for terminal collection.

    Parameters
    ----------
    argv : list of str or None, optional
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Process exit code.
    """
    raise NotImplementedError("built in BUILD_TRAINER")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
