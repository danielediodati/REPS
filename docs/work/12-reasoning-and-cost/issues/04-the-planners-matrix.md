# The planner's matrix

Status: ready-for-agent

Blocked by: 01, 02.

The planner's bar is 100% on six invariants (ADR-0010), and it also has to write a mesocycle (10.1, 10.5). A plan is longer than a log document, and its tool loop longer, so effort may matter differently here.

## What to do

1. **Screen** on `trainer eval --suite plan --repetitions 1`, the same candidates as 03 plus `anthropic/claude-sonnet-5` at low and high, as the large-model reference.
2. **One mesocycle per finalist**: `trainer plan --mesocycle`, with its seconds and cost.
3. **Write the table here**, as in 03.

This is also **11.1's measurement**: the same request on a large model at full reasoning. Put the session-7 request (chest and arms, 45 minutes, body weight and bands) through Sonnet at high and the chosen row, and hand both plans to 11.2.

**Budget**: as 03; stop and ask above $15.

## References

- ADR-0001, ADR-0008, ADR-0010
- `src/trainer/evaluation.py`, `docs/work/11-a-plan-worth-doing/issues/02-nobody-ever-told-it-what-a-workout-is.md`

## Acceptance criteria

- [ ] Every row of the screening run and written, with its spend.
- [ ] A mesocycle from each finalist, timed and costed.
- [ ] The two session-7 plans written into 11.2.
- [ ] The chosen row named, with the rule that chose it.
