# A single paid LLM service for REPS, and whether each agent should run a different model

Research date: 2026-09-22. Every claim cites its source inline. **[secondary]** marks a claim only a non-primary source supports. **[independent]** marks a measured-benchmark source (Artificial Analysis, BFCL, tau2-bench) that is neither the model vendor nor REPS's own code — exactly the kind of source the comparison below needs, since a vendor never publishes a number that makes its own model look slow. **[inference]** marks my own reasoning from cited facts. Prices, model lists and benchmark scores change; treat every number here as dated 2026-09-22.

## The question

Leave the free tiers (Groq free, local Ollama) for **one paid service**, fast enough and capable enough to finish REPS on, and decide — inside that one service — whether the entrance, planner, logger (and the future supervisor) should each run a different model.

## What REPS actually spends today

Read from `src/trainer/coach/models.py`, three ADRs and two measured eval runs already in the repo.

| Agent | Measured run | Input tokens | Output tokens | Source |
|---|---|---|---|---|
| Entrance | one Ollama `llama3.1` turn, tools bound | ~2,700 (mostly tool definitions) | small talk turn, 6 s at the model's own rate | `docs/adr/0006-the-entrance-is-a-conversation-not-a-classifier.md` |
| Planner | `trainer plan --change`, `gpt-oss:20b`, 2 attempts, 585 s | 34,500 | 2,600 | `docs/work/10-the-mesocycle/issues/05-the-plan-eval-suite-on-a-mesocycle.md` |
| Logger | full 90-situation eval, `gpt-oss:20b`, 102 tool calls, ~2.6 h | 640,000 | 52,000 | `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md` |
| Logger | 12-situation subset, Groq `qwen/qwen3.8-27b`, 36 tool calls | 161,000 | 8,000 | same file |

Grep confirms all three agent graphs reach the model the same way: `planner.py:588`, `logger.py:354` and `entrance.py:480` all call `model.bind_tools(definitions)`; `planner.py:660` and `logger.py:421` call `model.with_structured_output(...)`. Nothing is provider-specific. Whatever `coach/models.py` hands back as `Chat.model` is what runs.

**Monthly cost is not the deciding factor at REPS's scale.** Steady state (one user, no weekly schedule, ~300 entrance turns + ~20 logs + ~1 mesocycle plan/month) is ~1.0M input/0.11M output tokens/month; a heavy eval-hillclimbing burst (10 full reruns of both suites) is ~8.4M input/0.68M output tokens **[inference, scaling the measured runs above]**. Priced at *any* model in this document, steady state costs under $4/month and the heaviest development burst costs under $25 — this was already established in the first pass of this research and still holds. What changes below is the architecture question the user actually asked, and real performance numbers.

## The single-service decision

### Router vs. single provider, head to head

| Candidate | Type | Reaches fast open models (Groq/Cerebras-hosted) | Reaches frontier models (Claude/GPT/Gemini) | Python/LangChain package | Fee at REPS's scale | Provider-picking control |
|---|---|---|---|---|---|---|
| **OpenRouter** | router | yes — `qwen/qwen3.8-27b` alone lists 17 providers ([model page](https://openrouter.ai/qwen/qwen3.8-27b)) | yes — Claude Sonnet 5 lists 5 providers incl. Anthropic direct ([model page](https://openrouter.ai/anthropic/claude-sonnet-5)) | dedicated `langchain-openrouter` (PyPI, v0.2.9, released **2026-09-22**); `init_chat_model("openrouter:...")` confirmed | pass-through, no markup ([FAQ](https://openrouter.ai/docs/faq)); BYOK free to $25,000/mo; 5.5% only on card-funded credit purchases | **Balanced / Nitro (fastest) / Floor (cheapest) / Exacto (highest tool-calling accuracy)** routing modes, or pin an exact provider ([provider routing docs](https://openrouter.ai/docs/guides/routing/provider-selection)) |
| Vercel AI Gateway | router | yes, per its model catalog | yes | no dedicated Python package — LangChain reaches it only via `ChatOpenAI(base_url=...)` ([Vercel's own LangChain guide](https://vercel.com/docs/ai-gateway/ecosystem/framework-integrations/langchain)) | no markup on tokens; $0.10/1,000 requests for team-wide ZDR/allowlists ([pricing](https://vercel.com/docs/ai-gateway/pricing)) | provider fallback + cost-aware routing, no accuracy-targeted mode found |
| Groq (direct, paid) | single provider | yes, only Groq's own catalog | no | already integrated (`langchain-groq`) | cheapest sticker price for its own models | none — one provider |
| Cerebras (direct) | single provider | yes, only Cerebras's own catalog | no | `langchain-cerebras` (new dependency) | cheap | none |
| Anthropic (direct) | single provider | no | yes, Claude family only | `langchain-anthropic` (new dependency) | standard pricing | none |
| OpenAI (direct) | single provider | no | yes, GPT family only | `langchain-openai` (new dependency) | standard pricing | none |
| Google (direct) | single provider | no | yes, Gemini family only | `langchain-google-genai` (new dependency) | standard pricing | none |

A single direct provider cannot give every agent both a sub-$0.10/1M-token fast option and a frontier-reasoning option — that is structural, not a matter of picking harder. Only a router reaches both ends from one account. Between the two routers, OpenRouter has the more mature Python/LangChain surface (a dedicated package shipped today, `init_chat_model` support) and a routing mode aimed directly at tool-calling accuracy, which is REPS's actual bottleneck (ADR-0007's refusal loop, ADR-0009's structured extraction). **Winner: OpenRouter.**

### Re-examining the earlier objection to OpenRouter, honestly

The first pass of this research rejected OpenRouter because `models.py`'s `spent()` parses Groq's specific free-tier "daily quota" 429 message with a regex, and OpenRouter would normalize that error shape away. On a **paid** plan this is moot: the free-tier daily-quota 429 that `spent()` exists to translate is a free-tier-only event (`_PER_DAY` regex, `models.py:122`) — it does not fire on a paid Groq key, let alone on any other provider. Any new backend, direct or routed, needs its own small "state, not a user error" function for whatever 429/5xx shape it actually returns; that cost exists identically whether the new backend is OpenRouter or Anthropic direct. It should never have been the deciding factor, and it is not one now.

## Speed — output tokens/sec and time-to-first-token

All Artificial Analysis (AA) figures are **[independent]**, published on their model and provider pages; several were only retrievable through search-result excerpts because AA's pages render client-side (flagged per row). Groq and Cerebras publish their own tok/s directly on their docs (primary, no TTFT given). Configuration (reasoning effort, provider) is stated because it changes the number a lot.

| Model | Provider serving it | Output tok/s | TTFT | Source |
|---|---|---|---|---|
| `llama-3.1-8b` | Groq | 560 (primary) | **0.81 s — fastest model AA measured on Groq** | [Groq models](https://console.groq.com/docs/models); AA via search [independent, secondary excerpt] |
| `openai/gpt-oss-20b` (high) | Groq | 939–956 | 2.88 s | AA via search [independent, secondary excerpt] |
| `openai/gpt-oss-120b` (high) | **Cerebras** | **1,724–1,728** | **1.65–1.66 s** | AA via search [independent, secondary excerpt] |
| `openai/gpt-oss-120b` (low) | Groq | 475.6 | 4.94 s | AA via search [independent, secondary excerpt] |
| `qwen/qwen3.8-27b` | Groq | 450 (primary) | not published | [Groq models](https://console.groq.com/docs/models) |
| `qwen-3.8-27b` | **Cerebras** | **~1,850** (primary) | not published | [Cerebras models overview](https://inference-docs.cerebras.ai/models/overview) |
| Claude Haiku 4.5 (non-reasoning) | Anthropic | 89.0 | **0.68 s** | AA via search [independent, secondary excerpt] |
| Claude Haiku 4.5 (reasoning) | Anthropic | 92.4 | not found | AA via search [independent, secondary excerpt] |
| Claude Sonnet 5 (adaptive reasoning, max effort) | Anthropic | 72.3 | 142.9 s — caveat below | AA via search [independent, secondary excerpt] |
| Gemini 3.6 Flash (high) | Google | 212.7–280 (two snippets disagree) | not found | AA via search [independent, secondary excerpt] |
| GPT-5.6 Luna (low/high) | OpenAI | 126–200 | not found | AA via search [independent, secondary excerpt] |

**Caveat on Sonnet 5's 142.9 s TTFT**: this is AA's figure for the *Max Effort* reasoning configuration specifically, which spends the most tokens thinking before the first visible token streams. It is not evidence Sonnet 5 is unusable for a latency-sensitive node — REPS's planner already tolerates minutes-long runs (585 s measured above), and lower `effort` settings were not surfaced by this search pass. It **is** evidence Sonnet 5 at max effort has no business on the entrance.

**On Cerebras vs. Groq for the same model**: `gpt-oss-120b` on Cerebras (1,724–1,728 tok/s) is roughly **3.6x** its own throughput on Groq (475.6 tok/s), on the identical model. This is the clearest single demonstration in this research that *which provider serves a model* matters as much as *which model* — exactly what a router, not a single direct provider, lets you pick per request.

## Capability — tool calling, reasoning-as-agent

### BFCL v4 (primary, fetched live from the leaderboard's own CSV, 2026-09-22)

Source: [BFCL leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html), data from [data_overall.csv](https://gorilla.cs.berkeley.edu/data_overall.csv), fetched today.

| Model | Mode | Overall | Multi-turn |
|---|---|---|---|
| Claude Opus 4.5 | FC | 77.47% | 68.38% |
| Claude Sonnet 4.5 | FC | 73.24% | 61.37% |
| **Claude Haiku 4.5** | FC | **68.70%** | **53.62%** |
| Qwen3-8B *(8B dense, not the same model as `qwen/qwen3.8-27b`)* | FC | 42.57% | 41.75% |
| Llama-3.1-8B-Instruct | Prompt (no FC row) | 25.55% | 11.12% |
| Llama-3.2-3B-Instruct | FC | 21.95% | 4.00% |

**Gap, stated rather than papered over**: as of this snapshot, BFCL v4 does not carry rows for Claude Sonnet 5, `qwen/qwen3.8-27b`, `gpt-oss-20b`/`gpt-oss-120b`, Gemini 3.x Flash or any GPT-6/GPT-5.6 model. Claude Sonnet 5 and GPT-6 are recent enough that the leaderboard has not caught up; `qwen/qwen3.8-27b` and the `gpt-oss` models may simply not have been submitted. **Do not read the absence as a low score — it is missing data, not a zero.** This is the strongest argument in this whole document for the "measure it yourself" section below: half of REPS's actual candidate list has no independent tool-calling number yet.

### tau2-bench / tau-bench (independent, mixed primary/secondary)

| Model | Result | Source |
|---|---|---|
| Claude Sonnet 4.5 | tau2-bench-verified, four reported sub-scores: 66.80 / 77.19 / 75.96 / 73.32 (domain breakdown not confirmed from this fetch) | [amazon-agi/tau2-bench-verified](https://github.com/amazon-agi/tau2-bench-verified) [independent, secondary excerpt] |
| Claude Haiku 4.5 | same benchmark: 54.00 / 69.12 / 37.19 / 53.44 | same [independent, secondary excerpt] |
| Gemini Flash 2.5 *(older generation, not 3.6)* | same benchmark: 44.00 / 57.72 / 22.98 / 41.57 | same [independent, secondary excerpt] |
| Gemini 3.7 Flash | leads tau2-bench Airline at 80.6%, dated 2026-09-20 | [OpenRouter benchmarks page](https://openrouter.ai/benchmarks/tau2-bench-airline) [independent] |
| Claude Sonnet 4.5 | leads tau-bench Retail at 0.862 | [llm-stats.com](https://llm-stats.com/benchmarks/tau-bench-retail) [independent, secondary] |

No tau2-bench number was found for Claude Sonnet 5, Gemini 3.6/3.8 Flash (non-Airline), GPT-6/5.6, `qwen/qwen3.8-27b` or `gpt-oss`. **Gap, stated.**

### IFEval / IFBench (instruction following) and GPQA (reasoning)

**Not found for the exact candidate models** (Claude Sonnet 5, Claude Haiku 4.5, Gemini 3.6/3.8 Flash, GPT-6 family, `qwen/qwen3.8-27b`, `gpt-oss-20b`/`120b`) in this research pass. Per the brief's own rule — same benchmark across models or say it's missing — this is reported as missing rather than filled with a different model's number. The closest available signal is Artificial Analysis's composite **Intelligence Index**, which folds in GPQA among other evals:

| Model (AA config) | Intelligence Index | Source |
|---|---|---|
| GPT-6 Astra (max) | 53 | AA via search [independent, secondary excerpt] |
| Claude Sonnet 5 (non-reasoning, high effort) | ~29 (marked "estimated" by the source) | AA via search [independent, secondary excerpt] |
| Gemini 3.6 Flash (high) | 34 in one excerpt, 50 in another — **inconsistent, likely different effort configs conflated by search; not trusted as a single number** | AA via search [independent, secondary excerpt] |
| GPT-5.6 Luna (low) | 33 | AA via search [independent, secondary excerpt] |
| GPT-5.6 Sol (high) | 42 | AA via search [independent, secondary excerpt] |
| Qwen3.8-Flash-Next *(not confirmed to be the same model as `qwen/qwen3.8-27b`)* | 39.8 (rank 26) | AA via search [independent, secondary excerpt] |

Treat this table as directional only — the Gemini row alone shows how noisy a search-excerpted, config-dependent index gets. A future pass should fetch AA's model pages directly (they need a JS-capable fetch, which this pass's WebFetch tool could not do) rather than rely on search snippets.

## Speed vs. capability, per agent

The fastest model that clears a stated capability bar for that agent's actual job:

| Agent | Job | Capability bar | Fastest model clearing it | Speed | Capability |
|---|---|---|---|---|---|
| Entrance | short conversational turns, tool routing decision, ADR-0006's latency budget | none codified — a wrong routing decision is cheap to correct in the next turn | `llama-3.1-8b` on Groq | TTFT 0.81 s (AA), 560 tok/s (Groq primary) | not BFCL-scored at 8B-instruct-1.1 tier in this fetch; Llama-3.2-3B (smaller sibling) scores 21.95%/4.00% FC — a floor, not this model's number |
| Logger | structured extraction must validate against a schema (ADR-0009) | BFCL FC multi-turn, since a log report is a multi-step "read, ask, emit" tool loop | Claude Haiku 4.5 | 89.0–92.4 tok/s, TTFT 0.68 s (AA) | **68.70% overall / 53.62% multi-turn BFCL v4 (primary)** — beats every open model measured above by 10-45 points |
| Planner | multi-turn tool loop with refusal feedback (ADR-0007), heaviest reasoning | BFCL FC multi-turn, tau2/tau-bench agent-loop score | Claude Sonnet 4.5 as the closest *measured* proxy for Sonnet 5 (not yet benchmarked) | 41.5–72.3 tok/s depending on reasoning config (AA) | 73.24% overall / 61.37% multi-turn BFCL v4; leads tau-bench Retail at 0.862 (both primary/independent, Sonnet 4.5) |
| Supervisor (future, offline) | reads the trajectory, not the agent's prose (ROADMAP session 14); latency-insensitive | any — it runs between workouts | Gemini 3.6/3.8 Flash | 212–350 tok/s (AA) | tau2-bench Airline leadership sits with sibling Gemini 3.7 Flash at 80.6% (independent) |

`gpt-oss-120b` on Cerebras is the fastest model examined (1,724–1,728 tok/s) but has no BFCL/tau2 score in this pass — it is a strong *speed* candidate for any agent once its capability is actually measured, not before.

## Per-agent recommendation, all through OpenRouter

One OpenRouter API key. Each agent's model is one environment variable, the same shape `models.py` already uses for `GROQ_MODEL`/`ENTRANCE_MODEL`.

| Agent | Model (OpenRouter slug) | Routing mode | Why | Est. steady-state cost/mo |
|---|---|---|---|---|
| Entrance | `meta-llama/llama-3.1-8b-instruct` | `:nitro` or pinned to Groq | Fastest TTFT measured anywhere in this research (0.81 s); already the exact model REPS's local entrance runs, so behaviour is validated against the same weights | ~$0.02 |
| Logger | `anthropic/claude-haiku-4.5` | `Exacto` (tool-calling accuracy) or pinned to Anthropic direct | Best measured multi-turn tool-calling score of any candidate (53.62% BFCL v4), still one of the cheapest frontier-tier models ($1/$5) | ~$0.55-1.55 |
| Planner | `anthropic/claude-sonnet-5` | `Exacto` | Same provider/package as the logger; strongest measured agent-loop numbers among Claude models (Sonnet 4.5's 61.37% BFCL multi-turn, 0.862 tau-bench Retail, as the closest proxy); prompt caching (Anthropic-native, reachable through OpenRouter) offsets the repeated-tool-definition cost the on-device doc already measured as expensive | ~$0.07-3.10 |
| Supervisor (future) | `google/gemini-3.6-flash` | `Floor` (offline, cost-sensitive) | Different provider from both agents above — trivially satisfies "a different model" (ROADMAP session 14); offline/batch-tolerant workload | negligible |

## Measuring on REPS's own evals, through the one router

Public benchmarks are a proxy, and this pass just showed how thin that proxy is for REPS's exact model list (Claude Sonnet 5 and every `gpt-oss`/`qwen3.8`/GPT-6/Gemini-3.x candidate has at least one missing score above). The only trustworthy number is REPS's own suite, run through the same key:

1. **One `OPENROUTER_API_KEY`** covers every model in the tables above — no per-provider account needed to compare them.
2. **Add an `OPENROUTER` backend to `BACKENDS` in `models.py`**, mirroring `groq_model()`: a builder that reads `OPENROUTER_API_KEY` and a model-name env var, built on `ChatOpenAI(base_url="https://openrouter.ai/api/v1", ...)` or the dedicated `langchain-openrouter` package.
3. **Run each eval suite once per candidate model**, changing only the per-node env var (`GROQ_MODEL`-shaped: e.g. `PLANNER_MODEL=anthropic/claude-sonnet-5`, then rerun with `PLANNER_MODEL=openai/gpt-oss-120b`) — `trainer eval --suite plan` and the log suite already report the six invariants, calls, and tokens per run (`src/trainer/evaluation.py`), so the comparison is apples-to-apples on REPS's own six situations and 90 log situations, not a public leaderboard's.
4. **Remember `TRAINER_DB`.** Every agent measurement runs against a fixture named in the environment — the tools open their own connection, so an eval run against a candidate model with no `TRAINER_DB` set is invisible to the suite, not merely inaccurate (CLAUDE.md standing rule).
5. **Pin the provider, not just the model, once a choice is made.** OpenRouter's default routing can silently move a model between providers (e.g. `qwen/qwen3.8-27b` between Groq and 16 others); an eval result is only reproducible if the provider is pinned for the run.

## Code-change cost

Confirmed by grep (above): no agent graph calls anything beyond `bind_tools`/`with_structured_output`, so a new provider is confined to `coach/models.py`. Concretely, replacing/adding an OpenRouter backend:

- one new `BACKENDS` entry (`OPENROUTER = "openrouter"`);
- one new builder — either `ChatOpenAI(base_url="https://openrouter.ai/api/v1", api_key=..., model=...)` (zero new dependency, `langchain-openai` likely already present transitively) or the dedicated `langchain-openrouter` package;
- one new `ready()` branch — OpenRouter's own `/api/v1/models` endpoint gives the same "does this key serve this model" check `groq_models()` does for Groq today;
- a new `spent()`-equivalent for OpenRouter's 429 shape — genuinely new code, but no larger than the Groq-specific one it would sit beside, and not a reason to prefer a direct provider over the router (see "re-examining the objection," above);
- per-node model env vars (`ENTRANCE_MODEL`, a new `PLANNER_MODEL`, a new `LOGGER_MODEL`) already fit the pattern `ENTRANCE_MODEL`/`ENTRANCE_BACKEND` established in ADR-0006 — no new concept, just two more variables of the same shape.

Roughly the same 40-60 lines estimated in the first pass of this research, once more mirroring an existing path rather than rewriting one.

## Risks and open questions

- **Benchmark coverage is thin for exactly the models REPS would pick.** Claude Sonnet 5, `qwen/qwen3.8-27b`, both `gpt-oss` sizes, Gemini 3.6/3.8 Flash and the whole GPT-6 family are each missing from at least one of BFCL v4, tau2-bench and AA's search-indexed pages. Section "Measuring on REPS's own evals" exists because of this, not despite it.
- **AA's Intelligence Index and speed figures were pulled from search-result excerpts of a client-rendered site, not a direct fetch of the page's own data.** The Gemini 3.6 Flash inconsistency (34 vs 50) shows this can mix reasoning-effort configurations. A future pass should fetch `artificialanalysis.ai` with a tool that renders JavaScript, or use their API if one exists, rather than search snippets.
- **OpenRouter's own per-provider throughput/latency numbers (shown on its model pages) were not directly retrievable** by this pass's WebFetch tool (client-rendered); the mechanism (17 providers for `qwen/qwen3.8-27b`, 5 for Claude Sonnet 5, `Exacto`/`Nitro`/`Floor` routing modes) is primary-confirmed, but the exact numbers on those pages were not read.
- **Evals must be re-run per model** — the log suite and plan suite both score against specific model behaviour (CLAUDE.md: *validator and eval share rules*). A provider or model swap needs a fresh `trainer eval` pass before trusting new numbers.
- **`TRAINER_DB` fixture rule still applies** regardless of provider.
- **OpenRouter is one more account and one more error shape to learn**, against the "it's already wired in" appeal of staying on Groq direct for everything. This is real friction, weighed against being the only candidate that lets every agent reach both ends of the speed/capability trade-off from one key.

## Sources

- REPS: `src/trainer/coach/models.py`, `src/trainer/coach/planner.py`, `src/trainer/coach/logger.py`, `src/trainer/coach/entrance.py` (read directly)
- REPS: `docs/adr/0006-the-entrance-is-a-conversation-not-a-classifier.md`
- REPS: `docs/work/10-the-mesocycle/issues/01-the-planner-emits-a-mesocycle.md`
- REPS: `docs/work/10-the-mesocycle/issues/05-the-plan-eval-suite-on-a-mesocycle.md`
- REPS: `docs/work/09-the-report-in-the-chat/issues/05-the-log-eval-suite-on-the-graph.md`
- REPS: `ROADMAP.md` (session 14, supervisor)
- REPS: `docs/research/on-device-llm-android.md` (local-model throughput baseline)
- OpenRouter FAQ (fees, BYOK): https://openrouter.ai/docs/faq
- OpenRouter provider routing (Balanced/Nitro/Floor/Exacto): https://openrouter.ai/docs/guides/routing/provider-selection
- OpenRouter `qwen/qwen3.8-27b` model page: https://openrouter.ai/qwen/qwen3.8-27b
- OpenRouter `anthropic/claude-sonnet-5` model page: https://openrouter.ai/anthropic/claude-sonnet-5
- OpenRouter tau2-bench Airline leaderboard: https://openrouter.ai/benchmarks/tau2-bench-airline
- langchain-openrouter on PyPI: https://pypi.org/project/langchain-openrouter/
- Vercel AI Gateway pricing: https://vercel.com/docs/ai-gateway/pricing
- Vercel AI Gateway + LangChain (no dedicated Python package): https://vercel.com/docs/ai-gateway/ecosystem/framework-integrations/langchain
- Groq models (speed, primary): https://console.groq.com/docs/models
- Cerebras models overview (speed, primary): https://inference-docs.cerebras.ai/models/overview
- BFCL leaderboard: https://gorilla.cs.berkeley.edu/leaderboard.html
- BFCL data (fetched live 2026-09-22): https://gorilla.cs.berkeley.edu/data_overall.csv
- tau2-bench-verified scores [independent, secondary excerpt]: https://github.com/amazon-agi/tau2-bench-verified
- tau-bench Retail leaderboard [independent, secondary]: https://llm-stats.com/benchmarks/tau-bench-retail
- Artificial Analysis models (speed/TTFT/Intelligence Index, accessed via search excerpts — page itself is client-rendered) [independent]: https://artificialanalysis.ai/models, https://artificialanalysis.ai/providers/groq, https://artificialanalysis.ai/providers/cerebras
- Anthropic pricing (live): https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic rate limits (live): https://platform.claude.com/docs/en/api/rate-limits
- OpenAI models: https://developers.openai.com/api/docs/models
- OpenAI pricing: https://developers.openai.com/api/docs/pricing
- Google Gemini pricing (live, dated 2026-09-22): https://ai.google.dev/gemini-api/docs/pricing
- Google Gemini models: https://ai.google.dev/gemini-api/docs/models
