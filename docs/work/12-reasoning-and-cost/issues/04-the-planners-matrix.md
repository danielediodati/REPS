# The planner's matrix

Status: ready-for-agent

Blocked by: 01, 02, 10.5.

**Found before it ran** ([research](../../../research/planner-in-steps.md), where the first screening is written):
- `gpt-oss-120b` cannot reliably emit the plan's schema: broken or empty JSON on DeepInfra, which does not enforce `strict`, and *"Failed to generate JSON"* on Groq, which does. Screen it, but count runs lost this way.
- A host is chosen also for holding the schema: `require_parameters` routes to hosts that declare `response_format`, not to hosts that honour it.
- Report runs lost to a provider fault as their own column; a run that ends in `ProviderFailed` leaves no record today, so its emitted text is lost.

The planner's bar is 100% on six invariants (ADR-0010), measured on mesocycles: after 10.5 every situation of `--suite plan` asks for one, and there is no single-workout pass to screen on. A plan is longer than a log document, and its tool loop longer, so effort may matter differently here.

**Budget: $4 in total, hard.** The candidates run cheapest first, one at a time, each with an estimate before and a report after, and the next only on the user's go ([spec](../spec.md): In what order, The report after each run, Candidates). The first costed mesocycle run is below (Left by 10.5): $0.003 a situation on `gpt-oss-120b`.

## What to do

The spec's five candidates, in its order.

| Step | What | Runs | Estimate |
|---|---|---|---|
| 1. Screen | each candidate on `trainer eval --suite plan --repetitions 1` (6 situations, *refused* plans twice) | 7 per candidate | from list price and 10.5's tokens |
| 2. Confirm | the cheapest candidate at 100%, at `--repetitions 3` | 21 | |
| 3. 11.1's measurement | the session-7 request, `trainer plan --group chest --group arms --time 45 --equipment "body only" --equipment bands`, on `anthropic/claude-sonnet-5` at high, and on the chosen row | 2 | ~$0.6 |

Sonnet is the large-model reference for 11.1 only, not a screening candidate: its one run is the most expensive line here. `--group` plans one workout from nothing, so the comparison is with the session-7 plan like for like.

- Above $0.08 a run on any candidate, stop and ask.
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

## Step 1, screened: Qwen the one at 100%

`--suite plan --repetitions 1`, 6 situations, bar 100% on six invariants.

| Date | Candidate | Host | Held | $ a run | s a run | $ in all |
|---|---|---|---|---|---|---|
| 09-25 | `gpt-oss-20b` low | CoreWeave | 0 / 6: empty emit three times, then the host went silent | 0.0021 | 76 | ~0.002 |
| 09-25 | `gpt-oss-20b` low | AkashML | 1 / 2 run, 4 not run (429, shared pool) | 0.0019 | 183 | 0.0056 |
| 09-25 | `gpt-oss-120b` low | DeepInfra | 2 / 6: time under the floor, `despite` misused, one emission that did not parse | 0.0032 | 211 | 0.0222 |
| 09-25 | `deepseek-v4-flash` high | DeepInfra | 5 / 6: `contradictory` repeats an exercise | 0.0069 | 497 | 0.0484 |
| 09-26 | `deepseek-v4-flash` high | DeepInfra | 3 / 6: `no-equipment` and `contradictory` leave a group untrained, `preference-against-the-split` over the time | 0.0048 | 318 | 0.0338 |
| 09-26, 09-28 | `qwen3.8-27b` low | DeepInfra | **6 / 6** | 0.029 to **0.126**, 0.054 on average | 360 to 1,900 | 0.3748 |

**Spent on step 1: ~$0.49 of $4.** The planner-in-steps measures ([research](../../../research/planner-in-steps.md)) are not counted here.

Qwen's four 09-26 runs were interrupted before the pass printed its matrix; they were scored afterwards from their records with `evaluation.check`, which gives DeepSeek's 09-26 records the same verdicts the live pass printed. `refused` and `preference-against-the-split` ran live on 09-28 at 100%: $0.035 and $0.029 a run, 396 s and 360 s.

- `deepseek-v4-flash` takes only `high` or `xhigh`; the spec's `low` is not on offer.
- The same model and host went from 5 / 6 to 3 / 6 in a day: one repetition does not rank DeepSeek against the bar.
- Qwen is the only candidate at 100%, at 10 to 40 times the others' price. `contradictory` alone cost $0.126 (93k in, 61k out, 12 tool calls), **over the $0.08 stop line**; the user chose to finish the screen anyway.
- Haiku (candidate 5) is not screened: it costs more than Qwen, so it runs only if Qwen fails step 2.
- Records, until the scratchpads are cleaned: `%TEMP%\claude\<project>\9b7445f4-…\scratchpad\runs-12.4-*` (09-25) and `…\db7b2547-…\scratchpad\{deepseek,qwen}` (09-26, 09-28).

**Next, on the user's go**: step 2, Qwen at `--repetitions 3`, 21 runs, ~$1.1 at its average and up to ~$2.6 if every run costs what `contradictory` did.

## References

- ADR-0001, ADR-0008, ADR-0010
- `src/trainer/evaluation.py`, `src/trainer/data/methodology.md`

## Acceptance criteria

- [ ] The candidates screened, cheapest first, each reported to the user and written here with its spend.
- [ ] The winner confirmed at three repetitions, with seconds and cost per mesocycle.
- [ ] The two session-7 plans written here, and neither is a circuit of same-muscle exercises like the one above (11.2).
- [ ] The chosen row named, with the rule that chose it, holding the six invariants at 100% with 11.3's floor in.
- [ ] Total spend at or under $4.
