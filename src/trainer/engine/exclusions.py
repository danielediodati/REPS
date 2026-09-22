"""The exclusion state: two granularities, a re-test date, nothing else.

TRAINER.md's glossary is explicit that an exclusion is a hard engine
boundary reserved for safety -- a movement pattern, or everything loading a
named joint -- and that a preference is never allowed to enter through the
same door. This module is what makes that hard rather than merely
documented: `classify` only ever returns one of the two granularities or
refuses outright, and nothing here accepts an exercise id.

Triage is the one thing that will call `add` for real, once it exists. Until then, tests write rows directly to exercise the mechanism, and
`--exclude` on the CLI classifies an ad-hoc value for a single query without
persisting it -- a re-test date only means something for a decision meant to
outlive the command that made it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine import catalog

GRANULARITIES = ("pattern", "joint")


class ExclusionError(RuntimeError):
    """A value that names neither a pattern nor a joint -- an exercise id,
    a preference, or a plain typo. The caller cannot tell which, and it does
    not matter: none of the three is admissible here."""


@dataclass(frozen=True)
class Exclusion:
    """A pattern or a joint, kept out of the admissible set until its
    `retest_date` -- never an exercise id and never a third granularity."""

    granularity: str
    value: str


def classify(connection: sqlite3.Connection, value: str) -> Exclusion:
    """Decide which granularity `value` is, against the catalog's own
    vocabulary -- never a constant in this module, for the same reason
    `catalog.values` reads `movement_pattern` from the table rather than a
    copy of the twelve patterns.

    A movement pattern and a loaded joint are disjoint vocabularies in this
    catalog, so a value can never match both; if it matches neither, it is
    refused, exercise id or otherwise.
    """
    patterns = catalog.values(connection, "movement_pattern")
    joints = catalog.joint_values(connection)
    if value in patterns:
        return Exclusion("pattern", value)
    if value in joints:
        return Exclusion("joint", value)
    raise ExclusionError(
        f"{value!r} is not a movement pattern or a loaded joint -- "
        "an exclusion names one of the two, never an exercise id.\n"
        f"Movement patterns: {', '.join(patterns)}\n"
        f"Loaded joints: {', '.join(joints)}"
    )


def add(connection: sqlite3.Connection, exclusion: Exclusion, retest_date: str) -> None:
    """Persist one exclusion. `exclusion` is assumed already classified --
    `classify` is what a raw string has to pass through first."""
    if exclusion.granularity not in GRANULARITIES:
        raise ExclusionError(f"not a granularity: {exclusion.granularity!r}")
    connection.execute(
        "INSERT INTO exclusions (granularity, value, retest_date) VALUES (?, ?, ?)",
        (exclusion.granularity, exclusion.value, retest_date),
    )


def active(connection: sqlite3.Connection, today: str) -> tuple[Exclusion, ...]:
    """Every exclusion whose `retest_date` has not yet arrived, as of `today`
    (an ISO-8601 date, the same format the column stores).

    Once `today` reaches `retest_date` the row stops excluding -- TRAINER.md
    is explicit that a wall with no way back is the one failure this state
    cannot afford. The row itself is never deleted; this answers only whether
    it currently applies.
    """
    rows = connection.execute(
        "SELECT granularity, value FROM exclusions WHERE retest_date > ? "
        "ORDER BY granularity, value",
        (today,),
    )
    return tuple(Exclusion(row["granularity"], row["value"]) for row in rows)


def covering(
    connection: sqlite3.Connection,
    exclusions: Sequence[Exclusion],
    exercise_id: str,
) -> tuple[Exclusion, ...]:
    """Which of these exclusions reach this exercise, in the order given.

    The one definition of *an exclusion covers an exercise*, and there are two
    readers of it that ask for opposite reasons. `admissible.rejection`
    explains why a plan may not name it; session 5's report says it was
    performed anyway. Written twice, the day the two disagree is the day the
    engine forbids something on the way in that it does not flag on the way
    out -- and the flag is the row TRAINER.md's whole learning loop is built
    on.

    An exercise enrichment does not cover -- a stretch, a cardio row, a row
    read by hand and decided to have no honest pattern -- is covered by
    nothing. It has no pattern to match and no joints to load, which is a
    fact about the row rather than a failure to answer, so the empty tuple is
    the truthful answer and `catalog.enrichment`'s four states stay where
    they are worded.
    """
    try:
        profile = catalog.enrichment(connection, exercise_id)
    except catalog.CatalogError:
        return ()

    return tuple(
        exclusion
        for exclusion in exclusions
        if (exclusion.granularity == "pattern" and exclusion.value == profile.movement_pattern)
        or (exclusion.granularity == "joint" and exclusion.value in profile.loaded_joints)
    )
