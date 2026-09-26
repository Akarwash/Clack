"""Start the Clack server on localhost.

Ensures runtime directories, builds the FastAPI app, and serves the dashboard and
trainer with no network dependency (CLACK_BUILD_PLAN.md section 5).

Owner: BUILD_BACKEND.

Usage
-----
    python scripts/serve.py --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for the server.

    Parameters
    ----------
    argv : list of str or None, optional
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Process exit code.
    """
    raise NotImplementedError("built in BUILD_BACKEND")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
