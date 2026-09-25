# A slot of the split names muscles, not only groups

Status: ready-for-agent

`split` in `training.toml` declares groups: `["chest", "arms"]`. `arms` is biceps, triceps and forearms, so the planner cannot know whether today is chest with biceps or chest with triceps, and `legs` hides six muscles. `muscle-groups.md` already says volume is never counted per group; the split is the one place that still speaks only in groups.

## What to build

- A slot may name **muscles** (`["chest", "biceps"]`), one of the catalog's `primary_muscles`; a group stays valid as shorthand for all its muscles, and a slot may mix the two.
- `admissible_set`, the allocation and the coverage rule read a slot's muscles, whichever way it was written.
- Coverage: a named group needs one exercise whose primary muscle is in it, as today; a named muscle needs one whose primaries include it.
- Time within a slot stays the planner's call. No fixed share per entry; `--group` allocations work as today.
- The vocabulary is read from `muscle-groups.md` and the catalog, never copied.
- `training.example.toml`'s split comment names muscles as well as groups.

## Decisions

| case | answer |
|---|---|
| a muscle mapped to no group (`neck`) | refused: `muscle-groups.md` says no split asks for it |
| a slot naming a group and one of its own muscles (`["arms", "biceps"]`) | refused as redundant, naming the overlap |

## After closing

The user's `~/.reps/training.toml` becomes, with their approval (their comments already say this):

```toml
["chest", "triceps"],
["core"],
["back", "biceps"],
["legs"],
["shoulders", "abdominals"],
```

## Acceptance criteria

- [ ] `["chest", "biceps"]` produces a plan with no triceps exercise, and `["chest", "arms"]` behaves as today.
- [ ] A misspelt muscle is rejected naming the valid ones.
- [ ] `neck` and `["arms", "biceps"]` are refused with the reason.
- [ ] `trainer config` prints a slot as it was written.
- [ ] The full test suite and mypy are green.
