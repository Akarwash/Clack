"""Demo-day preflight checks.

Verifies the environment before a demo: microphone present and permitted, compute
device detected, a trained model available, UI assets self-hosted (no CDN), and
runtime directories writable. Fails loudly with a clear report
(CLACK_BUILD_PLAN.md sections 5 and 13; docs/runbook.md).

Owner: BUILD_BACKEND.

Usage
-----
    python scripts/preflight.py
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for preflight.

    Parameters
    ----------
    argv : list of str or None, optional
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Process exit code (``0`` if all checks pass, non-zero otherwise).
    """
    raise NotImplementedError("built in BUILD_BACKEND")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
