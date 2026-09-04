# 03 — What the user declares, in a file

**What to build:** the training configuration — cycle length, the cap on a workout's duration, the split being trained, and the denominator volume is counted on — read from a committed file, never from SQLite. ADR-0003 carries why; this ticket is the file, its schema, its reader, and the errors it gives when it is wrong.

**The line is who writes the value.** SQLite holds what the system writes: performed workouts, accumulated volume, exclusions and their re-test dates. These four are declared by the user, changed by hand, and read back by the user. In a file they are visible without a query and `git diff` says when the user changed their mind about the cycle, which is itself training history. In a table they are rows that have to be interrogated to find out what was decided, sitting beside rows the system measured.

**What it holds, and nothing more.**

- **cycle length** — how many workouts one complete rotation holds. Not days of the week: the user trains when they have time, and the rotation advances when a workout is performed.
- **duration cap** — the most a single workout may run.
- **split** — for each of the cycle's workouts, which muscle groups it trains. An ordered list as long as the cycle. Declared here until session 7, where the agent starts choosing it at the mesocycle boundary and recording its reason.
- **volume denominator** — what volume is counted over. `cycle` is the value that matches how the user trains; it is written down rather than assumed because it is the user's call, not the engine's.

**The six muscle groups are vocabulary, and the file is checked against them.** `chest`, `back`, `shoulders`, `arms`, `legs`, `core` — defined in CONTEXT.md as a curated grouping of the catalog's own seventeen `primary_muscles` values. That mapping belongs in this ticket too, as a committed file with its decisions visible, the way `docs/enrichment/residue.md` carries its own. `lower back` is core, not back — it is trunk musculature. `neck` maps to no group: its five rows stay reachable in the catalog and no split ever asks for them.

**Every way the file can be wrong is a named state.** A split whose length does not match the cycle length, a group name that is not one of the six, a duration cap of zero, a missing file. Each says what is wrong and what the file should look like. The standing rule applies with full force here: a missing config is *«no training configuration yet»* and the command that creates one, never a validation error on a field nobody filled in.

**It reads. Nothing in the engine writes it.** Session 6's onboarding is what fills it by talking to the user. This ticket ships the reader, the schema and the errors, and a hand-written example committed in the repo.

Reference: ADR-0003; CONTEXT.md (*cycle*, *split*, *muscle group*, *volume deficit*); TRAINER.md § Persistent state; CLAUDE.md § Standing rules (a missing precondition is a state, and vocabulary is read from the data); ROADMAP.md § Session 3.

**Blocked by:** None — independent of tickets 01 and 02.

**Status:** ready-for-agent

- [ ] A committed mapping from the catalog's seventeen `primary_muscles` values to the six muscle groups, with `lower back` in core and `neck` mapped to nothing, each grouping decision visible in the file
- [ ] Every one of the seventeen values is accounted for — a test that fails the day the catalog grows an eighteenth rather than silently dropping it
- [ ] A config file format holding cycle length, duration cap, split and volume denominator, with a hand-written example committed
- [ ] A reader returning a typed shape, validating against the six groups read from the mapping rather than a copy of the names
- [ ] Split length not matching cycle length is a named error that says both numbers
- [ ] An unknown group name is rejected and the valid ones are listed
- [ ] A missing config file is reported as a state — *«no training configuration yet»* — never as a field validation failure
- [ ] Nothing in `engine/` writes the file
- [ ] Unit tests over a valid config and each way it can be wrong — no LLM, no network
- [ ] `tests/test_engine_boundary.py` still passes

## Comments

**From ticket 02 — `allocate` does not check its group names, and this ticket is why.**

`budget.allocate(40, {"Chest": 0.6, "arms": 0.4})` succeeds today and returns minutes keyed by the typo; the caller who later reads `allocated["chest"]` gets a `KeyError` a long way from the mistake. Raised in ticket 02's review and declined there deliberately: the six groups do not exist anywhere a function can read them yet, and a constant in `budget.py` listing them would be exactly the hand-copied vocabulary CLAUDE.md's standing rule was written about.

This ticket is what creates the mapping from the catalog's seventeen `primary_muscles` values to the six groups. **When it lands, add the check to `allocate`** — reading the vocabulary from the mapping, never from a copy — and a test that a misspelled group is refused with the valid names listed, the way `catalog.check_value` already does it for a filter.
