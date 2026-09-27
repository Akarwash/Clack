# Changelog

## Protected virtual microphone

- Add macOS BlackHole routing with validated aggregate membership, continuous
  digital noise and decoys, health meters, limiting, and silence on failure/stop.
- Add separate Speaker Masker and Virtual Mic controls on Demo and Attack,
  explicit recording/live microphone selection, and capture conflict handling.
- Document manual setup, protection boundaries, and future suppression.

All notable changes to Clack are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Clack adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repository scaffold: full module tree as clean-importing stubs, `config.py`
  and typed `config_types.py` (with `ensure_dirs`), the `docs/` skeletons,
  pinned `requirements.txt`, `pyproject.toml` pytest config, `conftest.py`
  synthetic fixtures, and one real green test suite (`tests/test_config.py`).
- Clack Trainer (`feat/trainer`): balanced random-character prompts, microphone
  capture with clock/latency mapping, pynput key logging (training only),
  session start/stop writing the section 9 on-disk contract, the monkeytype-style
  trainer page (paced and flow, coverage strip, purpose quotas), the terminal
  fallback collector, and the full physical protocol in `docs/data-collection.md`.
- Model (`feat/model`): shared onset segmentation (identical window for train and
  attack), log-Mel features, session-split dataset with augmentation, the
  nearest-centroid floor and the CNN with an embedding head, seeded training with
  device detection and a confusion matrix, the offline attack with password
  search-space reduction, and embedding-prototype cross-keyboard calibration.
- Evaluation (`feat/eval`): the metrics harness (onset recall/precision, top-k
  recall, CER, latency, masker-to-key ratio), `evaluate_attack`,
  `evaluate_defense`, `compare_models`, `cross_typist_eval`, and a `format_report`
  that only reports computed values, plus `docs/evaluation.md`.
- Defense (`feat/defense`): the acoustic masker (band-limited noise plus decoy
  transients) with the continuous Standard Shield, the honest before/after
  measurement and minimum-effective-level sweep, the adaptive band, the D1 Exposure
  Check (labeled Clack grade with reasons and recommendations), the D3 saved-report
  fleet view, and `docs/threat-model.md`.
- Backend (`feat/backend`): local n-gram beam-search correction over a bundled
  corpus (no network), the live streaming decoder with ambient calibration and a
  provably mic-only attack path, the FastAPI server wiring the trainer, attack
  WebSocket, defense, exposure, fleet, and status routes plus the static UI, the
  `serve.py` and `preflight.py` entry points, and `docs/api.md` with the runbook
  preflight section.
- Frontend (`feat/frontend`): the editorial-minimal attack dashboard with the
  INPUT SOURCES credibility bar, RAW vs CORRECTED recovered text, the five canvas
  hero visuals on a single non-blocking render loop, the defense/exposure/fleet
  panel, a light/dark projector theme, self-hosted fonts (no CDN), and a `/correct`
  endpoint so the CORRECTED line uses the real local corrector live.

## [0.1.0] - 2026-09-26

### Added
- Initial project scaffold for hackUMBC 2026.

[Unreleased]: https://example.invalid/clack/compare/v0.1.0...HEAD
[0.1.0]: https://example.invalid/clack/releases/tag/v0.1.0

## Demo Claude correction

- Added backend-only Opus 5.5 correction using probabilities and validated candidate indices.
- Demo shows acoustic results immediately and corrects both streams independently.
- Added explicit local fallback, correction timing/token usage, and stale-response protection.
- Confirmed live artificial-text smoke test; labeled real-session accuracy comparison pending
  because the only local evaluation recording has an empty events list.
- Live Demo requests exercised refusal handling independently for both streams;
  Correction Off hides correction panels and does not request remote correction.
- Credentials use an ignored, private `.env` file; `.env.example` is blank.

## Correction prompt framing

- Framed candidate selection as a constraint-satisfaction logic puzzle, preserving
  one allowed candidate per ordered position.
- The repeated noisy-candidate smoke test still returned a provider refusal;
  local fallback remains explicitly labeled.
