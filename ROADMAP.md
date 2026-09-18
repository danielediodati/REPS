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

The details are in `git show v0.N.0`. Sessions 1-5 predate ADR-0004, and their agent layer is what sessions 6-9 replace.

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
2. **The plan in the chat**, formatted for Telegram and streamed with `sendMessageDraft`. What is streamed is the graph's progress — the tools it calls, and the violations it is sent back — because that is what makes the refusal loop visible; the plan itself arrives as one message. — **done** `c65f18c`
3. **Refusal and *"only 30 minutes"* as `interrupt()`**, with buttons that resume the thread. A plan becomes a prescribed workout when it is accepted and not before (ADR-0005), so a refused plan never reaches SQLite. — **done** `2bda69f`
   - What the user says when they turn a plan down reaches the model and never becomes a training fact. `--refused --because` carried this in session 6 and the test that guarded it went with them; the guarantee comes back here, asserted over every table in `TRAINER_DB`.
4. **Today's inputs.** Equipment, time and the groups are taken from `training.toml` and the rotation, and both doors assemble the request through one function. The rotation moved out of `cli._rotated` into the engine, and `training.toml` gained `equipment` as a fifth declaration. — **done** `c7aee6d`
5. **The provider's state is checked when the bot starts.** Ollama is reachable, the model is present and the context length is set; Groq has its key; Telegram has its token and its owner id. Only the selected provider is checked, and each failure is reported as a state, with its fix. — **done** `11653e0`

## Session 8 — `0.8.0` — You can see what it is doing

**Demo**: pull the plug mid-run, restart, and read back what the bot was doing and why it stopped. Everything the machine writes is in one directory you copy in one move.

1. **Logging to a file the bot owns**, rotated. Every state and every exception, recorded where the person who can act on it is sitting; the token and the owner id never in it. `BLOCKED` and `FAILED` then name the log instead of *«dove gira il bot»*. — **done** `35340d2`

   **Nothing raised leaves the machine**, and this is where it goes instead. Session 7 made those two lines generic on purpose: the engine's states carry absolute paths — the file to copy, the directory to copy it into — and quoted into Telegram they leave this installation's account name and disk layout on a third party's servers, for a path nobody can act on from a phone. Until this lands, the only record is the bot's own stderr.
2. **One directory for everything the machine writes.** `TRAINER_HOME` holds the training database, the checkpointer, `eval-runs/` and the logs; the per-artifact variables stay as overrides. `training.toml` goes in with them: onboarding writes it from session 11, and in the repository it published the user’s own declarations. The files that exist are **moved, not recreated**. — **done** `3d6f5ce`
3. **The checkpoint's types are registered.** `plan.Request`, `plan.Violation` and `plan.WorkoutPlan` are written into checkpoints by a serializer that now warns it will stop reading them back. Today a warning; on the LangGraph upgrade, every conversation on disk is unreadable. — **done** `be457c6`
4. **The run record can be read back.** Session 6 item 3 already puts it in the graph state — attempts, tool calls, tokens, wall time per node — and nothing has ever read it. Without this, *control* means only *I have logs*. — **done** `edd866d`

## Session 9 — `0.9.0` — The report in the chat

**Demo**: after training you write the report in Telegram. The bot asks one question and you answer with a button. The next plan arrives without being asked for.

1. **What a run is, and where it goes when it ends** (ADR-0007). `trainer runs` was built in session 8 over a state machine that overwrites its own history: a plan turned down already ends a run, and the record of the run that offered it is destroyed at that moment -- which is the measurement session 10 is built on. A run ends, the ending is written, the closed run is a document in the home, and a negotiation holds the runs of one ask. The reader depends on nothing that can break. `record.Run` and `unfinished` go with it. — **done** `94e2068`
2. **The logger subgraph, on the same tools.** The clarifying question and the exclusion confirmation are interrupts. The old loop, the `QUESTION:` marker and the hand-written Groq adapter are deleted with it -- a deletion is the second half of the work that makes it possible, not an issue of its own -- and the Groq settings move into `coach/models.py`, including the default model name that answers with a 404 today. — **done** `af6a6f2`
3. **The entrance talks** (ADR-0006). A chat model holds the conversation and reaches the planner and logger as tools, on a small fast model of its own: a router would classify into three branches that each answer from constants, which is today's woodenness times three. Five of the bot's seven fixed lines go; `BLOCKED` and `FAILED` stay. It carries the per-node model with it, which issue 1 has already moved into the record's nodes. `bot.Coach` is renamed here: it is the turn-taking, and the word is needed for the node that coaches.
4. **The next plan is prepared asynchronously.** A performed workout triggers planning, and the plan waits in the chat. A negotiation nobody asked for is still a negotiation.
5. **The log eval suite runs against the graph.**

## Session 10 — `0.10.0` — A plan worth doing

**Demo**: the same request twice — the 25-minute circuit the bot proposed in session 7 beside what comes out now.

In this order. Measuring first is what stops the methodology being written against a cause nobody confirmed, and the floor is last because on its own it buys nothing: given a floor and no methodology, the cheapest way to fill the time is a tenth exercise in the circuit.

1. **The measurement that separates the causes.** The same request on Groq, on a large model at full reasoning. If the plan is sound the cause is the local model and the machine; if it is the same shape, the cause is a brief that says only what is forbidden.
2. **What a workout is, written down.** Needs the user's methodology: how many exercises a group gets, what a working set is, which rest goes with which intent, and when a superset or a circuit is the right answer rather than the cheap one.
3. **The declared minutes are a target, not a ceiling.** Within five minutes either side, refused on both. The first real plan out of the bot spent 25 of 45 minutes and every rule passed it.

## Later sessions

Their issues are cut when each session opens.

| # | version | demo | scope |
|---|---|---|---|
| 11 | `0.11.0` | ten onboarding questions, resumed after a day away, ending in a week 1 plan; weeks later, *"I hate pressing"* still holds | onboarding subgraph with resume; it writes `training.toml` with its comments, a missing one starts the interview instead of blocking the bot, and the example file goes with the state that named it; memory in the LangGraph store behind the admission rule (a source or nothing); triage producing exclusions; the medical trigger |
| 12 | `0.12.0` | *"lunges don't work for me"* becomes a two-workout trial, which runs and ends in a conclusion | hypotheses that must have a discriminating trial; a trial as a plan modification that holds everything else fixed; a thread alive across workouts; the outcome written back |
| 13 | **`1.0.0`** | a scripted six-week drift, and the supervisor's observation reaching the next plan | a separate graph on a different model, run between workouts; it reads the trajectory and never the agent's prose; the golden set; an observation ignored twice becomes an engine constraint |

**Portfolio-ready** is session 13. It closes only when the README is rewritten around the working system and shows a GIF of the demo. Until then the README still has to describe what the system does *today* at every release — that is hygiene, not the flag.

**After 1.0.0**:
- progression and return from a break (the mesocycle scheme, ramp-in by dates, the methodology document);
- Level 2, a simulated user with hidden truths;
- diagnosed pathologies;
- an on-device feature, if a phone model ever earns one.

## Risks

- **The local model has no GPU on this machine.** Measured in session 7, and it is not memory: `gpt-oss:20b` crashes the Vulkan backend of the Radeon 860M at *any* offload, four layers and 2.4 GB included, while `llama3.1` runs on the same device. It is the model, not the size. So it runs on the CPU at **10.3 tok/s generated and 52 tok/s read**, which is four to five minutes for one plan and eleven for a run the validator refuses twice. `reasoning="low"` is already set and buys nothing further. The fallbacks are `qwen3.5:9b`, to measure with `trainer eval --suite plan`, and `LLM_BACKEND=groq`.
- **Local tool use.** If `gpt-oss:20b` with feedback cannot hold the invariants at 100%, that is a finding about the model, not a reason to lower the bar.
- **Telegram's 24-hour window.** Messages sent while the PC is off for longer than that are lost.
