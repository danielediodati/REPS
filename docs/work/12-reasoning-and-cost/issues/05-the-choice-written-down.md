# The choice, written down

Status: ready-for-agent

Blocked by: 03, 04.

## What to build

- **An ADR**: per subgraph, the chosen model, effort and host, the rule that chose it, and the two tables. The next model change adds a row and reruns the rule.
- **The defaults follow it**: `DEFAULT_OPENROUTER_MODEL`, and the effort defaults, in `models.py` and `.env.example`.
- **What a month costs**, from measured cost per interaction: ~20 reports, ~300 entrance turns, one mesocycle. In the README, as a range.
- **The research note is corrected** where the measurement contradicts it (`docs/research/paid-llm-provider.md`: `:nitro` speed, price per report).

## Acceptance criteria

- [ ] The ADR exists and the defaults match it.
- [ ] `trainer bot` starts on the defaults with an empty `.env` apart from the key and the Telegram settings.
- [ ] Full test suite and mypy green.
