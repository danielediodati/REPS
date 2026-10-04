# The supervisor's set

Status: ready-for-agent

Blocked by: 02, 03.

Read first: ADR-0010; ADR-0011 (the cheapest configuration that clears its bar); TRAINER.md § Evaluation; `docs/adapting/eval-set.toml` as the shape of a set.

## What to build

- **`trainer eval --suite supervise`**: 15-20 scripted histories, each with what the next direction, and the mesocycle planned from it, must hold. Checked by code; no judge model. Rows include:
  - after two mesocycles alike, something changes (exercises or scheme);
  - an exercise the user said they love is kept while the rest rotates (the key row);
  - reps and rest stay inside the goal's range in the methodology;
  - the direction carries on the thread of the last one.
- **How often the planner follows the direction**, at a bar declared in the set before any run.
- **The supervisor's model by ADR-0011's rule**, and the row in ADR-0011.
- $ and s per run in the pass, as the other suites.

**Spends credits.** Every pass is estimated first and runs only on the user's go (CLAUDE.md), against a fixture named in `TRAINER_DB`.

## Acceptance criteria

- [ ] The set declares its bars before the first run.
- [ ] A pass on the chosen configuration clears them, with $ and s per run.
- [ ] ADR-0011 has the supervisor's row.
- [ ] Full test suite and mypy green.
