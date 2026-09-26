# Clack — BUILD_FRONTEND.md

The UI: an editorial-minimal web interface inspired by siteinspire.com, plus the five hero visuals that carry the demo. Read `CLACK_BUILD_PLAN.md` first. Commit regularly.

Covers files: `ui/index.html` (attack dashboard), `ui/app.js`, `ui/style.css`, and the self-hosted `ui/fonts/` and `ui/vendor/`. (The trainer page `ui/trainer.html` + `ui/trainer.js` is specified in BUILD_TRAINER; it shares `style.css`.) One page each, vanilla JS plus canvas, self-hosted fonts and libs (no CDN), no build step.

---

## 1. Design language (the siteinspire brief)

siteinspire is content-first minimalism: a near-white background, near-black text, a strict grid, hairline dividers, tiny uppercase labels, and a lot of whitespace, with no decoration competing for attention. Translate that here into a gallery-grade interface where the attack visuals are the "content" and everything else recedes. The result should read as a considered design object, not a neon hacker dashboard. That restraint is what wins the overall prize on aesthetics.

Principles:
- **Whitespace separates, not boxes.** Panels are divided by hairline rules and space, not heavy cards or borders.
- **One accent, used rarely.** Monochrome ink on paper, with a single signal color for the live/attack state and the defense drop. Confidence uses a green and an amber, nothing else.
- **Type does the work.** A precise grotesk for the interface, a mono for all data and recovered text. Big confident numerals for stats, tiny uppercase micro-labels for everything else.
- **Motion is precise and fast.** Short durations, a single easing curve, no bounce.
- **The data graphics are drawn like editorial infographics:** thin strokes, generous margins, minimal axes, the accent used only to mark the live value.

---

## 2. Design tokens (`style.css` `:root`)

Fonts are **self-hosted, not from a CDN** (venue wifi must never be able to break the page, per the master's no-network rule). Download Space Grotesk and JetBrains Mono into `ui/fonts/` during scaffold and declare them with `@font-face` in `style.css`:
```css
@font-face { font-family: "Space Grotesk"; src: url("fonts/SpaceGrotesk.woff2") format("woff2"); font-weight: 400 700; font-display: swap; }
@font-face { font-family: "JetBrains Mono"; src: url("fonts/JetBrainsMono.woff2") format("woff2"); font-weight: 400 700; font-display: swap; }
```
Any JS libs load from `ui/vendor/` the same way. No `<link>` to fonts.googleapis.com, no CDN `<script>`.

```css
:root {
  /* Light "paper" theme (default, the siteinspire look) */
  --bg:        #F4F3EF;   /* warm paper */
  --surface:   #FBFAF7;
  --ink:       #14140F;   /* near-black */
  --ink-soft:  #6D6C64;   /* muted labels */
  --line:      #E2E0D8;   /* hairline */
  --accent:    #E5433A;   /* signal red, used rarely */
  --good:      #2F9E64;   /* high confidence */
  --warn:      #C98A3C;   /* low confidence */

  --font-ui:   "Space Grotesk", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  /* type scale */
  --t-micro: 11px;   /* uppercase labels, +0.12em tracking */
  --t-body:  15px;
  --t-lead:  19px;
  --t-stat:  44px;   /* big numerals */
  --t-hero:  72px;   /* trainer current char, search-space number */

  --gap: 24px;
  --pad: 48px;       /* page side padding (24px on phones) */
  --ease: cubic-bezier(0.2, 0, 0, 1);
  --dur: 160ms;
}

:root[data-theme="dark"] {
  /* "projector" theme, toggle with the button or the D key */
  --bg:      #0E0E0C;
  --surface: #161613;
  --ink:     #F1F0EA;
  --ink-soft:#9A988E;
  --line:    #2A2A26;
  --accent:  #FF5A4D;
  --good:    #4CC585;
  --warn:    #E0A24E;
}
```

Global: `body { background:var(--bg); color:var(--ink); font-family:var(--font-ui); }`. Micro-label utility: `text-transform:uppercase; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-soft);`. All data values and recovered text use `--font-mono`. Respect `prefers-reduced-motion` by cutting animations.

Default to the light theme (faithful to siteinspire). Provide a one-tap theme toggle in the top bar and a `D` key shortcut, because a projector in a bright room may read better in dark. Persist the choice in `localStorage` inside a try/catch.

---

## 3. Shared chrome (both pages)

**Top bar** (fixed, hairline underneath, `--pad` side padding):
- Left: wordmark `Clack` in Space Grotesk 700, plus a tiny mono version tag.
- Center: nav links `Trainer` and `Attack` (the two pages), current one marked with a short underline in `--accent`.
- Right: a **live status dot** (filled `--accent` when a session or attack is running, hollow when idle) with a micro-label (`LIVE` / `IDLE`), and the theme toggle.

**Grid:** a max-width container (about 1200px) centered, 12-column grid, `--gap` gutters. Sections separated by 1px `--line` rules and vertical space, never boxed.

---

## 4. Trainer page (`trainer.html`, `trainer.js`)

**Authoritative spec: BUILD_TRAINER.md section 9.** The trainer page is built as part of the Clack Trainer (step 1), not the dashboard work. This section is a summary; where it differs from BUILD_TRAINER.md, that file wins. It uses the same design tokens defined here in `style.css`.

The monkeytype-style collector. Editorial and calm so it looks intentional if a judge sees it.

Layout, top to bottom:
1. **Setup row** (before Start): micro-labeled controls for `Keyboard` (text, for example "blue" or "c3equalz"), `Typist`, `Mode` (Paced / Flow segmented control), `Length`, and a `Mic` dropdown populated from `GET /devices`. A single `Start` button (ghost style: ink text, hairline border, accent on hover).
2. **The stage** (center, large):
   - **Paced mode:** one giant current character in `--t-hero` mono, centered, with the next few upcoming characters faint (`--ink-soft`) to its right and completed ones faded out to the left. A thin metronome progress line under the current char that fills over `TRAINER_PACED_GAP_MS` and resets on each correct press.
   - **Flow mode:** a single line of upcoming random characters scrolling right to left, monkeytype-style, the current one marked, correct/incorrect colored with `--good` / `--accent`.
3. **Live readout row** (micro-labels + big mono numerals): `Keys captured`, `Elapsed`, and in flow mode `WPM`.
4. **Coverage strip:** a horizontal row of 37 tiny cells, one per key, each filling from `--line` toward `--ink` as that key accumulates samples, so the typist can see which keys still need data. This is both useful and a nice visual.
5. **Stop** button, which calls `/trainer/stop` and shows the saved session summary (counts, path) as a quiet confirmation line.

`trainer.js`:
- On Start: `POST /trainer/start`, then `GET /trainer/prompt` for the character sequence, start the local UI clock and (paced) the metronome.
- The browser's own `keydown` drives only the UI (advance the pointer, color correct/incorrect, update the coverage strip). It does not label anything; labels come from the backend keylogger.
- On Stop: `POST /trainer/stop`, render the summary.

---

## 5. Attack dashboard (`index.html`, `app.js`)

An editorial grid of panels, hairline-separated. Suggested layout on desktop:

- **Top status bar: INPUT SOURCES.** Always visible: `Microphone: ACTIVE` and `Keyboard Events: DISABLED` (from `GET /status`), plus `Ambient: calibrated` once the 2 s calibration finishes. This is the credibility line: it proves the attack uses sound alone. Make it prominent, not buried.
- **Row 1, full width: Recovered text, RAW and CORRECTED.** Two lines, both large mono: `RAW MODEL` (the classifier's top-1 per position, for example `p a s s w 0 r d`) and `CORRECTED` (after the language model, for example `password`). Each recovered character rises and fades in over `--dur` with a confidence glow between `--good` (high) and `--warn` (low). Showing raw next to corrected proves the classifier works and the LM is a boost, not the whole trick. This is the emotional center; give it room.
- **Row 2, left (8 cols): Signal.** The live **waveform** (thin ink stroke) above the live **spectrogram** (ink-to-accent heatmap). Overlay the **onset debug markers** (detected peaks + current threshold) as a toggle, so you can see detection working in the room.
- **Row 2, right (4 cols): Confidence + metrics.** The current keystroke's top-3 candidates as thin horizontal bars (top one in `--accent`), plus a compact **metrics readout** from `evaluate.py`: onset recall, raw top-1, top-3, CER, median latency. Only values actually measured.
- **Row 3, left (7 cols): Keyboard.** A clean line-art on-screen keyboard; the guessed key flashes (fill fades from `--accent` back to transparent over ~400ms), tinted by confidence. This is the "it is reading my mind" moment.
- **Row 3, right (5 cols): Two modes:**
  - **Password mode:** the **search-space collapse** number in `--t-hero` mono, animating from a huge value down to the surviving candidate count, with a thin bar underneath.
  - **Defense panel:** a toggle (`Masker off / on`), the measured **before/after** accuracy as two thin bars (the "on" bar craters on toggle), the **minimum effective masking level** chosen, and the latest **Exposure Check** grade (A to F).
- **Top-right controls:** `Start attack` / `Stop`, a model selector (baseline / CNN), and a `Clean run` switch (event mode) for the guaranteed demo.

---

## 6. The five hero visuals (implementation)

All drawn on `<canvas>` with a single shared render loop. No heavy library is required; if you want a waveform helper, vendor it into `ui/vendor/` (no CDN), but custom canvas keeps full control and stays on-theme. Draw with `--ink` and `--accent` read from CSS variables so both themes work.

**Shared render loop (critical-path rule):** one `requestAnimationFrame` loop reads the latest state (last prediction, last audio frame) and redraws. The WebSocket handler only updates state, it never draws. If frames pile up, the loop naturally shows the newest. Rendering must never block or slow the decode; the decode is on the backend and the socket just delivers results.

1. **Waveform:** keep a ring buffer of the latest samples from `audio` frames; draw a thin polyline scaled to the panel. Light, ink stroke.
2. **Spectrogram:** scroll a column heatmap; map dB to a ramp from `--surface` through `--ink` to `--accent` at the hottest. New column on the right each frame, shift left.
3. **On-screen keyboard:** a static array of key rectangles (line-art). On each `key` message, set that key's highlight to 1.0 and decay it toward 0 each frame; fill color = mix of `--accent` and the confidence tint by the current highlight value.
4. **Confidence text:** as each character is appended, store its confidence; render the recovered string with per-character color = lerp(`--warn`, `--good`, confidence), and animate opacity and a few px of rise on entry.
5. **Search-space collapse:** on a password run, start from the theoretical space (for example `charset_size ** length`, shown in scientific notation) and tween down to the product of top-k-per-position counts. Use a short eased count-down; end on the small number in `--accent`.
6. **Defense bars:** two bars, `Masker off` and `Masker on`, values from `GET /defense/measure`; when the toggle flips on, animate the "on" bar down to its low value.

---

## 7. WebSocket client (`app.js`)

- Connect to `ws://<host>/ws/attack` after `POST /attack/start`.
- On message:
  - `type:"key"`: append the raw `key` to the RAW line and the corrected string to the CORRECTED line, with its `confidence`; update top-3 bars, trigger the keyboard flash, store for the render loop. Never drop these.
  - `type:"status"` / poll `GET /status`: update the INPUT SOURCES bar (mic active, keyboard events disabled, ambient calibrated) and the metrics readout.
  - `type:"onset"` (debug): draw the detected peak marker and threshold on the signal panel.
  - `type:"audio"`: replace the latest waveform and spectrogram frame (drop older ones).
- Reconnect with backoff if the socket closes. Show the top-bar status dot state from the socket state.

---

## 8. Responsiveness and projector readiness

- Works down to phone width: the 12-col grid collapses to one column, `--pad` drops to 24px, the keyboard visual scales or scrolls.
- Because the demo is on a projector, keep contrast high, type large, and make sure the dark theme is one tap away. Test both themes on an external display during Phase 10.

---

## 9. Predicted frontend failures and fixes

| Problem | Fix |
|---|---|
| Visuals stutter under fast typing | Confirm the single rAF loop is the only thing drawing and the socket handler only sets state; drop `audio` frames, never `key` messages. |
| Light theme washes out on the projector | The `D` key / toggle switches to the dark token set; test on the real projector in Phase 10. |
| Fonts flash or fail to load | Fonts are self-hosted (`@font-face`, `font-display: swap`); keep a system-ui fallback in the stack so layout holds even if a woff2 is missing. No CDN dependency at load. |
| Canvas colors wrong after theme switch | Re-read CSS variables (`getComputedStyle`) at the start of each frame or on theme change, do not cache hex values. |
| localStorage throws (private window) | Wrap the theme read/write in try/catch and default to light. |

## 10. DONE for the frontend

- The dashboard matches the editorial-minimal design system (paper background, hairlines, mono data, one accent), with self-hosted fonts and no network at load.
- It shows the INPUT SOURCES bar (mic active, keyboard events disabled, ambient calibrated), RAW next to CORRECTED text, the metrics readout, and all five hero visuals live, driven by the WebSocket on a single rAF loop that never blocks the decode, with a working light/dark toggle.
- (The trainer page's DONE is in BUILD_TRAINER.)
