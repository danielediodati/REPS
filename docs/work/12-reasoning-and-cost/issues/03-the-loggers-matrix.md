# The logger's matrix

Status: ready-for-agent

Blocked by: 01, 02, and 9.5's full pass, which is the reference row.

## The reference row

9.5's full pass, 2026-09-24, `qwen/qwen3.8-27b:nitro`, no effort set, 3 repetitions:

| Unambiguous | Must ask | Tokens | Cost | Time |
|---|---|---|---|---|
| 45 / 54, 83% | 25 / 36, 40 counted, 62% | 989k in, 733k out, 256 tool calls | ~$4: nearly $3 at two thirds, by OpenRouter's activity page | about a minute a report |

Where it fails, so a cheaper row is read against the same misses:

- **Must ask**: A8 3/3, A10 3/3, A6 2/3, A11 2/3, A3 1/3 never asked; A8 and A11 wrote a confident answer twice each. 6 of 54 unambiguous runs asked anyway.
- **Provenance invented** on a value nobody gave (`asked` with no question, `reported` with nothing said): U4, U5, U6, U7, U11, U14.
- **U8** once reported against a prescription where the report names none; **U6** once looped on a null rest with nothing behind it until the attempts ran out.

Earlier passes, for the record: 2026-09-21 `gpt-oss:20b` on Ollama 24 / 90 (~2.6 h); 2026-09-22 Ollama 3 / 15 and Groq Qwen 9 / 12 on U1 U2 U9 U15 A8; 2026-09-23 OpenRouter Qwen 9 / 15 on the same rows, which closed 9.6.

## What to do

**Budget: $4 in total, hard.** The candidates run cheapest first, one at a time, each with an estimate before and a report after, and the next only on the user's go ([spec](../spec.md): In what order, The report after each run, Candidates). The reference row cost about $0.04 a report on `:nitro`; U1 on default routing cost $0.0027 (02).

**The minimal set: 10 rows**, picked where the reference fails, so they tell the candidates apart. One easy row to catch a model that cannot log at all.

| Kind | Rows |
|---|---|
| Must ask | A3, A6, A8, A10, A11 |
| Unambiguous | U1 (control), U4, U6, U8, U11 |

The reference is **not re-run**: its per-row results on these 10 are the ones above.

| Step | What | Runs |
|---|---|---|
| 1. Screen | each candidate on the 10 rows, `--only`, `--repetitions 1` | 10 per candidate |
| 2. Confirm | the cheapest candidate no worse than the reference on the 10 rows, at `--repetitions 3` | 30 |
| 3. Check the bar | the same one on the whole set, `--repetitions 1`, against both bars (ADR-0010) | 30 |

- Above $0.06 a report on any candidate, stop and ask.
- If the winner fails the bar in step 3, stop: the second candidate is not run without asking.
- Write the table here: per row, unambiguous and must-ask on the 10, $ and s per report, host, and the spend so far.

## Left by 01

- **Effort**: `LOGGER_REASONING` / `PLANNER_REASONING`. A model whose listing takes no effort refuses every value, `none` included: for *Haiku none*, check its listing and leave the variable empty if it has no `reasoning`.
- **Host**: `OPENROUTER_PROVIDER` takes the slug (`deepinfra`); the record names it as the response does (`DeepInfra`).
- **Groq no longer serves `qwen/qwen3.8-27b`** (2026-09-24): pinned there, the request is a 404 mid-run, not a state before it. `deepinfra` serves it (bf16): 46 tokens in, 18 out, 1.7 s at `low`. Check each candidate's hosts on its model page before pinning.

## Left by 02

- **Cost is read, not estimated**: the pass ends with `$ in all, $ a run, s a run`; each record holds `dollars` per run and per node. Report spend from those lines.
- **U1 on default routing** (2026-09-25, `qwen/qwen3.8-27b`, no suffix, no effort, no host pinned): held, **$0.0027 and 10 s a report**, 472 tokens out, answered by Reka and Wafer within one run. The reference's ~$0.04 was `:nitro`. The host moves the price by an order of magnitude, so each candidate's row names its host, and a screen that does not pin one is measuring the router.

## References

- ADR-0009, ADR-0010, `docs/logging/eval-set.md`
- 9.5's full pass in `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md`

## Acceptance criteria

- [ ] The candidates screened on the 10 rows, cheapest first, each reported to the user and written here with its spend.
- [ ] The winner confirmed at three repetitions, and checked against both bars on the whole set.
- [ ] The chosen row named, with the rule that chose it.
- [ ] Total spend at or under $4.
