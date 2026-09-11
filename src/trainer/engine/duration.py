"""How long a plan takes.

A plan is a sequence of **blocks**. A block is one or more exercises performed
for a number of rounds, with the rest taken **after each round**; it costs

    setup(every exercise in it, once) + rounds x (sum of work + rest)

Straight sets are the block holding one exercise, a superset holds two, a
triset three, a circuit as many as it has -- so there is one formula and no
branch on what kind of block this is. ADR-0002 carries why the flat list this
replaced was not merely less expressive but wrong: costed as two adjacent
entries, a superset comes out several minutes long, and the number looks
exactly like every other number this module produces.

**Rest is prescribed, not derived.** It is a field on the block, put there by
whoever planned the workout. TRAINER.md's three bands survive below as
`reference_rest`, which a planner may consult and which nothing in the costing
path calls -- a deliberately short rest is legitimate training, and an engine
that overrode it would be deciding method. ADR-0001.

What this module does is cost a plan. It has no opinion about whether the plan
is a good one.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine.enrichment import MOVEMENT_PATTERNS

SECONDS_PER_REP = 3
"""`work ~ reps x 3s`, TRAINER.md's own approximation. One number for every
exercise on purpose: a per-exercise tempo is a second enrichment field, and
the error it would remove is smaller than the rest interval it sits inside."""

SECONDS_PER_MINUTE = 60

UNENRICHED_MESSAGE = "run `trainer enrich derive` first"
"""The remedy, appended to whichever row could not be costed. A missing
precondition is reported as a state and named with its fix, never left to
look like a caller's typo."""


class DurationError(RuntimeError):
    """A plan this cannot be honest about: an exercise the catalog does not
    have, one nothing has enriched yet, or an exercise listed twice.

    Never a fallback value. A default here would be a workout quietly costed
    at a number nobody decided, and then spent as if it were measured.
    """


@dataclass(frozen=True)
class BlockItem:
    """One exercise inside a block, and how it is prescribed.

    Either a number of reps or a duration in seconds, never both and never
    neither: a light walk, a carry or a sled push is prescribed in time, and
    *"3 rounds of 10 reps of walking"* means nothing. Rest is not here -- it
    belongs to the block, because it is taken after the round rather than
    after each exercise, which is the whole difference between a superset and
    two exercises that happen to be adjacent.
    """

    exercise_id: str
    reps: int | None = None
    seconds: int | None = None

    def __post_init__(self) -> None:
        if (self.reps is None) == (self.seconds is None):
            raise ValueError(
                f"{self.exercise_id!r}: prescribe either reps or seconds, not "
                f"both and not neither"
            )
        # Zero is not a prescription, it is one that was removed, and a
        # negative count would subtract time from the workout -- an item that
        # makes the plan look shorter is the exact shape of the fault this
        # module exists to prevent.
        if self.reps is not None and self.reps < 1:
            raise ValueError(f"reps must be at least 1, got {self.reps}")
        if self.seconds is not None and self.seconds < 1:
            raise ValueError(f"seconds must be at least 1, got {self.seconds}")

    @property
    def work_seconds(self) -> int:
        """How long this exercise is worked for, in one round."""
        if self.seconds is not None:
            return self.seconds
        assert self.reps is not None  # __post_init__ leaves no third case
        return self.reps * SECONDS_PER_REP


@dataclass(frozen=True)
class Block:
    """One or more exercises, a number of rounds, and the rest after each.

    One exercise is straight sets, two a superset, three a triset, more a
    circuit. Nothing here records which of those it is: the name is how people
    talk about the shape, and the shape is already fully described by how many
    exercises the block holds.
    """

    items: tuple[BlockItem, ...]
    rounds: int
    rest: int
    """Seconds rested after each round -- **prescribed**, not derived. Zero is
    a legitimate prescription, which is why it is not treated as missing."""

    def __post_init__(self) -> None:
        # Materialised before anything looks at it, for the reason
        # `plan_seconds` materialises the plan: `items` is walked three times
        # -- by `check_plan`, by `_setup_costs` and by the sum -- and a
        # generator would be empty after the first, costing the block at its
        # rest alone. `not self.items` is also true of an empty generator, so
        # even the guard below would wave it through. A list would pass every
        # check here and then make this frozen dataclass unhashable.
        object.__setattr__(self, "items", tuple(self.items))
        if not self.items:
            raise ValueError("a block holds at least one exercise")
        if self.rounds < 1:
            raise ValueError(f"rounds must be at least 1, got {self.rounds}")
        if self.rest < 0:
            raise ValueError(f"rest cannot be negative, got {self.rest}")

    @property
    def round_seconds(self) -> int:
        """One pass through every exercise, plus the rest after it.

        Every round is charged its rest, the last one included. Between
        blocks that rest is real -- nobody goes from their final squat
        straight into the next exercise -- so the only interval this
        overcounts is the one after the very last round of the very last
        block, at most three minutes on a whole plan. Deliberate, and in the
        safe direction: this number decides whether a plan fits a declared
        budget, and the failure this project refuses is saying it fits when
        it does not. See ADR-0002.
        """
        return sum(item.work_seconds for item in self.items) + self.rest


Plan = Sequence[Block]
"""An ordered sequence of blocks -- the vocabulary the rest of this session
builds on. Ordered because a workout is performed in an order, even though the
total itself does not depend on it.

`remaining_budget` takes one, and an agent emitting a workout in session 4 is
emitting exactly this. An exercise appears **at most once** across the whole
plan -- see `check_plan`.
"""


def check_plan(plan: Plan) -> None:
    """An exercise appears at most once in a plan.

    A workout has one line per exercise: three rounds of five and two of
    twelve on the same bar is one entry whose prescription differs, not two
    entries, and the bar is not re-loaded in between. Allowing the duplicate
    would make `setup_cost_min` ambiguous -- charged once, it undercounts the
    exercise that genuinely returns later; charged twice, it overcounts the
    back-off set that never left -- and nothing in the plan tells those two
    apart. Refusing the shape removes the question instead of answering it
    wrongly in one of the two directions.

    The rule spans the plan rather than the block: the ambiguity is about the
    bar, and the bar does not care which block the second entry sits in.

    The cost of the rule, named because it is real: ramp-up sets on the same
    lift cannot be written as a light block followed by a working block. The
    warm-up this session's timed work exists for is a different exercise --
    external rotations, a light walk -- so it is unaffected, and the rule was
    kept knowingly when this came up. ADR-0002.

    Public, and separate from `plan_seconds`, because it is an invariant of
    the vocabulary rather than of the sum: whoever assembles a plan can ask
    for it without costing anything.
    """
    seen: set[str] = set()
    for block in plan:
        for item in block.items:
            if item.exercise_id in seen:
                raise DurationError(
                    f"{item.exercise_id!r} appears more than once in the plan; "
                    "an exercise is one line of a workout -- give it one block "
                    "with the rounds and reps it needs, rather than two"
                )
            seen.add(item.exercise_id)


def plan_seconds(connection: sqlite3.Connection, plan: Plan) -> int:
    """The exact total, in seconds.

    Whole seconds all the way through, so the sum is exact and no block
    contributes a rounding error of its own; `plan_duration` converts once, at
    the end.

    The plan is resolved before any of it is counted: a block naming an
    exercise that cannot be costed fails the whole call rather than being
    skipped, because a total missing one exercise is smaller than the truth
    and looks exactly like a total that is not.
    """
    # Materialised before anything reads it. The plan is walked twice -- once
    # to resolve the ids, once to sum -- and a caller passing a generator
    # would have it exhausted by the first pass and counted as empty by the
    # second. That failure returns 0 and raises nothing, which is this
    # module's one forbidden direction wearing its most convincing disguise.
    plan = tuple(plan)
    check_plan(plan)
    setup = _setup_costs(connection, plan)

    total = 0
    for block in plan:
        # Setup sits outside the `rounds x` term: each bar in the block is
        # loaded once, not once per round. `check_plan` has already made
        # "once per block" and "once per exercise in the plan" the same
        # sentence, so there is nothing left for this line to decide.
        total += sum(setup[item.exercise_id] for item in block.items) * SECONDS_PER_MINUTE
        total += block.rounds * block.round_seconds
    return total


def plan_duration(connection: sqlite3.Connection, plan: Plan) -> int:
    """How long this plan takes, in whole minutes, rounded up.

    Minutes because that is what a budget is spoken in, everywhere from
    `setup_cost_min` to *"I have 40 minutes"*. Up rather than to-nearest
    because the half minute that rounding away would drop is real time the
    workout still takes, and this number's one job is to never say something
    fits when it does not.
    """
    return math.ceil(plan_seconds(connection, plan) / SECONDS_PER_MINUTE)


def _setup_costs(connection: sqlite3.Connection, plan: Plan) -> dict[str, int]:
    """`setup_cost_min` for every id the plan names, in one query rather than
    one lookup per exercise."""
    wanted = sorted({item.exercise_id for block in plan for item in block.items})
    if not wanted:
        return {}

    placeholders = ",".join("?" for _ in wanted)
    rows = connection.execute(
        f"SELECT id, setup_cost_min, movement_pattern FROM exercises "
        f"WHERE id IN ({placeholders})",
        wanted,
    ).fetchall()
    found = {str(row["id"]): row for row in rows}

    costs: dict[str, int] = {}
    for exercise_id in wanted:
        row = found.get(exercise_id)
        if row is None:
            raise DurationError(f"no such exercise: {exercise_id!r}")
        # `setup_cost_min` is what costing actually reads; `movement_pattern`
        # is checked beside it because enrichment writes the two together, so
        # a row holding one without the other is a state that should not
        # exist. Naming it is cheaper than costing the row at a number that
        # came from neither the catalog nor a rule.
        if row["setup_cost_min"] is None or row["movement_pattern"] is None:
            raise DurationError(
                f"{exercise_id!r} is not enriched, so it cannot be costed; "
                f"{UNENRICHED_MESSAGE}"
            )
        costs[exercise_id] = int(row["setup_cost_min"])
    return costs


# --- the reference bands -------------------------------------------------
#
# Everything below this line is a reference for whoever plans a workout.
# Nothing above it calls any of it, and a test enforces that: rest reaches the
# costing path as a prescription on the block, never as a value this module
# picked. ADR-0001.

ISOLATION_PATTERN = "isolation"
"""The one `movement_pattern` whose reference rest does not depend on reps."""

STRENGTH_REP_CEILING = 6
"""At or below this, a set is strength work; above it, hypertrophy. Six is the
conventional boundary in the literature, not a number chosen for this module."""

REST_SECONDS = {
    "strength": 180,
    "hypertrophy": 120,
    "isolation": 60,
}
"""The top of each band TRAINER.md gives -- strength 2.5-3 min, hypertrophy
90-120 s, isolation 60 s. The top rather than the middle because a planner
reaching for a default should reach for the conservative one; a planner who
means something shorter prescribes it.

Keyed by band and not by pattern: `reference_rest` is what maps a pattern and
a rep count onto one of these three."""

_KNOWN_PATTERNS = frozenset(MOVEMENT_PATTERNS)
"""The twelve values `movement_pattern` can hold, taken from where the
vocabulary is already defined rather than restated here -- a second copy is a
second thing to keep in step, and the one hand-copied vocabulary in this
project was wrong in three places. Not read from the table: this guards a
value the caller passed in, and a catalog nobody has enriched holds no
patterns at all, which would turn every call into a rejection."""


def reference_rest(movement_pattern: str, reps: int) -> int:
    """What TRAINER.md suggests resting between rounds of this kind.

    A **reference**, offered to whoever is planning. The engine never calls it
    to cost anything: the rest that counts is the one prescribed on the block.

    Isolation first, and unconditionally: TRAINER.md gives it a single value
    rather than a range because isolation work does not vary by load the way a
    compound lift does, so a low-rep set of curls still suggests 60 s.
    """
    if movement_pattern == ISOLATION_PATTERN:
        # The band, spelled out. The two strings match today by coincidence:
        # one is a value the catalog holds, the other names a rest interval.
        return REST_SECONDS["isolation"]
    if movement_pattern not in _KNOWN_PATTERNS:
        raise DurationError(f"not a movement pattern: {movement_pattern!r}")
    band = "strength" if reps <= STRENGTH_REP_CEILING else "hypertrophy"
    return REST_SECONDS[band]
