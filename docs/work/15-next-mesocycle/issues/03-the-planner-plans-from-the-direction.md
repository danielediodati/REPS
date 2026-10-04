# The planner plans from the direction, and the user reads it

Status: ready-for-agent

Blocked by: 02.

Read first: ADR-0014 items 4-5; ADR-0010 (judgement at a declared bar); ADR-0006 (situations are said by the entrance); `planner.continued` and `planner.mesocycle_brief`.

## What to build

- **The brief of a following mesocycle** holds the direction and the mesocycle that ended. The per-workout log in `continued` goes; `volume_deficit`, `pattern_history` and `last_performed_load` remain as tools.
- **The validator does not hold the direction.** Following it is measured in 04.
- **The proposal tells the user the direction** in a line, in the entrance's words: a situation, not a constant.

## Acceptance criteria

- [ ] A following mesocycle's brief contains the direction and no per-workout log (a test).
- [ ] The proposal in Telegram states the direction.
- [ ] Full test suite and mypy green.
