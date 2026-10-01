# The next workout is the first not yet performed

Status: ready-for-agent

Blocked by: none.

Read first: ADR-0008 item 3; CONTEXT.md *Cycle*.

## What to build

- **Today's workout** is the first of the mesocycle's workouts not yet performed in the current cycle, read off the performed workouts. Today it is `performed % length` (`engine/state.py`, `mesocycles.today`), which a swapped order would throw off.
- **A performed workout records which of the mesocycle's it was**, so the log says what was done, not where the count stood.
- No stored order and no "postponed" state: the log is the only source.
- A cycle still ends after as many performed workouts as its length, whichever they were. A workout done twice and another skipped is not prevented; it shows in the volume deficit.

## Acceptance criteria

- [ ] Cycle A, legs, B: A performed, then B performed → the next is legs, then A.
- [ ] An unchanged order serves exactly as today; existing tests stay green.
- [ ] Full test suite and mypy green.
