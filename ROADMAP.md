# Roadmap

The order things get built in. [TRAINER.md](TRAINER.md) is the design; [ADR-0004](docs/adr/0004-an-agent-graph-over-the-engine-reached-through-telegram.md) is the architecture.

**Slicing rule.** A session has at most seven issues and ends with a **demo someone can watch**: a chat, a Studio trace, a command. If there is nothing to record, the session was sliced wrong. Each issue must be closable on its own, in a clean context.

## Done

| # | version | shipped |
|---|---|---|
| 1 | `0.1.0` | 876 exercises from free-exercise-db in SQLite, `trainer catalog` with filters, a versioned snapshot |
| 2 | `0.2.0` | six enrichment fields (rules plus hand-read residue), the reference set, exclusions, `trainer admissible` |
| 3 | `0.3.0` | duration over blocks (ADR-0002), `remaining_budget` and `allocate`, `training.toml` (ADR-0003), the MCP server |
| 4 | `0.4.0` | plan shape and validator, a tool-loop planner on Groq, six invariants over six adverse situations |
| 5 | `0.5.0` | prescribed and performed workouts with per-field provenance, volume views on two axes, a logging agent, a 30-report eval set |
| 6 | `0.6.0` | the planner as a LangGraph graph: a validator that refuses and a planner that reads why, a checkpointer, `trainer plan` on it, the plan suite against it |
| 7 | `0.7.0` | the Telegram bot: today's plan with buttons, *Non mi va* brings another, the provider checked at start |
| 8 | `0.8.0` | a log the bot owns, one directory for everything the machine writes, the run record read back after a crash |
| 9 | `0.9.0` | the report in the chat: runs and negotiations (ADR-0007), the logger subgraph, the entrance that talks, the log suite on the graph |
| 10 | `0.10.0` | the mesocycle (ADR-0008): planned once, today's workout read off it, a change or an adaptation, the next one prepared when the last cycle ends |
| 11 | `0.11.0` | a plan worth doing: `methodology.md`, the declared minutes a target, a slot naming muscles |
| 12 | `0.12.0` | effort and host per node, the cost of every run, a model matrix per subgraph, the cheapest configuration that clears the bar (ADR-0011) |
| 13 | `0.13.0` | memory with a source, the onboarding conversation, declarations in the database (ADR-0013) and changed through onboarding (ADR-0012) |
| 14 | `0.14.0` | anything about this workout: the adaptation set, the next workout off the log, one adaptation tool, this workout or from now on, prompt caching |
| 15 | `0.15.0` | the supervisor (ADR-0014) and `variation.md`: the next mesocycle arrives with its reason; the demo's home |
| 15b | `1.0.0rc1` | a message mid-plan is read: one suite runner, one negotiation for the bot and the CLI, one roster of node models, the front page |

The details are in `git show v0.N.0`. Sessions 1-5 predate ADR-0004, and their agent layer is what sessions 6-9 replace.

## Session 15c — `1.0.0` — Portfolio-ready

**Demo**: after three mesocycles, the fourth arrives in Telegram with its reason; and *"actually, I only have 30 minutes"* mid-plan brings the 30-minute plan. Recorded in English, with a GIF in the README.

6. **The repository made public.** The history checked for secrets, the switch on the user's go, the badges checked logged out.

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
- the chat's history bounded: the entrance sends the whole `chat:<id>` thread to the model on every turn, forever, so each message costs more with use and a tone set once stays (*«You are an O.G. bro»* turned the demo's bot into a bro until the home was rebuilt);
- secrets out of `.env`: one file per key in a directory under `TRAINER_HOME` (Docker's `/run/secrets` layout), the environment still winning; no OS keychain, which differs per OS and is absent in a container;
- a Docker image and a compose file for the bot, the keys passed as Docker secrets.
- the planner's `emit` read from the cache (ADR-0011, 14.5: $0.015 of a $0.052 mesocycle). Keeping the tools and setting `tool_choice: "none"` recovers only tools and system, ~$0.004, since `tool_choice` invalidates the messages; the history needs the emission as a call to a tool already in the list.

## Risks

- **Telegram's 24-hour window.** Messages sent while the PC is off for longer than that are lost.
