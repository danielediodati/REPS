# 03 — What the state can now answer

**Status:** ready-for-agent

**Blocked by:** 01 (needs the tables). Independent of 02 — it reads rows and
does not care who wrote them, so its fixtures are inserted directly.

## What to build

The read side, against rows that finally exist. No model and no network, and
every one of these is covered by `pytest`.

**`pattern_state` stops being a table and becomes a view** over the performed
rows. Two reasons, both already written down. `pattern_history(pattern, cycles)`
takes a window of cycles and one aggregate row per pattern cannot answer for a
window — `state.volume_history`'s own docstring says session 5's rows are what
would give it the dimension it lacks. And `cycle_length` lives in a file the
user edits: change it from 4 to 3 and every historical cycle boundary moves,
which a view gets right on the next read and a stored aggregate gets silently
wrong forever, because nothing in the engine watches that file.

**The muscle axis gets its counterpart view**, and `state._SOURCES` gets the
second entry the module was written to receive. The commented-out block in
`state.py` says exactly what goes in it, down to the vocabulary callable and the
`unenriched=None`. One entry, not a second contract: `_SOURCES` holds a table
name and a key column, and a view drops into both without touching the query.

**Volume is rounds performed** (CONTEXT.md § Volume). Every round counts whole
to the exercise's movement pattern and whole to each of its primary muscles;
nothing is divided. A block of two exercises for four rounds is four rounds of
*each*, not two.

**The cycle index and the position in the rotation become derived** — performed
workouts in date order, `cycle_length` from the config. `--workout N` stops
being a flag nobody computes, which is exactly what ROADMAP.md § Session 4
reserved for this session.

**`load_trend` gets a written rule** over the recorded loads, not a stored
judgement. Same reason session 2's definitions are executable: a rule is
checkable by anyone later, an opinion is not. Write the rule down where a person
reads it, and let the view execute it.

**`pattern_history` and `last_performed_load` stop answering «I don't know»**
against real rows, and nothing else in their contract changes — that was the
whole point of building them early. `adherence_history(cycles)` arrives:
TRAINER.md's tool surface has it and `tools.py:30` says why it could not be
built before.

**The volume deficit as a single quantity**, on both axes (ADR-0001). It absorbs
substitution, a cut for time, a shortened workout and a skipped one into one
number.

**And the two read tools that do not exist yet**: a search from text to
candidate exercises over the catalog's own fields, and the prescribed workouts
with no report. The second one states a fact — *«there is a prescribed workout
from twelve days ago with no report»* — and decides nothing: whether to ask
about it is the agent's call, not a rule's.

**Read first:** `state.py` in full, including the commented `_SOURCES` entry and
the `_LoadSource` contract. CONTEXT.md § Volume, § Unreported, § Adherence.
ADR-0001 (two axes). ROADMAP.md § Session 5, the note on why `pattern_state`
had to stop being a table. TRAINER.md § The tool surface.

## Acceptance criteria

- [ ] `pattern_state` is a view, and every existing caller of it still passes unchanged.
- [ ] `state._SOURCES` has two entries and the query is still written once; asking for the muscle axis returns an answer instead of a named gap.
- [ ] `pattern_history(pattern, 3)` and `pattern_history(pattern, 1)` return different numbers against a fixture spanning several cycles — the window narrows the query for real.
- [ ] Changing `cycle_length` in the config changes what a window covers, with no migration and no recompute.
- [ ] A superset of two exercises for four rounds contributes four rounds to each exercise's pattern, and four to each of their primary muscles.
- [ ] An `unreported` prescribed workout contributes zero volume and is not counted as adherence.
- [ ] `adherence_history(cycles)` distinguishes performed, unreported, and never-prescribed workouts.
- [ ] The volume deficit is reported on both axes, and a leg workout of calf raises shows on the pattern axis while an arm workout of curls shows only on the muscle one.
- [ ] Catalog search returns candidates for a plain-language phrase and returns nothing rather than a guess when there is no match.
- [ ] The unreported-workouts tool states the fact and takes no action.
- [ ] `last_performed_load` reads the columns `state.LOAD_SOURCE` already names, or that constant changes and says why.
