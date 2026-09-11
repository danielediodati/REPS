# The plan eval suite runs against the graph

Status: ready-for-agent
Blocked by: 04

## What to build

- **`trainer eval --suite plan` runs the six situations against the planner graph**, reading ticket 03's run records.
- **The matrix gains the planner's own numbers:** attempts to a valid plan, and wall time per run. When a run is still refused after its last attempt, the matrix names the rule that refused it.
- **The bar stays at 100%**, and the command exits non-zero below it (TRAINER.md § Evaluation).
- **The fixtures are named in the environment** (`TRAINER_DB`), as CLAUDE.md requires.

## Acceptance criteria

- [ ] A full pass at one repetition ran on `gpt-oss:20b`; paste the matrix and the totals.
- [ ] Every failure is diagnosed from its run record and fixed. The bar is never lowered to make a run pass.
- [ ] The full test suite and mypy are green.
