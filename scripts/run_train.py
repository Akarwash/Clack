"""Build a combined dataset from recorded sessions and train the model.

Discovers recording sessions under ``data/recordings/``, builds ONE combined
dataset across both boards' training sessions (BUILD_MODEL section 8A), holds out
the eval-purpose sessions for validation (session-level split), fits the centroid
floor, trains the CNN, and saves both with metrics and a confusion matrix. Runs
end to end once real data exists.

Owner: BUILD_MODEL.

Usage
-----
    python scripts/run_train.py --name combined
    python scripts/run_train.py --name combined --recordings data/recordings
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from clack import dataset as _dataset  # noqa: E402
from clack import train as _train  # noqa: E402
from clack.config_types import ensure_dirs  # noqa: E402


def _discover_sessions(recordings_dir: str) -> tuple[list[str], list[str]]:
    """Return (train_session_dirs, eval_session_ids) by reading each purpose."""
    train_dirs: list[str] = []
    eval_ids: list[str] = []
    if not os.path.isdir(recordings_dir):
        return train_dirs, eval_ids
    for name in sorted(os.listdir(recordings_dir)):
        session_dir = os.path.join(recordings_dir, name)
        events_path = os.path.join(session_dir, "events.json")
        if not os.path.isfile(events_path):
            continue
        with open(events_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        purpose = meta.get("purpose", "train")
        if purpose in ("train", "eval"):
            train_dirs.append(session_dir)
        if purpose == "eval":
            eval_ids.append(meta.get("session_id", name))
    return train_dirs, eval_ids


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the Clack model from recorded sessions.")
    parser.add_argument("--name", default="combined", help="output model name")
    parser.add_argument("--recordings", default=config.RECORDINGS_DIR, help="recordings directory")
    parser.add_argument("--val-fraction", type=float, default=0.3, help="session holdout fraction if no eval sessions")
    parser.add_argument(
        "--drop-overlaps",
        action="store_true",
        help="exclude keystrokes flagged as contaminated (window overlaps a too-close neighbor)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for training."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    ensure_dirs()

    session_dirs, eval_ids = _discover_sessions(args.recordings)
    if not session_dirs:
        raise SystemExit(
            f"no recording sessions found under {args.recordings!r}. Collect data "
            "first with the trainer page or scripts/collect.py."
        )
    print(f"[run_train] {len(session_dirs)} sessions, {len(eval_ids)} held out for eval")

    ds = _dataset.build_dataset(session_dirs, drop_contaminated=args.drop_overlaps)
    dataset_path = os.path.join(config.DATASETS_DIR, f"{args.name}.npz")
    _dataset.save_dataset(ds, dataset_path)
    print(f"[run_train] cached dataset: {dataset_path}  (N={len(ds)})")

    result = _train.train_model(
        dataset_path,
        args.name,
        val_session_ids=eval_ids or None,
        val_fraction=args.val_fraction,
    )
    print(f"[run_train] saved model: {result.model_dir}")
    print(f"[run_train] floor model: {result.baseline_dir}")
    print(f"[run_train] metrics: acc={result.metrics.get('val_accuracy'):.3f} "
          f"top3={result.metrics.get('val_top3_accuracy'):.3f} "
          f"floor={result.metrics.get('centroid_val_accuracy'):.3f}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
