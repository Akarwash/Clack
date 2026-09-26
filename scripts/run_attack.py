"""Run the offline attack on a held-out recording.

Loads a trained model and a recording, recovers the keystrokes, and prints the
raw and corrected text alongside metrics (CLACK_BUILD_PLAN.md section 5).

Owner: BUILD_MODEL.

Usage
-----
    python scripts/run_attack.py --model combined --session <session_dir>
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for the offline attack.

    Parameters
    ----------
    argv : list of str or None, optional
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Process exit code.
    """
    raise NotImplementedError("built in BUILD_MODEL")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
