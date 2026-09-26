"""Exposure Check: grade a keyboard setup's leakage risk via the attack (D1).

The audit any organization runs per endpoint: attack a short typing sample,
measure how much an attacker would recover, and map it to a labeled Clack Exposure
Grade (A to F) with concrete reasons and recommendations. This is what turns Clack
from an attack demo into a posture tool. The grade is a Clack heuristic based on
measured recoverability, NOT an industry cybersecurity rating, and the UI and
README say so.

Reports are saved so the fleet view (D3) can read them
(``config.FLEET_REPORTS_DIR``); D3 reads saved reports from disk, not live
heartbeats.

Owner: BUILD_DEFENSE.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

import config
from clack import segment as _segment


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
        ``config.EXPOSURE_GRADE_BANDS`` (A best, F worst). ``recovery <= 0.15`` is
        A, ``<= 0.25`` B, ``<= 0.40`` C, ``<= 0.60`` D, else F.
    """
    bands = config.EXPOSURE_GRADE_BANDS
    for grade in ("A", "B", "C", "D"):
        if recovery <= bands[grade]:
            return grade
    return "F"


def compute_snr(audio: np.ndarray, sample_rate: int) -> float:
    """Estimate keystroke SNR in dB: onset-frame energy over the noise floor.

    Parameters
    ----------
    audio : numpy.ndarray
        A recording of the keyboard.
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    float
        SNR in dB (``0.0`` if no clear onsets or no signal).
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return 0.0
    energy, _, threshold = _segment._energy_and_threshold(audio, sample_rate)
    if energy.size == 0:
        return 0.0
    onset_frames = energy[energy > threshold]
    noise_frames = energy[energy <= threshold]
    if onset_frames.size == 0 or noise_frames.size == 0:
        return 0.0
    onset_e = float(np.mean(onset_frames))
    noise_e = float(np.mean(noise_frames)) or 1e-12
    return 10.0 * math.log10(max(onset_e / noise_e, 1e-12))


@dataclass
class ExposureReport:
    """A single endpoint's exposure assessment.

    Attributes
    ----------
    grade : str
        Letter grade from ``config.EXPOSURE_GRADE_BANDS`` (A..F).
    recovery : float
        Measured recovery fraction driving the grade.
    snr : float
        Keystroke SNR in dB.
    endpoint : str
        Identifier for the audited endpoint/keyboard.
    reasons : list of str
        Concrete reasons for the grade.
    recommendations : list of str
        Concrete mitigations.
    detail : dict
        Supporting metrics.
    """

    grade: str
    recovery: float
    snr: float
    endpoint: str
    reasons: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Return a JSON-serializable dict of the report."""
        return {
            "grade": self.grade,
            "recovery": self.recovery,
            "snr": self.snr,
            "endpoint": self.endpoint,
            "reasons": list(self.reasons),
            "recommendations": list(self.recommendations),
            "detail": dict(self.detail),
        }


def check_exposure(model: object, sample_session: str) -> dict:
    """Assess acoustic exposure for a typing sample (the D1 audit).

    Runs the real attack on the sample, measures recovery and keystroke SNR, and
    returns a labeled Clack Exposure Grade with reasons and recommendations.

    Parameters
    ----------
    model : object
        The trained attack model.
    sample_session : str
        A recording session (with ground-truth events) to audit.

    Returns
    -------
    dict
        ``{grade, recovery, snr, reasons, recommendations, detail}``. The grade is
        a Clack heuristic based on measured recoverability, not an industry rating.
    """
    import soundfile as sf

    from clack import evaluate as _evaluate

    wav_path = os.path.join(sample_session, "audio.wav")
    if not os.path.isfile(wav_path):
        raise FileNotFoundError(f"sample session missing audio.wav: {sample_session}")
    audio, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)

    metrics = _evaluate.evaluate_attack(model, sample_session)
    recovery = float(metrics["raw"]["top1"])
    snr = compute_snr(audio, int(sr))
    grade = grade_recovery(recovery)

    reasons: list[str] = [f"the attack recovered {recovery * 100:.0f}% of your text"]
    if snr >= 15:
        reasons.append(f"your keystrokes are loud and distinct (SNR {snr:.0f} dB)")
    elif snr > 0:
        reasons.append(f"keystroke SNR is {snr:.0f} dB")
    top3 = metrics["raw"]["topk"].get(3)
    if top3 is not None:
        reasons.append(f"top-3 recall is {top3 * 100:.0f}% (a password search space collapse)")

    recommendations = [
        "enable Protected Typing (the acoustic masker) before typing secrets",
        "move the microphone away from the keyboard",
        "avoid typing passwords while on a video or voice call",
    ]
    if snr >= 15:
        recommendations.append("consider a quieter keyboard switch")

    return ExposureReport(
        grade=grade,
        recovery=recovery,
        snr=snr,
        endpoint=metrics.get("keyboard_id", "unknown"),
        reasons=reasons,
        recommendations=recommendations,
        detail={"onset": metrics["onset"], "topk": metrics["raw"]["topk"]},
    ).as_dict()


def save_report(report: dict, reports_dir: Optional[str] = None) -> str:
    """Save an audit report JSON for the fleet view (D3).

    Parameters
    ----------
    report : dict
        A report with at least ``machine_id``/``endpoint`` and ``grade``.
    reports_dir : str or None, optional
        Directory to write into; defaults to ``config.FLEET_REPORTS_DIR``.

    Returns
    -------
    str
        The path of the written report file.
    """
    directory = reports_dir or config.FLEET_REPORTS_DIR
    os.makedirs(directory, exist_ok=True)
    report = dict(report)
    report.setdefault("timestamp", _dt.datetime.now().isoformat(timespec="seconds"))
    machine = report.get("machine_id") or report.get("endpoint", "endpoint")
    safe = "".join(c if c.isalnum() else "-" for c in str(machine))
    stamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    path = os.path.join(directory, f"{safe}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return path


def load_fleet_reports(reports_dir: Optional[str] = None) -> list[dict]:
    """Load all saved audit reports, newest first (the D3 fleet view).

    Parameters
    ----------
    reports_dir : str or None, optional
        Directory of saved reports; defaults to ``config.FLEET_REPORTS_DIR``.

    Returns
    -------
    list of dict
        Every saved report (possibly empty), newest first by timestamp.
    """
    directory = reports_dir or config.FLEET_REPORTS_DIR
    if not os.path.isdir(directory):
        return []
    reports: list[dict] = []
    for name in os.listdir(directory):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                reports.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    reports.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return reports


def run_exposure_check(
    session_dir: str,
    model: object,
    endpoint: str,
    save: bool = True,
    reports_dir: Optional[str] = None,
    defense_result: Optional[dict] = None,
) -> ExposureReport:
    """Run the Exposure Check and optionally save a fleet report.

    Parameters
    ----------
    session_dir : str
        A recording with ground-truth text to score recovery against.
    model : object
        The trained attack model.
    endpoint : str
        Identifier for the audited endpoint (the fleet ``machine_id``).
    save : bool, optional
        Whether to persist a fleet report (default ``True``).
    reports_dir : str or None, optional
        Where to save; defaults to ``config.FLEET_REPORTS_DIR``.
    defense_result : dict or None, optional
        Optional before/after defense measurement to include in the saved report.

    Returns
    -------
    ExposureReport
        The grade and supporting detail.
    """
    data = check_exposure(model, session_dir)
    report = ExposureReport(
        grade=data["grade"],
        recovery=data["recovery"],
        snr=data["snr"],
        endpoint=endpoint,
        reasons=data["reasons"],
        recommendations=data["recommendations"],
        detail=data["detail"],
    )
    if save:
        fleet_entry = {
            "machine_id": endpoint,
            "grade": report.grade,
            "off_recovery": (defense_result or {}).get("off", report.recovery),
            "on_recovery": (defense_result or {}).get("on"),
            "masker_ratio_db": (defense_result or {}).get("masker_key_ratio_db"),
        }
        save_report(fleet_entry, reports_dir=reports_dir)
    return report
