# Session 12 — How much the model thinks, and what it costs

**Demo**: one table per subgraph, each row a model at a reasoning effort: held against the suite's bar, dollars and seconds per interaction. The configuration in `.env.example` is the row the rule picked, with the numbers beside it.

The first full log pass on OpenRouter (2026-09-24, `qwen/qwen3.8-27b:nitro`) cost about $4 for 90 runs, a minute each. Most of that was reasoning: ~9k output tokens a report, where the document is a few hundred. Nobody has measured whether that thinking buys anything.

| Question | Answer |
|---|---|
| What varies | The model, and how hard it reasons (`none`/`low`/`medium`/`high`, where the model has the setting). One provider: OpenRouter. |
| What is measured | The existing suites, unchanged: `--suite log` against the set's bars (ADR-0010), `--suite plan` at 100%. Plus cost and wall time per interaction, read from the provider, never from a price typed here. |
| How it is chosen | Per subgraph, the **cheapest configuration that clears its bar**; wall time breaks a tie. Written down with the table, so the next model change is one more row. |
| How much it may spend | **$6 per matrix, hard.** Screening on a minimal set of the rows where the reference fails, at `--repetitions 1`; one finalist at 3, then once on the whole set against the bar. Each ticket states its spend before it runs and reports it after. |
| Not measured | The entrance: it has no suite. It keeps the fastest model the logger's screening shows can call tools, and a suite of its own is a later session's. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | Reasoning effort and the host are settings | — |
| 02 | Every run says what it cost | — |
| 03 | The logger's matrix | 01, 02, 9.5 |
| 04 | The planner's matrix | 01, 02, 10.5 |
| 05 | The choice, written down | 03, 04 |
