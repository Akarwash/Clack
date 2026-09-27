# Clack

**An acoustic side-channel security auditor.** Clack measures how vulnerable a
keyboard environment is to microphone-based keystroke inference, demonstrates the
leakage live, applies an acoustic countermeasure, and quantitatively verifies the
reduction.

```
AUDIT  ->  ATTACK SIMULATION  ->  DEFENSE  ->  VERIFY
(grade exposure) (prove leakage live) (apply masker) (measure the drop)
```

Clack is a defensive auditing tool whose attack step is how it proves and
measures leakage. The novelty is not the attack (acoustic keystroke inference is
established prior work): it is the closed loop that turns the attack into an
audit-and-verify tool an organization would actually run per endpoint.

Built for hackUMBC 2026 (Cyber track). Grounded in Harrison, Toreini, and
Mehrnezhad, "A Practical Deep Learning-Based Acoustic Side Channel Attack on
Keyboards," IEEE EuroS&PW 2023 (https://arxiv.org/abs/2308.01074), and extended
into a defensive tool. Clack's implementation is written fresh; no existing
implementation of the paper is copied.

> Honest claim: Clack reports measured reduction against its own attack in the
> tested environment ("under our test setup, Clack reduced recovery from X% to
> Y%"). It does not claim typing is made unrecoverable in general; a more robust
> attacker could exist.

## Screenshot

The dashboard is an editorial-minimal, single-page interface (warm paper, hairline
rules, mono data, one accent) with a light and a dark "projector" theme. The top
INPUT SOURCES line is the credibility statement: `Microphone: ACTIVE,
Keyboard Events: DISABLED`. Below it, the RAW model output sits next to the
language-CORRECTED text, with the live signal, top-3 confidence bars, an on-screen
keyboard that flashes the guessed key, the password search-space collapse, and the
defense panel (Protected Typing toggle, before/after recovery bars, Clack Exposure
Grade, and saved fleet reports).

To capture `docs/dashboard.png`: run `python scripts/serve.py`, open
`http://127.0.0.1:8000/`, start an attack, and screenshot the window (see
[docs/runbook.md](docs/runbook.md)). The whole page loads with no network.

## Install

For digital microphone protection, see [Protected Virtual Mic setup](docs/virtual-microphone.md).
It adds noise and decoy clicks to a BlackHole stream on macOS, separately from
speaker masking. Keystroke suppression is future work.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Everything runs on localhost, with no network call at demo time.

## Usage (by entry point)

```bash
# Collect auto-labeled training data (paced, coverage-driven)
python scripts/collect.py --keyboard blue --typist <name> --purpose train

# Build datasets and train the combined model (CNN + centroid floor)
python scripts/run_train.py --name combined

# Run the offline attack on a held-out recording
python scripts/run_attack.py --model combined --session <session_dir>

# Serve the dashboard and trainer on localhost
python scripts/serve.py --host 127.0.0.1 --port 8000

# Demo-day preflight checks
python scripts/preflight.py
```

The individual entry points are filled in by the component build plans; the
scaffold ships them as documented stubs.

## Threat Model

Clack defends against a **passive microphone near a keyboard**, including
keystrokes captured over a voice channel (a call, a meeting, a recording). Under
Clack's MVP threat model the target types at gaps of at least 250 ms (about 3 to
4 keys per second); faster overlapping entry is a stretch, claimed only if
demonstrated.

Clack does **not** defend against a compromised endpoint. An attacker who already
controls the machine can disable the defense, read keyboard events directly, or
capture the screen, and no acoustic masker helps against that. Clack addresses
the acoustic side channel only. See [docs/threat-model.md](docs/threat-model.md).

## User Controls

- Microphone choice (device selection) and keyboard profile.
- Calibration: ambient onset calibration at attack start, and few-shot
  cross-keyboard calibration for a new board.
- Defense toggle (arm/disarm the masker) and masker intensity.
- Local correction on/off (defaults to a fully local model; no network).
- Save or delete recordings.

## Data and Privacy

- Everything is local. Nothing is sent off the machine.
- Raw audio and key events live under `data/recordings/<session_id>/` and are
  gitignored. Recovered attack text is not persisted by default.
- Wipe a session by deleting its directory under `data/recordings/`.

## Known Limitations

- Keyboard-specific acoustics: a model trained on one board transfers only
  partially to a different, untrained board (the cross-keyboard stretch).
- Noisy rooms, distance from the mic, and different microphones degrade recovery.
- Unsupported punctuation and modifier combinations are out of the class set.
- Typist variability: a very different typist (force, rhythm) reduces accuracy.
- Fast, overlapping keystrokes below the MVP cadence are not guaranteed.

## Security Evaluation

Clack reports a reproducible before/after table (recovery with the defense off
vs on) plus onset recall, top-k keystroke recall, and raw vs corrected character
error rate. See [docs/evaluation.md](docs/evaluation.md). Numbers are only shown
when they can be reproduced live; the scaffold ships no fabricated results.

## Why This Is Defensive

- Consent-only training: Clack records only the team's own keyboards and
  consenting typists.
- No third-party target collection: it exploits no software and targets no
  person.
- The attack is used strictly as validation, to prove leakage exists and to
  measure how much the defense removes.
- Attack mode is provably microphone-only: the keyboard-event listener is never
  instantiated in attack mode, and the dashboard shows
  `Keyboard Events: DISABLED`.

## Research Attribution

Clack builds conceptually on Harrison, Toreini, and Mehrnezhad, "A Practical Deep
Learning-Based Acoustic Side Channel Attack on Keyboards," IEEE EuroS&PW 2023
(https://arxiv.org/abs/2308.01074). Borrowed conceptually: the log-Mel + CNN
keystroke-classification methodology and the onset-centered windowing idea. What
Clack adds: the closed defensive loop (Exposure Check audit, adaptive acoustic
masker, before/after verification, and a fleet view across endpoints), a
nearest-centroid floor model, and embedding-based cross-keyboard calibration.
`CITATION.cff` describes Clack itself, not the paper.

## Documentation

- [docs/architecture.md](docs/architecture.md) - system design and the pipeline.
- [docs/data-collection.md](docs/data-collection.md) - the physical operator
  protocol.
- [docs/threat-model.md](docs/threat-model.md) - what Clack does and does not
  defend against.
- [docs/evaluation.md](docs/evaluation.md) - metrics and the before/after table.
- [docs/runbook.md](docs/runbook.md) - demo-day operations and fallbacks.
- [docs/api.md](docs/api.md) - HTTP and WebSocket endpoints.

## License

MIT. See [LICENSE](LICENSE).
