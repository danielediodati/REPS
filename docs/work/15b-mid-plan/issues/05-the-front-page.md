# The front page

Status: ready-for-agent

Blocked by: 01, 02, 03, 04.

Read first: `spec.md`; README.md; CLAUDE.md § Closing a session; the commit-time rule in the user's memory (pushes happen in the evening, and an Action runs at push time).

## Decided with the user

| Question | Answer |
|---|---|
| Licence | MIT, `LICENSE` at the root, `license` in `pyproject.toml`. |
| Badges | Two rows. Live: tests (pytest and mypy in a GitHub Action), coverage, release, licence. Stack: Python 3.12+, LangGraph, mypy strict, uv, Telegram bot. No badge claims a tool the project does not run (no Ruff). |
| Coverage | `pytest-cov` in the same Action; the badge is written by the Action to a branch of its own in this repository. No external service. |
| Visibility | The repository stays private until `1.0.0` (session 15c). Until then the live badges render only for its owner; that is expected, not a bug. |

## What to build

- **A logo**: an SVG in `docs/`, legible at badge height and at full width, in both GitHub themes.
- **The GitHub Action**: on push to `main`, `uv sync`, `pytest` with coverage, `mypy`; no secrets, no network beyond installing. It fits GitHub's free minutes for a private repository.
- **The README, opened by a stranger**: logo, badges, one line on what REPS is, then the demo's place (the GIF lands at `1.0.0`). It still describes the system as it runs, as CLAUDE.md requires.
- **The version**: `pyproject.toml` at `1.0.0rc1` (PEP 440), tag `v1.0.0rc1`, by CLAUDE.md § Closing a session.

## Acceptance criteria

- [ ] The Action runs green on a push, and the tests and coverage badges show its result.
- [ ] The README renders on GitHub in both light and dark themes with the logo and both badge rows.
- [ ] `trainer --version` prints `1.0.0rc1`.
- [ ] Nothing in the README claims what the program does not do.
