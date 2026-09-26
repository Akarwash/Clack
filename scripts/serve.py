"""Start the Clack server on localhost.

Ensures runtime directories, builds the FastAPI app, and serves the dashboard and
trainer with no network dependency (fonts and libraries are self-hosted).

Owner: BUILD_BACKEND.

Usage
-----
    python scripts/serve.py --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clack.config_types import ensure_dirs  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Clack dashboard and trainer.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the server."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    ensure_dirs()

    import uvicorn

    print(f"Clack dashboard: http://{args.host}:{args.port}/")
    print(f"Clack trainer  : http://{args.host}:{args.port}/trainer")
    print("Everything runs locally with no network dependency.")
    uvicorn.run("clack.server:app", host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
