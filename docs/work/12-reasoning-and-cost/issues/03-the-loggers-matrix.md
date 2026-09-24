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

1. **Screen** every candidate on the whole set at `--repetitions 1` (30 runs each):

   | Model | Efforts |
   |---|---|
   | `qwen/qwen3.8-27b` | none, low, high |
   | `openai/gpt-oss-20b` | low, high |
   | `openai/gpt-oss-120b` | low, high |
   | `anthropic/claude-haiku-4.5` | none, low |

   Add a model only with a reason written beside it. Pin the host per model (01) so the row is one machine.
2. **Confirm** the two cheapest configurations that clear both bars (ADR-0010) at `--repetitions 3`.
3. **Write the table here**: per row, unambiguous %, must-ask %, $ per report, s per report, host.

**Budget**: state the estimate from the screening's first row before running the rest; stop and ask above $15 in total.

## References

- ADR-0009, ADR-0010, `docs/logging/eval-set.md`
- 9.5's full pass in `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md`

## Acceptance criteria

- [ ] Every row of the screening run and written, with its spend.
- [ ] Two finalists confirmed at three repetitions.
- [ ] The chosen row named, with the rule that chose it.
