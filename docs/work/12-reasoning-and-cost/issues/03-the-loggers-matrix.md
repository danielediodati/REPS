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

## Step 2, `gpt-oss-120b` low on DeepInfra at three repetitions (09-29)

| Row | Held | Where it failed | $ a run | s a run |
|---|---|---|---|---|
| U1 | 3 / 3 | | 0.0003 | 6 |
| U4 | 3 / 3 | | 0.0003 | 9 |
| U6 | 2 / 3 | not run: not JSON ×3 | 0.0007 | 17 |
| U8 | 1 / 3 | not run twice: empty emissions | 0.0023 | 54 |
| U11 | 3 / 3 | | 0.0004 | 14 |
| A3 | 3 / 3 | | 0.0009 | 21 |
| A6 | 1 / 3 | asked nothing twice | 0.0004 | 11 |
| A8 | 0 / 3 | asked nothing; once a confident rest | 0.0003 | 11 |
| A10 | 2 / 3 | asked nothing once | 0.0004 | 10 |
| A11 | 2 / 3 | once a confident 6 reps | 0.0004 | 14 |

- **Against the reference on the same rows**: must ask **8 / 15 against 4 / 15**, false confidence 2 against 4. Unambiguous 12 / 15, and **every miss is a run lost to an emission that is not JSON**, never a wrong document.
- U8 is the weak row: 5 of its 6 runs across both steps emitted nothing readable. Model or host, the records cannot say.
- $0.014 in all. Spent on the ticket: ~$0.27 counted.

## `gpt-oss-120b` at medium, the same ten rows at three (09-29)

Asked for by the user, outside the rule: whether more reasoning buys a better question.

| | low | medium |
|---|---|---|
| Must ask | **8 / 15** | 3 / 15 (A11 never ran) |
| False confidence | 2 | 2 |
| Unambiguous | **12 / 15** | 11 / 15 (U8 0 / 3) |
| Lost to not JSON | 3 runs | 7 runs: all of U8 and A11 |
| s a run | 6–54 | 9–56, mostly 25–55 |
| $ | 0.014 | 0.018 counted |

- **Medium is worse on every column**: it asks less, loses more runs to emissions that are not JSON, and is slower. More reasoning does not buy the question.
- Spent on the ticket: ~$0.29 counted.

## Step 3, `gpt-oss-120b` low on the whole set (09-29): not conclusive

Run twice, on DeepInfra and then on AkashML (same bf16 weights, 99.95% uptime against DeepInfra's 96.5% that day). **Each lost two thirds of its rows to 429**, and the second says why: `limit_source: upstream_provider_shared_pool`, `queue_timeout`. OpenRouter's shared pool at the host is full, whichever cheap host; the client retries once (`RETRIES = 1`), within a second.

| Row | DeepInfra | AkashML |
|---|---|---|
| Held | U1 U2 U3 U4 U11 U12 U13, A4 | U1 U2 U9 U15 U16 U17 U18, A1 A2 A4 A5 A11 |
| Failed | U5: rounds `reported`, expected `assumed`. A5: no question, an exclusion on shoulder | U14: rest `reported`, expected `assumed`. A8: no question, a confident rest. A10: no question |
| Not run | 20 | 16 |

- **Measured on neither**: U6 U7 U8 U10, A3 A6 A7 A9 A12.
- Unambiguous, both passes together: 12 held of 14 measured; the bar needs 15 of 18. Must ask: nothing to read yet.
- $0.012 and $0.006 counted. Spent on the ticket: ~$0.31.

**The nine, again on AkashML after `b2da01d`** (a 429 now waits 5, 15, 45 s): none rate-limited. U6 U7 U10 A7 A9 held; U8 not JSON again; A3 A6 A12 asked nothing.

**Stitched**, one result a row, AkashML's where it has one:

| Half | Held | Bar | |
|---|---|---|---|
| Unambiguous | 15 / 18, **83%** | 80% | held. U5, U14: a value from the plan marked `reported`; U8: not JSON |
| Must ask | 7 / 12, A8 counted double: 7 / 13, **54%** | 60% | **below**. A3 A6 A10 A12 asked nothing; A8 wrote a rest |

- **Below the must-ask bar by one question**: at one repetition each row is 8 points. The reference cleared it at 62%.
- Three passes on two hosts, not one: a row's result is one run, whichever host served it.
- Spent on the ticket: ~$0.32.

**The must-ask half at three repetitions**, AkashML, to take the noise out of one run a row:

| Held 3 / 3 | 2 / 3 | 0 / 3 |
|---|---|---|
| A1 A2 A4 A5 A7 A9 A11 | A3 | A6, A8 (writes a rest twice), A10, A12 (writes a value all three times) |

- **23 / 36, 41 counted: 56%, below the 60% bar.** The reference: 25 / 36, 40 counted, 62%.
- **The failures are fixed, not noise**: four rows at 0 / 3 and the rest nearly clean. A6, A8, A10 the reference misses too; **A12 it held**, and 120b answers it with a confident value every time.
- **`gpt-oss-120b` low fails the bar.** Spent on the ticket: ~$0.34.

## Step 1 again, `deepseek-v4-flash` high (09-29)

On DeepInfra, with the waits of `b2da01d`: 10 of 11 rows still rate-limited past 65 s. On **Parasail** (fp8 as DeepInfra, 99.9% uptime, $0.14 / $0.28), the ten rows plus A12, which failed 120b:

| Held | Failed |
|---|---|
| U1 U4 U6 U8, **A3 A6 A8 A10** A11 | U11: rounds `assumed`, said. A12: no question |

- **9 / 11**, and the first candidate to hold A6, A8 and A10, which the reference and 120b miss every time. U8 held.
- $0.001–0.004 and 6–115 s a report, ~35 s typical: a tenth of the reference's price, 120b's speed at worst.
- $0.029. Spent on the ticket: ~$0.37.

## Step 2, `deepseek-v4-flash` high on Parasail at three repetitions (09-29)

| Row | Held | Where it failed | $ a run | s a run |
|---|---|---|---|---|
| U1 | 3 / 3 | | 0.0007 | 8 |
| U4 | 2 / 3 | rest `reported`, expected `assumed` | 0.0015 | 31 |
| U6 | 3 / 3 | | 0.0038 | 66 |
| U8 | 2 / 3 | once logged against workout 4 | 0.0043 | 68 |
| U11 | 1 / 3 | once `asked` with no question; once three documents refused on shape | 0.0038 | 69 |
| A3 | 2 / 3 | asked nothing once | 0.0026 | 56 |
| A6 | 2 / 3 | asked nothing once | 0.0022 | 41 |
| A8 | 3 / 3 | | 0.0018 | 37 |
| A10 | 2 / 3 | asked nothing once | 0.0025 | 51 |
| A11 | 3 / 3 | | 0.0030 | 69 |
| A12 | 2 / 3 | once an exclusion on knee, unasked | 0.0014 | 31 |

- **Must ask, on the five rows all three were run on (A3 A6 A8 A10 A11)**: DeepSeek **12 / 15**, 120b 8 / 15, the reference 4 / 15. All eleven: 14 / 18, 19 counted, 74%.
- **Unambiguous**: 11 / 15 against 120b's 12 / 15; its misses are provenance and one wrong workout, where 120b's were emissions that were not JSON.
- **Slower**: 30–70 s a report, the reference's pace. Rate-limited never, on Parasail.
- A run whose three documents are all refused on shape lands in *not run* (`LogEvaluationError`, by design since 5.5): it is the model's failure, not the host's.
- $0.079. Spent on the ticket: ~$0.45.

## References

- ADR-0009, ADR-0010, `docs/logging/eval-set.md`
- 9.5's full pass in `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md`

## Acceptance criteria

- [ ] The candidates screened on the 10 rows, cheapest first, each reported to the user and written here with its spend.
- [ ] The winner confirmed at three repetitions, and checked against both bars on the whole set.
- [ ] The chosen row named, with the rule that chose it.
- [ ] Total spend at or under $4.
