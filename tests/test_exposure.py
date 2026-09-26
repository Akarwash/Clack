"""Tests for :mod:`clack.exposure` (Exposure Check grading and fleet reports).

Owner: BUILD_DEFENSE. Uses mock models (favoring the truth or a wrong key) on
synthetic sessions to drive high vs low recovery.
"""

from __future__ import annotations

import numpy as np

import config
from clack import exposure


class _MockModel:
    """A mock model that always favors one fixed class."""

    def __init__(self, favored_key: str) -> None:
        self.classes = list(config.KEY_SET)
        self._idx = self.classes.index(favored_key)

    def scores(self, X: np.ndarray) -> np.ndarray:
        n = np.asarray(X).shape[0]
        s = np.zeros((n, len(self.classes)), dtype=np.float32)
        s[:, self._idx] = 5.0
        return s


def test_grade_recovery_bands() -> None:
    """Grades follow EXPOSURE_GRADE_BANDS, including the B band."""
    assert exposure.grade_recovery(0.10) == "A"
    assert exposure.grade_recovery(0.20) == "B"
    assert exposure.grade_recovery(0.35) == "C"
    assert exposure.grade_recovery(0.55) == "D"
    assert exposure.grade_recovery(0.90) == "F"


def test_check_exposure_high_recovery_is_poor(tmp_session) -> None:
    """A sample the attack recovers well grades F with concrete reasons."""
    session = tmp_session(keys=["a"] * 6, keyboard_id="blue")
    model = _MockModel("a")  # always predicts the truth -> high recovery
    result = exposure.check_exposure(model, session)
    assert result["grade"] == "F"
    assert result["recovery"] > 0.6
    assert len(result["reasons"]) >= 1
    assert len(result["recommendations"]) >= 1
    assert any("recovered" in r for r in result["reasons"])


def test_check_exposure_low_recovery_is_good(tmp_session) -> None:
    """A sample the attack fails on grades A."""
    session = tmp_session(keys=["a"] * 6, keyboard_id="blue")
    model = _MockModel("z")  # always wrong -> low recovery
    result = exposure.check_exposure(model, session)
    assert result["grade"] == "A"
    assert result["recovery"] < 0.15


def test_fleet_reports_roundtrip_newest_first(tmp_path) -> None:
    """Writing two reports then loading returns both, newest first."""
    reports_dir = str(tmp_path / "reports")
    exposure.save_report({"machine_id": "laptop-1", "grade": "F", "timestamp": "2026-09-26T10:00:00"}, reports_dir)
    exposure.save_report({"machine_id": "laptop-2", "grade": "B", "timestamp": "2026-09-26T11:00:00"}, reports_dir)
    loaded = exposure.load_fleet_reports(reports_dir)
    assert len(loaded) == 2
    assert loaded[0]["machine_id"] == "laptop-2"  # newest first
    assert loaded[1]["machine_id"] == "laptop-1"


def test_load_fleet_reports_empty(tmp_path) -> None:
    """An empty or missing directory yields an empty list."""
    assert exposure.load_fleet_reports(str(tmp_path / "nope")) == []


def test_run_exposure_check_saves_report(tmp_session, tmp_path) -> None:
    """run_exposure_check returns a report and saves a fleet entry."""
    session = tmp_session(keys=["a"] * 5, keyboard_id="blue")
    reports_dir = str(tmp_path / "reports")
    report = exposure.run_exposure_check(session, _MockModel("a"), endpoint="laptop-x", reports_dir=reports_dir)
    assert report.grade == "F"
    saved = exposure.load_fleet_reports(reports_dir)
    assert len(saved) == 1
    assert saved[0]["machine_id"] == "laptop-x"
