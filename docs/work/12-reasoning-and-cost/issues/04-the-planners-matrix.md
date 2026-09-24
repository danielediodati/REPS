# The planner's matrix

Status: ready-for-agent

Blocked by: 01, 02.

The planner's bar is 100% on six invariants (ADR-0010), and it also has to write a mesocycle (10.1, 10.5). A plan is longer than a log document, and its tool loop longer, so effort may matter differently here.

**Budget: $6 in total, hard.** No plan-suite run has been costed yet: the first candidate's real cost (02) is the estimate for the rest. One mesocycle on `openai/gpt-oss-120b:nitro` was 93k tokens in and 21k out (10.1).

## What to do

The same four candidates as 03, one effort each: `qwen/qwen3.8-27b` low, `openai/gpt-oss-20b` low, `openai/gpt-oss-120b` low, `anthropic/claude-haiku-4.5` none. Pin the host per model (01).

| Step | What | Runs | Estimate |
|---|---|---|---|
| 1. Screen | each candidate on `trainer eval --suite plan --repetitions 1` (6 situations, *refused* plans twice) | 28 | ~$1.5 |
| 2. Confirm | the cheapest candidate at 100%, at `--repetitions 3` | 21 | ~$1 |
| 3. A mesocycle | the same one, `trainer plan --mesocycle`, with its seconds and cost | 1 | ~$0.1 |
| 4. 11.1's measurement | the session-7 request (chest and arms, 45 minutes, body weight and bands) on `anthropic/claude-sonnet-5` at high, and on the chosen row | 2 | ~$0.6 |

Sonnet is the large-model reference for 11.1 only, not a screening candidate: its one run is the most expensive line here.

- After the first candidate, compare its real cost with the estimate. Above $0.08 a run, stop and ask.
- If no candidate reaches 100% in step 1, stop and ask before anything else runs.
- Write the table here: per row, invariants held, attempts, $ and s per run, host, and the spend so far. Hand the two session-7 plans to 11.2.

## References

- ADR-0001, ADR-0008, ADR-0010
- `src/trainer/evaluation.py`, `docs/work/11-a-plan-worth-doing/issues/02-nobody-ever-told-it-what-a-workout-is.md`

## Acceptance criteria

- [ ] The four candidates screened and written, with their spend.
- [ ] The winner confirmed at three repetitions, and one mesocycle from it, timed and costed.
- [ ] The two session-7 plans written into 11.2.
- [ ] The chosen row named, with the rule that chose it.
- [ ] Total spend at or under $6.
