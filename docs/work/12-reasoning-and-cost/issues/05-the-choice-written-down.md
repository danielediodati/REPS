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

## Acceptance criteria

- [ ] The ADR exists and the defaults match it.
- [ ] `trainer bot` starts on the defaults with an empty `.env` apart from the key and the Telegram settings.
- [ ] Full test suite and mypy green.
