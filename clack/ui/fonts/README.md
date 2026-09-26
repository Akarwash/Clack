Self-hosted fonts (no CDN; the page loads with no network).

- SpaceGrotesk.woff2 - Space Grotesk (SIL Open Font License 1.1), the UI grotesk.
- JetBrainsMono.woff2 - JetBrains Mono (SIL Open Font License 1.1), all data and
  recovered text.

Declared with @font-face in ../style.css with a system-ui fallback stack, so layout
holds even if a file is missing. No fonts.googleapis.com link, no CDN.
