# Clack — BUILD_FRONTEND.md

The UI: an editorial-minimal web interface inspired by siteinspire.com, plus the five hero visuals that carry the demo. Read `CLACK_BUILD_PLAN.md` first. Commit regularly.

Covers files: `ui/index.html` (attack dashboard), `ui/trainer.html` (collector), `ui/app.js`, `ui/trainer.js`, `ui/style.css`. One page each, vanilla JS plus canvas, fonts and any libs from CDN, no build step.

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

Fonts via Google Fonts in each HTML head:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

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

- **Row 1, full width: Recovered text.** Large mono, left aligned, with a blinking caret. Each recovered character rises and fades in over `--dur` with a confidence glow: text color interpolated between `--good` (high) and `--warn` (low). This is the emotional center; give it room.
- **Row 2, left (8 cols): Signal.** The live **waveform** (thin ink stroke) above the live **spectrogram** (ink-to-accent heatmap). Minimal axes, generous margin.
- **Row 2, right (4 cols): Confidence.** The current keystroke's top-3 candidates as three thin horizontal bars (mono labels, bar length = probability), the top one in `--accent`.
- **Row 3, left (7 cols): Keyboard.** A clean line-art on-screen keyboard; the guessed key flashes (fill fades from `--accent` back to transparent over ~400ms), tinted by confidence. This is the "it is reading my mind" moment.
- **Row 3, right (5 cols): Two modes:**
  - **Password mode:** the **search-space collapse** number in `--t-hero` mono, animating from a huge value down to the surviving candidate count, with a thin bar underneath.
  - **Defense panel:** a toggle (`Masker off / on`) and the **before/after** accuracy as two thin horizontal bars; flipping the toggle animates the "on" bar cratering.
- **Top-right controls:** `Start attack` / `Stop`, a model selector, and a `Clean run` switch (event mode) for the guaranteed demo.

---

## 6. The five hero visuals (implementation)

All drawn on `<canvas>` with a single shared render loop. No heavy library is required; if you want a waveform helper, load one from CDN, but custom canvas keeps full control and stays on-theme. Draw with `--ink` and `--accent` read from CSS variables so both themes work.

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
  - `type:"key"`: append `key` to the recovered string with its `confidence`, update top-3 bars, trigger the keyboard flash, store for the render loop. Never drop these.
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
| Fonts flash or fail to load | `display=swap` is set; keep a system-ui fallback in the stack so layout holds. |
| Canvas colors wrong after theme switch | Re-read CSS variables (`getComputedStyle`) at the start of each frame or on theme change, do not cache hex values. |
| localStorage throws (private window) | Wrap the theme read/write in try/catch and default to light. |

## 10. DONE for the frontend

- Both pages match the editorial-minimal design system (paper background, hairlines, mono data, one accent) and pass as a considered design object.
- The trainer collects sessions with the paced/flow stage and coverage strip.
- The dashboard shows all five hero visuals live, driven by the WebSocket, on a single rAF loop that never blocks the decode, with a working light/dark toggle.
