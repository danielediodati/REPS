# Portfolio-ready

Status: ready-for-human

Blocked by: 04.

Read first: ROADMAP.md (session 15's demo); CLAUDE.md § Closing a session; README.md.

## What to build

- **The demo fixture as a script**: three mesocycles performed (hypertrophy, hypertrophy, strength), the third at its last cycle.
- **The demo in Telegram**: the user writes, the fourth mesocycle arrives with its direction, and what changed is visible.
- **The README rewritten around the working system**, with a GIF of the demo. Every sentence a claim about the running program.

The demo reaches a paid model: estimated first, run on the user's go.

## From 04

- The demo's mesocycles must be ones the validator accepts under the demo's declaration: inside the time window and training each slot's groups. A direction that keeps exercises is planned into a copy of them, and 04's first screening lost 8 of 17 histories to fixtures 23-38 min long against a 40-50 window. `supervise_evaluation.refused` checks a set of them through `plans.mesocycle_requested`.
- The supervisor runs on `openai/gpt-6-luna` (ADR-0011), ~$0.0015 a direction. Its known habit: with a loved exercise in the conclusions it may keep every exercise rather than rotate the rest, so a demo built on *«adoro lo stacco»* can show no change in exercises.
- `trainer bot` checks the supervisor's model at start-up but prints no line for it.

## Acceptance criteria

- [ ] The script builds the fixture from nothing, and `TRAINER_DB` points the bot at it.
- [ ] The demo runs in Telegram as the roadmap's line says.
- [ ] The README shows the GIF and describes 1.0.0 as it runs.
