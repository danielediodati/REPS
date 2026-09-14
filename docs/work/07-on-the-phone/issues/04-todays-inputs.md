# Today's inputs, assembled once for both doors

Status: ready-for-agent

The bot has to answer *"what am I doing today?"* with no arguments. Everything needed is already computed somewhere; the problem is that it is computed inside the CLI.

## What to build

- **The rotation moves into the engine.** `cli._rotated` reads which workout of the split today is from the performed workouts. A bot cannot call a private function of the CLI module, and a second copy is the thing this project has been bitten by. It belongs next to `constraints.constraining_today`: it is a fact about training, derived from workouts performed, not an interface concern.
- **One function assembles `plan.Request`**, and both the CLI and the bot call it. `Request`'s own docstring carries why: assembled at each call site, the two drift and a plan is checked against a request nobody made.
- **What is not derivable is asked in the chat**, as an `interrupt()` like ticket 03's: equipment when it is not the declared default, minutes when the user wants something other than the cap, groups when there is no `training.toml` to take them from. What *is* derivable is never asked.
- **`trainer plan` becomes invoke-then-resume.** With the write living after the resume (ADR-0005), the CLI resumes immediately and implicitly: it has no buttons, and printing a plan has always meant keeping it. It therefore needs a checkpointer even with no bot in sight — the same machine on both doors, which is the point.

## Acceptance criteria

- [ ] The rotation lives in `engine/`, with `cli` calling it and no logic left behind.
- [ ] One function builds `plan.Request`; a test shows the CLI and the bot produce an identical request from the same state.
- [ ] *"cosa faccio oggi?"* with no other words reaches a plan: groups from the rotation, minutes from the cap, equipment from the declaration.
- [ ] A missing `training.toml` is reported as the state it already is (`config.NoTrainingConfig`), naming the example file, and the chat asks for what it needs rather than failing.
- [ ] `trainer plan` still prints and still records exactly one workout, through the resume.
- [ ] The full test suite and mypy are green.
