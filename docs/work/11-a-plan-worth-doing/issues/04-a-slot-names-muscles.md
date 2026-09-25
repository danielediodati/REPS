# A slot of the split names muscles, not only groups

Status: needs-triage

`split` in `training.toml` declares groups: `["chest", "arms"]`. `arms` is biceps, triceps and forearms, so the planner cannot know whether today is chest with biceps or chest with triceps, and `legs` hides six muscles. `muscle-groups.md` already says volume is never counted per group; the split is the one place that still speaks only in groups.

## What to build

- A slot may name **muscles** (`["chest", "biceps"]`), one of the catalog's `primary_muscles`; a group stays valid as shorthand for all its muscles.
- `admissible_set`, the allocation and the coverage rule (*each group needs an exercise whose primary muscle is in it*) read a slot's muscles, whichever way it was written.
- The vocabulary is read from `muscle-groups.md` and the catalog, never copied.

## Acceptance criteria

- [ ] `["chest", "biceps"]` produces a plan with no triceps exercise, and `["chest", "arms"]` behaves as today.
- [ ] A misspelt muscle is rejected naming the valid ones.
- [ ] The full test suite and mypy are green.
