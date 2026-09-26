# Threat Model

Owner: BUILD_DEFENSE. Stating the boundary explicitly is what makes the defense
credible rather than hand-wavy, and it is the answer to a sharp judge.

## What Clack defends against

Clack defends against **passive nearby acoustic capture**: a microphone near the
keyboard, or keystrokes carried over a voice or video channel. This is real and
current: the 2023 research recovered keystrokes at 93% over a Zoom call. Anyone
typing a password while on a video call, in a shared office, or near any
microphone is exposed.

Under Clack's MVP threat model the target types at gaps of at least
`DEMO_MIN_GAP_MS` (250 ms, about 3 to 4 keys per second). Faster, overlapping
entry is a stretch, claimed only if demonstrated.

The countermeasure is the acoustic masker (Protected Typing): band-limited noise
(`MASKER_BAND_HZ`, 1 to 10 kHz, where laptop speakers are strong and keystroke
energy lives) plus jittered fake keystroke transients that make the attack's onset
detector fire on phantom presses. The guaranteed mode is the Standard Shield: a
continuous masker while armed, so no identifying transient reaches the mic
unmasked.

## What Clack does NOT defend against

Clack does **not** defend against a fully compromised endpoint. An attacker who
already controls the machine can disable the masker, read keyboard events
directly, or capture the screen, and no acoustic countermeasure helps against
that. Clack addresses the acoustic side channel only.

## "Isn't this just your speaker blasting noise next to your mic?"

For the demo, a co-located speaker and microphone (inches apart in the same
laptop) make the effect reliable to show: the masker reaches the mic at a high
level without volume effort. In a real deployment the masker is a small device
near the protected keyboard. Two requirements hold in both cases: capture raw
audio with OS processing off (no echo cancellation, noise suppression, or auto
gain), and keep the masker band where the speakers are strong (1 to 10 kHz). The
narrowed threat model above is the real answer, not a dodge.

## The Clack Exposure Grade is a heuristic, not a standard

The Exposure Check maps measured attack recovery to a letter grade
(`EXPOSURE_GRADE_BANDS` = {A: 0.15, B: 0.25, C: 0.40, D: 0.60}, above D is F). It
is a Clack heuristic based on measured recoverability, NOT an industry
cybersecurity rating, and it is labeled as such on the dashboard and here.

## Honest claim

Clack reports the measured reduction against its own attack in the tested
environment: "under our test setup, recovery fell from X% to Y% at a +N dB masker
ratio at the mic." It does not claim typing is made unrecoverable in general; a
more robust attacker could exist. See [evaluation.md](evaluation.md) for how the
before/after table is reproduced.

## Provably microphone-only in attack mode

In attack mode the pynput keyboard listener is never instantiated
(`ATTACK_DISABLES_KEYLOGGER`), and the dashboard shows `Keyboard Events: DISABLED`.
A judge can verify that recovery uses sound alone. The keylogger exists only for
consented training data collection.
