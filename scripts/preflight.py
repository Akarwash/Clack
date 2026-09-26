"""Demo-day preflight checks.

Runs the same readiness checks as ``GET /status`` from the terminal and prints the
checklist. Run it before every demo and treat any failed item as blocking. Fails
loudly with a clear report (CLACK_BUILD_PLAN.md sections 5 and 13;
docs/runbook.md).

Owner: BUILD_BACKEND.

Usage
-----
    python scripts/preflight.py
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clack.config_types import ensure_dirs  # noqa: E402
from clack.server import build_status  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Entry point for preflight.

    Returns
    -------
    int
        ``0`` if all checks pass, the count of failures otherwise.
    """
    ensure_dirs()
    shim = SimpleNamespace(state=SimpleNamespace(attack={}))
    report = build_status(shim)

    print("Clack preflight checklist")
    print("=" * 32)
    failures = 0
    for name, item in report.items():
        ok = bool(item.get("ok"))
        mark = "PASS" if ok else "FAIL"
        detail = {k: v for k, v in item.items() if k != "ok"}
        detail_str = f"  {detail}" if detail else ""
        print(f"[{mark}] {name}{detail_str}")
        if not ok:
            failures += 1

    print("=" * 32)
    if failures:
        print(f"{failures} check(s) failed. Resolve them before the demo.", file=sys.stderr)
    else:
        print("All checks passed.")
    return failures


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
