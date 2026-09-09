# 02 — The performed workout is a document: schema, validator, writer, renderer

**Status:** ready-for-agent

**Blocked by:** 01 (needs the tables).

## What to build

The door the logging agent's output will come through, built and testable
**before** there is an agent — the mirror of session 4's ticket 02.
`trainer log --from FILE` reads a performed workout someone wrote by hand,
validates it, writes it in one transaction, and renders what it understood. No
model and no network.

**The schema.** Which prescribed workout this reports against, or none. The
blocks actually performed, with their rounds, their rest and an optional RPE.
One item per exercise, with its unit, its amount and its load. A `_source` on
every reported value. Plus two fields the plan document does not have: the
user's own words, verbatim, and an optional **proposed exclusion** — a
granularity, a value and a re-test date — which ticket 04 makes the agent fill
and which stays empty here.

The schema is the wire shape and lives beside the tool surface, the way the plan
schema does. The engine grows no new types.

**The validator, and this is where the symmetry with session 4 breaks.** That
one refuses a plan outside the admissible set, because the plan has not happened
and can still be prevented. This one cannot refuse **a fact**. You had an
exclusion on `vertical push` and you pressed anyway: that row is the most
valuable one in the database — it is what feeds session 9's hypotheses and the
medical escalation — and rejecting it would mean keeping a clean state by lying
about what happened. A performed workout is **recorded and flagged**, never
rejected.

What it still refuses, because none of it is a matter of opinion:

1. an `exercise_id` the catalog does not have;
2. a unit that is neither `reps` nor `seconds`, or an amount that is not a
   number;
3. a provenance outside the three values;
4. a proposed exclusion whose value `exclusions.classify` cannot resolve to a
   pattern or a joint.

What it **flags** on the row instead of refusing: an exercise that was not in
the prescribed workout (a substitution), an exercise under an active exclusion,
a performed workout with no prescribed counterpart, and a load that moved
further than the recorded history explains.

**The writer.** One transaction: the workout, its blocks, its exercises, and the
exclusion if there is one — or nothing. An interrupted write leaves no half
workout, which is the guarantee ticket 04's interactive command depends on.

**The renderer.** ASCII only. What was prescribed set against what was
performed, the deviations named, the flags, and the provenance of anything that
was assumed rather than said — so a reader can see at a glance which numbers the
user actually gave.

**Read first:** CONTEXT.md § What a report says (all four terms). ROADMAP.md §
Session 5, the note on the two validators. `plan.py` for the shape this mirrors.
`exclusions.py` for `classify`. CLAUDE.md § Standing rules — anything the CLI
prints is ASCII, and a missing precondition is a named state.

## Acceptance criteria

- [ ] `trainer log --from FILE` writes a performed workout and renders prescribed against performed, with the deviations named.
- [ ] An exercise id the catalog does not have is refused, naming the id.
- [ ] A performed exercise under an active exclusion is **written**, and the render says so. It is not refused.
- [ ] A performed workout with no prescribed counterpart is written, and every value in it carries a provenance of `reported` or `asked` — never `assumed`, because there was nothing to assume against.
- [ ] Unmentioned items of a prescribed workout come back as performed with provenance `assumed`.
- [ ] A proposed exclusion naming something that is neither a pattern nor a joint is refused, with the two granularities listed.
- [ ] A file that is not a performed workout fails as a shape error naming the field it choked on, never as a traceback.
- [ ] A write that fails partway leaves the database exactly as it was — asserted by injecting a failure between the workout row and its children.
- [ ] Against a database with no catalog, the answer names that state and the command that fixes it.
- [ ] The rendered output is ASCII.
