# An agent graph over the engine, reached through Telegram

At `v0.5.0` REPS had a solid engine and a thin agent. The agent was two single-node tool loops on Groq, with no LangGraph, and a refused plan ended the run. The project exists to show agentic engineering, and what it showed was a pipeline with a model at the end.

This ADR resets the agent layer. The engine and its tools stay.

## Decision

1. **The agent is a LangGraph graph.** Planner, logger, onboarding and supervisor are graphs or subgraphs. The engine stays a deterministic library that the graph reaches only as tools.
2. **A refusal goes back to the planner.** `validate` is a node. It sends every violation back to the planner as feedback, up to a bounded number of attempts, and nothing invalid is ever persisted. This replaces *"no way back in"* from session 4. ADR-0001 still holds: the engine never repairs a plan, the agent does, knowing why it was refused.
3. **The form is constrained while the model writes.** The emit schema is built per request, with `exercise_id` as an enum of today's admissible ids, so constrained decoding cannot produce an invented id. The validator keeps what a schema cannot express: budget, preferences, duplicates. Enforcement is asked for explicitly (`strict=True`): left unsaid, langchain sends `strict: false`, and until 2026-09-26 every OpenRouter emission ran unconstrained.
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
8. **The provider is configuration.** `LLM_BACKEND` names `ollama` or `groq`, and the graph reaches either through LangChain's chat-model interface.
   - The default is Ollama: `gpt-oss:20b` **on the CPU**, with `OLLAMA_IGPU_ENABLE=0` and the context length set explicitly. See the correction below: the integrated GPU cannot run this model at all.
   - The supervisor runs on a different model.
   - The hand-written Groq adapter goes with the old loop. Groq stays, as a provider.
9. **Nothing runs on the phone.**

## Why

- **The phone cannot host the agent.** LangGraph does not run inside an Android app: its Rust dependencies such as pydantic-core have no Android wheels, and LangGraph.js v1 needs Node. The 1-4B models a phone can run score 4-22% on BFCL V4 multi-turn. See `docs/research/on-device-llm-android.md`.
- **The laptop is slow.** Measured on the Ryzen AI 7 350 with 32 GB and the Radeon 860M:
  - `gpt-oss:20b` reads 140 tok/s and generates 11.6 tok/s.
  - The first planner probe took about 4 minutes to reach a refused plan.

  **Corrected in session 7: the integrated GPU is not available to this model, and never was.** `gpt-oss:20b` terminates the Vulkan backend of the Radeon 860M with a C++ exception at *any* offload -- four layers and 2.4 GB included -- while `llama3.1` runs on the same device. It is the model's MXFP4 quantisation against this driver, not memory, and `OLLAMA_IGPU_ENABLE=1` as written above only makes it fail at startup. Re-measured on the CPU: **10.3 tok/s generated, 52 tok/s read**, one plan in 4 minutes and 11 for a run refused twice. That the generation figures agree within a token per second suggests the original measurement was already on the CPU, with the GPU setting doing nothing.

  Minutes are acceptable only when nobody is waiting, which is what Telegram and an asynchronous graph give.
- **Groq stays selectable.** A 12 GB model plus its context is at the edge of this laptop's memory, and the OS killed the first probe. When the laptop cannot hold the model, the same graph runs on Groq.
- **Most of those minutes came from the design:** a 12k-character tool result, prefix-cache misses, a turn of prose, and an invented id. Items 2 and 3 address them.
- **Telegram removes three problems in one move:** the app, the API between app and server, and reaching the PC over the network. Its costs are accepted:
  - messages pass through Telegram's servers and are not end-to-end encrypted;
  - updates wait there for at most 24 hours while the PC is off.
- **Verdict on `gpt-oss:20b` at `reasoning: low` (ticket 6.1): it does not hold yet.** 4 of 6 situations reached a valid plan, 2 of them only after a refusal came back, and most refusals were the clock. The numbers are in `docs/research/on-device-llm-android.md` § 5. The fallback to measure next is `qwen3.5:9b`, or Groq through `LLM_BACKEND`.

## Consequences

- **Replaced:**
  - `agent.py`'s loop;
  - the hand-written Groq adapter (Groq stays, through `langchain-groq`);
  - the `QUESTION:` marker;
  - the plan and log orchestration in `cli.py`.
- **Kept and ported:**
  - `engine/` and `tools.py`;
  - the plan and report shapes, and the plan validator;
  - both eval sets.
- **Superseded in TRAINER.md:** *"a graph adds nothing to a node that loops"* and *"LangGraph never persists a domain fact"*, by items 1 and 5.
- **The roadmap is re-cut from session 6.**
