# Compact tool results, and standing exclusions on the tool surface

Status: ready-for-agent
Blocked by: 01

## Problem

- **`admissible_set` is still too large for the planner.** The planner's results are already trimmed: `agent.PLANNER.hides` is `NOT_FOR_CONTEXT`, seven fields dropped on the way to the model. After that trim, a dumbbell day training chest, shoulders and arms still returns about 12,000 characters, roughly 4k tokens, and the model re-reads that on every later turn. At the measured 140 tok/s it is the largest single cost in a planning run.
- **The agent can be handed an excluded exercise.** Standing exclusions (`exclusions.active(connection, today)`) are read by `cli.py` and `log.py`, but never by `tools.py`. In the graph, the agent would only learn about an exclusion when the validator refused the plan.

## What to build

- **The planner keeps a list of fields instead of dropping one.** Replace its deny-list with an allow-list of what planning actually reads. Pick the fields by reading the planner prompt and the six invariants. Build it into the existing trim, not a second mechanism.
  - `name` stays out: `NOT_FOR_CONTEXT`'s docstring says why.
  - `_trimmed` walks every tool's answer by key. The allow-list applies to exercise records only, never to the envelope of an `Answer` or of `compare_variants`.
  - The logger's trim does not change. `NOT_FOR_THE_LOG` is derived from `NOT_FOR_CONTEXT` today, so give it its own definition first: `trainer eval --suite log` depends on it.
  - The MCP door already returns the full record, and keeps doing so.
- **One function that answers *what constrains training today*:** standing exclusions plus the given ones, the duration cap, and the groups. `tools.admissible_set`, the CLI and the graph all call it, so no door can forget the exclusions.

## Acceptance criteria

- [ ] A test shows a persisted exclusion removes its exercises from `admissible_set` when called as a tool.
- [ ] The size of the planner's `admissible_set` result (45 min, dumbbell, chest, shoulders and arms) is measured before and after, with both numbers in the commit message.
- [ ] A test shows the fields the logger sees are unchanged.
- [ ] `trainer mcp` still returns the full record.
- [ ] The full test suite and mypy are green.
