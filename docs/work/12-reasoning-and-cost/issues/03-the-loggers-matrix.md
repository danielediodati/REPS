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

**Budget: $6 in total, hard.** The reference row costs about $0.04 a report; every estimate below uses that as the ceiling.

**The minimal set: 10 rows**, picked where the reference fails, so they tell the candidates apart. One easy row to catch a model that cannot log at all.

| Kind | Rows |
|---|---|
| Must ask | A3, A6, A8, A10, A11 |
| Unambiguous | U1 (control), U4, U6, U8, U11 |

The reference is **not re-run**: its per-row results on these 10 are the ones above.

| Step | What | Runs | Estimate |
|---|---|---|---|
| 1. Screen | each candidate on the 10 rows, `--only`, `--repetitions 1` | 40 | ~$1.6 |
| 2. Confirm | the cheapest candidate no worse than the reference on the 10 rows, at `--repetitions 3` | 30 | ~$1.2 |
| 3. Check the bar | the same one on the whole set, `--repetitions 1`, against both bars (ADR-0010) | 30 | ~$1.2 |

Candidates, one effort each: `qwen/qwen3.8-27b` low, `openai/gpt-oss-20b` low, `openai/gpt-oss-120b` low, `anthropic/claude-haiku-4.5` none. `high` is left out: the reference already reasons at length, and the question is whether less loses anything. Pin the host per model (01).

- After the first candidate, compare its real cost (02) with the estimate. Above $0.06 a report, stop and ask.
- If the winner fails the bar in step 3, stop: the second candidate is not run without asking.
- Write the table here: per row, unambiguous and must-ask on the 10, $ and s per report, host, and the spend so far.

## References

- ADR-0009, ADR-0010, `docs/logging/eval-set.md`
- 9.5's full pass in `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md`

## Acceptance criteria

- [ ] The four candidates screened on the 10 rows and written, with their spend.
- [ ] The winner confirmed at three repetitions, and checked against both bars on the whole set.
- [ ] The chosen row named, with the rule that chose it.
- [ ] Total spend at or under $6.
