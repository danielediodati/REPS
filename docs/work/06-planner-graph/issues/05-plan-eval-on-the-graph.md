# The plan eval suite runs against the graph, and the Groq planner loop goes

Status: ready-for-agent
Blocked by: 04

## What to build

- **`trainer eval --suite plan` runs the six situations against the planner graph**, on the provider `LLM_BACKEND` names, reading ticket 03's run records.
- **The matrix gains the planner's own numbers:** attempts to a valid plan, and wall time per run. When a run is still refused after its last attempt, the matrix names the rule that refused it.
- **The bar stays at 100%**, and the command exits non-zero below it (TRAINER.md § Evaluation).
- **The fixtures are named in the environment** (`TRAINER_DB`), as CLAUDE.md requires.
- **Delete `trainer.coach.probe`.** Ticket 01's one measured pass over the six situations is what this suite now does. Keep its way of measuring memory, Ollama's `/api/ps` plus the least free system memory: on the iGPU the weights sit outside Ollama's working set.
- **Delete the Groq planner loop**, now that nothing measures through it.
  - First move what the graph still reads from `agent.py` into `coach/planner.py`: the planner's tool names, its field allow-list, `PLANNING` and `brief`.
  - Then delete `agent.plan_workout`, `RunRecord`, `agent.PLANNER` and their tests, along with the eval's use of them (`evaluation.py`, `cli._plan_suite`).
  - The Groq adapter's tests that use the planner's door move to the logger's.
  - `Door`, `LOGGER`, the logger's loop and the hand-written Groq adapter stay until session 8.
  - `PLANNING` is no longer shared with a loop that ends at a refusal, so it can now tell the model a refusal comes back with its reasons.

Ask the user to close heavy apps before the pass on `gpt-oss:20b`.

## Acceptance criteria

- [ ] A full pass at one repetition ran on `gpt-oss:20b`; paste the matrix and the totals.
- [ ] Every failure is diagnosed from its run record and fixed. The bar is never lowered to make a run pass.
- [ ] Nothing under `src/` or `tests/` names `plan_workout` or `RunRecord`.
- [ ] `trainer log` still works on Groq.
- [ ] The full test suite and mypy are green.
