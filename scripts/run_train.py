"""Build datasets and train the combined model from recorded sessions.

Wires session recordings into a session-split dataset, trains the CNN and fits
the centroid floor, and saves the model (CLACK_BUILD_PLAN.md section 5). Runs
end to end once real data exists.

Owner: BUILD_MODEL.

Usage
-----
    python scripts/run_train.py --name combined
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for training.

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
