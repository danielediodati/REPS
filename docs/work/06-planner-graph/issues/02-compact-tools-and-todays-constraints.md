# Compact tool results, and standing exclusions on the tool surface

Status: ready-for-agent
Blocked by: 01

## Problem

- **`admissible_set` is too large for the planner.** For a dumbbell day training chest, shoulders and arms it returns about 12,000 characters, roughly 4k tokens, and the model re-reads that on every later turn. At the measured 140 tok/s it is the largest single cost in a planning run.
- **The agent can be handed an excluded exercise.** Standing exclusions (`exclusions.active(connection, today)`) are read by `cli.py` and `log.py`, but never by `tools.py`. In the graph, the agent would only learn about an exclusion when the validator refused the plan.

## What to build

- **A compact exercise record for the planner.** For each admissible exercise it gets only the fields planning actually reads. Pick them by reading the planner prompt and the six invariants. The MCP door keeps the full record.
- **One function that answers *what constrains training today*:** standing exclusions plus the given ones, the duration cap, and the groups. `tools.admissible_set`, the CLI and the graph all call it, so no door can forget the exclusions.

## Acceptance criteria

- [ ] A test shows a persisted exclusion removes its exercises from `admissible_set` when called as a tool.
- [ ] The size of the planner's `admissible_set` result (45 min, dumbbell, chest, shoulders and arms) is measured before and after, with both numbers in the commit message.
- [ ] `trainer mcp` still returns the full record.
- [ ] The full test suite and mypy are green.
