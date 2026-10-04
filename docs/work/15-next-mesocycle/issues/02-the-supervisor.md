# The supervisor

Status: ready-for-agent

Blocked by: 01.

Read first: ADR-0014; ADR-0008 (a mesocycle is planned once and repeated); ADR-0004 item 5 (each store has one owner); TRAINER.md § The supervisor; CONTEXT.md *Supervisor*, *Direction*.

## What to build

- **A graph** that runs when a mesocycle ends, before the planner plans the next. Not on the first mesocycle, not on a change.
- **Tools over the history**: what a past mesocycle held, volume per muscle and pattern per mesocycle, adherence, the past directions. Its prompt starts from the last mesocycle only; it chooses what else to look at.
- **It writes a direction**: one theme for the whole mesocycle, what changes from the last, why; inside the goal's ranges in `methodology.md`, reasoning with `variation.md` (01). Kept with the mesocycle it shaped, beside `mesocycles.why`.
- **It never reads** the planner's `why` or the entrance's messages. Its own past directions it does.
- A run record like every other run's: what it called, what it cost.
- **Reading `variation.md`**: it has no loader yet. Add one beside `engine/methodology.py`, giving the document without its sources the way `for_planner` does, and move `tests/test_variation.py`'s `VARIATION_PATH` onto it.

## Acceptance criteria

- [ ] On a fixture with a mesocycle at its last cycle, the supervisor runs before the planner and the direction is stored with the next mesocycle.
- [ ] On the first mesocycle and on a change, it does not run.
- [ ] No tool it holds returns the planner's or the entrance's prose (a test).
- [ ] Full test suite and mypy green.

Running it against a paid model is asked for first, with an estimate.
