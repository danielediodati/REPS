# 01 — The two faces of a workout: the schema, and a plan that persists

**Status:** ready-for-agent

**Blocked by:** None — can start immediately. Gates 02 and 03.

## What to build

Migration 0006 and the write path for a prescribed workout. No model and no
network anywhere in this ticket.

**The tables.** `workouts` is one row per workout, with a `state` of
`prescribed` or `performed` — the two states CONTEXT.md now defines. `unreported`
is deliberately **not** a third value: it is a *reading* of a prescribed workout
that a later one has overtaken, and storing it would mean something has to go
and set it, which nothing does.

A workout transitions in place, and its children carry a `phase`.
`workout_blocks` and `workout_exercises` mirror the plan document's own shape —
a block with its rounds and its rest, one row per exercise with its unit and
amount — and every row is tagged `prescribed` or `performed`. Both phases live
side by side because **deviation is the difference between them**: overwrite the
prescribed rows when a report arrives and the deviation stops being computable
the moment it is recorded. A workout nobody planned has only performed rows; a
workout never reported has only prescribed ones.

**Provenance is per field**, the way migration 0003 already does it for
enrichment: a `_source` column beside the value it describes, holding
`reported`, `assumed` or `asked`, with a CHECK enforcing the closed vocabulary.
It is NULL on the prescribed phase, where nothing has been reported yet. This
column is what makes *«assume adherence and flag the uncertainty»* a query
rather than a slogan.

**RPE sits on the block and is nullable.** It is never asked for: if the user
says it, it is recorded; if they do not, the column stays empty. Session 7's
autoregulated scheme is its only consumer, and a column that is empty 90% of the
time is information about which schemes are available, not a fault.

**`pattern_state.pain` goes.** Nothing will ever write it. Pain is prose the
agent reads, and its only structured outcome is an exclusion the user confirms —
see ROADMAP.md § Declared deviations, the row on pain as a tracked quantity.

**Plan persistence.** `trainer plan` writes the workout it prescribes, **in the
CLI command and nowhere else** — not in `plan.py`, not in `agent.py`.
`trainer eval` runs eighteen agent loops against the project database, and a
plan that persisted from inside the agent would write eighteen phantom
prescribed workouts into the very state the measurement is taken from, where
ticket 03 would then count them as an unreported rotation.

**Read first:** CONTEXT.md § The unit of training (*Workout*, *Unreported*), §
What a report says (*Provenance*). ROADMAP.md § Session 5. Migration 0003 for
the per-field provenance pattern already in use. ADR-0002 (a plan is a sequence
of blocks). CLAUDE.md § Standing rules — tests derive the expected schema
version from the migration set.

## Acceptance criteria

- [ ] `trainer db status` reports the new schema version, and the suite derives that number from the migration set rather than holding a literal.
- [ ] `trainer plan --from FILE --equipment dumbbell --time 45` renders exactly as before **and** leaves one `prescribed` workout in the database, its blocks and exercises readable back.
- [ ] Running it twice leaves two prescribed workouts, not one overwritten.
- [ ] A plan the validator rejects writes nothing at all — no workout row, no orphaned blocks.
- [ ] A test runs the agent loop against a stand-in model and asserts the workout count is unchanged: neither `agent.py` nor `evaluation.py` reaches a writer.
- [ ] A performed row accepts a provenance of `reported`, `assumed` or `asked` and nothing else; a fourth value is refused by the database, not by Python.
- [ ] A prescribed row carries no provenance, and no RPE.
- [ ] `pattern_state` no longer has a `pain` column.
- [ ] Both phases of the same workout coexist: a fixture with prescribed and performed rows reads back as two distinct sets.
- [ ] The full suite is green — everything that already read `pattern_state` still does.
