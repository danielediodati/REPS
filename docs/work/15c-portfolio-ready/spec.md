# Session 15c — Portfolio-ready

**Demo**: after three mesocycles, the fourth arrives in Telegram with its reason; and *"actually, I only have 30 minutes"* mid-plan brings the 30-minute plan. Recorded in English, with a GIF in the README.

Tickets 01 and 02 are the fixes found using `1.0.0rc1` on the demo's home, 2026-10-07. A substitute exercise inheriting its block's numbers was raised and dropped by the user: likely not a real problem.

## Carried from 15c.5

- Recording the demo took three attempts, $0.82 in all: $0.19 and $0.20 when it ran clean, $0.41 when the fourth mesocycle was refused by the validator three times on `anthropic/claude-haiku-4.5` and planned again on *«yes»*.
- To show a run stopped mid-plan, the correction is sent as soon as the bot answers «On it»: an adaptation is written in ~35 s.

## Carried from 15c.4

- Measured in the rehearsal, 2026-10-15, on `anthropic/claude-haiku-4.5`: a mesocycle $0.042–0.058; the report, the supervisor and the entrance's turns together under $0.01.
- A planner turn that looks at two workouts at once names the last of them in the draft.

## Carried from 15c.2

- Exercise names in the chat are the catalog's, in English (*Barbell Squat*); everything else is in the chat's language, English for the recording (ADR-0016).
- A workout adapted only in time keeps the reasons of the slot it adapts; new reasons appear when the exercises change, e.g. *«oggi ho solo i manubri»*.
- Measured on `anthropic/claude-haiku-4.5`: an adaptation $0.014–0.029, a mesocycle ~$0.06.

## Carried from 15.5

- `trainer demo HOME` builds the demo's home from `docs/demo/history.toml`; the bot is pointed at it with `TRAINER_HOME`, and a `TRAINER_DB` already set wins over it.
- The demo's mesocycles must be ones the validator accepts under the demo's declaration: inside the time window and training each slot's groups. `trainer demo` checks them before writing.
- The supervisor runs on `openai/gpt-6-luna` (ADR-0011), ~$0.0015 a direction. With a loved exercise in the conclusions it may keep every exercise rather than rotate the rest, so a demo built on *«adoro lo stacco»* can show no change in exercises.
- Recording the demo reaches paid models: estimated first, run on the user's go.

## Carried from 15b.5

- The tests badge is GitHub's own; coverage and release are SVGs the Action writes to the `badges` branch, read from `github.com/danielediodati/REPS/raw/badges/`. While the repository is private they show only to its owner: once public, check them logged out.
- The Action runs on Python 3.12, the floor `requires-python` claims; local development is on 3.14. Before 3.14 `asyncio.run` takes only a coroutine, so mypy on 3.14 alone misses it.
- The release badge is orange for a pre-release tag (`rc`, `a`, `b`) and blue for `v1.0.0`.
