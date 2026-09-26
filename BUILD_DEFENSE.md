# Clack — BUILD_DEFENSE.md

The defense is the product. Clack protects sensitive typing (passwords, secrets) from acoustic surveillance. The attack (BUILD_MODEL, BUILD_BACKEND) exists to prove the threat is real and to measure how well the defense stops it. This file owns the parts that win the Cyber rubric's 30% Security Improvement: a real, deployable defensive function any organization could run on its endpoints.

Read `CLACK_BUILD_PLAN.md` first. Commit regularly. Build the basic masker and measurement first (sections 3 to 4), then D1, D2, D3 in that order. Each has a stated DONE. Do not let the extra defense features block the working attack-plus-basic-defense demo, which is the floor.

Owns: `clack/defense.py`, `clack/exposure.py`, defense and exposure and fleet routes in `clack/server.py`, the defense panel contract used by the dashboard, and tests `tests/test_defense.py`, `tests/test_exposure.py`. (The dashboard's defense panel UI lives in `app.js`, owned by the FRONTEND agent, built against the contracts here.)

---

## 1. Why this is the center of the project

The rubric rewards a real cybersecurity function that an organization would use and deploy at scale. An attack alone does not score there; a defense does. So Clack is framed as protection, and the demo spends about two of its three minutes on defense: prove you are exposed, turn on the protection, watch the attack collapse, show it deployed across machines.

The threat is real and current: the 2023 paper recovered keystrokes at 93% over a Zoom call. Anyone typing a password while on a video call, in a shared office, or near any microphone is exposed. Clack is the countermeasure.

---

## 2. Threat model (state it explicitly, it is the answer to a sharp judge)

Clack defends against **passive nearby acoustic capture**: a microphone near the keyboard, or keystrokes carried over a voice or video channel (the 93%-over-Zoom threat). It does **not** claim to defend against a fully compromised endpoint that can disable the defense or read keyboard events directly; that is out of scope, and the README says so. Stating the boundary is what makes the defense credible rather than hand-wavy.

A sharp judge may say "isn't this just your speaker blasting noise next to your mic?" The honest answer: for the demo, co-located speaker and mic make the effect reliable to show; in a real deployment the masker is a small device near the protected keyboard. The narrowed threat model above is the real answer, not a dodge.

## 2A. Why the Mac's own speakers are enough (for the demo)

Speaker and microphone are inches apart in the same laptop, so the masker reaches the mic at a high level without volume effort. Co-location helps the defense. Two requirements: capture raw audio with OS processing off (no echo cancellation, noise suppression, auto gain), and keep the masker band where laptop speakers are strong (1 to 10 kHz), which is exactly where keystroke energy lives.

---

## 3. The masker (`defense.py`, base version)

Two components, summed and played on a loop through the default output device via sounddevice.
1. **Band-limited noise:** white noise band-pass filtered to `MASKER_BAND_HZ` (1000 to 10000 Hz) with a Butterworth filter, scaled to `MASKER_LEVEL` (0.3).
2. **Fake keystroke transients:** short click-like bursts injected at jittered intervals (every 40 to 120 ms) so the attack's onset detector fires on phantom presses.

Interface:
- `class Masker`: `start()` (background `OutputStream`, non-blocking), `stop()`, `is_on() -> bool`.

---

## 4. Measurement (the honest before/after)

- `measure(model, text, masker) -> {"off_acc", "on_acc", "off_cer", "on_cer", "delta", "masker_key_ratio_db"}`: type a fixed known `text` with the masker off, run the attack, compute recovery; repeat with the masker on; return both plus the delta. Use `evaluate.py` (BUILD_EVAL) for the actual metrics (top-1, CER) so the numbers match everywhere. Type the SAME fixed text both times, from a session not used in training.
- **Report the masker level as received at the mic, not just the digital amplitude.** `MASKER_LEVEL=0.3` means nothing without the speaker volume, so measure RMS at the microphone: keystroke RMS (dBFS), masked-environment RMS (dBFS), and the effective masker-to-keystroke ratio in dB (for example "keys -31 dBFS, masked -19 dBFS, +12 dB"). This makes the result reproducible and credible, and it is what you show, not the raw `0.3`.
- Report the real measured drop under your test setup. A believable "recovery fell from X% to Y% at a +N dB masker ratio" beats "100 percent blocked".

**DONE (base):** the masker plays and stops cleanly, and `measure()` returns off vs on accuracy over the same text with a clear drop.

---

## 5. D1: Exposure Check (the rubric-closer, must-have)

A one-button "am I vulnerable?" assessment. This is what turns Clack from an attack demo into a posture tool an organization runs on every endpoint.

`exposure.py`:
- `check_exposure(model, sample_session) -> dict`: take a short typing sample (recorded via the trainer flow or a quick record), and compute:
  - **Recovery:** run the real attack on the sample, character accuracy `R` (how much an attacker would recover).
  - **Signal metrics:** keystroke SNR (onset energy over the noise floor) and per-key distinguishability (mean classifier confidence or embedding separation).
  - **Grade (the "Clack Exposure Grade"):** map exposure to A to F by recovery `R` using `EXPOSURE_GRADE_BANDS` = {A: 0.15, B: 0.25, C: 0.40, D: 0.60} (above D is F), combined with SNR so a loud, distinct keyboard is flagged even before a full attack. Label it clearly as a Clack heuristic based on measured recoverability, NOT an industry cybersecurity rating, on the UI and in the README. Include the B band (do not skip it).
  - **Reasons:** concrete strings, for example "the attack recovered 82% of your text", "your keystrokes are loud and distinct (high SNR)", "microphone is close to the keyboard".
  - **Recommendations:** enable the masker, move the mic away, use a quieter switch, avoid typing secrets on video calls.
- Return `{grade, recovery, snr, reasons: [...], recommendations: [...]}`.

Route: `POST /exposure/check` body references a recorded sample id -> the dict above.

Why it scores: this is a real cybersecurity function ("assess acoustic exposure"), it is usable by any organization (run it on staff laptops), and it runs per endpoint, which is the honest form of "scalable across an organization."

Tests (`test_exposure.py`): on a synthetic high-recovery sample the grade is poor (F) and on a masked or low-SNR sample the grade is good (A); reasons and recommendations are non-empty and match the metrics.

**DONE (D1):** running Exposure Check on a typing sample returns a risk grade with specific reasons and recommendations, driven by the real attack.

---

## 6. D2: Adaptive, minimum-effective masker (upgrade `defense.py`)

Make the masker something a person would actually leave running, and turn it into a real usability-vs-security result. Two shield modes:

- **Standard Shield (the guaranteed defense): continuous masker while "Protected Typing" is armed.** The masker is already running before the user types, so no identifying transient reaches the mic unmasked. This is the guaranteed demo path: arm the shield, then type. Do NOT make triggering part of the guaranteed path.
- **Smart Shield (stretch): triggered masking** that plays only while typing is detected, for lower friction. This is an optimization, off by default (`MASKER_TRIGGERED=False`), because a triggered masker can fire after the press onset has already been captured. Build it only after Standard Shield works.

Upgrades that apply to Standard Shield:
- **Minimum-effective level (the headline).** `find_min_effective_level(model, text)`: sweep `MASKER_LEVEL_STEPS` ([0.1, 0.2, 0.3, 0.5]); for each level, measure attack recovery (via `evaluate`); pick the LOWEST level whose recovery falls below `MASKER_TARGET_RECOVERY` (0.20). Report it: "reduced recovery from 84% to 13% at the minimum effective masking level." This answers the rubric line that protection should preserve normal function with minimal friction.
- **Adaptive band:** `measure_keyboard_band(sample) -> (low, high)`: find the dominant keystroke energy band and tune the masker to cover exactly that band.
- **Profile-matched decoys:** shape the fake keystroke transients from the user's own keyboard profile.

Interface additions: `Masker.set_level(v)`, `Masker.set_band(low, high)`, `Masker.set_trigger(enabled)` (default off), `find_min_effective_level(...)`, and an activity detector for the stretch trigger.

Tests: the sweep picks the lowest level meeting the target on a synthetic recovery curve; the tuned band covers the measured keyboard energy; Standard Shield is continuous while armed.

**DONE (D2):** Standard Shield (continuous) craters the measured recovery at the minimum effective level, with the mic-level dB ratio reported. Smart Shield (triggered) is optional.

---

## 7. D3: Effectiveness report and multi-endpoint view (lowest priority, first to cut)

Sell "deployable across an organization" without building distributed infrastructure. Keep it simple; if behind, cut D3 first. Cyber judges care far more about working attack -> measured vulnerability -> working defense -> measured improvement than about a live fleet.
- **Effectiveness report:** the defense panel shows measured off vs on recovery, the mic-level masker ratio, the current protection state (Standard/Smart, adaptive band, min level), and the latest Clack Exposure Grade.
- **Multi-endpoint view (saved reports, not live heartbeats):** each endpoint's audit run SAVES a report JSON to `FLEET_REPORTS_DIR` (`data/reports/`); the dashboard reads and lists those saved reports. No heartbeat service, no in-memory registry.
  - Report file: `{machine_id, grade, off_recovery, on_recovery, masker_ratio_db, timestamp}`.
  - `GET /fleet` -> the list of saved reports read from disk.
  - For the demo, run the audit on two or three team laptops and drop their report files in; the dashboard shows them. Say the architecture could support live fleet reporting later; do not build it now.

Tests: writing two report files then `GET /fleet` returns both, newest first.

**DONE (D3):** the dashboard lists saved audit reports from two or more machines. This is the first feature to cut if time is short.

---

## 8. Server and UI integration

Routes (defined here, wired in `server.py`):
- `POST /defense/on`, `POST /defense/off` (Standard Shield: continuous masker while armed), `GET /defense/measure`.
- `POST /exposure/check`, `GET /exposure/last`.
- `GET /fleet` (reads saved report files from `data/reports/`).

Dashboard defense panel (built in `app.js` per BUILD_FRONTEND, against these contracts):
- An Exposure Check button that shows the Clack Exposure Grade (big A to F, labeled a heuristic), the reasons, and the recommendations.
- A "Protected Typing" toggle (Standard Shield, continuous) showing the min level and adaptive band; a Smart Shield switch if the stretch is built.
- The before/after recovery bars plus the mic-level masker ratio (dB), animating the "on" bar cratering.
- The saved-reports list.

---

## 9. Demo moment (about two of three minutes on defense)

1. Attack, fast (about 45s): a judge picks a phrase and types it (or a teammate types the judge's phrase, the guaranteed fallback), Clack recovers it live from sound. "This is the threat, and it is real: 93% over a Zoom call in the research."
2. Exposure Check (about 30s): run it on that sample, show the grade and the reasons. "Any org can run this on every laptop to find who is exposed."
3. Arm Protected Typing (about 45s): the continuous Standard Shield is on before typing; type the same phrase, the recovered text turns to garbage and the recovery bar craters. "The shield is running before you type, at the minimum effective level, a plus-N-dB masker ratio at the mic."
4. Saved reports (about 20s): show audit reports from two or three machines. "Run the audit across every endpoint in an organization."
Close on the before/after bars: "Under our test setup, Clack cut recovery from X% to Y%. A measured audit-and-mitigate loop against acoustic leakage."

---

## 10. Predicted failures and fixes

| Problem | Fix |
|---|---|
| Masker barely dents accuracy | Raise `MASKER_LEVEL`, re-tune the adaptive band onto the measured keystroke band, add more decoys; confirm OS audio processing is off so the masker is actually recorded. |
| Exposure grade looks random | Base it primarily on real attack recovery `R`, with SNR as a tiebreaker; calibrate the bands on a couple of known samples. |
| First keystrokes leak (with the stretch Smart Shield) | Use Standard Shield (continuous while armed) for the guaranteed demo; the masker is already running before typing, so nothing leaks. Smart Shield stays a stretch. |
| Fleet view empty on stage | Pre-place the saved report files in `data/reports/`; the dashboard reads whatever is there. |
| Both measurement runs look the same | Same fixed `text` both times, identical model and mic settings, from a non-training session. |

## 11. DONE for the defense component

- Base masker plus measurement work (section 4), reporting the mic-level masker-to-key ratio in dB.
- D1 Exposure Check returns a labeled Clack Exposure Grade (A to F, including B) with reasons and recommendations.
- D2 Standard Shield (continuous) craters recovery at the minimum effective level; Smart Shield (triggered) is optional.
- D3 shows saved audit reports from two or more machines (first to cut if behind).
- The defense demo runs end to end and occupies about two thirds of the three-minute demo.
- `docs/threat-model.md` and the before/after table in `docs/evaluation.md` are written.
