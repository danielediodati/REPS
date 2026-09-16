# Roadmap

The order things get built in. [TRAINER.md](TRAINER.md) is the design; [ADR-0004](docs/adr/0004-an-agent-graph-over-the-engine-reached-through-telegram.md) is the architecture.

**Slicing rule.** A session has at most five issues and ends with a **demo someone can watch**: a chat, a Studio trace, a command. If there is nothing to record, the session was sliced wrong. Each issue must be closable on its own, in a clean context.

## Done

| # | version | shipped |
|---|---|---|
| 1 | `0.1.0` | 876 exercises from free-exercise-db in SQLite, `trainer catalog` with filters, a versioned snapshot |
| 2 | `0.2.0` | six enrichment fields (rules plus hand-read residue), the reference set, exclusions, `trainer admissible` |
| 3 | `0.3.0` | duration over blocks (ADR-0002), `remaining_budget` and `allocate`, `training.toml` (ADR-0003), the MCP server |
| 4 | `0.4.0` | plan shape and validator, a tool-loop planner on Groq, six invariants over six adverse situations |
| 5 | `0.5.0` | prescribed and performed workouts with per-field provenance, volume views on two axes, a logging agent, a 30-report eval set |

The details are in `git show v0.N.0`. Sessions 1-5 predate ADR-0004, and their agent layer is what sessions 6-8 replace.

## Session 6 — `0.6.0` — The planner is a graph

**Demo**: in LangGraph Studio, the planner proposes a plan, the validator refuses it, and the planner reads why and fixes it.

1. **Feasibility first.** The smallest planner graph that answers one question: does `gpt-oss:20b` reach a valid plan on this laptop when refusals come back to it? — **done** `8b9bcbe`
   - A planner node over the tools, and a `validate` node with a bounded edge back to the planner.
   - The emit schema lists today's admissible ids as the only allowed values of `exercise_id`.
   - `langgraph.json`, so that `langgraph dev` serves the graph.
   - One run over the six adverse situations, recording the valid rate, attempts, wall time and memory.

   If the model does not hold, the model choice is revisited before issue 2.
2. **Compact tool results, and today's constraints in one place.** — **done** `7966b1e`
   - `admissible_set` returns only what planning reads. Today it returns about 12k characters.
   - Standing exclusions are applied on the tool surface. Today only the CLI reads them.
3. **Named violations, a checkpointer, and the run record from the graph state.** — **done** `b2c20d0`
   - `validate` returns every violation, by name, instead of raising the first.
   - The run record comes from the graph state: calls, attempts, tokens, wall time per node.
4. **`trainer plan` runs the graph**, on the provider `LLM_BACKEND` names: Ollama or Groq. — **done** `91c2712`
5. **The plan eval suite runs against the graph.** The six invariants must hold at 100%, and each run also reports attempts to a valid plan and wall time. The Groq planner loop is then deleted; the hand-written adapter stays until session 8, for `trainer log`. — **done** `0f40acb`

## Session 7 — `0.7.0` — On the phone

**Demo**: a screen recording. You ask Telegram for today's workout, the plan arrives with buttons, you tap *Non mi va*, and a different plan follows.

1. **The bot.** `trainer bot` long-polls from the graph's process and answers only the owner. One chat is one thread, and a message arriving mid-run is queued rather than dropped. — **done** `c33b561`
2. **The plan in the chat**, formatted for Telegram and streamed with `sendMessageDraft`. What is streamed is the graph's progress — the tools it calls, and the violations it is sent back — because that is what makes the refusal loop visible; the plan itself arrives as one message.
3. **Refusal and *"only 30 minutes"* as `interrupt()`**, with buttons that resume the thread. A plan becomes a prescribed workout when it is accepted and not before (ADR-0005), so a refused plan never reaches SQLite. — **done** `2bda69f`
   - What the user says when they turn a plan down reaches the model and never becomes a training fact. `--refused --because` carried this in session 6 and the test that guarded it went with them; the guarantee comes back here, asserted over every table in `TRAINER_DB`.
4. **Today's inputs.** Equipment, time and the groups are taken from `training.toml` and the rotation, and both doors assemble the request through one function. The rotation moved out of `cli._rotated` into the engine, and `training.toml` gained `equipment` as a fifth declaration. — **done** `c7aee6d`
5. **The provider's state is checked when the bot starts.** Ollama is reachable, the model is present and the context length is set; Groq has its key; Telegram has its token and its owner id. Only the selected provider is checked, and each failure is reported as a state, with its fix. — **done** `11653e0`

## Session 8 — `0.8.0` — The report in the chat

**Demo**: after training you write the report in Telegram. The bot asks one question and you answer with a button. The next plan arrives without being asked for.

**Portfolio-ready.** This session closes only when the README is rewritten around the working system and shows a GIF of the demo. If the project stopped here, it would stand on its own.

1. **The logger subgraph, on the same tools.** The clarifying question and the exclusion confirmation are interrupts.
2. **The router.** A message is a report, a plan request, or a question.
3. **The next plan is prepared asynchronously.** A performed workout triggers planning, and the plan waits in the chat.
4. **The log eval suite runs against the graph.**
5. **The old loop, the `QUESTION:` marker and the hand-written Groq adapter are deleted.** Groq stays, as a provider of the graph.

## Later sessions

Their issues are cut when each session opens.

| # | version | demo | scope |
|---|---|---|---|
| 9 | `0.9.0` | ten onboarding questions, resumed after a day away, ending in a week 1 plan; weeks later, *"I hate pressing"* still holds | onboarding subgraph with resume; memory in the LangGraph store behind the admission rule (a source or nothing); triage producing exclusions; the medical trigger |
| 10 | `0.10.0` | *"lunges don't work for me"* becomes a two-workout trial, which runs and ends in a conclusion | hypotheses that must have a discriminating trial; a trial as a plan modification that holds everything else fixed; a thread alive across workouts; the outcome written back |
| 11 | **`1.0.0`** | a scripted six-week drift, and the supervisor's observation reaching the next plan | a separate graph on a different model, run between workouts; it reads the trajectory and never the agent's prose; the golden set; an observation ignored twice becomes an engine constraint |

**After 1.0.0**:
- progression and return from a break (the mesocycle scheme, ramp-in by dates, the methodology document);
- Level 2, a simulated user with hidden truths;
- diagnosed pathologies;
- an on-device feature, if a phone model ever earns one.

## Risks

- **Memory.** A 12 GB model plus its context is at the edge of a 32 GB laptop in use, and the OS killed the first probe. The fallbacks are `qwen3.5:9b`, to measure, and `LLM_BACKEND=groq`.
- **Local tool use.** If `gpt-oss:20b` with feedback cannot hold the invariants at 100%, that is a finding about the model, not a reason to lower the bar.
- **Telegram's 24-hour window.** Messages sent while the PC is off for longer than that are lost.
