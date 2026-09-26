"""Training loop, seeding, and run logging.

Trains :class:`clack.model.ClackCNN` on a session-split dataset with early
stopping, seeds all RNGs from ``config.SEED``, detects the compute device once
(CUDA, else MPS, else CPU), and logs the config used for every run. Also fits the
:class:`clack.model.CentroidBaseline` floor alongside.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TrainResult:
    """Outcome of a training run.

    Attributes
    ----------
    model_dir : str
        Where the trained model was saved.
    metrics : dict
        Final validation metrics.
    device : str
        The compute device used (``cuda``, ``mps``, or ``cpu``).
    """

    model_dir: str
    metrics: dict
    device: str


def detect_device() -> str:
    """Detect the compute device once (CUDA, else MPS, else CPU).

    Returns
    -------
    str
        One of ``"cuda"``, ``"mps"``, or ``"cpu"``.
    """
    raise NotImplementedError("built in BUILD_MODEL")


def set_seed(seed: Optional[int] = None) -> None:
    """Seed all RNGs for deterministic runs.

    Parameters
    ----------
    seed : int or None, optional
        Seed value; defaults to ``config.SEED``.
    """
    raise NotImplementedError("built in BUILD_MODEL")


def train_cnn(train_dataset_path: str, val_dataset_path: str, model_name: str) -> TrainResult:
    """Train the CNN classifier and fit the centroid floor.

    Parameters
    ----------
    train_dataset_path : str
        Path to the training ``.npz`` dataset.
    val_dataset_path : str
        Path to a SEPARATE-session validation ``.npz`` dataset.
    model_name : str
        Name for the output model directory under ``config.MODELS_DIR``.

    Returns
    -------
    TrainResult
        The saved model directory, metrics, and device used.

    Raises
    ------
    FileNotFoundError
        If a dataset path is missing.
    """
    raise NotImplementedError("built in BUILD_MODEL")
