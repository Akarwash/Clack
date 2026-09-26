"""Run the offline attack on a held-out recording.

Loads a trained model and a recording, recovers the keystrokes from audio only,
and prints the RAW recovered text next to the language-corrected text (when the
corrector is available) plus the password top-k search-space reduction. If the
recording carries ground-truth events, the full metric report from
:mod:`clack.evaluate` is printed too.

Owner: BUILD_MODEL.

Usage
-----
    python scripts/run_attack.py --model data/models/combined --session <session_dir>
    python scripts/run_attack.py --model data/models/combined --wav path/to/audio.wav
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from clack import attack as _attack  # noqa: E402
from clack import model as _model  # noqa: E402
from clack.config_types import ensure_dirs  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attack a recording with a trained Clack model.")
    parser.add_argument("--model", required=True, help="model directory under data/models/")
    parser.add_argument("--session", default=None, help="a recording session directory")
    parser.add_argument("--wav", default=None, help="a WAV file (alternative to --session)")
    parser.add_argument("--k", type=int, default=5, help="candidates per press")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the offline attack."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    ensure_dirs()

    model = _model.load_model(args.model)

    if args.wav:
        result = _attack.attack_wav(args.wav, model, k=args.k)
    elif args.session:
        wav = os.path.join(args.session, "audio.wav")
        result = _attack.attack_wav(wav, model, k=args.k)
    else:
        raise SystemExit("provide --session or --wav")

    print(f"presses: {result.meta['n_presses']}")
    print(f"RAW      : {result.text!r}")

    # Language correction, if the local corrector is available.
    try:
        from clack.correct import NgramCorrector

        corrector = NgramCorrector()
        lattice = [[kk for kk, _ in pk["topk"]] for pk in result.per_key]
        corrected = corrector.correct(lattice)
        print(f"CORRECTED: {corrected!r}")
    except NotImplementedError:
        print("CORRECTED: (corrector not built yet)")
    except Exception as exc:  # pragma: no cover - corpus/setup dependent
        print(f"CORRECTED: (unavailable: {exc})")

    space = _attack.password_search_space(result.topk, top_n=3)
    print(f"password top-3-per-position search space: {space}")

    # Full metrics if the recording carries ground truth.
    if args.session:
        try:
            from clack import evaluate as _evaluate

            report = _evaluate.evaluate_recording(args.session, model, correct=True)
            print("\n== evaluation ==")
            print(f"onset recall     : {report.onset_recall:.3f}")
            print(f"top-k recall     : {report.topk_recall}")
            print(f"CER raw/corrected: {report.cer_raw:.3f} / {report.cer_corrected:.3f}")
            print(f"median latency ms: {report.latency_ms:.1f}")
        except NotImplementedError:
            print("\n(metrics: evaluate.py not built yet)")
        except Exception as exc:  # pragma: no cover
            print(f"\n(metrics unavailable: {exc})")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
