# Clack — BUILD_DEFENSE.md

The countermeasure: an acoustic masker that corrupts the microphone signal the attack depends on, plus the measurement that proves it works. This is the half that wins the Cyber track, so make the effect unmistakable and honest. Read `CLACK_BUILD_PLAN.md` first. Commit regularly.

Covers files: `defense.py`, defense routes in `server.py`, the defense panel in `ui/app.js`.

---

## 1. What it counters

The attack needs a clean recording of each keystroke: a detectable onset and a distinguishable spectral shape. The masker attacks both. It adds sound in the same frequency band as the keystrokes so the classifier's features are corrupted, and it injects fake keystroke-like transients so the onset detector fires on phantom presses. With the masker on, onsets are wrong and windows are noisy, so recovery collapses toward random guessing.

This is a real, on-topic defense: acoustic masking and "sound cover" are the standard mitigation discussed for keyboard acoustic side channels, including in the 2023 paper's mitigation section. We build one and measure it.

---

## 2. Why the Mac's own speakers are enough (and better)

Speaker and microphone are inches apart in the same laptop chassis, so the masker reaches the mic at a high level relative to the keystrokes without any volume effort. Co-location is an advantage here, not a compromise. Two requirements:
- **Capture raw audio with OS processing off** (no echo cancellation, noise suppression, or auto gain). Otherwise the OS may try to subtract the speaker output from the mic input and weaken the demonstrated effect. We want the masker genuinely present in the recording.
- The masker band sits at 1 to 10 kHz (`MASKER_BAND_HZ`), which laptop speakers reproduce fine, so the weak-bass limitation of laptop speakers does not matter.

---

## 3. The masker (`defense.py`)

Two components, summed and played on a loop through the default output device via sounddevice.

1. **Band-limited noise.** Generate white noise, band-pass filter it to `MASKER_BAND_HZ` (1000 to 10000 Hz) with a Butterworth filter (scipy), scale to `MASKER_LEVEL` (0.3 relative amplitude). This covers the spectral region where keystroke energy lives.
2. **Fake keystroke transients.** At random intervals (for example every 40 to 120 ms, jittered), inject short click-like bursts (a few ms of shaped noise, or pre-recorded real keystroke clips played at random times). These create false onsets so the attack's onset detector cannot cleanly separate real presses.

Interface:
- `class Masker`:
  - `start()`: begin playback on a background `OutputStream` that continuously generates and streams the summed signal. Non-blocking.
  - `stop()`: stop playback.
  - `is_on() -> bool`.
- Keep `MASKER_LEVEL` and `MASKER_BAND_HZ` in config so the effect can be tuned at the venue.

Safety and courtesy: keep the level modest, it only needs to reach the co-located mic, not fill the room.

---

## 4. Measurement (the honest before/after)

The demo claim must be a measured number, not a vibe.

- `measure(model, text, masker) -> {"off_acc": float, "on_acc": float}`:
  1. With the masker **off**, have the typist type a fixed known `text`; run the live attack; compute character accuracy against `text`.
  2. With the masker **on**, type the same `text` again; run the attack; compute accuracy.
  3. Return both. Optionally repeat and average for stability.
- Report character accuracy (and, for prose, post-correction accuracy) in both conditions. Expect a sharp drop with the masker on.
- Keep the exact `text` short and fixed so the two runs are comparable, and so the number is reproducible on stage.

Do not overstate: report the real measured drop. A believable "accuracy fell from X to near chance" beats an unbelievable "100 percent blocked".

---

## 5. Server and UI integration

Backend routes (also listed in BUILD_BACKEND.md):
- `POST /defense/on` -> `masker.start()`, return `{on:true}`.
- `POST /defense/off` -> `masker.stop()`, return `{on:false}`.
- `GET /defense/measure` -> `{off_acc, on_acc}`.

Dashboard defense panel (see BUILD_FRONTEND.md):
- A toggle `Masker off / on` wired to the routes; the top-bar status reflects it.
- Two thin horizontal bars, `Masker off` and `Masker on`, from `/defense/measure`. Flipping the toggle on animates the "on" bar cratering to its low value. Keep it minimal and let the collapse read at a glance.

---

## 6. Demo moment

After the attack has wowed them, this is the turn: "Now the countermeasure." Flip the toggle, have the judge type the same thing, and the recovered text turns to garbage while the accuracy bar craters. Close on the before/after bars: "Attack, then defense, both measured." It reframes the project from a scary trick into a complete security contribution, which is what the Cyber judges reward.

---

## 7. Predicted defense failures and fixes

| Problem | Fix |
|---|---|
| Masker barely dents accuracy | Raise `MASKER_LEVEL`, widen or re-center `MASKER_BAND_HZ` onto the measured keystroke band, and add more frequent fake transients. Confirm OS audio processing is off so the masker is actually in the recording. |
| OS cancels the masker (echo cancellation) | Open the input stream raw, disable echo cancellation / noise suppression / auto gain; verify by recording with the masker on and inspecting the spectrogram. |
| Both runs look the same | Ensure the same fixed `text` is typed both times and the model and mic settings are identical between runs. |
| Masker annoys the room | Lower the level; it only needs to reach the co-located mic. |

## 8. DONE for the defense

- `defense.py` plays a band-limited masker with fake transients through the Mac speakers and stops cleanly.
- `measure()` returns off vs on accuracy over the same fixed text, with a clear, reproducible drop.
- The dashboard toggle and before/after bars work live, and the effect is unmistakable on screen.
