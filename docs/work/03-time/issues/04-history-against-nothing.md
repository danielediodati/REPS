# 04 — Two questions the state can't answer yet

**What to build:** `pattern_history(connection, pattern, weeks)` and `last_performed_load(connection, exercise_id)`, both in `engine/`, both real library functions with real signatures — and both, today, always answering *«I don't know»*, because the data they will eventually read does not exist until session 5 writes `workouts`.

**This ticket builds functions for a table that is not there yet, on purpose.** `pattern_state` exists — session 2's migration created it — but nothing writes `weekly_volume`, `load_trend` or `pain` into it until logged workouts exist. `last_performed_load` is worse: there is no `workouts` table at all yet to read a load from. Both facts are already named in ROADMAP.md's own account of this session: *"against still-empty state — they have to answer «I don't know», not break"*. Building the shape now, against nothing, is what stops session 5 from having to invent a new contract under time pressure once real rows exist.

**"I don't know" has to be a value, not a caught exception.** Session 4's agent will call these mid-loop, inside its call budget, and CLAUDE.md's own standing rule already names this failure mode once — a missing precondition reported as a user error rather than a state. An agent that gets an exception here has no way to distinguish *"you asked something malformed"* from *"nobody has trained this pattern yet"*; a typed "unknown" answer lets it carry on and reason about it, which is exactly what an agentic loop needs and a crash does not give it.

**Do not special-case emptiness with an `if not rows`.** Write the query so that a genuinely empty `pattern_state`, a pattern with no rows in it, and — once session 5 lands — a pattern with real history, are three cases the same query distinguishes on its own. The goal is that session 5 changes what gets written into `pattern_state` and `workouts`, and changes nothing in this ticket's code.

**`last_performed_load(exercise_id)` still validates its input against the real catalog.** An unknown exercise id is a caller error and should be reported as one — the "I don't know" contract is for *"no history exists for this valid exercise"*, never a cover for *"this id does not exist"*.

Reference: TRAINER.md § Persistent state (`pattern_state`), § The tool surface; ROADMAP.md § Session 2 (`pattern_state`'s migration), § Session 3; CLAUDE.md § Standing rules (a missing precondition is a state, not a user error).

**Blocked by:** None — can start immediately; independent of tickets 01-03.

**Status:** ready-for-agent

- [ ] `pattern_history(connection, pattern, weeks)` returns a typed result distinguishing *no data for this pattern* from *real history*, never raising for the empty case
- [ ] `last_performed_load(connection, exercise_id)` returns the same kind of typed "unknown" when no load has ever been logged for that exercise
- [ ] An unknown `pattern` value is rejected against the catalog's own vocabulary (`catalog.values`), the same way `admissible_set` already rejects one
- [ ] An unknown `exercise_id` is rejected as a caller error, distinct from and never confused with "unknown, no history"
- [ ] Tests run against the current schema with zero rows in `pattern_state` and assert no exception is raised and the "unknown" branch is returned
- [ ] `tests/test_engine_boundary.py` still passes

## Comments
