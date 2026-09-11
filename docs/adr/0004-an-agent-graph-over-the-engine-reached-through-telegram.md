# An agent graph over the engine, reached through Telegram

At `v0.5.0` REPS had a solid engine and a thin agent. The agent was two single-node tool loops on Groq, with no LangGraph, and a refused plan ended the run. The project exists to show agentic engineering, and what it showed was a pipeline with a model at the end.

This ADR resets the agent layer. The engine and its tools stay.

## Decision

1. **The agent is a LangGraph graph.** Planner, logger, onboarding and supervisor are graphs or subgraphs. The engine stays a deterministic library that the graph reaches only as tools.
2. **A refusal goes back to the planner.** `validate` is a node. It sends every violation back to the planner as feedback, up to a bounded number of attempts, and nothing invalid is ever persisted. This replaces *"no way back in"* from session 4. ADR-0001 still holds: the engine never repairs a plan, the agent does, knowing why it was refused.
3. **The form is constrained while the model writes.** The emit schema is built per request, with `exercise_id` as an enum of today's admissible ids, so constrained decoding cannot produce an invented id. The validator keeps what a schema cannot express: budget, preferences, duplicates.
4. **Human-in-the-loop is `interrupt()`.** It covers clarifying questions, confirming an exclusion and refusing a plan. It replaces the `QUESTION:` marker and `--refused FILE`.
5. **Each store has one owner.**

   | store | holds |
   |---|---|
   | engine SQLite | training facts: catalog, workouts, exclusions |
   | LangGraph checkpointer | conversation state |
   | LangGraph store | what is known about the person (preferences, conclusions), each with a source |

   No store writes another's facts.
6. **The interface is a Telegram bot running on the PC.** It uses long polling, so there is no public IP, no tunnel and no cloud deploy. The bot runs in the same process as the graph, one chat is one thread, and it answers only the owner's user id.
7. **The graph is asynchronous.** A report is processed when it arrives, and the next plan is prepared at that point rather than on request. A pending question waits as long as it takes.
8. **Models run locally on Ollama.**
   - The default is `gpt-oss:20b` on the integrated GPU, with `OLLAMA_IGPU_ENABLE=1` and the context length set explicitly.
   - The supervisor runs on a different model.
   - The Groq adapter goes.
9. **Nothing runs on the phone.**

## Why

- **The phone cannot host the agent.** LangGraph does not run inside an Android app: its Rust dependencies such as pydantic-core have no Android wheels, and LangGraph.js v1 needs Node. The 1-4B models a phone can run score 4-22% on BFCL V4 multi-turn. See `docs/research/on-device-llm-android.md`.
- **The laptop is slow.** Measured on the Ryzen AI 7 350 with 32 GB and the Radeon 860M:
  - `gpt-oss:20b` reads 140 tok/s and generates 11.6 tok/s.
  - The first planner probe took about 4 minutes to reach a refused plan.

  Minutes are acceptable only when nobody is waiting, which is what Telegram and an asynchronous graph give.
- **Most of those minutes came from the design:** a 12k-character tool result, prefix-cache misses, a turn of prose, and an invented id. Items 2 and 3 address them.
- **Telegram removes three problems in one move:** the app, the API between app and server, and reaching the PC over the network. Its costs are accepted:
  - messages pass through Telegram's servers and are not end-to-end encrypted;
  - updates wait there for at most 24 hours while the PC is off.

## Consequences

- **Replaced:**
  - `agent.py`'s loop;
  - the Groq adapter;
  - the `QUESTION:` marker;
  - the plan and log orchestration in `cli.py`.
- **Kept and ported:**
  - `engine/` and `tools.py`;
  - the plan and report shapes, and the plan validator;
  - both eval sets.
- **Superseded in TRAINER.md:** *"a graph adds nothing to a node that loops"* and *"LangGraph never persists a domain fact"*, by items 1 and 5.
- **The roadmap is re-cut from session 6.**
