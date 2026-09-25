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
- Write the table here: per row, invariants held, attempts, $ and s per run, host, and the spend so far.

**Carried from 11.2**, closed without spending so that the planner is measured once. Every run here already plans with [the methodology](../../../../src/trainer/data/methodology.md) in its prompt and a goal in its request (every situation plans for `hypertrophy`). The session-7 plan it is judged against, for chest and arms in 45 minutes with body weight and bands:

```
Blocco 1 · 3 giri · 90s di recupero · 10:18
  Cross Over - With Bands, Incline Push-Up, Clock Push-Up, Push-Up Wide  -- 8 reps each
Blocco 2 · 3 giri · 90s di recupero · 14:00
  Band Skull Crusher, Bench Dips, Speed Band Overhead Triceps,
  Standing Towel Triceps Extension, Body Tricep Press  -- 10 reps each
Totale 25 min su 45
```

No plan-suite pass without the methodology was kept, so there is no *before* to set these tables against; that comparison was given up for one measurement.

**Carried from 11.3**, closed on the same terms. Every run also plans against the time as a target: a plan is refused outside `plan.window` (the minutes asked, ±5). The floor is a new way to fail the 100% bar:

- `no-equipment` asks for 15 minutes, so its floor is 10; `contradictory` asks for 30 over six groups.
- A situation that cannot be met with the floor is a finding about the request or the model, written here. It is not a reason to lower the floor.

## References

- ADR-0001, ADR-0008, ADR-0010
- `src/trainer/evaluation.py`, `src/trainer/data/methodology.md`

## Acceptance criteria

- [ ] The four candidates screened and written, with their spend.
- [ ] The winner confirmed at three repetitions, and one mesocycle from it, timed and costed.
- [ ] The two session-7 plans written here, and neither is a circuit of same-muscle exercises like the one above (11.2).
- [ ] The chosen row named, with the rule that chose it, holding the six invariants at 100% with 11.3's floor in.
- [ ] Total spend at or under $6.
