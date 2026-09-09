"""Two questions the state cannot answer yet, and the shape of not answering.

`pattern_history` and `last_performed_load` are the two calls in TRAINER.md's
tool surface that read what the user has actually done. Today both answer
*«I don't know»*, because nothing writes what they read: `pattern_state` exists
and is empty, and migration 0006's `workouts` holds prescribed rows only --
nothing has been performed, and a load is something a report carries.

**Building them now, against nothing, is the point.** Session 4's agent calls
these mid-loop, inside its call budget, and session 5 is when real rows arrive.
An agent that gets an exception here cannot tell *«you asked something
malformed»* from *«nobody has trained this yet»*, and the second one is a fact
it is supposed to reason about -- an under-served pattern is a signal, not a
failure. So the answer is a value: `Answer.known` is False and the agent
carries on. A crash gives it nothing to carry.

**«I don't know» is not the same as «you asked wrongly».** An unknown movement
pattern, an exercise id the catalog does not have, a window of zero cycles --
all caller errors, all raised. The typed unknown covers exactly one case: the
question was well formed and the state has nothing recorded for it.

**No `if not rows`.** Each query below is written to return exactly one row
whatever the state holds, with a column saying whether anything was recorded.
An empty `pattern_state`, a pattern nobody has trained, and -- once session 5
writes rows -- a pattern with real history are three answers to the same query,
so session 5 changes what is written and changes nothing here.

**Volume has two axes and one of them has no table yet.** ADR-0001 counts the
deficit per movement pattern *and* per muscle, because neither catches the
other's degeneration: a leg workout of calf raises shows up on the pattern
axis, an arm workout of nothing but curls only shows up on the muscle one,
since biceps, triceps and forearms are all `isolation`. `pattern_state` is
keyed by `movement_pattern` and has no room for the second axis, so session 5
has a counterpart table to add. `_SOURCES` below is where it is added -- one
entry, not a second contract -- and until then asking for the muscle axis is a
named state rather than a fabricated unknown.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from trainer.engine import catalog
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

    Both payload fields are nullable on their own: a pattern can have volume
    counted against it before enough of it exists for a trend to mean
    anything. `Answer.known` is about whether the state has this key at all.

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
    renamed the column so it says the same thing."""
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


_SOURCES: dict[str, _Source] = {
    "pattern": _Source(
        table="pattern_state",
        key_column="movement_pattern",
        vocabulary=_patterns,
        # A catalog nobody has enriched holds no patterns, and every pattern
        # checked against that empty vocabulary would be refused as a typo.
        unenriched=UNENRICHED_MESSAGE,
    ),
    # "muscle": one more entry, once session 5 has built `pattern_state`'s
    # counterpart -- keyed by the catalog's own `primary_muscles`, whose
    # vocabulary is `catalog.values(connection, "primary_muscles")` and which
    # is populated by the import rather than by enrichment, so it is empty
    # only when the catalog is, which `_require_catalog` already names:
    # `unenriched=None`.
}

AXES = ("pattern", "muscle")
"""The two axes ADR-0001 counts the volume deficit on. Only the ones in
`_SOURCES` can be answered today; the rest are a named state, so the gap is
visible rather than looking like an axis nobody thought of."""


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


def volume_history(
    connection: sqlite3.Connection, axis: str, key: str, cycles: int
) -> Answer[VolumeHistory]:
    """What the state has recorded for one pattern or one muscle.

    `cycles` is the window the answer is about. It is validated and carried on
    the answer rather than narrowing the query, because `pattern_state` holds
    one aggregate row per key and has no cycle dimension to narrow over yet --
    session 5's rows are what will give it one. Fixing it in the signature now
    is the whole reason this function exists this early: the unit is the cycle,
    and no caller written against it has to change when the data arrives.
    """
    if cycles < 1:
        raise StateError(f"a window of {cycles} cycles asks about nothing")

    source = _source(axis)
    _require_catalog(connection)

    known_keys = source.vocabulary(connection)
    if not known_keys and source.unenriched is not None:
        raise StateError(source.unenriched)
    if key not in known_keys:
        raise StateError(
            f"no such {axis}: {key!r}; the catalog holds {', '.join(known_keys)}"
        )

    about = f"volume per {axis} for {key!r}, over the last {cycles} cycle(s)"

    # One row, always. `asked` is a one-row table the state is joined onto, so
    # an empty `pattern_state`, a key with no row, and a key with real history
    # are three shapes of the same answer rather than three code paths -- and
    # `recorded` says which, without anyone testing a result set for emptiness.
    row = connection.execute(
        f"SELECT recorded.{source.key_column} IS NOT NULL AS recorded, "  # from _SOURCES
        f"recorded.cycle_volume AS volume, recorded.load_trend AS load_trend "
        f"FROM (SELECT 1) AS asked "
        f"LEFT JOIN {source.table} AS recorded "  # from _SOURCES
        f"ON recorded.{source.key_column} = ?",  # from _SOURCES
        (key,),
    ).fetchone()

    if not row["recorded"]:
        return Answer(about, None)
    return Answer(
        about,
        VolumeHistory(
            axis=axis,
            key=key,
            cycles=cycles,
            volume=row["volume"],
            load_trend=row["load_trend"],
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


@dataclass(frozen=True)
class _LoadSource:
    """Where a performed load will be read from, once a report writes one.

    Named here rather than left implicit in a query, because the columns are a
    contract with a table that did not exist when this was written: session 5
    either uses these names or changes this one constant, and either way the
    expectation is written down instead of being discovered when the query
    fails.

    **It is about to change, and this is where.** Migration 0006 built
    `workouts` around the two states, and a load belongs to one exercise of
    one block -- so `load_kg` sits on `workout_exercises` and `performed_on`
    on `workouts`, which is two tables and not the one this shape assumes.
    Session 5's issue 03 is what rewrites it, against rows a report has
    actually produced; until then `_has_source` finds the columns missing and
    the answer stays the honest *«I don't know»* it has always been.
    """

    table: str = "workouts"
    key_column: str = "exercise_id"
    load_column: str = "load_kg"
    order_column: str = "performed_on"


LOAD_SOURCE = _LoadSource()


def _has_source(connection: sqlite3.Connection, source: _LoadSource) -> bool:
    """Whether the table exists and carries the columns this reads.

    Not a special case of emptiness: a table whose columns are not there is a
    different fact from a table with no matching row, and both are honestly
    *«I don't know»* to the caller. `workouts` exists as of migration 0006 and
    this still answers False, because the load moved to a child table -- see
    `_LoadSource`. Once issue 03 points the constant at the right columns, this
    stops being the branch taken and nothing else here changes.
    """
    present = {
        str(row["name"]) for row in connection.execute(f"PRAGMA table_info({source.table})")
    }
    return {source.key_column, source.load_column, source.order_column} <= present


def last_performed_load(
    connection: sqlite3.Connection, exercise_id: str
) -> Answer[float]:
    """The load this exercise was last performed with, if it ever was.

    An exercise id the catalog does not have is a **caller error** and is
    raised: the typed unknown means *«no load has been recorded for this valid
    exercise»*, and letting a bad id return it would turn a typo into a silent
    *«you have never done this»*.
    """
    _require_catalog(connection)
    if catalog.exercise(connection, exercise_id) is None:
        raise StateError(
            f"no such exercise: {exercise_id!r}; ids come from the catalog "
            "(`trainer catalog --name ...`)"
        )

    about = f"the load last performed for {exercise_id!r}"
    if not _has_source(connection, LOAD_SOURCE):
        # There is nowhere a load could have been recorded yet. Session 5's
        # `workouts` is what creates it, and until then this is the same
        # answer as an exercise that table simply holds nothing for.
        return Answer(about, None)

    # One row, always: the scalar subquery yields NULL rather than no row when
    # nothing matches, so "never performed" and "performed" come back the same
    # shape and neither is detected by testing a result set for emptiness.
    row = connection.execute(
        f"SELECT (SELECT {LOAD_SOURCE.load_column} FROM {LOAD_SOURCE.table} "  # from LOAD_SOURCE
        f"WHERE {LOAD_SOURCE.key_column} = ? "
        f"AND {LOAD_SOURCE.load_column} IS NOT NULL "
        f"ORDER BY {LOAD_SOURCE.order_column} DESC LIMIT 1) AS load",
        (exercise_id,),
    ).fetchone()

    return Answer(about, None if row["load"] is None else float(row["load"]))
