"""Placeholder tests for `clack.correct`, filled in BUILD_BACKEND.

The scaffold ships this file so the test tree is complete and importable. The
real behavioral tests (Hypothesis where section 11 calls for it) are written by
BUILD_BACKEND as part of its DONE. The module must import cleanly even as a stub.
"""

from __future__ import annotations

import importlib


def test_module_importable() -> None:
    """The target module imports (scaffold guarantee)."""
    assert importlib.import_module("clack.correct") is not None
