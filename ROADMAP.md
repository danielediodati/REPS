# Roadmap

The order things get built in. [TRAINER.md](TRAINER.md) is the design; [ADR-0004](docs/adr/0004-an-agent-graph-over-the-engine-reached-through-telegram.md) is the architecture.

**Slicing rule.** A milestone ends with a **demo someone can watch**: a chat, a Studio trace, a command. If there is nothing to record, it was sliced wrong. Each ticket must be closable on its own, in a clean context.

## Done

| milestone | version | shipped |
| --- | --- | --- |
| 1 - The catalog | `0.1.0` | 876 exercises from free-exercise-db in SQLite, `trainer catalog` with filters, a versioned snapshot |
| 2 - Enrichment | `0.2.0` | six enrichment fields (rules plus hand-read residue), the reference set, exclusions, `trainer admissible` |
| 3 - Duration and budget | `0.3.0` | duration over blocks (ADR-0002), `remaining_budget` and `allocate`, `training.toml` (ADR-0003), the MCP server |
| 4 - The planner | `0.4.0` | plan shape and validator, a tool-loop planner on Groq, six invariants over six adverse situations |
| 5 - The log | `0.5.0` | prescribed and performed workouts with per-field provenance, volume views on two axes, a logging agent, a 30-report eval set |
| 6 - The planner graph | `0.6.0` | the planner as a LangGraph graph: a validator that refuses and a planner that reads why, a checkpointer, `trainer plan` on it, the plan suite against it |
| 7 - The Telegram bot | `0.7.0` | the Telegram bot: today's plan with buttons, *Non mi va* brings another, the provider checked at start |
| 8 - A log the bot owns | `0.8.0` | a log the bot owns, one directory for everything the machine writes, the run record read back after a crash |
| 9 - The report in the chat | `0.9.0` | the report in the chat: runs and negotiations (ADR-0007), the logger subgraph, the entrance that talks, the log suite on the graph |
| 10 - The mesocycle | `0.10.0` | the mesocycle (ADR-0008): planned once, today's workout read off it, a change or an adaptation, the next one prepared when the last cycle ends |
| 11 - A plan worth doing | `0.11.0` | a plan worth doing: `methodology.md`, the declared minutes a target, a slot naming muscles |
| 12 - Cost per node | `0.12.0` | effort and host per node, the cost of every run, a model matrix per subgraph, the cheapest configuration that clears the bar (ADR-0011) |
| 13 - Memory and onboarding | `0.13.0` | memory with a source, the onboarding conversation, declarations in the database (ADR-0013) and changed through onboarding (ADR-0012) |
| 14 - Anything about this workout | `0.14.0` | anything about this workout: the adaptation set, the next workout off the log, one adaptation tool, this workout or from now on, prompt caching |
| 15 - The supervisor | `0.15.0` | the supervisor (ADR-0014) and `variation.md`: the next mesocycle arrives with its reason; the demo's home |
| 15b - A message mid-plan | `1.0.0rc1` | a message mid-plan is read: one suite runner, one negotiation for the bot and the CLI, one roster of node models, the front page |
| 15c - Portfolio-ready | `1.0.0` | portfolio-ready: a plan answered in words, the chat in Telegram's language and one progress line, the demo recorded with its GIF, the repository public |
| 16 - Answer from sources | `1.1.0` | the entrance answers technique and prevention from openly licensed texts, quoting its passage under a link, or says they do not cover it; the `answer` suite with a calibrated judge (ADR-0017, ADR-0018) |

The details are in `git show v<version>`. Milestones 1-5 predate ADR-0004, and their agent layer is what 6-9 replace.

## Later

**Parked**:
- exercise photos: a plan in Telegram shows each exercise's pictures; an exercise without is sent without; nothing is generated. Not free-exercise-db's, which were taken from other sites; wger's, licensed per image, are the source to check first.

**After 1.0.0**:
- secrets out of `.env`: one file per key in a directory under `TRAINER_HOME` (Docker's `/run/secrets` layout), the environment still winning; no OS keychain, which differs per OS and is absent in a container;
- a Docker image and a compose file for the bot, the keys passed as Docker secrets.

## Risks

- **Telegram's 24-hour window.** Messages sent while the PC is off for longer than that are lost.
