# Contributing to Clack

Clack is built during hackUMBC 2026 by a small team. These conventions keep the
codebase coherent and the demo reliable.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Everything runs on localhost. There is no cloud dependency to collect, train,
attack, or serve, and no live network call anywhere at demo time (fonts and
libraries are self-hosted; correction defaults to a local model).

## Branching

- `main` always imports and passes `pytest`.
- Each component is built on its own branch off `main`
  (`feat/trainer`, `feat/model`, `feat/eval`, `feat/backend`, `feat/frontend`,
  `feat/defense`) and merged back only when its stated DONE is met and tests are
  green. Sync with `main` and resolve conflicts before merging.
- Commit regularly with clear messages (for example
  `phase 1: sounddevice capture + device enumeration`). Never leave the tree
  uncommitted between sub-steps.

## Style

- Python 3.11+, type hints on all signatures, numpydoc docstrings on every
  public function, class, and module (Parameters, Returns, Raises, and a short
  example for non-trivial ones).
- Comments explain why, not what. No commented-out code. Mark shortcuts with
  `TODO:` stating what and why.
- Config over hardcoding: every tunable lives in `config.py`.
- Fail loudly: missing device, missing permission, or empty dataset raises a
  clear, specific error. Never fall back to silent placeholder behavior.
- No em dashes in prose. Use commas, parentheses, or colons.

## Testing

- Stack: pytest, pytest-cov, hypothesis, pytest-asyncio, httpx, numpy.testing.
- Use `numpy.testing.assert_allclose` for arrays. Use Hypothesis for `segment`,
  `features`, and `prompts`. Every test asserts real behavior. Do not train a
  real model in a test. `pytest` alone runs everything with coverage.

## Ethics and scope

Clack is a defensive auditing tool. It records only the team's own keyboards and
consenting typists. It exploits no software and targets no person. The attack
step exists solely to prove and measure leakage so the defense can be verified.
