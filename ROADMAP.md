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
2. **One directory for everything the machine writes.** `TRAINER_HOME` holds the training database, the checkpointer, `eval-runs/` and the logs; the per-artifact variables stay as overrides. `training.toml` goes in with them: onboarding writes it from session 13, and in the repository it published the user’s own declarations. The files that exist are **moved, not recreated**. — **done** `3d6f5ce`
3. **The checkpoint's types are registered.** `plan.Request`, `plan.Violation` and `plan.WorkoutPlan` are written into checkpoints by a serializer that now warns it will stop reading them back. Today a warning; on the LangGraph upgrade, every conversation on disk is unreadable. — **done** `be457c6`
4. **The run record can be read back.** Session 6 item 3 already puts it in the graph state — attempts, tool calls, tokens, wall time per node — and nothing has ever read it. Without this, *control* means only *I have logs*. — **done** `edd866d`

## Session 9 — `0.9.0` — The report in the chat

**Demo**: after training you write the report in Telegram. The bot asks one question and you answer with a button.

1. **What a run is, and where it goes when it ends** (ADR-0007). `trainer runs` was built in session 8 over a state machine that overwrites its own history: a plan turned down already ends a run, and the record of the run that offered it is destroyed at that moment -- which is the measurement session 11 is built on. A run ends, the ending is written, the closed run is a document in the home, and a negotiation holds the runs of one ask. The reader depends on nothing that can break. `record.Run` and `unfinished` go with it. — **done** `94e2068`
2. **The logger subgraph, on the same tools.** The clarifying question and the exclusion confirmation are interrupts. The old loop, the `QUESTION:` marker and the hand-written Groq adapter are deleted with it -- a deletion is the second half of the work that makes it possible, not an issue of its own -- and the Groq settings move into `coach/models.py`, including the default model name that answers with a 404 today. — **done** `af6a6f2`
3. **The entrance talks** (ADR-0006). A chat model holds the conversation and reaches the planner and logger as tools, on a small fast model of its own: a router would classify into three branches that each answer from constants, which is today's woodenness times three. Five of the bot's seven fixed lines go; `BLOCKED` and `FAILED` stay. It carries the per-node model with it, which issue 1 has already moved into the record's nodes. `bot.Coach` is renamed here: it is the turn-taking, and the word is needed for the node that coaches. — **done** `d8f7fc9`
4. ~~**The next plan is prepared asynchronously.**~~ **Withdrawn** (ADR-0008): planning after every workout re-plans a programme that should hold for several cycles. It returns as session 10 item 4.
5. **The log eval suite runs against the graph.** — **done** `b4ba690`
6. **The logger writes only what was said.** A value the user did not give is left empty and the engine fills it; a refusal goes back to the model; an exclusion's vocabulary comes from the catalog. The first pass held 24 of 90, and 7 of 50 determined runs on the document against 30 on what would be written. — **done** `632f5ae`

## Session 10 — `0.10.0` — The mesocycle

**Demo**: you ask for a mesocycle and accept it once. On each of the next workouts the bot answers at once with the next one from it, the last load beside each exercise. After the last cycle the next mesocycle is waiting in the chat.

1. **The planner emits a mesocycle** (ADR-0008): a workout per slot of the cycle, how many cycles it lasts, and why. Each workout validated as one is today. Accepted, it is kept in SQLite. — **done** `cbce01c`
2. **Today's workout is read, not planned.** The rotation's slot off the mesocycle, no model call, the last performed load beside each exercise. It is prescribed when served. — **done** `ea736ea`
3. **A change and an adaptation.** A change rewrites the mesocycle for the cycles left; an adaptation plans today from the mesocycle's workout and leaves it alone. The entrance tells them apart, and asks when it cannot. — **done** `a706cba`
4. **The next mesocycle is prepared when the last cycle ends**, and waits in the chat. What ticket 9.4 established still holds: — **done** `950c050`
   - a negotiation nobody asked for is still one, and `trainer runs list` tells it apart from one the user opened;
   - left unanswered it reads *waiting*, with how long, never *abandoned* (ADR-0007 item 8);
   - it runs outside the turn-taking queue, so a message arriving meanwhile is answered, and it opens no draft;
   - it starts its run with `planner.starting` alone, on `bot.under(thread, PLANNING)`, so a user request while it waits gets the prepared one and never a second.
5. **The plan eval suite on a mesocycle**, with its wall time. It replaces the single workout: no door asks for one alone. On the local model a mesocycle is ten minutes; on OpenRouter it was 17 seconds. — **done** `9d0d153`

## Session 11 — `0.11.0` — A plan worth doing

**Demo**: the same request twice — the 25-minute circuit the bot proposed in session 7 beside what comes out now.

In this order. Measuring first is what stops the methodology being written against a cause nobody confirmed, and the floor is last because on its own it buys nothing: given a floor and no methodology, the cheapest way to fill the time is a tenth exercise in the circuit.

1. **The measurement that separates the causes.** The same request on a large model at full reasoning; session 12 item 4 runs it. If the plan is sound the cause is the local model and the machine; if it is the same shape, the cause is a brief that says only what is forbidden. Ran after 11.2 and 11.3 were in, so the cause cannot be read: Sonnet 5 and Haiku 4.5 now plan the same shape, neither a circuit. — **done** `8009190`
2. **What a workout is, written down.** [`methodology.md`](src/trainer/data/methodology.md): ranges per goal and principles the planner reasons with, never a template. The goal is declared in `training.toml`, one per mesocycle. — **done** `e92dc9e`
3. **The declared minutes are a target, not a ceiling.** Within five minutes either side, refused on both. The first real plan out of the bot spent 25 of 45 minutes and every rule passed it. — **done** `a3974a2`
4. **A slot of the split names muscles**, not only groups: `arms` cannot tell biceps from triceps. — **done** `530ebd6`

## Session 12 — `0.12.0` — How much the model thinks, and what it costs

**Demo**: one table per subgraph, each row a model at a reasoning effort: held against its bar, dollars and seconds per interaction. The configuration shipped is the row the rule picked.

1. **Reasoning effort and the host are settings**, per node, sent only to a model that takes them; the run record names both. — **done** `85bfd35`
2. **Every run says what it cost**, in dollars read from the provider, and a pass reports dollars and seconds per run. — **done** `38c774f`
3. **The logger's matrix.** Models by effort on the log set, screened at one repetition, finalists at three; the cheapest that clears both bars (ADR-0010). — **done** `504b1da`
4. **The planner's matrix**, the same on the plan suite, which after 10.5 plans mesocycles. It is also 11.1's measurement, and 11.2's: the session-7 request must not come back as a circuit of same-muscle exercises. — **done** `8009190`
5. **The choice, written down**: an ADR with both tables, the defaults that follow it, and what a month costs. — **done** `80d582f`

## Session 13 — `0.13.0` — Onboarding and memory

**Demo**: an onboarding conversation, resumed after a day away, ending in a first mesocycle; weeks later, *"I hate pressing"* still holds.

1. **Memory with a source.** Conclusions in the LangGraph store through a `remember` tool; admitted only when the user's verbatim sentence is in one of their messages. The planner reads them. — **done** `417df7e`
2. **The onboarding conversation.** Led by the agent from a prompt, one question per interrupt, resumed after a day; it cannot end with a field missing. Triage is a tool proposing an exclusion the user confirms. It writes `training.toml` and ends in a first mesocycle. — **done** `665a70f`
3. **Declarations live in the database** (ADR-0013): one dated version per change, written by onboarding, read by `trainer config`; with none, the bot starts the interview. `training.toml` is imported once and goes. — **done** `f2ef10a`
4. **A declaration changes through onboarding** (ADR-0012): code lists the paths open for the running mesocycle, the agent picks one, the user accepts. — **done** `f9d1fd4`
5. **The onboarding and memory eval**, and onboarding's model chosen by ADR-0011's rule. — **done** `aee7e92`

## Session 14 — `0.14.0` — Anything about this workout

**Demo**: *«oggi niente squat, stacchi rumeni in superset con i bulgari»* and *«oggi niente gambe, stasera gioco a calcio»* each come back as this workout, and the cycle after them is still right.

1. **The adaptation set.** `trainer eval --suite adapt`: real requests, where each must go and what its plan must hold; a baseline run. — **done** `b21e804`
2. **The next workout is the first not yet performed** in the cycle, read off the log; no stored order. — **done** `e7e6324`
3. **One tool for anything about this workout.** `adapt_this_workout`: minutes over the cap, this workout's equipment in full, exercises left out and asked for, another of the cycle's workouts; the validator holds them. — **done** `af0302b`, its fields dropped in 14.4: the planner reads the words
4. **This workout or from now on.** The entrance tells adaptation, change, declaration and memory apart, and asks when the words do not say; the set at its bars. — **done** `4a5af5f`
5. **Prompt caching.** The run record counts cached input; the planner's prompt and tools cached on Anthropic; $ a mesocycle before and after in ADR-0011. — **done** `251dacc`

## Session 15 — `0.15.0` — The next mesocycle has a reason

**Demo**: after three mesocycles, the fourth arrives with its reason, and what changed is visible in it.

1. **Between mesocycles, in a methodology of its own.** `variation.md`, read by the supervisor and not the planner: varying exercises, reps and rest from one mesocycle to the next, from primary sources. — **done** `a8bd45a`
2. **The supervisor.** A graph (ADR-0014) with tools over the history; when a mesocycle ends, before the planner, it writes the next one's direction, kept with that mesocycle, reading its own past directions. — **done** `46fd078`
3. **The planner plans from the direction, and the user reads it.** The brief holds the direction and the mesocycle that ended, not the per-workout log; the proposal says the direction in a line. — **done** `b14f581`
4. **The supervisor's set.** `trainer eval --suite supervise`: 15-20 scripted histories with what the direction must hold, checked by code, and how often the planner follows it at a declared bar; the model chosen by ADR-0011's rule. — **done** `9c732e1`
5. **The demo's home.** The three-mesocycle fixture as a script, and the README describing the working system; the recorded demo and its GIF move to `1.0.0`. — **done** `a557ba5`

## Session 15b — `1.0.0rc1` — A message mid-plan is read, not queued

**Demo** (recorded at `1.0.0`): *«anzi, ho solo 30 minuti»* sent while a plan is being written stops it, and the 30-minute plan arrives instead.

1. **One suite runner.** Fixture, run, quota stop, run record, bars and CLI wiring in one module; the five suites keep only what differs; no paid call to close it. — **done** `c2ea32f`
2. **One Negotiation, two doors.** "At most one plan" moves out of the bot into a module both the bot and the CLI call, tested without Telegram; nothing the user sees changes.
3. **The entrance reads a message mid-plan.** A question is answered at once, a correction or a new ask stops the run in flight, a report still waits.
4. **One roster of node models.** Which model each node runs on, its effort and host, in one table that the bot, the CLI and the evals read whole; no node changes model.
5. **The front page.** MIT licence, a logo, a README worth opening, and badges: tests and coverage from a GitHub Action, release, licence, and the stack.

## Session 15c — `1.0.0` — Portfolio-ready

**Demo**: after three mesocycles, the fourth arrives in Telegram with its reason; and *«anzi, ho solo 30 minuti»* mid-plan brings the 30-minute plan. Recorded, with a GIF in the README.

Its issues are cut when it opens: the recorded demo, the repository made public, and the fixes found using `1.0.0rc1`.

## Later sessions

Their issues are cut when each session opens.

| # | version | demo | scope |
|---|---|---|---|
| 16 | `1.1.0` | a plan in Telegram shows each exercise done: its start and end photos | the two photos free-exercise-db has for 873 of 876 exercises, sent with the plan; an exercise without photos is sent without; nothing generated |

**Portfolio-ready** is session 15c, `1.0.0`. Until then the README still has to describe what the system does *today* at every release — that is hygiene, not the flag.

**After 1.0.0**:
- progression and return from a break (the mesocycle's scheme, ramp-in by dates, the methodology document); until then a cycle repeats with the last load shown and the user raises it;
- Level 2, a simulated user with hidden truths;
- the drift guard: observations pointing at a measure, an engine constraint when one is ignored twice (TRAINER.md before ADR-0014);
- the memory gate: the supervisor marking a conclusion suspect or retiring it, e.g. *«this suits me»* after six weeks of falling volume;
- diagnosed pathologies;
- an on-device feature, if a phone model ever earns one.
- secrets out of `.env`: one file per key in a directory under `TRAINER_HOME` (Docker's `/run/secrets` layout), the environment still winning; no OS keychain, which differs per OS and is absent in a container;
- a Docker image and a compose file for the bot, the keys passed as Docker secrets.
- the planner's `emit` read from the cache (ADR-0011, 14.5: $0.015 of a $0.052 mesocycle). Keeping the tools and setting `tool_choice: "none"` recovers only tools and system, ~$0.004, since `tool_choice` invalidates the messages; the history needs the emission as a call to a tool already in the list.

## Risks

- **The local model has no GPU on this machine.** Measured in session 7, and it is not memory: `gpt-oss:20b` crashes the Vulkan backend of the Radeon 860M at *any* offload, four layers and 2.4 GB included, while `llama3.1` runs on the same device. It is the model, not the size. So it runs on the CPU at **10.3 tok/s generated and 52 tok/s read**, which is four to five minutes for one plan and eleven for a run the validator refuses twice. `reasoning="low"` is already set and buys nothing further. The fallbacks are `qwen3.5:9b`, to measure with `trainer eval --suite plan`, and `LLM_BACKEND=groq`.
- **Local tool use.** If `gpt-oss:20b` with feedback cannot hold the invariants at 100%, that is a finding about the model, not a reason to lower the bar. Measured on the logger (9.6): 3 of 15 on `gpt-oss:20b` where Qwen 27B on Groq held 9 of 12 on the same rows; the local model wrote numbers the contract let it leave out.
- **Telegram's 24-hour window.** Messages sent while the PC is off for longer than that are lost.
