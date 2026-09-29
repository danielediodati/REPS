# Session 12 — How much the model thinks, and what it costs

**Demo**: one table per subgraph, each row a model at a reasoning effort: held against the suite's bar, dollars and seconds per interaction. The configuration in `.env.example` is the row the rule picked, with the numbers beside it.

The first full log pass on OpenRouter (2026-09-24, `qwen/qwen3.8-27b:nitro`) cost about $4 for 90 runs, a minute each. Most of that was reasoning: ~9k output tokens a report, where the document is a few hundred. Nobody has measured whether that thinking buys anything.

| Question | Answer |
|---|---|
| What varies | The model, and how hard it reasons (`none`/`low`/`medium`/`high`, where the model has the setting). One provider: OpenRouter. |
| What is measured | The existing suites, unchanged: `--suite log` against the set's bars (ADR-0010), `--suite plan` at 100%. Plus cost and wall time per interaction, read from the provider, never from a price typed here. |
| How it is chosen | Per subgraph, the **cheapest configuration that clears its bar**; wall time breaks a tie. Written down with the table, so the next model change is one more row. |
| How much it may spend | **$4 per matrix, hard.** Screening on a minimal set of the rows where the reference fails, at `--repetitions 1`; one finalist at 3, then once on the whole set against the bar. |
| In what order | **Cheapest candidate first, then up**, by its pinned host's price. **One run at a time**: each run gets its estimate before and a report after (below), and the next runs only on the user's go. |
| The report after each run | In Italian, in the conversation: the model, effort and host; held against the bar, row by row where it failed; attempts and tool calls; $ and s per interaction; the spend so far against the $4; what the records show about how it failed; and the next run proposed with its estimate. |
| Not measured | The entrance: it has no suite. It keeps the fastest model the logger's screening shows can call tools, and a suite of its own is a later session's. |

## Candidates

The same five for both matrices, one effort each, in the order they run. Each pinned to the cheapest host that serves tools, `json_schema` and the effort, by OpenRouter's endpoint listing on 2026-09-25 ($ per million tokens). `high` is left out: the reference already reasons at length, and the question is whether less loses anything.

| # | Model | Effort | Host (`OPENROUTER_PROVIDER`) | In | Out |
|---|---|---|---|---|---|
| 1 | `openai/gpt-oss-20b` | low | `coreweave` | 0.03 | 0.13 |
| 2 | `openai/gpt-oss-120b` | low | `deepinfra` | 0.037 | 0.17 |
| 3 | `deepseek/deepseek-v4-flash` | high (it takes no `low`) | `deepinfra` | 0.09 | 0.18 |
| 4 | `qwen/qwen3.8-27b` | low | `deepinfra` | 0.15 | 1.875 |
| 5 | `anthropic/claude-haiku-4.5` | none | `anthropic` | 1.00 | 5.00 |

Hosts differ in what they support: five of `deepseek-v4-flash`'s sixteen take no `json_schema`, and the emit node fails there. Check the listing again before pinning; prices move.

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | Reasoning effort and the host are settings | — |
| 02 | Every run says what it cost | — |
| 03 | The logger's matrix | 01, 02, 9.5 |
| 04 | The planner's matrix | 01, 02, 10.5 |
| 05 | The choice, written down | 03, 04 |
| 06 | Secrets in the keychain, models in a file | 05 |
