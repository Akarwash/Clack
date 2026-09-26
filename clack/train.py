"""Training loop, seeding, device detection, and run logging.

Trains :class:`clack.model.ClackCNN` on a session-split dataset with class-weighted
loss, a plateau scheduler, and early stopping, seeds all RNGs from ``config.SEED``,
detects the compute device once (CUDA, else Apple MPS, else CPU), fits the
:class:`clack.model.CentroidBaseline` floor alongside, and logs the config used
for every run. Never trains a real model inside a test.

Owner: BUILD_MODEL.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

import config
from clack import dataset as _dataset
from clack import model as _model


@dataclass
class TrainResult:
    """Outcome of a training run.

    Attributes
    ----------
    model_dir : str
        Where the trained CNN was saved.
    baseline_dir : str
        Where the centroid floor was saved.
    metrics : dict
        Final validation metrics (overall/top-3 accuracy, per-key, floor).
    device : str
        The compute device used (``cuda``, ``mps``, or ``cpu``).
    """

    model_dir: str
    baseline_dir: str
    metrics: dict = field(default_factory=dict)
    device: str = "cpu"


def detect_device() -> str:
    """Detect the compute device once (CUDA, else MPS, else CPU).

    Returns
    -------
    str
        One of ``"cuda"``, ``"mps"``, or ``"cpu"``.
    """
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def set_seed(seed: Optional[int] = None) -> None:
    """Seed all RNGs for deterministic runs.

    Parameters
    ----------
    seed : int or None, optional
        Seed value; defaults to ``config.SEED``.
    """
    s = config.SEED if seed is None else seed
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


def _accuracy(pred_top1: np.ndarray, y: np.ndarray) -> float:
    return float((pred_top1 == y).mean()) if y.size else 0.0


def _topk_accuracy(topk: np.ndarray, y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    return float(np.mean([yt in row for yt, row in zip(y, topk)]))


def _per_key_accuracy(pred_top1: np.ndarray, y: np.ndarray, classes: list[str]) -> dict:
    out: dict[str, float] = {}
    for c, name in enumerate(classes):
        mask = y == c
        if mask.any():
            out[name] = float((pred_top1[mask] == c).mean())
    return out


def _save_confusion(y_true: np.ndarray, y_pred: np.ndarray, classes: list[str], path: str) -> None:
    """Render a confusion matrix PNG (Agg backend, no display)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(classes)
    cm = np.zeros((n, n), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(cm, cmap="magma")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(classes, fontsize=6, rotation=90)
    ax.set_yticklabels(classes, fontsize=6)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Clack confusion matrix (validation)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def train_model(
    dataset_path: str,
    model_name: str,
    val_session_ids: Optional[list[str]] = None,
    val_fraction: float = 0.3,
    epochs: Optional[int] = None,
) -> TrainResult:
    """Train the CNN classifier and fit the centroid floor on a session split.

    Parameters
    ----------
    dataset_path : str
        Path to a combined ``.npz`` dataset (both boards' training sessions).
    model_name : str
        Base name for the output model directories under ``config.MODELS_DIR``.
    val_session_ids : list of str or None, optional
        Sessions to hold out for validation (default: a session-level fraction).
    val_fraction : float, optional
        Fraction of sessions to hold out when ``val_session_ids`` is ``None``.
    epochs : int or None, optional
        Max epochs; defaults to ``config.EPOCHS``.

    Returns
    -------
    TrainResult
        The saved model directories, metrics, and device used.

    Raises
    ------
    FileNotFoundError
        If ``dataset_path`` is missing.
    """
    set_seed()
    device = detect_device()
    print(f"[train] device: {device}")

    ds = _dataset.load_dataset(dataset_path)
    train_ds, val_ds = _dataset.split_by_session(ds, val_session_ids, val_fraction)
    classes = ds.classes
    n_classes = len(classes)

    counts = np.bincount(train_ds.y, minlength=n_classes)
    low = [classes[i] for i, c in enumerate(counts) if 0 < c < config.TRAIN_SAMPLES_PER_KEY]
    if low:
        print(f"[train] WARNING: keys below {config.TRAIN_SAMPLES_PER_KEY} samples: {low}")

    # Floor: centroid baseline, saved even if the CNN step fails.
    baseline = _model.CentroidBaseline().fit(train_ds.X, train_ds.y)
    base_top1 = baseline.predict_topk(val_ds.X, k=1)[:, 0]
    base_acc = _accuracy(base_top1, val_ds.y)
    baseline_dir = os.path.join(config.MODELS_DIR, f"{model_name}-centroid")
    _model.save_model(baseline, baseline_dir, metrics={"val_accuracy": base_acc})
    print(f"[train] centroid floor val accuracy: {base_acc:.3f}")

    # CNN.
    net = _model.ClackCNN(n_classes).to(device)
    weights = torch.tensor(_dataset.class_weights(train_ds.y, n_classes), device=device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(net.parameters(), lr=config.LR, weight_decay=config.WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=3)

    val_x = torch.from_numpy(val_ds.X[:, None, :, :]).to(device)
    val_y = torch.from_numpy(val_ds.y).to(device)
    max_epochs = epochs or config.EPOCHS

    best_state = None
    best_val = float("inf")
    patience = 0
    losses: list[float] = []
    n = train_ds.X.shape[0]
    rng = np.random.default_rng(config.SEED)

    for epoch in range(max_epochs):
        net.train()
        perm = rng.permutation(n)
        epoch_loss = 0.0
        for start in range(0, n, config.BATCH_SIZE):
            idx = perm[start : start + config.BATCH_SIZE]
            # SpecAugment on the fly (train only).
            batch = np.stack([_dataset.spec_augment(train_ds.X[i], seed=int(rng.integers(1 << 30))) for i in idx])
            xb = torch.from_numpy(batch[:, None, :, :]).to(device)
            yb = torch.from_numpy(train_ds.y[idx]).to(device)
            optimizer.zero_grad()
            loss = criterion(net(xb), yb)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss) * len(idx)
        epoch_loss /= n
        losses.append(epoch_loss)

        net.eval()
        with torch.no_grad():
            val_loss = float(criterion(net(val_x), val_y))
        scheduler.step(val_loss)
        if val_loss < best_val - 1e-4:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
            patience = 0
        else:
            patience += 1
            if patience >= config.EARLY_STOP_PATIENCE:
                print(f"[train] early stop at epoch {epoch}")
                break

    if best_state is not None:
        net.load_state_dict(best_state)

    # Validation metrics.
    val_scores = net.scores(val_ds.X)
    top1 = val_scores.argmax(axis=1)
    top3 = _model._topk_from_scores(val_scores, 3)
    metrics = {
        "val_accuracy": _accuracy(top1, val_ds.y),
        "val_top3_accuracy": _topk_accuracy(top3, val_ds.y),
        "per_key_accuracy": _per_key_accuracy(top1, val_ds.y, classes),
        "centroid_val_accuracy": base_acc,
        "loss_curve": losses,
        "n_train": int(n),
        "n_val": int(val_ds.X.shape[0]),
        "val_sessions": sorted(set(val_ds.session_ids.tolist())),
    }
    per_key = metrics["per_key_accuracy"]
    worst = sorted(per_key.items(), key=lambda kv: kv[1])[:5]
    print(f"[train] CNN val acc {metrics['val_accuracy']:.3f}  top-3 {metrics['val_top3_accuracy']:.3f}")
    print(f"[train] five worst keys: {worst}")

    model_dir = os.path.join(config.MODELS_DIR, model_name)
    _model.save_model(net, model_dir, metrics=metrics)
    try:
        _save_confusion(val_ds.y, top1, classes, os.path.join(model_dir, "confusion_matrix.png"))
    except Exception as exc:  # pragma: no cover - plotting is non-critical
        print(f"[train] could not render confusion matrix: {exc}")

    return TrainResult(model_dir=model_dir, baseline_dir=baseline_dir, metrics=metrics, device=device)
