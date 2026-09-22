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
- `trainer runs list` and `trainer runs show`, which read a run back: what it called, what the validator refused, what it cost, and for one cut mid-flight what it had reached.

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
uv run trainer plan --mesocycle                               # a workout per slot of the split, kept when accepted
uv run trainer plan                                           # today's workout off it, with the last load beside each exercise
uv run trainer log --say "panca bene, solo 3 serie di military"
uv run trainer state
uv run trainer eval --suite plan                              # or --suite log
uv run trainer mcp                                            # the engine's tools over MCP
uv run trainer bot                                            # answer Telegram, the owner only
uv run trainer runs list                                      # every negotiation, and what it came to
uv run trainer runs show 20260918-190412-3f9a                 # its runs: what each called, spent and reached
```

**Choosing the provider.** `trainer plan` and `trainer eval --suite plan` run the planner graph on whichever provider `LLM_BACKEND` names, and copying `.env.example` to `.env` is where that is set.

| `LLM_BACKEND` | what it needs |
|---|---|
| `ollama` (default) | Ollama running, and the model pulled: `ollama pull gpt-oss:20b`. `OLLAMA_MODEL`, `OLLAMA_CONTEXT_LENGTH` and `OLLAMA_BASE_URL` override the rest. |
| `groq` | `GROQ_API_KEY`. `GROQ_MODEL` and `GROQ_MAX_TOKENS` override the rest. |

An unreachable server, a model nobody pulled, a missing key and a model Groq has retired are each reported as a state with the command that fixes it, before the run starts. `trainer log` runs the logger graph on the same provider as everything else.

**The entrance has a model of its own** (ADR-0006). `trainer bot` answers every turn through a chat model that holds the conversation and reaches the planner and the logger as tools; it is the node you wait on, so it runs on something small and fast while the subgraphs keep the one `LLM_BACKEND` names. `ENTRANCE_MODEL` names it — `llama3.1` on Ollama, `GROQ_MODEL`'s on Groq — and `ENTRANCE_BACKEND` puts it on the other provider, which is how the planner goes to Groq while hello stays on this machine. Both models are checked before the bot starts.

**Telegram.** `trainer bot` needs `TELEGRAM_BOT_TOKEN`, which @BotFather issues, and `TELEGRAM_OWNER_ID`, the only user id it answers, which @userinfobot replies with. Both live in `.env`, never in `training.toml`. On Ollama it also needs `OLLAMA_CONTEXT_LENGTH` of at least 8192, and it checks both providers and the token before it starts. It long-polls, so there is no public IP and no tunnel, and one chat is one thread: the conversation survives a restart.

**What the chat does with what you write.** You write in your own words and the entrance decides: a request for today's workout starts the planner, a report starts the logger, and a question about what you have trained is answered from the engine's read tools without either. Your turn is answered at once and the work goes on behind it, with the graph's progress in the draft — a plan is minutes. The plan arrives with three buttons; the logger's clarifying question is a message to reply to and the exclusion it proposes is two. Nothing the chat says is a fixed line except the two about the machine being in trouble, and neither of those quotes what went wrong: that goes to `trainer.log`.

**Everything the machine writes is in one directory**, `~/.reps`, so replacing the laptop is one directory to copy and two terminals are one installation. `TRAINER_HOME` moves it, and each artifact keeps an override that wins over it: `TRAINER_DB` for the training database, `TRAINER_CHECKPOINTS` for the graph's own state (never the training database), `TRAINER_CONFIG` for `training.toml`, and `TRAINER_EVAL_RUNS` for the eval records. `trainer bot` also writes `trainer.log` there, rotated at a megabyte and four files deep, holding every state and every exception and never the token or the owner id. It has no override, because the chat names it by name when a run cannot start or falls over.

**Every run can be read back.** A *run* is one proposal pursued, from the request being assembled to your answer; turning a plan down ends it and the plan that follows belongs to another. One ask and all its runs are a *negotiation* (ADR-0007). A run that ends is written into `runs/` in the home the moment it ends, so the evidence of an evening survives the checkpointer, which keeps only the run that is alive.

The log says why a run stopped; `trainer runs` says what it was doing. `trainer runs list` names every negotiation with when it last moved, how many runs it took and what it came to — accepted, turned down, refused by the validator, fallen over, *cut*, or *waiting since* the day it asked. `trainer runs show NAME` takes a negotiation or one of its runs and prints each one's record: the tools it called, the attempts the validator refused, the tokens, the seconds each node cost, and the words you turned it down with. `--json` gives the documents whole, which is what `trainer plan --record` copies. It reads documents and nothing else — no provider, no graph, no model — because it is the tool you reach for when the provider is what is wrong.

## Development

```sh
uv run pytest       # offline: conftest.py removes sockets and credentials
uv run mypy         # strict
uv run langgraph dev  # the planner and the logger in LangGraph Studio
```

In Studio the planner's input is the request as JSON: `{"request": {"equipment": ["dumbbell"], "budget_min": 45, "groups": ["chest", "arms"]}}`. The logger's is the report: `{"report": "panca bene, solo 3 serie di military", "today": "2026-09-18"}`. The entrance's is a message: `{"messages": [{"role": "user", "content": "cosa faccio oggi?"}]}` — it decides, and says which subgraph it would have started rather than starting one.

## Layout

```
src/trainer/
  engine/     pure library: no LLM, no network, no knowledge of any client
  coach/      the LangGraph agent: the entrance, the planner and logger graphs, the Telegram bot, the checkpointer and the run archive
  data/       vendored catalog, muscle-group mapping, config example
  tools.py    the tool surface and how a model calls it, shared by the graphs and the MCP server
  plan.py     the plan's shape, validator and renderer
  log.py      the report's shape and validator
docs/
  adr/        decisions
  enrichment/ vocabulary definitions and hand-decided rows, read by the code
  logging/    the log eval set
  research/   notes behind decisions
```
