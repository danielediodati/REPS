# Today's workout is read, not planned

Status: ready-for-agent

Blocked by: 01.

ADR-0008 item 3: between workouts nothing is planned. With a mesocycle active, *"what am I doing today?"* is answered at once from it.

## What to build

- **Today's workout off the mesocycle**: the slot at `state.rotation().position`, its blocks as accepted. No model call.
- **The last load beside each exercise**: `state.last_performed_load`, *"I don't know"* where nothing is recorded. Shown, never raised (progression is after 1.0).
- **Prescribed when served** (ADR-0008 item 4): serving it writes the prescribed workout, so the report, adherence and the volume deficit work as they do today. Served twice before it is performed, it is the same prescribed workout, not a second one.
- **Both doors**: `trainer plan` and the bot read it when a mesocycle is active. With none active, the bot offers to plan one and `trainer plan` says so and names `--mesocycle`: a missing precondition is a state (CLAUDE.md).
- **The entrance** reaches it as a tool that reads, not as the planner.

## References

- ADR-0005, ADR-0006, ADR-0008; CONTEXT.md: Workout, Mesocycle, Cycle
- `src/trainer/coach/bot.py`, `src/trainer/coach/entrance.py`, `src/trainer/cli.py` (`plan`), `src/trainer/engine/state.py`, `src/trainer/engine/workouts.py`

## Acceptance criteria

- [ ] With a mesocycle active, the bot answers today's workout without a model call, the slot matching the rotation, the last load beside each loaded exercise.
- [ ] Serving it prescribes it once; reporting it advances the rotation to the next slot.
- [ ] With none active, both doors name the state and the fix.
- [ ] Full test suite and mypy green.
