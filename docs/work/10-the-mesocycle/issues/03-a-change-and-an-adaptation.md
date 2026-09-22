# A change and an adaptation

Status: ready-for-agent

Blocked by: 02.

ADR-0008 item 6. A **change** (*"no more lunges"*) rewrites the mesocycle for the cycles left. An **adaptation** (*"only 30 minutes today"*, *"no dumbbells today"*) plans today's workout from the mesocycle's and leaves the mesocycle alone.

## What to build

- **An adaptation**: the planner in single-workout mode, briefed with today's slot of the mesocycle as the starting point and today's constraint as the request. Accepted, it is today's prescribed workout; the mesocycle is untouched.
- **A change**: the planner in mesocycle mode, briefed with the active mesocycle and what the user wants changed. Accepted, it replaces the active one for the cycles left, keeping the count already done.
- **The entrance tells them apart** from the user's words and asks when it cannot. This is the model's reading, never a keyword rule.
- Both are negotiations (ADR-0007): turned down, the next proposal must differ.

## Left by 02

- The entrance has no single-workout handoff: 02 replaced `plan_today` with `todays_workout` (a read) and `plan_mesocycle`. The adaptation is the handoff that brings the single-workout planner back. The bot's plumbing for it is still there: `BUTTONS` with *Solo 30 minuti*, `told`'s single-plan branch, `entrance.PRESCRIBED`.
- `trainer plan` serves the mesocycle only when no option shapes the workout; `--time`, `--equipment`, `--exclude`, `--avoid`, `--workout` and `--group` still plan one workout from nothing. That is where the CLI's adaptation goes.
- A served workout is not checked against today's exclusions: an exclusion added after acceptance is still served. An adaptation, or a change, is the answer.
- An adapted workout accepted for today must count as that slot's serving (the `served` table, migration 0009), or asking again serves the unadapted slot beside it.

## References

- ADR-0006, ADR-0007, ADR-0008; CONTEXT.md: Change, Adaptation, Negotiation
- `src/trainer/coach/entrance.py`, `src/trainer/coach/planner.py`

## Acceptance criteria

- [ ] *"solo 30 minuti oggi"* reaches an adaptation; accepted, the mesocycle in the database is unchanged.
- [ ] *"basta affondi"* reaches a change; accepted, the new mesocycle has no lunges and continues the cycle count.
- [ ] A sentence that could be either is asked about, not guessed.
- [ ] Full test suite and mypy green.
