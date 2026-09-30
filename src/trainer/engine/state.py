"""What the state can answer, now that there are rows in it.

`pattern_history` and `last_performed_load` were built against nothing, on
purpose: an agent that gets an exception where a fact should be cannot tell
*«you asked something malformed»* from *«nobody has trained this yet»*, and the
second one is a fact it is supposed to reason about. That contract does not
change here. What changes is the data: migration 0007 turned `pattern_state`
into a view over the performed workouts and gave the muscle axis its
counterpart, so the same questions now come back with numbers in them.

**«I don't know» is still not the same as «you asked wrongly».** An unknown
movement pattern, an exercise id the catalog does not have, a window of zero
cycles -- all caller errors, all raised. The typed unknown covers exactly one
case: the question was well formed and the state has nothing recorded for it
inside the window asked about.

**No `if not rows`.** Every question that has one answer is asked as an
aggregate with no `GROUP BY`, which returns exactly one row whatever the state
holds, with a column saying whether anything was recorded. An empty database, a
pattern nobody has trained and a pattern with real history are three answers to
the same query rather than three code paths.

**The window is a number of cycles, and a cycle is not a length of time.**
`cycle_length` is declared, and read on every call. Change it
from 4 to 3 and every window moves on the next read, with no migration and
nothing to recompute -- which is the whole reason `pattern_state` had to stop
being a stored aggregate. The window is drawn as a **date**: the day the oldest
performed workout inside it happened, so a prescribed workout nobody reported
falls inside it too and counts as the deficit it is. Fewer workouts performed
than the window asks for is not an error -- the window simply starts at the
beginning.

**Two axes, and one query.** ADR-0001 counts the deficit per movement pattern
*and* per muscle, because neither catches the other's degeneration: a leg
workout of calf raises shows up on the pattern axis, an arm workout of nothing
but curls only on the muscle one, since biceps, triceps and forearms are all
`isolation`. `_SOURCES` holds a table name and a key column per axis, and every
query below is written once and interpolated with them.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar

from trainer.engine import catalog, config
from trainer.engine.admissible import UNENRICHED_MESSAGE

NO_CATALOG_MESSAGE = "the catalog is empty; run `trainer db import` first"
"""A vocabulary read from an empty table is empty, and every value checked
against it looks like a typo. The state is named instead, with its remedy --
CLAUDE.md's standing rule, the one written after `catalog --equipment dumbbell`
rejected a correct value against a database nobody had imported into."""

T = TypeVar("T")


class StateError(RuntimeError):
    """The question itself cannot be asked: a pattern or an exercise that does
    not exist, an axis nothing counts yet, a window of no cycles.

    Never *«nothing is recorded»* -- that is an `Answer`, and conflating the
    two is what this module exists to prevent.

    Not raised for missing or unusable declarations. That is
    `config.ConfigError`, and it reaches the reader in its own wording rather
    than in a second phrasing of the same state invented here.
    """


@dataclass(frozen=True)
class Answer(Generic[T]):
    """What the state knows, or that it knows nothing.

    `about` carries the question in words so an unknown answer is still
    self-describing: an agent holding `Answer(about=..., value=None)` can say
    what it asked and got nothing for, which is the difference between a fact
    it can plan around and a hole in its context.
    """

    about: str
    value: T | None

    @property
    def known(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class VolumeHistory:
    """What one axis value has accumulated, over a window of cycles.

    `axis` and `key` travel with the numbers because the same type answers a
    question about a movement pattern and a question about a muscle, and an
    answer that does not say which it is can be filed under the wrong one.

    `load_trend` is nullable on its own: a pattern can have volume counted
    against it before enough of it exists for a trend to mean anything -- see
    `_load_trend`, which is where the rule is written down. `Answer.known` is
    about whether anything at all was performed for this key inside the window.

    There is no `pain` field, and migration 0006 dropped the column it read.
    ROADMAP.md § Declared deviations carries the reversal: a 0-10 scale is the
    `required_rom` failure applied to the most delicate thing the system
    touches, and pain's only structured outcome is an exclusion the user
    confirms -- which `exclusions` already holds.
    """

    axis: str
    key: str
    cycles: int
    volume: int | None
    """Volume per cycle -- one complete rotation through the workouts being
    trained, never a week. CONTEXT.md settled the denominator; migration 0005
    renamed the column so it says the same thing. Counted in **rounds
    performed**: every round counts whole to the exercise's movement pattern
    and whole to each of its primary muscles, and nothing is divided."""
    load_trend: str | None


@dataclass(frozen=True)
class _Source:
    """Where one axis's volume is recorded.

    A table name and a key column, not a query: the query is the same for
    every axis, and writing it once is what keeps the second axis from
    arriving as a second contract. `vocabulary` is what a key is checked
    against, read from the catalog rather than from a copy of it.
    """

    table: str
    key_column: str
    vocabulary: Callable[[sqlite3.Connection], tuple[str, ...]]
    unenriched: str | None
    """The state to report when the vocabulary comes back empty, or `None` if
    an empty vocabulary is not a distinguishable state for this axis."""


def _patterns(connection: sqlite3.Connection) -> tuple[str, ...]:
    return catalog.values(connection, "movement_pattern")


def _muscles(connection: sqlite3.Connection) -> tuple[str, ...]:
    return catalog.values(connection, "primary_muscles")


_SOURCES: dict[str, _Source] = {
    "pattern": _Source(
        table="pattern_state",
        key_column="movement_pattern",
        vocabulary=_patterns,
        # A catalog nobody has enriched holds no patterns, and every pattern
        # checked against that empty vocabulary would be refused as a typo.
        unenriched=UNENRICHED_MESSAGE,
    ),
    "muscle": _Source(
        table="muscle_state",
        key_column="muscle",
        vocabulary=_muscles,
        # `primary_muscles` comes from the import rather than from the
        # enrichment, so it is empty only when the catalog is -- which
        # `_require_catalog` already names, with its own remedy.
        unenriched=None,
    ),
}

AXES = ("pattern", "muscle")
"""The two axes ADR-0001 counts the volume deficit on. Both have a view to
read now; the tuple stays so that an axis nobody thought of is refused by name
rather than by a `KeyError`."""

LOAD_TREND_BAND = 0.025
"""How far the recorded loads have to move before the trend says so -- 2.5%,
either way.

The rule, not an opinion, for the reason session 2's definitions are
executable: a rule is checkable by anyone later. 2.5% is the smallest step
progression actually takes -- 2.5 kg on a 100 kg lift -- so anything at least
that big is a move and anything under it is the noise of a different bar, a
different day, or a number rounded when it was written down.
"""


def _require_catalog(connection: sqlite3.Connection) -> None:
    if catalog.count(connection) == 0:
        raise StateError(NO_CATALOG_MESSAGE)


def _source(axis: str) -> _Source:
    """The axis's source, or the state that it is not counted yet.

    This is also what makes the interpolation below safe: the table and column
    names reaching SQL come from this dict and never from a caller.
    """
    if axis in _SOURCES:
        return _SOURCES[axis]
    if axis in AXES:
        raise StateError(
            f"volume is not counted per {axis} yet; the axes with somewhere to "
            f"record them are {', '.join(sorted(_SOURCES))}"
        )
    raise StateError(f"not an axis: {axis!r}; volume is counted per {', '.join(AXES)}")


# -- where in the rotation, and how far back a window reaches ------------------


@dataclass(frozen=True)
class Rotation:
    """Where the training is in its cycle, derived rather than declared.

    A cycle advances when a workout is **performed**, never when a date passes
    (CONTEXT.md): a user who trains when they have time completes a rotation in
    a span no calendar decides, and a prescribed workout nobody reported did
    not move them along it.

    `cycle` and `position` describe the **next** workout, because that is the
    one anybody asks about: `trainer plan` needs to know which entry of the
    split it is planning, and after four performed workouts of a four-workout
    cycle the answer is the first of the next one.
    """

    performed: int
    cycle_length: int
    cycle: int
    position: int


def rotation(connection: sqlite3.Connection) -> Rotation:
    """How many workouts have been performed, and where that leaves the next.

    `cycle_length` is read from the declarations in force on every call, so a
    change is in the next answer.
    """
    length = config.load(connection).cycle_length
    row = connection.execute(
        "SELECT COUNT(*) AS performed FROM workouts WHERE state = 'performed'"
    ).fetchone()
    performed = int(row["performed"])
    return Rotation(
        performed=performed,
        cycle_length=length,
        cycle=performed // length + 1,
        position=performed % length + 1,
    )


@dataclass(frozen=True)
class Window:
    """The stretch of training a question is asked about.

    `start` is an ISO-8601 date, or `None` when fewer workouts have been
    performed than the window asks for -- in which case it reaches back to the
    beginning, which is the honest answer rather than an empty one.

    A **date** and not a count of rows, so that a prescribed workout nobody
    reported falls inside the window it was prescribed in: a skipped workout is
    one of the four mechanisms the volume deficit exists to absorb, and a
    window that could only see performed rows would be blind to exactly the
    case that matters. Its cost is that a day holding two workouts is not split
    down the middle: both are in.
    """

    cycles: int
    workouts: int
    start: str | None


def window(connection: sqlite3.Connection, cycles: int) -> Window:
    """The last `cycles` cycles, as a date to count from."""
    if cycles < 1:
        raise StateError(f"a window of {cycles} cycles asks about nothing")
    workouts = cycles * config.load(connection).cycle_length
    row = connection.execute(
        "SELECT performed_on FROM workouts WHERE state = 'performed' "
        "ORDER BY performed_on DESC, id DESC LIMIT 1 OFFSET ?",
        (workouts - 1,),
    ).fetchone()
    return Window(
        cycles=cycles,
        workouts=workouts,
        start=None if row is None else str(row["performed_on"]),
    )


_WITHIN = "(? IS NULL OR {column} >= ?)"
"""The window, as a predicate. `NULL` is *«everything there is»*, so a window
that reaches back further than the training goes needs no second query and no
branch -- it is the same SQL with a different parameter."""


def _bounds(covered: Window) -> tuple[str | None, str | None]:
    """The two parameters `_WITHIN` takes: the same date, asked about twice."""
    return covered.start, covered.start


# -- volume, per axis ---------------------------------------------------------


def volume_history(
    connection: sqlite3.Connection, axis: str, key: str, cycles: int
) -> Answer[VolumeHistory]:
    """What one pattern or one muscle has accumulated, over a window of cycles.

    The key is checked against the catalog's own vocabulary first and the
    window computed after, so a mistyped pattern is reported as a mistyped
    pattern even on a machine with nothing declared yet.
    """
    source = _source(axis)
    _require_catalog(connection)

    known_keys = source.vocabulary(connection)
    if not known_keys and source.unenriched is not None:
        raise StateError(source.unenriched)
    if key not in known_keys:
        raise StateError(
            f"no such {axis}: {key!r}; the catalog holds {', '.join(known_keys)}"
        )

    covered = window(connection, cycles)
    about = f"volume per {axis} for {key!r}, over the last {cycles} cycle(s)"

    # One row, always: an aggregate with no GROUP BY returns a row whatever the
    # state holds, and `recorded` is what says whether anything is behind it.
    row = connection.execute(
        f"SELECT COUNT(*) > 0 AS recorded, COALESCE(SUM(rounds), 0) AS volume "
        f"FROM {source.table} "  # from _SOURCES
        f"WHERE {source.key_column} = ? AND phase = 'performed' "  # from _SOURCES
        f"AND {_WITHIN.format(column='dated_on')}",
        (key, *_bounds(covered)),
    ).fetchone()

    if not row["recorded"]:
        return Answer(about, None)
    return Answer(
        about,
        VolumeHistory(
            axis=axis,
            key=key,
            cycles=cycles,
            volume=int(row["volume"]),
            load_trend=_load_trend(connection, source, key, covered),
        ),
    )


def pattern_history(
    connection: sqlite3.Connection, pattern: str, cycles: int
) -> Answer[VolumeHistory]:
    """TRAINER.md's `pattern_history(pattern, cycles)`, on the pattern axis.

    A named entry point rather than a wrapper worth inlining: it is the name
    the tool surface exposes, and the axis is not the agent's to pick when it
    is asking about a movement pattern.
    """
    return volume_history(connection, "pattern", pattern, cycles)


def _load_trend(
    connection: sqlite3.Connection, source: _Source, key: str, covered: Window
) -> str | None:
    """Which way the recorded loads have moved, by a written rule.

    The rule, in full:

    1. Take every load recorded against this key inside the window, and reduce
       each workout to **one** load per exercise -- the last one in it. A
       warm-up at 60 and a work set at 100 on the same day are one session's
       training, and read as two points they would say the loads doubled.
    2. Group what is left by exercise. An exercise lifted in fewer than two
       workouts says nothing about a direction and is dropped: a first entry
       has nothing to have moved from.
    3. For each of the rest, the change is the last load over the first, minus
       one -- a **ratio**, because 5 kg is a different thing on a curl and on a
       deadlift and averaging kilos across exercises would let the heaviest one
       decide the answer.
    4. The key's trend is the mean of those changes: `up` above
       `LOAD_TREND_BAND`, `down` below it, `flat` between.
    5. Nothing left to compare leaves the trend **unknown**, which is not
       `flat`. Bodyweight training records no load at all, and calling that
       *«steady»* would be an opinion about training nobody measured.

    A rule and not a stored judgement, for the reason session 2's definitions
    are executable: this one is checkable by anyone later, against the rows.
    """
    rows = connection.execute(
        f"SELECT exercise_id, workout_id, load_kg FROM {source.table} "  # from _SOURCES
        f"WHERE {source.key_column} = ? AND phase = 'performed' "  # from _SOURCES
        f"AND load_kg IS NOT NULL AND load_kg > 0 "
        f"AND {_WITHIN.format(column='dated_on')} "
        f"ORDER BY dated_on, workout_id, block_position, position",
        (key, *_bounds(covered)),
    ).fetchall()

    # Step 1, as a dict rather than as a GROUP BY: the rows arrive oldest
    # first and a workout's are contiguous, so the last write for a pair wins
    # and the insertion order is still the order they were trained in.
    per_workout: dict[tuple[str, int], float] = {}
    for row in rows:
        per_workout[(str(row["exercise_id"]), int(row["workout_id"]))] = float(
            row["load_kg"]
        )

    lifted: dict[str, list[float]] = {}
    for (exercise_id, _), load in per_workout.items():
        lifted.setdefault(exercise_id, []).append(load)

    changes = [loads[-1] / loads[0] - 1.0 for loads in lifted.values() if len(loads) > 1]
    if not changes:
        return None
    moved = sum(changes) / len(changes)
    if moved > LOAD_TREND_BAND:
        return "up"
    if moved < -LOAD_TREND_BAND:
        return "down"
    return "flat"


# -- the volume deficit -------------------------------------------------------


@dataclass(frozen=True)
class Deficit:
    """Planned against performed, for one key of one axis, over one window.

    One quantity absorbing four mechanisms (CONTEXT.md § Volume deficit): a
    substitution moves rounds onto another key, a cut for time takes rounds off
    a block, a shortened workout drops one, and a skipped workout leaves its
    whole prescription unanswered. All four arrive here as the same number, and
    which of them it was is not something the engine claims to know.

    Negative is training nobody planned, and it is left signed rather than
    clamped: an agent reading *«minus twelve rounds of isolation»* is reading
    the other half of the same fact.
    """

    axis: str
    key: str
    cycles: int
    planned: int
    performed: int

    @property
    def deficit(self) -> int:
        return self.planned - self.performed


def volume_deficit(
    connection: sqlite3.Connection, cycles: int
) -> tuple[Deficit, ...]:
    """The deficit on **both** axes, largest first.

    Both, in one call, because neither catches the other's degeneration and an
    answer that gave one of them would be read as the whole picture (ADR-0001).
    Ordered largest first **within each axis** and then concatenated, pattern
    before muscle: the two are not on one scale -- a round counts once per
    pattern and once per primary muscle -- and sorting them together would rank
    them against each other.

    Every key with anything planned or performed against it in the window is
    here; a key with neither is not a deficit, it is a movement this training
    has never touched, and the catalog holds hundreds of those.

    **A workout still to do is not a deficit.** A prescription that has been
    neither performed nor overtaken by a later workout is `outstanding`, and it
    is left out of both sides: `trainer plan` writes a prescribed row every
    time it runs, and counted here the planner would read its own last
    prescription as a shortfall and add volume to cover volume already
    scheduled. It joins the count the moment it becomes unreported, which is
    the same moment the unreported list starts naming it.
    """
    _require_catalog(connection)
    covered = window(connection, cycles)

    found: list[Deficit] = []
    for axis in AXES:
        source = _SOURCES[axis]
        rows = connection.execute(
            f"SELECT {source.key_column} AS key, "  # from _SOURCES
            f"COALESCE(SUM(CASE WHEN phase = 'prescribed' THEN rounds END), 0) AS planned, "
            f"COALESCE(SUM(CASE WHEN phase = 'performed' THEN rounds END), 0) AS performed "
            f"FROM {source.table} "  # from _SOURCES
            f"WHERE outstanding = 0 AND {_WITHIN.format(column='dated_on')} "
            f"GROUP BY {source.key_column} "  # from _SOURCES
            f"ORDER BY planned - performed DESC, key",
            _bounds(covered),
        ).fetchall()
        found.extend(
            Deficit(
                axis=axis,
                key=str(row["key"]),
                cycles=cycles,
                planned=int(row["planned"]),
                performed=int(row["performed"]),
            )
            for row in rows
        )
    return tuple(found)


# -- adherence, and the workouts nobody reported ------------------------------


@dataclass(frozen=True)
class Adherence:
    """What became of the workouts in the window, in three counts.

    Three and not a percentage: the numerator would have to decide what an
    unreported workout is worth, and CONTEXT.md is explicit that it is worth
    nothing and that nothing closes it automatically. The counts say what
    happened; whether four unreported workouts mean a holiday or a quit is the
    agent's reading, not the engine's.

    `unplanned` is training nobody prescribed, which is training all the same
    and is recorded like any other (CONTEXT.md § Workout).
    """

    cycles: int
    performed: int
    unreported: int
    unplanned: int


def adherence_history(
    connection: sqlite3.Connection, cycles: int
) -> Answer[Adherence]:
    """TRAINER.md's `adherence_history(cycles)`, over a window of cycles.

    Unknown when the window holds nothing at all -- neither a performed
    workout nor an unreported one. That is *«nobody has trained yet»*, which is
    a fact to plan around and not zero-percent adherence.
    """
    covered = window(connection, cycles)
    about = f"what became of the workouts of the last {cycles} cycle(s)"

    within = _WITHIN.format(column="performed_on")
    row = connection.execute(
        f"SELECT "
        f"(SELECT COUNT(*) FROM workouts WHERE state = 'performed' AND {within}) "
        f"AS performed, "
        f"(SELECT COUNT(*) FROM workouts WHERE state = 'performed' "
        f"AND prescribed_on IS NULL AND {within}) AS unplanned, "
        f"(SELECT COUNT(*) FROM unreported_workouts "
        f"WHERE {_WITHIN.format(column='prescribed_on')}) AS unreported",
        (*_bounds(covered), *_bounds(covered), *_bounds(covered)),
    ).fetchone()

    performed = int(row["performed"])
    unreported = int(row["unreported"])
    if performed == 0 and unreported == 0:
        return Answer(about, None)
    return Answer(
        about,
        Adherence(
            cycles=cycles,
            performed=performed,
            unreported=unreported,
            unplanned=int(row["unplanned"]),
        ),
    )


@dataclass(frozen=True)
class Unreported:
    """One prescribed workout that a later one has overtaken, with no report.

    A fact and nothing else. Whether to ask the user about it is the agent's
    call (CONTEXT.md § Unreported): a rule that asked every time would nag
    somebody who had a week of flu, and a rule that never asked would lose the
    one workout they meant to report.
    """

    workout_id: int
    prescribed_on: str
    days_ago: int


def unreported(connection: sqlite3.Connection, today: str) -> tuple[Unreported, ...]:
    """The prescribed workouts with no report, oldest first.

    `today` is supplied by the caller for the reason `exclusions.active` takes
    it: the engine does not read the clock, so a test can place a workout in
    any week it needs one in.

    It is parsed rather than compared as text, because `days_ago` is arithmetic
    on it -- so a date that is not one is a caller error stated in words, and
    not a `ValueError` about a string arriving at a door that has no clause for
    it.
    """
    try:
        now = date.fromisoformat(today)
    except ValueError as error:
        raise StateError(
            f"{today!r} is not a date; today is given as ISO-8601 (YYYY-MM-DD)"
        ) from error
    rows = connection.execute(
        "SELECT workout_id, prescribed_on FROM unreported_workouts "
        "ORDER BY prescribed_on, workout_id"
    ).fetchall()
    return tuple(
        Unreported(
            workout_id=int(row["workout_id"]),
            prescribed_on=str(row["prescribed_on"]),
            days_ago=(now - date.fromisoformat(str(row["prescribed_on"]))).days,
        )
        for row in rows
    )


# -- the load last performed --------------------------------------------------


@dataclass(frozen=True)
class _LoadSource:
    """Where a performed load is read from.

    Named here rather than left implicit in a query, because the columns are a
    contract with a view: migration 0007 either provides these names or this
    constant moves, and either way the expectation is written down instead of
    being discovered when the query fails.

    **It moved, and this is what changed.** It used to name `workouts`, from
    before migration 0006 built that table around the two states -- a load
    belongs to one exercise of one block, so `load_kg` sits on
    `workout_exercises` while the date sits on `workouts`, which is two tables
    and not the one this shape reads. `performed_loads` is the view that joins
    them and keeps only the rows a load could honestly come from: performed,
    and carrying a load.

    `tiebreak_column` is the second half of the ordering. Two workouts on one
    day are ordered by which was written second, so *the load this exercise was
    last performed with* is a fact rather than whichever row SQLite reached
    first.
    """

    table: str = "performed_loads"
    key_column: str = "exercise_id"
    load_column: str = "load_kg"
    order_column: str = "performed_on"
    tiebreak_column: str = "workout_id"


LOAD_SOURCE = _LoadSource()


def _has_source(connection: sqlite3.Connection, source: _LoadSource) -> bool:
    """Whether the table exists and carries the columns this reads.

    Not a special case of emptiness: a table whose columns are not there is a
    different fact from a table with no matching row, and both are honestly
    *«I don't know»* to the caller. It answers True from migration 0007 on,
    against a database that has been migrated -- which is every database
    `trainer` opens, since `cli._require_current_schema` refuses one that is
    behind. It stays because the answer it protects is *«nowhere a load could
    have been recorded»*, and that is worth one PRAGMA rather than a traceback
    about a view.
    """
    present = {
        str(row["name"]) for row in connection.execute(f"PRAGMA table_info({source.table})")
    }
    return {
        source.key_column,
        source.load_column,
        source.order_column,
        source.tiebreak_column,
    } <= present


def last_performed_load(
    connection: sqlite3.Connection, exercise_id: str
) -> Answer[float]:
    """The load this exercise was last performed with, if it ever was.

    An exercise id the catalog does not have is a **caller error** and is
    raised: the typed unknown means *«no load has been recorded for this valid
    exercise»*, and letting a bad id return it would turn a typo into a silent
    *«you have never done this»*.

    No window. *The last load* is the last one there is, however long ago:
    coming back after two months, what the bar had on it in June is the only
    number anybody has, and `log._loads_that_jumped` comparing against nothing
    would flag the return to training rather than the typo it exists to catch.
    """
    _require_catalog(connection)
    if catalog.exercise(connection, exercise_id) is None:
        raise StateError(
            f"no such exercise: {exercise_id!r}; ids come from the catalog "
            "(`trainer catalog --name ...`)"
        )

    about = f"the load last performed for {exercise_id!r}"
    if not _has_source(connection, LOAD_SOURCE):
        return Answer(about, None)

    # One row, always: the scalar subquery yields NULL rather than no row when
    # nothing matches, so "never performed" and "performed" come back the same
    # shape and neither is detected by testing a result set for emptiness.
    row = connection.execute(
        f"SELECT (SELECT {LOAD_SOURCE.load_column} FROM {LOAD_SOURCE.table} "  # from LOAD_SOURCE
        f"WHERE {LOAD_SOURCE.key_column} = ? "
        f"AND {LOAD_SOURCE.load_column} IS NOT NULL "
        f"ORDER BY {LOAD_SOURCE.order_column} DESC, "
        f"{LOAD_SOURCE.tiebreak_column} DESC LIMIT 1) AS load",
        (exercise_id,),
    ).fetchone()

    return Answer(about, None if row["load"] is None else float(row["load"]))
