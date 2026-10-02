# Each node runs the cheapest configuration that clears its bar

Session 12 measured models by reasoning effort and host on OpenRouter, against the suites' bars (ADR-0010) and in dollars and seconds read from the provider. Until then the default was Ollama on the laptop's CPU (ADR-0004 item 8), a mesocycle took minutes, and OpenRouter's default was a model nobody had chosen.

## Decision

1. **The rule**: per node, the **cheapest configuration that clears its suite's bar**; wall time breaks a tie. A configuration is a model, an effort and a host.
2. **The choices**:

   | Node | Model | Effort | Host | Bar | $ | s |
   |---|---|---|---|---|---|---|
   | Planner | `anthropic/claude-haiku-4.5` | none | `anthropic` | plan suite, 100% | ~0.13 a mesocycle | ~47 |
   | Logger | `deepseek/deepseek-v4-flash` | high | `parasail` | log suite, 80% / 60% | ~0.003 a report | 8–200 |
   | Onboarding | `deepseek/deepseek-v4-flash` | high | `parasail` | onboard suite, 100% held / 80% on time, remembered, routed | ~0.0015 an onboarding | 3–150 |
   | Entrance | `deepseek/deepseek-v4-flash` | high | `parasail` | adapt suite, 80% routed | 0.0003–0.001 a turn | 1–6 |

3. **The default provider is OpenRouter.** `LLM_BACKEND` empty is `openrouter`, so the key alone runs every choice. Ollama and Groq stay selectable.
4. **A choice's effort and host belong to its model.** Another model named on a node's line runs at its own default effort, on OpenRouter's routing. `OPENROUTER_MODEL` moves every node off its choice, which is how a matrix row runs.
5. **The host is pinned per node**: `PLANNER_HOST`, `LOGGER_HOST`, `ONBOARDING_HOST`, `ENTRANCE_HOST`, then `OPENROUTER_PROVIDER` for all, then the choice's. No fallback to another host, so the run record names one.
6. **The next model change is one more row** in the table below, run the same way, then this rule reapplied.

## The planner's matrix

`--suite plan`, bar 100% on six invariants. A run is one two-slot mesocycle.

| Model, effort, host | Screen (1 rep) | 3 reps | $ a mesocycle | s a mesocycle |
|---|---|---|---|---|
| `openai/gpt-oss-20b` low, CoreWeave / AkashML | 0 / 6; 1 / 2 run | — | 0.002 | 76–183 |
| `openai/gpt-oss-120b` low, DeepInfra | 2 / 6 | — | 0.003 | 211 |
| `deepseek/deepseek-v4-flash` high, DeepInfra | 5 / 6, then 3 / 6 a day later | — | 0.005–0.007 | 318–497 |
| `qwen/qwen3.8-27b` low, DeepInfra | 6 / 6 | stopped at 8 / 9: `contradictory` 1 / 3, two calls to the 65,536-token limit | ~0.05 | 330–765 |
| **`anthropic/claude-haiku-4.5` none, Anthropic** | 5 / 6, then 6 / 6 with `untrained` in the validator | **18 / 18** | **~0.13** | **~47** |

- Haiku's one screening failure was a group left untrained that the eval checked and the validator did not; `untrained` moved into the validator (`491f084`). Rows above Haiku ran before that.
- Sonnet 5 at high, on 11.1's request, planned the same shape as Haiku at $0.33 and 142 s. No row needs a large model.
- **Prompt caching** (14.5), `--only no-equipment`, 1 rep each, same evening: $0.073 without a breakpoint, **$0.052 with one**, 12 calls and 34–38 s both. 79,368 of 100,031 input tokens read from the cache. `emit` is $0.015 of the $0.052, the largest call: it binds no tools, and tools come first in Anthropic's prefix, so it cannot read the turns before it.

## The logger's matrix

`--suite log`, bars 80% unambiguous and 60% must ask. Screened on the ten rows where the reference fails (U1 U4 U6 U8 U11, A3 A6 A8 A10 A11), plus A12.

| Model, effort, host | Screen (1 rep) | 3 reps, same rows | Whole set | $ a report | s a report |
|---|---|---|---|---|---|
| Reference: `qwen/qwen3.8-27b:nitro`, no effort | — | — | 83% / 62% | ~0.04 | ~60 |
| `openai/gpt-oss-20b` low, CoreWeave | 2 / 4 run, 6 lost to the host | — | — | 0.0004 | 3–7 |
| `openai/gpt-oss-120b` low, DeepInfra / AkashML | 6 / 9 run | must ask 8 / 15 | 83% / **56%** | 0.0005 | 6–54 |
| `openai/gpt-oss-120b` medium, DeepInfra | — | must ask 3 / 15 | — | 0.0006 | 25–55 |
| **`deepseek/deepseek-v4-flash` high, Parasail** | 9 / 11 | must ask 12 / 15 | **83% / 92%** | **0.003** | **8–200** |
| `qwen/qwen3.8-27b` low, DeepInfra | 6 / 8 run | — | — | 0.002–0.008 | 13–230 |
| `anthropic/claude-haiku-4.5` none, Anthropic | 4 / 7 run, wrong unambiguous documents | — | — | 0.01–0.08 | 7–24 |

- `gpt-oss-20b` was never measured properly: the hosts lost 16 of its 20 rows. It is excluded on its 2 / 4 and its larger sibling's must-ask score.
- More reasoning did not buy better questions: 120b at medium asked less than at low, and the reference, which reasons longest, asked least.

## Onboarding's matrix

`--suite onboard` (ticket 13.5) on its six held cases, three interviews and three changes, 3 reps a pass; deepseek's row is three passes. Bars in `docs/onboarding/eval-set.toml`: 100% held (fields filled and valid, quotes said, path open, only the changed fields), 80% on time, 80% remembered, 80% routed.

| Model, effort, host | Held | On time | Remembered | $ an onboarding | s an onboarding |
|---|---|---|---|---|---|
| `openai/gpt-oss-120b` low, Cerebras | 11 / 18 | 14 / 18 | 2 / 9 | 0.009 | 0–15 |
| **`deepseek/deepseek-v4-flash` high, Parasail** | **54 / 54** | **52 / 54** | **27 / 27** | **0.0013–0.0017** | **3–150** |
| `anthropic/claude-haiku-4.5` none, Anthropic | 18 / 18 | 17 / 18 | 8 / 9 | 0.018 | 2–18 |

- **On time** is whether a field was declared before the next question: a persona that has said everything repeats an undeclared answer. It began at 100% and moved to a bar after the third pass, because code cannot tell a late declaration from a proposed split being confirmed, which the prompt asks for. The final state was valid in every run either way.
- gpt-oss-120b writes tool calls as text (`to=functions.finish{}`) and never ends.
- Routing (`change_declaration` against `adapt_today`) runs on the entrance's choice: 36 / 36 over three passes.

## The entrance's matrix

`--suite adapt` (ticket 14.4), 19 messages, 1 rep each, the planner on its choice. Bars in `docs/adapting/eval-set.toml`: 80% routed, and every adapted plan holding its row.

| Model, effort, host | Routed | Plans held | $ a turn | s a turn |
|---|---|---|---|---|
| `openai/gpt-oss-120b` low, Cerebras | 15 / 19 | 8 / 10 | 0.001–0.002 | 0–1 |
| `openai/gpt-oss-120b` medium, Cerebras | 16 / 19 | 9 / 10 | 0.001–0.003 | 0–2 |
| **`deepseek/deepseek-v4-flash` high, Parasail** | **17 / 19** | **11 / 11** | **0.0003–0.001** | **1–6** |
| `anthropic/claude-haiku-4.5` none, Anthropic | 9 / 19 | 4 / 4 | 0.006–0.008 | 1–3 |

- Haiku asks «solo oggi o d'ora in poi?» even after «oggi», and started `set_up` and `change_declaration` for this workout.
- All four sent «oggi vorrei fare trazioni» to `todays_workout`, gpt-oss-120b also «oggi stacchi rumeni».
- Plans held differ because the entrance decides which messages get planned; the planner is the same in every row.

## Consequences

- **A month costs about $0.3–0.5**: ~300 entrance turns ($0.10–0.30), ~20 reports (~$0.06), one mesocycle (~$0.13).
- **Time is the open cost, not dollars.** The logger on Parasail went from 8–63 s a report to 80–200 s within one evening.
- **OpenRouter's shared pool is what fails, not a host's uptime.** A 429 with `limit_source: upstream_provider_shared_pool` hit DeepInfra and AkashML at busy hours at 96–99.5% uptime. Pin a host by the run records, not by the listing.
- **New OpenRouter accounts are held to 20 requests a minute per model.** One report is several calls.
- **Amends ADR-0004 item 8** (the default is no longer Ollama) **and ADR-0006 item 3** (the entrance's model is this table's on OpenRouter; `llama3.1` stays Ollama's).
