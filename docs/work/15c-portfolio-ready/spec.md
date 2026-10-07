# Session 15c — Portfolio-ready

**Demo**: after three mesocycles, the fourth arrives in Telegram with its reason; and *«anzi, ho solo 30 minuti»* mid-plan brings the 30-minute plan. Recorded, with a GIF in the README.

Tickets 01 and 02 are the fixes found using `1.0.0rc1` on the demo's home, 2026-10-07. A substitute exercise inheriting its block's numbers was raised and dropped by the user: likely not a real problem.

## Carried from 15.5

- `trainer demo HOME` builds the demo's home from `docs/demo/history.toml`; the bot is pointed at it with `TRAINER_HOME`, and a `TRAINER_DB` already set wins over it.
- The demo's mesocycles must be ones the validator accepts under the demo's declaration: inside the time window and training each slot's groups. `trainer demo` checks them before writing.
- The supervisor runs on `openai/gpt-6-luna` (ADR-0011), ~$0.0015 a direction. With a loved exercise in the conclusions it may keep every exercise rather than rotate the rest, so a demo built on *«adoro lo stacco»* can show no change in exercises.
- Recording the demo reaches paid models: estimated first, run on the user's go.

## Carried from 15b.5

- The tests badge is GitHub's own; coverage and release are SVGs the Action writes to the `badges` branch, read from `github.com/dquadro/REPS/raw/badges/`. While the repository is private they show only to its owner: once public, check them logged out.
- The Action runs on Python 3.12, the floor `requires-python` claims; local development is on 3.14. Before 3.14 `asyncio.run` takes only a coroutine, so mypy on 3.14 alone misses it.
- The release badge is orange for a pre-release tag (`rc`, `a`, `b`) and blue for `v1.0.0`.
