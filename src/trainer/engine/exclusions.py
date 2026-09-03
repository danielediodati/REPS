"""The exclusion state: two granularities, a re-test date, nothing else.

TRAINER.md's glossary is explicit that an exclusion is a hard engine
boundary reserved for safety -- a movement pattern, or everything loading a
named joint -- and that a preference is never allowed to enter through the
same door. This module is what makes that hard rather than merely
documented: `classify` only ever returns one of the two granularities or
refuses outright, and nothing here accepts an exercise id.

Session 6's triage is the one thing that will call `add` for real, once it
exists. Until then, tests write rows directly to exercise the mechanism, and
`--exclude` on the CLI classifies an ad-hoc value for a single query without
persisting it -- a re-test date only means something for a decision meant to
outlive the command that made it.
"""

from __future__ import annotations

import sqlite3
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
    if value in catalog.values(connection, "movement_pattern"):
        return Exclusion("pattern", value)
    if value in catalog.joint_values(connection):
        return Exclusion("joint", value)
    raise ExclusionError(
        f"{value!r} is not a movement pattern or a loaded joint -- "
        "an exclusion names one of the two, never an exercise id"
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
    cannot afford. The row itself is never deleted: retiring the decision is
    session 6's business, this is only whether it currently applies.
    """
    rows = connection.execute(
        "SELECT granularity, value FROM exclusions WHERE retest_date > ? "
        "ORDER BY granularity, value",
        (today,),
    )
    return tuple(Exclusion(row["granularity"], row["value"]) for row in rows)
