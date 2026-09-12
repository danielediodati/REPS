# `trainer plan` runs the graph, on Ollama or Groq

Status: ready-for-agent
Blocked by: 02, 03

## What to build

- **`LLM_BACKEND` chooses the provider: `ollama`, the default, or `groq`.**
  - The variable already exists (`agent.backend`) and can only name `groq`. It gains `ollama`.
  - One function builds the chat model from it. `trainer plan`, the graph in `langgraph.json` and ticket 01's probe all use it.
  - Groq goes through `langchain-groq`, reading the settings `agent.py` reads today: `GROQ_MODEL`, `GROQ_API_KEY`, `GROQ_MAX_TOKENS`.
  - The run record's `provider` comes from it. `coach.probe.PROVIDER` is a constant until then.
  - `.env.example` lists `LLM_BACKEND` and the Ollama settings.
- **`trainer plan` without `--from`** builds the request as it does today and runs the planner graph.
  - `--record FILE` writes ticket 03's run record.
  - `--call-budget` still applies.
- **Provider problems are reported as a state, not a traceback**, each with its fix:
  - Ollama unreachable, or the model not pulled (`ollama pull gpt-oss:20b`);
  - Groq with no key (`agent.NO_CREDENTIALS` already says it);
  - an `LLM_BACKEND` value nobody built.
- **Remove `--refused FILE --because`.** It comes back as an interrupt in session 7. `Request.refused` stays: the validator and the after-a-refusal situation read it.
- **The old loops stay for now.**
  - `trainer log` runs on its Groq loop until session 8, whatever `LLM_BACKEND` names.
  - `trainer eval --suite plan` stays on the Groq planner loop until ticket 05, which deletes it.
- **All output stays ASCII** (CLAUDE.md), including the reasons the model writes.

Ask the user to close heavy apps before a run on `gpt-oss:20b`.

## Acceptance criteria

- [ ] With `LLM_BACKEND=ollama`, `uv run trainer plan --equipment dumbbell` prints a valid plan from `gpt-oss:20b`; paste the output.
- [ ] With `LLM_BACKEND=groq`, the same command prints a valid plan from Groq; paste the output.
- [ ] With Ollama stopped, the command names the state and its fix.
- [ ] With `LLM_BACKEND=groq` and no key, the command names the state and its fix.
- [ ] With `LLM_BACKEND=ollama`, `trainer log` still works on Groq.
- [ ] The Getting started section of the README matches the new `trainer plan` and says how to choose the provider.
- [ ] The full test suite and mypy are green.
