"""How long a selection actually takes.

TRAINER.md's own formula, executed: `sum [ setup + sets x (work + rest) ]`,
with `work = reps x 3s`, `setup` read once per item from the catalog's
`setup_cost_min`, and `rest` decided by the item rather than asked of anyone.

This is the first number in the project a person can be held to. Session 4's
agent cannot promise *"this fits in 40 minutes"* until something here can say
how long a list of exercises takes, and everything downstream in this session
-- the remaining budget, the cut -- is that same number spent twice.

**Rest is derived, never an input.** TRAINER.md gives three bands keyed off
the kind of set being performed; a knob asking the user for a rest value would
be a knob asking them to make the estimate the engine exists to make. So the
rule below has no gap and takes no new input: `isolation` rests 60 s, and
every other pattern falls on one side or the other of the conventional
strength/hypertrophy boundary at six reps.

**Every band is taken at its top.** This number is later spent by the cut to
decide whether a selection fits a declared budget, and undercounting rest
means the workout runs long *after* the system has said it fits -- which is
the failure this project keeps naming as the one to avoid. Picking the
conservative end of a range TRAINER.md already supplies is not the same move
as inventing a value: the range is sourced, only the end is chosen.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine.enrichment import MOVEMENT_PATTERNS

_KNOWN_PATTERNS = frozenset(MOVEMENT_PATTERNS)
"""The twelve values `movement_pattern` can hold, taken from where the
vocabulary is already defined rather than restated here -- a second copy is a
second thing to keep in step, and the one hand-copied vocabulary in this
project was wrong in three places. Not read from the table: this guards a
value the caller passed in, and a catalog nobody has enriched holds no
patterns at all, which would turn every call into a rejection."""

SECONDS_PER_REP = 3
"""`work ~ reps x 3s`, TRAINER.md's own approximation. One number for every
exercise on purpose: a per-exercise tempo is a second enrichment field, and
the error it would remove is smaller than the rest interval it sits inside."""

ISOLATION_PATTERN = "isolation"
"""The one `movement_pattern` value whose rest does not depend on reps."""

STRENGTH_REP_CEILING = 6
"""At or below this, a set is strength work; above it, hypertrophy. Six is
the conventional boundary in the literature session 7's methodology document
already leans on, not a number chosen for this module."""

REST_SECONDS = {
    "strength": 180,
    "hypertrophy": 120,
    "isolation": 60,
}
"""The top of each band TRAINER.md gives -- strength 2.5-3 min, hypertrophy
90-120 s, isolation 60 s. Keyed by band and not by pattern: `rest_seconds`
is what maps a pattern and a rep count onto one of these three."""

SECONDS_PER_MINUTE = 60

UNENRICHED_MESSAGE = "run `trainer enrich derive` first"
"""The remedy, appended to whichever row could not be costed. A missing
precondition is reported as a state and named with its fix, never left to
look like a caller's typo."""


class DurationError(RuntimeError):
    """A selection this cannot be honest about: an exercise the catalog does
    not have, or one nothing has enriched yet.

    Never a fallback rest value. A default here would be a workout quietly
    costed at a number nobody decided, and it would be spent as if it were
    measured.
    """


@dataclass(frozen=True)
class SelectionItem:
    """One line of a workout: this exercise, this many sets, this many reps.

    Deliberately three fields and no more. `role` -- primary or secondary --
    exists only for the cut in ticket 02 and has no meaning to duration, so
    it is not here; the ticket that needs it adds it.
    """

    exercise_id: str
    sets: int
    reps: int

    def __post_init__(self) -> None:
        # Zero sets is not an item, it is an item that was removed, and a
        # negative count would subtract time from the workout -- an item that
        # makes the plan look shorter is the exact shape of the fault this
        # module exists to prevent.
        if self.sets < 1:
            raise ValueError(f"sets must be at least 1, got {self.sets}")
        if self.reps < 1:
            raise ValueError(f"reps must be at least 1, got {self.reps}")


Selection = Sequence[SelectionItem]
"""An ordered sequence of items -- the vocabulary the rest of this session
builds on. Ordered because a workout is performed in an order and the cut
reports what it dropped from where, even though the total itself does not
depend on it.

Later tickets in this session extend this shape rather than replacing it:
`remaining_budget` and `simulate_cut` both take a selection, and an agent
emitting `(id, sets, reps)` in session 4 is emitting exactly this.

An exercise appears **at most once** -- see `check_selection`.
"""


def check_selection(selection: Selection) -> None:
    """An exercise appears at most once in a selection.

    A workout has one line per exercise: three sets of five and two of twelve
    on the same bar is one entry whose sets differ, not two entries, and the
    bar is not re-loaded in between. Allowing the duplicate would make
    `setup_cost_min` ambiguous -- charged once, it undercounts the exercise
    that genuinely returns later; charged twice, it overcounts the back-off
    set that never left -- and there is no way to tell those two apart from
    `(id, sets, reps)`. Refusing the shape removes the question instead of
    answering it wrongly in one of the two directions.

    Public, and separate from `plan_seconds`, because it is an invariant of
    the vocabulary rather than of the sum: ticket 02's cut has to preserve
    it, and session 4's agent emits selections that have to satisfy it.
    """
    seen: set[str] = set()
    for item in selection:
        if item.exercise_id in seen:
            raise DurationError(
                f"{item.exercise_id!r} appears more than once in the selection; "
                "an exercise is one line of a workout -- change its sets or "
                "reps rather than listing it twice"
            )
        seen.add(item.exercise_id)


def rest_seconds(movement_pattern: str, reps: int) -> int:
    """How long is rested between sets of this kind.

    Isolation first, and unconditionally: TRAINER.md gives it a single value
    rather than a range because isolation work does not vary by load the way
    a compound lift does, so a low-rep set of curls still rests 60 s.
    """
    if movement_pattern == ISOLATION_PATTERN:
        # The band, spelled out, not `REST_SECONDS[ISOLATION_PATTERN]`. The
        # two strings match today by coincidence: one is a value the catalog
        # holds, the other is a name for a rest interval. Renaming the
        # catalog's vocabulary would turn that lookup into a KeyError raised
        # from inside `plan_seconds`, in a dict a rename of a pattern has no
        # reason to touch.
        return REST_SECONDS["isolation"]
    if movement_pattern not in _KNOWN_PATTERNS:
        raise DurationError(f"not a movement pattern: {movement_pattern!r}")
    band = "strength" if reps <= STRENGTH_REP_CEILING else "hypertrophy"
    return REST_SECONDS[band]


def plan_seconds(connection: sqlite3.Connection, selection: Selection) -> int:
    """The exact total, in seconds.

    Whole seconds all the way through, so the sum is exact and no item
    contributes a rounding error of its own; `plan_duration` converts once,
    at the end.

    The selection is resolved before any of it is counted: an item naming an
    exercise that cannot be costed fails the whole call rather than being
    skipped, because a total missing one exercise is smaller than the truth
    and looks exactly like a total that is not.
    """
    # Materialised before anything reads it. The selection is walked twice --
    # once to resolve the ids, once to sum -- and a caller passing a generator
    # would have it exhausted by the first pass and counted as empty by the
    # second. That failure returns 0 and raises nothing, which is this
    # module's one forbidden direction wearing its most convincing disguise.
    selection = tuple(selection)
    check_selection(selection)
    costs = _costs(connection, selection)

    total = 0
    for item in selection:
        setup, pattern = costs[item.exercise_id]
        work = item.reps * SECONDS_PER_REP
        try:
            rest = rest_seconds(pattern, item.reps)
        except DurationError as error:
            # `movement_pattern` carries no CHECK constraint, so a typo in a
            # hand-curated residue decision reaches here as a real value the
            # vocabulary does not have. Naming the row turns "find the bad
            # one among 876" into an id.
            raise DurationError(f"{item.exercise_id!r}: {error}") from error
        # `setup` sits outside the `sets x` term: the bar is loaded once for
        # the exercise, not once per set. `check_selection` has already made
        # "once per item" and "once per exercise in the selection" the same
        # sentence, so there is nothing left for this line to decide.
        total += setup * SECONDS_PER_MINUTE + item.sets * (work + rest)
    return total


def plan_duration(connection: sqlite3.Connection, selection: Selection) -> int:
    """How long this selection takes, in whole minutes, rounded up.

    Minutes because that is what a budget is spoken in, everywhere from
    `setup_cost_min` to *"I have 40 minutes"*. Up rather than to-nearest for
    the same reason every rest band is taken at its top: the half minute that
    rounding away would drop is real time the workout still takes, and this
    number's one job is to never say something fits when it does not.
    """
    return math.ceil(plan_seconds(connection, selection) / SECONDS_PER_MINUTE)


def _costs(
    connection: sqlite3.Connection, selection: Selection
) -> dict[str, tuple[int, str]]:
    """`setup_cost_min` and `movement_pattern` for every id the selection
    names, in one query rather than one lookup per item."""
    wanted = sorted({item.exercise_id for item in selection})
    if not wanted:
        return {}

    placeholders = ",".join("?" for _ in wanted)
    rows = connection.execute(
        f"SELECT id, setup_cost_min, movement_pattern FROM exercises "
        f"WHERE id IN ({placeholders})",
        wanted,
    ).fetchall()
    found = {str(row["id"]): row for row in rows}

    costs: dict[str, tuple[int, str]] = {}
    for exercise_id in wanted:
        row = found.get(exercise_id)
        if row is None:
            raise DurationError(f"no such exercise: {exercise_id!r}")
        # Enrichment writes the pattern and the setup cost together, so a row
        # holding one without the other is a state that should not exist.
        # Naming it is cheaper than costing the row at a number that came
        # from neither the catalog nor a rule.
        if row["movement_pattern"] is None or row["setup_cost_min"] is None:
            raise DurationError(
                f"{exercise_id!r} is not enriched, so it cannot be costed; "
                f"{UNENRICHED_MESSAGE}"
            )
        costs[exercise_id] = (int(row["setup_cost_min"]), str(row["movement_pattern"]))
    return costs


