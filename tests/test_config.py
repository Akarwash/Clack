"""Real scaffold test: every module imports and the config invariants hold.

This is the one guaranteed-green test the scaffold ships (CLACK_BUILD_PLAN.md
section 12, step 9). It asserts that every ``clack`` module imports without error
and that the derived config values are real attributes with the specified values.
"""

from __future__ import annotations

import importlib

import pytest

import config

CLACK_MODULES = [
    "clack",
    "clack.config_types",
    "clack.capture",
    "clack.keylog",
    "clack.prompts",
    "clack.session",
    "clack.segment",
    "clack.features",
    "clack.dataset",
    "clack.model",
    "clack.train",
    "clack.attack",
    "clack.calibrate",
    "clack.evaluate",
    "clack.stream",
    "clack.correct",
    "clack.defense",
    "clack.exposure",
    "clack.server",
]


@pytest.mark.parametrize("module_name", CLACK_MODULES)
def test_module_imports(module_name: str) -> None:
    """Every clack module imports cleanly (stubs must not break the harness)."""
    assert importlib.import_module(module_name) is not None


def test_window_samples_value() -> None:
    """WINDOW_SAMPLES is a real attribute equal to 8820."""
    assert config.WINDOW_SAMPLES == 8820
    assert config.WINDOW_SAMPLES == int(config.SAMPLE_RATE * config.WINDOW_MS / 1000)


def test_spec_frames_value() -> None:
    """SPEC_FRAMES is a real attribute matching WINDOW_SAMPLES // HOP_LENGTH + 1."""
    assert config.SPEC_FRAMES == config.WINDOW_SAMPLES // config.HOP_LENGTH + 1


def test_key_set_shape() -> None:
    """The class set is 26 letters + 10 digits + space = 37 classes."""
    assert len(config.KEY_SET) == 37
    assert config.KEY_SET[-1] == "space"


def test_ensure_dirs_creates_runtime_tree(tmp_path, monkeypatch) -> None:
    """ensure_dirs creates the data subtree and is idempotent."""
    import os

    from clack import config_types

    targets = {
        "RECORDINGS_DIR": "data/recordings",
        "DATASETS_DIR": "data/datasets",
        "MODELS_DIR": "data/models",
        "CORPUS_DIR": "data/corpus",
        "REPORTS_DIR": "data/reports",
    }
    for attr, rel in targets.items():
        monkeypatch.setattr(config, attr, os.path.join(str(tmp_path), rel))

    config_types.ensure_dirs()
    config_types.ensure_dirs()  # idempotent
    for attr in targets:
        assert os.path.isdir(getattr(config, attr))


def test_load_config_snapshot() -> None:
    """The typed config snapshot mirrors the flat config values."""
    from clack import config_types

    cfg = config_types.load_config()
    assert cfg.audio.sample_rate == config.SAMPLE_RATE
    assert cfg.window.window_samples == config.WINDOW_SAMPLES
    assert cfg.spectrogram.spec_frames == config.SPEC_FRAMES
    assert cfg.key_set == list(config.KEY_SET)
