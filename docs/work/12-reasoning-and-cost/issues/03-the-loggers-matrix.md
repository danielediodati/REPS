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

## Left by 04

- **A run that never returns is paid for and not counted.** It lands in *not run* with no record, so its dollars are missing from `$ in all`: Qwen's two runs at the 65,536-token limit cost ~$0.12 each and the pass reported $0.03. Check OpenRouter's activity page after any pass with a *not run*.
- **An eval-only check hides a failure from the model.** Haiku failed the planner's screen on a rule the eval checked and the validator did not, so the plan passed at its first attempt; once the rule was in the validator it held. Before reading a row as the model's limit, check whether the rule that failed is one the agent is ever told.
- **One situation, or row, per call, in the background**: a pass interrupted mid-way loses its matrix, and the records alone had to be rescored with `evaluation.check`.
- **Before screening, give the logger's `emit` the planner's handling of an emission that is not JSON** (`c5be289`): it is the provider failing, retried within `REJECTIONS` without spending an attempt. The logger got `strict=True` but not the retry, so a host that ignores the schema costs it an attempt (code review of 12.4, declined there as the logger's).
- `deepseek-v4-flash` takes only `high` or `xhigh`, not the spec's `low`.
- Haiku 4.5 at `none` on Anthropic was accepted: its listing takes an effort.

## Step 1, the screen (09-29)

One row per call, `--repetitions 1`. *Asked*: the value's provenance is `asked` with no question put.

| Row | Reference (3 reps) | `gpt-oss-20b` low, CoreWeave | `gpt-oss-120b` low, DeepInfra | `qwen3.8-27b` low, DeepInfra | Haiku 4.5 none, Anthropic |
|---|---|---|---|---|---|
| U1 | ok | ok | ok | ok | ok |
| U4 | provenance invented | no: asked | ok | ok | ok |
| U6 | provenance invented, once looped | not run: not JSON | ok | ok | no: rounds `assumed`, said |
| U8 | once against a prescription | not run: not JSON | not run: empty ×3, twice | ok | no: wrong exercises |
| U11 | provenance invented | no: asked | ok | ok | no: rounds `assumed`, said |
| A3 | 1/3 never asked | not run: not JSON | ok | not run: host timeout | ok |
| A6 | 2/3 never asked | not run: host timeout | no: asked nothing | not run: host down | ok |
| A8 | 3/3 never asked | not run: host timeout | no: asked nothing | no: asked nothing | not run: 429 |
| A10 | 3/3 never asked | not run: host timeout | no: asked nothing | no: asked nothing | not run: 429 |
| A11 | 2/3 never asked | ok | ok | ok | not run: 429 |
| **Held** | | **2 / 4** run | **6 / 9** run | **6 / 8** run | **4 / 7** run |
| $ a report | ~0.04 (`:nitro`) | 0.0003–0.0005 | 0.0003–0.0008 | 0.002–0.008 | 0.012–0.08 |
| s a report | ~60 | 3–7 | 5–20 | 13–230 | 7–24 |

- **Not run is the host, not the model**, except 120b's U8: three empty emissions in each of two separate runs.
- **`gpt-oss-20b` on DeepInfra and `deepseek-v4-flash`: nothing measured.** Every call a 429 (*temporarily rate-limited upstream*), in parallel and again one at a time.
- **Haiku**: OpenRouter caps a new account at 20 requests a minute per model, and one report is several calls. It asks where the others do not (A3, A6) and gets unambiguous documents wrong where they do not.
- **Running candidates in parallel** tripped every rate limit at once: one at a time, as the spec says.
- Spent: ~$0.25 counted, plus the not-run calls (Qwen's A3 timed out after 5 min; check the activity page).

## References

- ADR-0009, ADR-0010, `docs/logging/eval-set.md`
- 9.5's full pass in `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md`

## Acceptance criteria

- [ ] The candidates screened on the 10 rows, cheapest first, each reported to the user and written here with its spend.
- [ ] The winner confirmed at three repetitions, and checked against both bars on the whole set.
- [ ] The chosen row named, with the rule that chose it.
- [ ] Total spend at or under $4.
