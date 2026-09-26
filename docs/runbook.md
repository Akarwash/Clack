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

The three-minute demo spends about two thirds of its time on the audit and
defense (that is where the 30% Security Improvement is won):

1. **Attack, fast (about 45s).** A judge picks a phrase and a teammate types it
   (the guaranteed fallback), or the judge types it. Clack recovers it live from
   sound, RAW next to CORRECTED. Point at the INPUT SOURCES line:
   `Microphone: ACTIVE, Keyboard Events: DISABLED`. "This is the threat, and it is
   real: 93% over a Zoom call in the research."
2. **Exposure Check (about 30s).** Run it on that sample; show the Clack Exposure
   Grade (labeled a heuristic) with its reasons. "Any org can run this on every
   laptop to find who is exposed."
3. **Arm Protected Typing (about 45s).** The continuous Standard Shield is on
   before typing; type the same phrase, the recovered text turns to garbage and the
   recovery bar craters. "The shield runs before you type, at the minimum effective
   level, a plus-N-dB masker ratio at the mic."
4. **Saved reports (about 20s).** Show audit reports from two or three machines.
   "Run the audit across every endpoint in an organization."

Close on the before/after bars: "Under our test setup, Clack cut recovery from X%
to Y%. A measured audit-and-mitigate loop against acoustic leakage."

Theme: press `D` (or the Theme button) to switch to the dark "projector" theme if
the room is bright. The `Clean run (event mode)` switch is the guaranteed clean
demo path; the `Wiring demo (synthetic)` switch drives the visuals without a mic or
model and is clearly badged, for plumbing only (never presented as a real result).

## Capturing the dashboard screenshot

Run `python scripts/serve.py`, open `http://127.0.0.1:8000/`, start an attack (or
the wiring demo), and capture the window. Save it as `docs/dashboard.png` and it
will appear in the README.

## Fallbacks

_To be written: the event-mode clean run, the judge-picks-phrase-teammate-types
fallback, and the nearest-centroid floor model as the model fallback._

## Troubleshooting

_To be written: common failure modes and fixes._
