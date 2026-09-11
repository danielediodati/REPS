# `trainer plan` runs the graph

Status: ready-for-agent
Blocked by: 02, 03

## What to build

- **`trainer plan` without `--from`** builds the request as it does today and runs the planner graph on Ollama.
  - `--record FILE` writes ticket 03's run record.
  - `--call-budget` still applies.
- **Ollama problems are reported as a state, not a traceback.** This covers Ollama being unreachable and the model not being pulled. Name the fix, for example `ollama pull gpt-oss:20b`.
- **Delete the Groq planner path:** `agent.plan_workout`, `RunRecord`, the planner `Door`, and their tests. The Groq adapter and the logger stay until session 8.
- **Remove `--refused FILE --because`.** It comes back as an interrupt in session 7.
- **All output stays ASCII** (CLAUDE.md), including the reasons the model writes.

## Acceptance criteria

- [ ] `uv run trainer plan --equipment dumbbell` prints a valid plan from `gpt-oss:20b`; paste the output.
- [ ] With Ollama stopped, the command names the state and its fix.
- [ ] `trainer log` still works on Groq.
- [ ] The Getting started section of the README matches the new `trainer plan`.
- [ ] The full test suite and mypy are green.
