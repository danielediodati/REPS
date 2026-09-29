# The choice, written down

Status: ready-for-agent

Blocked by: 03, 04.

## What to build

- **An ADR**: per subgraph, the chosen model, effort and host, the rule that chose it, and the two tables. The next model change adds a row and reruns the rule.
- **The defaults follow it**: `DEFAULT_OPENROUTER_MODEL`, and the effort defaults, in `models.py` and `.env.example`.
- **What a month costs**, from measured cost per interaction: ~20 reports, ~300 entrance turns, one mesocycle. In the README, as a range.
- **The research note is corrected** where the measurement contradicts it (`docs/research/paid-llm-provider.md`: `:nitro` speed, price per report).

## Left by 04, the planner's matrix (closed 2026-09-28)

The table for the ADR. `--suite plan`, bar 100% on six invariants; a run is one two-slot mesocycle.

| Model, effort, host | Screen (1 rep) | 3 reps | $ a mesocycle | s a mesocycle |
|---|---|---|---|---|
| `openai/gpt-oss-20b` low, CoreWeave / AkashML | 0 / 6; 1 / 2 run | — | 0.002 | 76–183 |
| `openai/gpt-oss-120b` low, DeepInfra | 2 / 6 | — | 0.003 | 211 |
| `deepseek/deepseek-v4-flash` **high**, DeepInfra | 5 / 6, then 3 / 6 a day later | — | 0.005–0.007 | 318–497 |
| `qwen/qwen3.8-27b` low, DeepInfra | 6 / 6 | stopped at 8 / 9: `contradictory` 1 / 3, two calls ran to the 65,536-token limit | ~0.05 | 330–765 |
| **`anthropic/claude-haiku-4.5` none, Anthropic** | 5 / 6, then 6 / 6 with `untrained` in the validator | **18 / 18** | **~0.13** | **~47** |

- **Chosen: Haiku, none, Anthropic**: the cheapest row at 100%. `contradictory` (six groups in 30 minutes) held at the last of its three attempts every time.
- **`untrained` moved into the validator** (`491f084`) during the matrix: Haiku's one screening failure was a group left untrained that the eval checked and the validator did not. Rows above Haiku ran before it.
- **11.1's request**, one workout, on Sonnet 5 at high: the same shape as Haiku's (straight sets, compound first, 42 vs 40 of 45 min) at $0.33 and 142 s against $0.05 and 30 s. No row needs a large model.
- Spent: ~$3.86 of $4.

## Left by 03, the logger's matrix (closed 2026-09-29)

The table for the ADR. `--suite log`, bars 80% unambiguous and 60% must ask (ADR-0010). Screened on ten rows where the reference fails (U1 U4 U6 U8 U11, A3 A6 A8 A10 A11), plus A12 once 120b failed it.

| Model, effort, host | Screen (1 rep) | 3 reps, same rows | Whole set | $ a report | s a report |
|---|---|---|---|---|---|
| Reference: `qwen/qwen3.8-27b:nitro`, no effort | — | — | 83% / 62% (9.5) | ~0.04 | ~60 |
| `openai/gpt-oss-20b` low, CoreWeave | 2 / 4 run, 6 lost to the host | — | — | 0.0004 | 3–7 |
| `openai/gpt-oss-120b` low, DeepInfra / AkashML | 6 / 9 run | must ask 8 / 15 | 83% / **56%** (must ask at 3 reps) | 0.0005 | 6–54 |
| `openai/gpt-oss-120b` medium, DeepInfra | — | must ask 3 / 15 | — | 0.0006 | 25–55 |
| **`deepseek/deepseek-v4-flash` high, Parasail** | 9 / 11 | must ask 12 / 15 | **83% / 92%** | **0.003** | **8–200** |
| `qwen/qwen3.8-27b` low, DeepInfra | 6 / 8 run | — | — | 0.002–0.008 | 13–230 |
| `anthropic/claude-haiku-4.5` none, Anthropic | 4 / 7 run, wrong unambiguous documents | — | — | 0.01–0.08 | 7–24 |

- **Chosen: DeepSeek v4 flash, high, Parasail**: the cheapest row that clears both bars. It is the first to ask on A6, A8, A10; A12 (*"il ginocchio cosi cosi"*) it misses on the whole set.
- **`gpt-oss-20b` was never measured properly**: the hosts lost 16 of its 20 rows. Excluded on its 2 / 4 and its larger sibling's must-ask score, not screened out.
- **More reasoning is not better questions**: 120b at medium asked less than at low, and the reference, which reasons longest, asked least.
- Spent: ~$0.54 of $4, counted; runs lost to a host are not in that figure.

**For the defaults and the host:**
- **OpenRouter's shared pool, not the host's uptime, is what fails.** A 429 with `limit_source: upstream_provider_shared_pool` hit DeepInfra (three models) and AkashML at busy hours, while their uptime read 96–99.5%. `b2da01d` waits 5, 15, 45 s; DeepInfra kept DeepSeek limited past all of it, Parasail limited it once. Pin the production host by that record, not the listing.
- **Time is the open cost.** DeepSeek on Parasail went from 8–63 s a report to 80–200 s within one evening pass. The user wants Cerebras in production for speed: **Cerebras serves `gpt-oss-120b`, not DeepSeek v4 flash** (OpenRouter's listing, 2026-09-29). Check what it serves before choosing, or name a fallback host (`allow_fallbacks`) and accept that the record then names more than one.
- **New OpenRouter accounts are held to 20 requests a minute per model**, which is what stopped Haiku: one report is several calls.

## Acceptance criteria

- [ ] The ADR exists and the defaults match it.
- [ ] `trainer bot` starts on the defaults with an empty `.env` apart from the key and the Telegram settings.
- [ ] Full test suite and mypy green.
