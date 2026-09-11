# Named violations, a checkpointer, and the run record from graph state

Status: ready-for-agent
Blocked by: 01

## Problem

- **`plan.validate` stops at the first failing rule.** The planner learns about one mistake per attempt, and the eval cannot tell which rule refused a plan. `evaluation.py` also recomputes three of the rules on its own.
- **A run leaves nothing to read back.** Ticket 01's graph has no checkpointer and writes no record.

## What to build

- **The plan's rules as named checks.** `validate` returns every violation with its rule name, and the feedback sent to the planner lists all of them. Where an invariant in `evaluation.py` computes the same property as a rule, it calls the rule instead.
- **A SQLite checkpointer in its own file**, not `trainer.sqlite`: the graph never writes training facts (ADR-0004, item 5).
- **A run record derived from the graph state**, written as JSON the way today's `--record` is. It holds:
  - the tool calls, with their arguments and any failures;
  - the attempts, with their violations;
  - tokens;
  - wall time per node;
  - the emitted plan and the outcome.

## Acceptance criteria

- [ ] A test shows a plan that breaks two rules gets both violations back in a single feedback message.
- [ ] A test shows a finished run's state can be read from the checkpointer by its thread id.
- [ ] The record of a real run shows the attempts and the wall time per node.
- [ ] The full test suite and mypy are green.
