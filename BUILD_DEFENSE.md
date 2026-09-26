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

- `measure(model, text, masker) -> {"off_acc", "on_acc", "off_cer", "on_cer", "delta"}`: type a fixed known `text` with the masker off, run the attack, compute recovery; repeat with the masker on; return both plus the delta. Use `evaluate.py` (BUILD_EVAL) for the actual metrics (top-1, CER) so the numbers match everywhere. Type the SAME fixed text both times, from a session not used in training.
- Report the real measured drop. A believable "accuracy fell from X to near chance" beats an unbelievable "100 percent blocked."

**DONE (base):** the masker plays and stops cleanly, and `measure()` returns off vs on accuracy over the same text with a clear drop.

---

## 5. D1: Exposure Check (the rubric-closer, must-have)

A one-button "am I vulnerable?" assessment. This is what turns Clack from an attack demo into a posture tool an organization runs on every endpoint.

`exposure.py`:
- `check_exposure(model, sample_session) -> dict`: take a short typing sample (recorded via the trainer flow or a quick record), and compute:
  - **Recovery:** run the real attack on the sample, character accuracy `R` (how much an attacker would recover).
  - **Signal metrics:** keystroke SNR (onset energy over the noise floor) and per-key distinguishability (mean classifier confidence or embedding separation).
  - **Grade:** map exposure to A to F, where more recoverable is worse. Suggested bands: `R < 0.15` = A (low risk), `0.15 to 0.35` = B/C, `0.35 to 0.6` = D, `> 0.6` = F (highly exposed). Combine with SNR so a loud, distinct keyboard is flagged even before a full attack.
  - **Reasons:** concrete strings, for example "the attack recovered 82% of your text", "your keystrokes are loud and distinct (high SNR)", "microphone is close to the keyboard".
  - **Recommendations:** enable the masker, move the mic away, use a quieter switch, avoid typing secrets on video calls.
- Return `{grade, recovery, snr, reasons: [...], recommendations: [...]}`.

Route: `POST /exposure/check` body references a recorded sample id -> the dict above.

Why it scores: this is a real cybersecurity function ("assess acoustic exposure"), it is usable by any organization (run it on staff laptops), and it runs per endpoint, which is the honest form of "scalable across an organization."

Tests (`test_exposure.py`): on a synthetic high-recovery sample the grade is poor (F) and on a masked or low-SNR sample the grade is good (A); reasons and recommendations are non-empty and match the metrics.

**DONE (D1):** running Exposure Check on a typing sample returns a risk grade with specific reasons and recommendations, driven by the real attack.

---

## 6. D2: Adaptive, minimum-effective masker (upgrade `defense.py`)

Make the masker something a person would actually leave running, and turn it into a real usability-vs-security result.
- **Minimum-effective level (the headline).** `find_min_effective_level(model, text)`: sweep `MASKER_LEVEL_STEPS` ([0.1, 0.2, 0.3, 0.5]); for each level, measure attack recovery (via `evaluate`); pick the LOWEST level whose recovery falls below `MASKER_TARGET_RECOVERY` (0.20). Report it: "reduced recovery from 84% to 13% at the minimum effective masking level." This directly answers the rubric line that protection should preserve normal function with minimal friction, and it is far more interesting than "play loud noise".
- **Trigger-based:** the masker plays only while typing is detected (reuse the onset detector on the live mic), silent when idle. No constant noise.
- **Adaptive band:** `measure_keyboard_band(sample) -> (low, high)`: find the dominant keystroke energy band and tune the masker to cover exactly that band instead of the fixed default.
- **Profile-matched decoys:** shape the fake keystroke transients from the user's own keyboard profile so decoys are hard to tell from real presses.

Interface additions: `Masker.set_level(v)`, `Masker.set_band(low, high)`, `Masker.set_trigger(enabled)`, `find_min_effective_level(...)`, and an activity detector that gates playback.

Why it scores: lowest-effective masking is both a security result and a usability result, which is exactly the "minimal friction" criterion.

Tests: the sweep picks the lowest level meeting the target on a synthetic recovery curve; the tuned band covers the measured keyboard energy; trigger gating starts and stops playback with detected activity.

**DONE (D2):** the masker auto-triggers on typing and is tuned to the measured keyboard band, and the before/after drop is still measured with it on.

---

## 7. D3: Effectiveness report and multi-endpoint status

Sell "deployable across an organization" concretely, not as a claim.
- **Effectiveness report:** the defense panel shows measured off vs on accuracy, the current protection state (on/off, adaptive band, trigger mode), and the latest Exposure Check grade.
- **Multi-endpoint status (a minimal fleet view):** each running defender periodically posts a heartbeat, and the dashboard lists the machines and whether each is protected.
  - `POST /fleet/heartbeat` body `{machine_id, protected: bool, grade?: str}` -> `{ok: true}`; keep an in-memory registry with `last_seen`.
  - `GET /fleet` -> `[{machine_id, protected, grade, last_seen}]`.
  - For the demo, run the defender on two or three team laptops so the fleet view shows real machines. Honest scope: this demonstrates scale across endpoints, not high request throughput.

Tests: `POST /fleet/heartbeat` then `GET /fleet` round-trips a machine's status; stale entries are marked.

**DONE (D3):** the dashboard shows measured protection, the current protection state, and a status view listing two or more machines.

---

## 8. Server and UI integration

Routes (defined here, wired in `server.py`):
- `POST /defense/on`, `POST /defense/off` (adaptive masker), `GET /defense/measure`.
- `POST /exposure/check`, `GET /exposure/last`.
- `POST /fleet/heartbeat`, `GET /fleet`.

Dashboard defense panel (built in `app.js` per BUILD_FRONTEND, against these contracts):
- An Exposure Check button that shows the grade (big A to F), the reasons, and the recommendations.
- A masker toggle showing the adaptive band and trigger state.
- The before/after accuracy bars, animating the "on" bar cratering when the masker turns on.
- The fleet status list.

---

## 9. Demo moment (about two of three minutes on defense)

1. Attack, fast (about 45s): a judge types, Clack recovers it live from sound. "This is the threat, and it is real: 93% over a Zoom call in the research."
2. Exposure Check (about 30s): run it on that sample, show the F grade and the reasons. "Any org can run this on every laptop to find who is exposed."
3. Turn on protection (about 45s): flip the adaptive masker, the judge types the same thing, the recovered text turns to garbage and the accuracy bar craters. "Protection kicks in only while you type, tuned to your keyboard."
4. Fleet view (about 20s): show the defender running on two or three machines. "Deployable across every endpoint in an organization."
Close on the before/after bars and the fleet: "A measured, deployable defense against acoustic surveillance."

---

## 10. Predicted failures and fixes

| Problem | Fix |
|---|---|
| Masker barely dents accuracy | Raise `MASKER_LEVEL`, re-tune the adaptive band onto the measured keystroke band, add more decoys; confirm OS audio processing is off so the masker is actually recorded. |
| Exposure grade looks random | Base it primarily on real attack recovery `R`, with SNR as a tiebreaker; calibrate the bands on a couple of known samples. |
| Trigger gating cuts masking late (first keystrokes leak) | Start masking on the first detected onset and keep a short hangover; for the demo, pre-arm the masker just before typing. |
| Fleet view empty on stage | Pre-start the defender on the other laptops; mark stale heartbeats but keep last-known status visible. |
| Both measurement runs look the same | Same fixed `text` both times, identical model and mic settings. |

## 11. DONE for the defense component

- Base masker plus measurement work (section 4).
- D1 Exposure Check returns a real risk grade with reasons and recommendations.
- D2 adaptive, trigger-based masker tunes to the keyboard and plays only while typing.
- D3 effectiveness report and a two-plus machine fleet view work live.
- The defense demo runs end to end and occupies about two thirds of the three-minute demo.
