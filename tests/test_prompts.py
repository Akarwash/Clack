"""Placeholder tests for `clack.prompts`, filled in BUILD_TRAINER.

The scaffold ships this file so the test tree is complete and importable. The
real behavioral tests (Hypothesis where section 11 calls for it) are written by
BUILD_TRAINER as part of its DONE. The module must import cleanly even as a stub.
"""

from __future__ import annotations

import importlib


def test_module_importable() -> None:
    """The target module imports (scaffold guarantee)."""
    assert importlib.import_module("clack.prompts") is not None
