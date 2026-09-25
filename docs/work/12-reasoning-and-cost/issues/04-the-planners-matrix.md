# The planner's matrix

Status: ready-for-agent

Blocked by: 01, 02, 10.5.

The planner's bar is 100% on six invariants (ADR-0010), measured on mesocycles: after 10.5 every situation of `--suite plan` asks for one, and there is no single-workout pass to screen on. A plan is longer than a log document, and its tool loop longer, so effort may matter differently here.

**Budget: $6 in total, hard; the estimates below are for single workouts and are now low.** A mesocycle run is about five workouts' worth of tokens, so steps 1 and 2 are to be re-estimated from 10.5's first costed run, and the budget confirmed with the user before step 1. No plan-suite run has been costed yet: the first candidate's real cost (02) is the estimate for the rest. One mesocycle on `openai/gpt-oss-120b:nitro` was 93k tokens in and 21k out (10.1).

## What to do

The same four candidates as 03, one effort each: `qwen/qwen3.8-27b` low, `openai/gpt-oss-20b` low, `openai/gpt-oss-120b` low, `anthropic/claude-haiku-4.5` none. Pin the host per model (01).

| Step | What | Runs | Estimate |
|---|---|---|---|
| 1. Screen | each candidate on `trainer eval --suite plan --repetitions 1` (6 situations, *refused* plans twice) | 28 | ~$1.5 |
| 2. Confirm | the cheapest candidate at 100%, at `--repetitions 3` | 21 | ~$1 |
| 3. 11.1's measurement | the session-7 request (chest and arms, 45 minutes, body weight and bands) on `anthropic/claude-sonnet-5` at high, and on the chosen row | 2 | ~$0.6 |

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

**Left by 10.5**, the first costed mesocycle run of the suite: 2026-09-25, `no-history`, `--repetitions 1`, `openai/gpt-oss-120b`, no effort, **no host pinned**.

| Held | Attempts | Tool calls | Tokens | Cost | Time | Hosts |
|---|---|---|---|---|---|---|
| 6 of 6 invariants, both workouts | 2 | 4 | 47k in, 8.4k out | **$0.0031** | **207 s** | DeepInfra (planner), CoreWeave and DekaLLM (emit) |

- **This is the estimate for step 1**, and it is far under the table's: at ~$0.003 a situation, the screening's 28 runs are cents on this model. A pinned `:nitro` host is the other end: 10.1's one mesocycle there was 17 s and about ten times the tokens' price.
- **207 s is the router, not the model**: a single emit took 23 s on CoreWeave and 51 s on DekaLLM. Pin the host per candidate (01), or the seconds column measures the router's choice.
- **The first attempt was refused on two rules**, both workouts: under the time floor (24 and 20 of 30 minutes, 11.3), and `despite` rows naming exercises the user never refused. The second attempt held. Expect both among the screening's refusals.
- The suite's two slots are `evaluation.SPLIT`, lower and upper, so a run is two workouts, not five.

## References

- ADR-0001, ADR-0008, ADR-0010
- `src/trainer/evaluation.py`, `src/trainer/data/methodology.md`

## Acceptance criteria

- [ ] The four candidates screened and written, with their spend.
- [ ] The winner confirmed at three repetitions, with seconds and cost per mesocycle.
- [ ] The two session-7 plans written here, and neither is a circuit of same-muscle exercises like the one above (11.2).
- [ ] The chosen row named, with the rule that chose it, holding the six invariants at 100% with 11.3's floor in.
- [ ] Total spend at or under $6.
