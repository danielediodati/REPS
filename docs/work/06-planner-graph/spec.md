# Session 6: the planner is a graph

**Goal**: the planning agent becomes a LangGraph graph running on a local Ollama model. A refused plan goes back to the planner with the reasons, and an invented exercise id cannot be decoded.

**Demo**: in LangGraph Studio, the planner proposes a plan, the validator refuses it, and the planner reads why and fixes it.

**Read first**:
- ADR-0004, the architecture;
- ADR-0001, the engine never repairs a plan;
- TRAINER.md § Architecture and § Evaluation;
- `docs/research/on-device-llm-android.md` § 5, the laptop's measured limits.

**Order**:
- 01 decides whether the rest of the session is built on `gpt-oss:20b`.
- 02 and 03 build on 01's graph.
- 04 needs 02 and 03.
- 05 needs 04.

**Out of scope**:
- Telegram and `interrupt()`: session 7.
- The logger: session 8. It keeps the Groq loop until then.
- Memory.

## Facts the tickets rely on

- **The planner's tools, prompt, brief and hidden fields**: `agent.PLANNER`, `agent.PLANNING`, `agent.brief`, `agent.NOT_FOR_CONTEXT`.
- **The request, the plan shape and the validator**: `plan.Request`, `plan.WorkoutPlan`, `plan.to_blocks`, `plan.validate`. `agent.strict_schema` makes a pydantic schema strict.
- **Today's request is assembled in `cli.py`'s plan command.** It reads `exclusions.active`, the duration cap, the split and the rotation.
- **The six situations and the six invariants**: `evaluation.py`.
- **`pytest` runs with no sockets and no credentials** (`conftest.py`). Graph tests use a scripted chat model; the real model runs only in probes and in `trainer eval`.
- **Measured on 2026-09-11** with `gpt-oss:20b` on the integrated GPU:
  - it reads 140 tok/s and writes 11.6 tok/s, with 12 GB loaded;
  - a probe with a 16k context was killed for low memory while normal apps were open.
