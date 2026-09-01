# 03 — `trainer catalog` with filters on the native fields

**What to build:** the command that closes the session. `trainer catalog --equipment dumbbell` lists the matching exercises, and the filters compose. Only the native fields — the seven enrichment fields belong to session 2, and nothing here should anticipate them.

The filtering itself is an engine function. The CLI parses arguments and formats rows; it holds no query logic. That boundary is what makes the same filter reusable later as a tool the agent calls, without rewriting it.

Reference: ROADMAP.md § Session 1, TRAINER.md § Engine — analytic / constrained.

**Blocked by:** 02 — Import the free-exercise-db catalog

**Status:** ready-for-agent

- [ ] `trainer catalog --equipment dumbbell` lists the matching exercises
- [ ] Every native field usable as a filter, and multiple filters compose as AND
- [ ] The CLI vocabulary is the source's own vocabulary — `dumbbell`, not `dumbbells`; a mismatch here would quietly become a rule the whole system inherits
- [ ] An unknown filter value is rejected with the list of valid values for that field. A typo and a genuinely empty result must never look alike
- [ ] A filter that legitimately matches nothing says so explicitly
- [ ] Output identifies each exercise and shows enough native fields to tell two variants apart
- [ ] Unit tests cover the engine function directly; a single smoke test goes through the CLI
- [ ] No test requires the network or a model

## Comments
