# REPS

> *Reasoning Engine for Personal Strength.* A strength coach built as an agent: a deterministic engine defines what is possible, and a LangGraph agent decides what is good, over weeks, through a Telegram chat, on a local model or on Groq.

REPS is not a plan generator: **it is a loop**. By week 3 the lunges at the end of the workout have cost three missed workouts, and the system changes the plan.

- [TRAINER.md](TRAINER.md): the design
- [ROADMAP.md](ROADMAP.md): what is built and what comes next
- [docs/adr/](docs/adr/): decisions ([ADR-0004](docs/adr/0004-an-agent-graph-over-the-engine-reached-through-telegram.md) is the architecture)

## Status

**`0.8.0` makes a run something you can look at afterwards.** On top of `0.7.0`'s bot (the planner graph on the phone, the graph's progress streamed into the chat, a plan with three buttons, today's inputs off `training.toml` and the rotation), it has:
- one directory for everything the machine writes, `~/.reps`, so replacing the laptop is one directory to copy and two terminals are one installation;
- a rotating log the bot owns, holding every state and every exception and never the token or the owner id, named by the two chat lines that point at it;
- a checkpointer that declares the types it writes, so the threads on disk survive the LangGraph version that stops constructing undeclared ones;
- `trainer runs list` and `trainer runs show`, which read a run back off the checkpointer: what it called, what the validator refused, what it cost, and for one cut mid-flight what it had reached.

Every message still asks for today's workout: the entrance that talks is session 9 (ADR-0006).

**Session 9** puts the report in the chat: the logger as a subgraph on the same tools, an entrance that holds the conversation, and the next plan prepared before it is asked for.

## Architecture (target)

```mermaid
flowchart LR
  tg([Telegram]) <--> bot[bot on the PC]
  bot --> entrance[entrance: a chat model]
  entrance --> planner
  entrance --> logger
  planner <--> tools[(engine tools)]
  logger <--> tools
  planner --> validate
  validate -- refused --> planner
  validate -- ok --> accept[/interrupt: accept or refuse/]
  logger --> ask[/interrupt: question or confirm/]
  accept --> db[(SQLite)]
  ask --> db
  store[(memory store)] -.-> planner
  supervisor[supervisor graph] -.-> store
```

## Getting started

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run trainer db init && uv run trainer db import
uv run trainer enrich derive && uv run trainer enrich curated
cp src/trainer/data/training.example.toml ~/.reps/training.toml   # cycle, cap, split, denominator, equipment

uv run trainer catalog --equipment dumbbell
uv run trainer admissible --equipment "body only" --time 45 --exclude "vertical push"
uv run trainer plan                                           # the next workout of the rotation, against what you declared
uv run trainer log --say "panca bene, solo 3 serie di military"
uv run trainer state
uv run trainer eval --suite plan                              # or --suite log
uv run trainer mcp                                            # the engine's tools over MCP
uv run trainer bot                                            # answer Telegram, the owner only
uv run trainer runs list                                      # the conversations the checkpointer holds
uv run trainer runs show chat:123456                          # what that run called, spent and reached
```

**Choosing the provider.** `trainer plan` and `trainer eval --suite plan` run the planner graph on whichever provider `LLM_BACKEND` names, and copying `.env.example` to `.env` is where that is set.

| `LLM_BACKEND` | what it needs |
|---|---|
| `ollama` (default) | Ollama running, and the model pulled: `ollama pull gpt-oss:20b`. `OLLAMA_MODEL`, `OLLAMA_CONTEXT_LENGTH` and `OLLAMA_BASE_URL` override the rest. |
| `groq` | `GROQ_API_KEY`. `GROQ_MODEL` and `GROQ_MAX_TOKENS` override the rest. |

An unreachable server, a model nobody pulled and a missing key are each reported as a state with the command that fixes it. `trainer log` stays on Groq until session 9 whatever `LLM_BACKEND` names, so it needs `GROQ_API_KEY` either way.

**Telegram.** `trainer bot` needs `TELEGRAM_BOT_TOKEN`, which @BotFather issues, and `TELEGRAM_OWNER_ID`, the only user id it answers, which @userinfobot replies with. Both live in `.env`, never in `training.toml`. On Ollama it also needs `OLLAMA_CONTEXT_LENGTH` of at least 8192, and it checks the provider and the token before it starts. It long-polls, so there is no public IP and no tunnel, and one chat is one thread: the conversation survives a restart.

**Everything the machine writes is in one directory**, `~/.reps`, so replacing the laptop is one directory to copy and two terminals are one installation. `TRAINER_HOME` moves it, and each artifact keeps an override that wins over it: `TRAINER_DB` for the training database, `TRAINER_CHECKPOINTS` for the graph's own state (never the training database), `TRAINER_CONFIG` for `training.toml`, and `TRAINER_EVAL_RUNS` for the eval records. `trainer bot` also writes `trainer.log` there, rotated at a megabyte and four files deep, holding every state and every exception and never the token or the owner id. It has no override, because the chat names it by name when a run cannot start or falls over.

**A run that stopped can be read back.** The log says why it stopped; `trainer runs` says what it was doing. `trainer runs list` names every conversation in the checkpointer with when it last moved and whether it ended with a plan, a refusal or nothing; `trainer runs show THREAD` prints that run's record — the tools it called, the attempts the validator refused, the tokens, the seconds each node cost — and `--json` gives the whole thing, the same document `trainer plan --record` writes. A run cut mid-flight reads back at the last checkpoint it reached, with no outcome invented for it.

## Development

```sh
uv run pytest    # offline: conftest.py removes sockets and credentials
uv run mypy      # strict
uv run langgraph dev                  # the planner graph in LangGraph Studio
```

In Studio the planner's input is the request as JSON: `{"request": {"equipment": ["dumbbell"], "budget_min": 45, "groups": ["chest", "arms"]}}`.

## Layout

```
src/trainer/
  engine/     pure library: no LLM, no network, no knowledge of any client
  coach/      the LangGraph agent: the planner graph, the Telegram bot, the checkpointer and the run records
  data/       vendored catalog, muscle-group mapping, config example
  tools.py    the tool surface, shared by the agent and the MCP server
  plan.py     the plan's shape, validator and renderer
  log.py      the report's shape and validator
  agent.py    the old tool loop, kept for `trainer log` until session 9
docs/
  adr/        decisions
  enrichment/ vocabulary definitions and hand-decided rows, read by the code
  logging/    the log eval set
  research/   notes behind decisions
```
