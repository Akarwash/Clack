"""Exposure Check: grade a keyboard setup's leakage risk via the attack (D1).

The audit any organization runs per endpoint: attack a short known sample,
measure recovery, and map it to a labeled Clack heuristic grade
(``config.EXPOSURE_GRADE_BANDS``; A is best, F is worst). This is a project
heuristic, not an industry standard, and the report is saved so the fleet view
(D3) can read it (``config.FLEET_REPORTS_DIR``).

Owner: BUILD_DEFENSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExposureReport:
    """A single endpoint's exposure assessment.

    Attributes
    ----------
    grade : str
        Letter grade from ``config.EXPOSURE_GRADE_BANDS`` (A..F).
    recovery : float
        Measured recovery fraction driving the grade.
    endpoint : str
        Identifier for the audited endpoint/keyboard.
    detail : dict
        Supporting metrics (onset recall, top-k, etc.).
    """

    grade: str
    recovery: float
    endpoint: str
    detail: dict = field(default_factory=dict)


def grade_recovery(recovery: float) -> str:
    """Map a recovery fraction to a Clack heuristic letter grade.

    Parameters
    ----------
    recovery : float
        Attack recovery in ``[0, 1]``.

    Returns
    -------
    str
        A grade in ``{"A", "B", "C", "D", "F"}`` per
        ``config.EXPOSURE_GRADE_BANDS``.
    """
    raise NotImplementedError("built in BUILD_DEFENSE")


def run_exposure_check(session_dir: str, model: object, endpoint: str, save: bool = True) -> ExposureReport:
    """Run the Exposure Check on a recording and optionally save the report.

    Parameters
    ----------
    session_dir : str
        A recording with ground-truth text to score recovery against.
    model : object
        The trained attack model.
    endpoint : str
        Identifier for the audited endpoint.
    save : bool, optional
        Whether to persist the report under ``config.FLEET_REPORTS_DIR``
        (default ``True``).

    Returns
    -------
    ExposureReport
        The grade and supporting detail.
    """
    raise NotImplementedError("built in BUILD_DEFENSE")


def load_fleet_reports(reports_dir: Optional[str] = None) -> list[ExposureReport]:
    """Load all saved exposure reports for the fleet view (D3).

    Parameters
    ----------
    reports_dir : str or None, optional
        Directory of saved reports; defaults to ``config.FLEET_REPORTS_DIR``.

    Returns
    -------
    list of ExposureReport
        Every saved report (possibly empty).
    """
    raise NotImplementedError("built in BUILD_DEFENSE")
