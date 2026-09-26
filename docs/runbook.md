# Runbook (demo-day operations)

_Owner: BUILD_BACKEND (preflight) and BUILD_FRONTEND (demo order). Filled as
those plans complete._

## Preflight

Run before every demo and treat any failed item as blocking:

```bash
python scripts/preflight.py
```

It runs the same checks as `GET /status` and prints a checklist:

- `microphone`: at least one input device is present (names the default).
- `sample_rate`: the configured capture rate (44100).
- `keyboard_permission`: a pynput listener can be created. Note: on macOS an
  untrusted process prints "not trusted" and silently fails to capture rather than
  raising, so also confirm Input Monitoring and Accessibility are granted in System
  Settings before collecting training data.
- `model`: a trained model exists under `data/models/` (fails until you train).
- `attack_keylogger`: shows `DISABLED` (the pynput listener is not instantiated in
  attack mode; it reads `ENABLED (event mode)` only during a deliberate clean run).
- `speaker`: an output device is present (for the masker).
- `compute`: the detected device (cuda, mps, or cpu).
- `ambient_calibration`: reports not calibrated until an attack starts (calibration
  runs at attack time over the quiet room).

Start the server with `python scripts/serve.py` (it calls `ensure_dirs()` and
prints the dashboard and trainer URLs). Everything is local; venue wifi cannot
break the demo.

## Demo order

_To be written in BUILD_FRONTEND: the three-minute demo, spending about two
minutes on audit, defense, and verification._

## Fallbacks

_To be written: the event-mode clean run, the judge-picks-phrase-teammate-types
fallback, and the nearest-centroid floor model as the model fallback._

## Troubleshooting

_To be written: common failure modes and fixes._
