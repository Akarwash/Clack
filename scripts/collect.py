"""Terminal fallback for on-site data collection.

A no-browser paced collector for the first minutes on-site before the trainer web
page is wired (CLACK_BUILD_PLAN.md section 5; BUILD_TRAINER section 10). It prints
a balanced random-character prompt one character at a time on a metronome while
the backend records audio and key events on one clock, then stops and reports.
Writes a recording session to ``data/recordings/`` per the section 9 contract.

Owner: BUILD_TRAINER.

Usage
-----
    python scripts/collect.py --keyboard blue --typist akarsh --purpose train
    python scripts/collect.py --keyboard c3equalz --typist sam --purpose eval --mode paced
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Allow running as a plain script (python scripts/collect.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from clack import prompts, session  # noqa: E402
from clack.config_types import ensure_dirs  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clack terminal collector (paced fallback).")
    parser.add_argument("--keyboard", required=True, help="keyboard_id, for example blue or c3equalz")
    parser.add_argument("--typist", required=True, help="consenting typist identifier")
    parser.add_argument(
        "--purpose",
        default="train",
        choices=list(session.VALID_PURPOSES),
        help="train, eval, or demo",
    )
    parser.add_argument("--mode", default="paced", choices=["paced", "flow"], help="collection cadence")
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=config.TRAINER_PACED_GAP_MS,
        help="metronome gap in milliseconds (paced)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="number of prompted characters (default: one balanced pass at the purpose quota)",
    )
    parser.add_argument("--device", type=int, default=None, help="input device index (default: config.INPUT_DEVICE)")
    return parser.parse_args(argv)


def _quota_for(purpose: str) -> int:
    if purpose == "eval":
        return config.EVAL_SAMPLES_PER_KEY
    if purpose == "demo":
        return 0
    return config.TRAIN_SAMPLES_PER_KEY


def main(argv: list[str] | None = None) -> int:
    """Entry point for terminal collection.

    Parameters
    ----------
    argv : list of str or None, optional
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    ensure_dirs()

    quota = _quota_for(args.purpose)
    length = args.count or (quota * len(config.KEY_SET) if quota else 120)
    seq = prompts.balanced_sequence(length=length, seed=int(time.time()))

    print(f"Clack collector: keyboard={args.keyboard} typist={args.typist} "
          f"purpose={args.purpose} mode={args.mode} chars={len(seq)}")
    print("Press each shown key ONCE, bottom it out, release before the next beat.")
    print("Grant Input Monitoring permission if prompted. Ctrl-C stops early.\n")

    from clack.capture import Recorder

    recorder = Recorder(device=args.device)
    session_id = session.start_session(
        keyboard_id=args.keyboard,
        typist=args.typist,
        purpose=args.purpose,
        mode=args.mode,
        recorder=recorder,
    )

    gap_s = max(0.05, args.gap_ms / 1000.0)
    try:
        for i, ch in enumerate(seq):
            glyph = "space" if ch == "space" else ch
            sys.stdout.write(f"\r[{i + 1:>4}/{len(seq)}]  ->  {glyph}      ")
            sys.stdout.flush()
            time.sleep(gap_s)
    except KeyboardInterrupt:
        print("\nInterrupted; stopping and saving what was collected.")

    summary = session.stop_session(session_id)
    print(
        f"\n\nSaved: {summary['n_events']} events, "
        f"{summary['duration_s']:.1f}s\npath: {summary['path']}"
    )
    if summary["n_events"] == 0:
        print(
            "WARNING: zero key events captured. Check Input Monitoring permission "
            "and that this terminal had focus while typing.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
