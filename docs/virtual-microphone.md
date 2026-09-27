# Protected virtual microphone (macOS)

Virtual Mic sends microphone audio plus band-limited noise and fake keyboard
clicks into BlackHole 2ch. Nothing is played through the speakers. This is digital
masking, **not keystroke suppression**. The original physical mic is unchanged.

## One-time setup

1. Install **BlackHole 2ch** from [the driver publisher](https://existential.audio/blackhole/).
   Restart Clack and the receiving app after installation. Follow any restart
   instructions from the installer. Clack does not install drivers automatically.
2. Open **Audio MIDI Setup**, click **+**, then **Create Aggregate Device**.
   Name it **Clack Protected Bridge**.
3. Include only an input-only physical microphone **first**, then **BlackHole
   2ch second**. Check the subdevice order, not just the checkboxes. The connected
   HyperX SoloCast and the Mac's built-in microphone are supported examples.
   Do not include speakers or an audio interface with physical outputs.
4. Set the microphone, BlackHole, and aggregate to **44.1 kHz**. Choose the physical
   microphone as the **Clock Source** and enable **Drift Correction** for BlackHole.
   [BlackHole aggregate guidance](https://github.com/ExistentialAudio/BlackHole/wiki/Aggregate-Device-(In-Depth))
5. Grant microphone access to the application running Python if macOS requests it.
   The bridge does not need keyboard monitoring permissions.
6. Open Demo or Attack, choose **Virtual Mic**, and click **Refresh route**.
   Start the virtual microphone, then select **BlackHole 2ch** in the receiving
   app's microphone settings. Keep the app's playback output on your usual
   speakers or headphones, not BlackHole.

BlackHole is the device name receiving apps see; this version does not create a
custom driver named "Clack Protected Mic" or change system defaults. Clack checks
the aggregate's actual ordered members, channel counts, clock, drift correction,
and sample rates before opening it. An incomplete route is rejected.

## Using and testing it

- The mode adds continuous 1–10 kHz noise and decoys at jittered 40–120 ms
  intervals while armed. Default mic gain is 0.7 and default masking level is 0.3.
  The level slider adjusts masking while running. These are digital amplitudes,
  not calibrated sound-pressure levels or an assurance of protection.
- Input/output meters indicate audio activity. Stream latency is PortAudio's
  reported input plus output latency, not measured call latency. The limited
  sample fraction indicates headroom problems; lower the level if it is high.
- Demo records the physical mic and actual BlackHole input simultaneously through
  one browser AudioContext. Start recording grants microphone access, matches the
  selected physical mic to the bridge, and starts Virtual Mic if needed. The two
  meters show captured raw and protected audio. Stop and decode sends both clips
  through the same model and settings and displays separate result panels.
  A disconnected input or stopped bridge invalidates the comparison. The clips
  cover the same capture window; the protected path still has its audio latency.
- Attack retains its separate recording/live selectors. For a protected Attack
  recording explicitly choose BlackHole 2ch; raw selection is blocked while
  Virtual Mic runs. For accuracy comparisons, type known text on the same rig;
  recovered guesses alone are not measured accuracy.
- Stopping the bridge leaves BlackHole silent. There is no raw-audio bypass.
  Stream errors, missing masking buffers, and callback stalls mute output and
  stop the bridge. A server shutdown releases the streams.
- Stop one protection mode before starting the other. Stop physical-mic training
  or live attack before starting the bridge. A live attack using BlackHole is
  allowed. Browser permissions and device names are separate from backend device
  names; they are not interchangeable.

Existing **Measure protection** results are software-mixed recorded-session
evaluations, not measurements of BlackHole delivery. Hardware acceptance requires
recording the actual BlackHole input, confirming no speaker output, checking voice
and masking, and testing stop/silence, device loss, and a ten-minute session.
The bridge's latency target is below 100 ms; verify it on the chosen hardware.

## Boundaries and future work

Only applications receiving BlackHole's processed stream benefit. A nearby
independent microphone, or an app selecting the original microphone, bypasses it.
The UI reports routing activity, **not proof that another app selected the route**.
No audio is persisted by the bridge. Noise and decoys can be audible to call
participants and may harm speech intelligibility; call quality and resistance to
an attacker trained on masked audio remain evaluation tasks.

Future **suppression** could remove typing transients or preserve speech while
reducing keyboard noise. Neither suppression nor speech separation is implemented
in this version. Windows/Linux support and automatic driver setup are also future
work.

## Troubleshooting

- **No driver:** install BlackHole 2ch, restart Clack, and refresh the route.
- **No valid bridge:** check the exact name, order, membership, 44.1 kHz settings,
  physical-mic clock source, and BlackHole drift correction.
- **No mic labels in browser:** click Refresh microphones and grant permission.
- **No output in the receiving app:** select BlackHole 2ch there, check Clack's
  output meter, and ensure the bridge is running. Do not select the aggregate as
  the receiving microphone; its first input is the unprotected physical mic.
- **Route fails after unplug/replug:** stop the mode and restart Clack. Clack
  never silently substitutes another device or falls back to speakers.
- **Output is silent after stopping:** this is intentional. Explicitly choose
  the physical mic for an unprotected call or recording.
