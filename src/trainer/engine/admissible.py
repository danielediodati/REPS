"""The admissibility filter -- the sentence the rest of the architecture
rests on, per README: *"the analytic layer defines the space, the agent
moves inside it"*. `admissible_set` **is** that space. From session 4 on an
agent chooses inside what this function returns and cannot prescribe
outside it, not because it is told not to but because nothing outside the
returned set exists for it to choose.

A pure function over the catalog and a caller-supplied list of exclusions --
it never reads the `exclusions` table itself. `exclusions.active` reads that
table, filtered by the re-test date; composing the two is the caller's job,
so the function that decides admissibility never has an opinion about where
an exclusion came from or whether it has expired.

TRAINER.md's own `WHERE` is the shape this executes: the pattern half is a
native column, the joint half is a `NOT EXISTS` over `loaded_joints`'s own
`json_each` -- the same mechanism `catalog.exercises_without_joint` uses,
inlined here as one more condition on the one query rather than a separate
table-wide scan per excluded joint.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from trainer.engine import catalog
from trainer.engine.catalog import Exercise
from trainer.engine.exclusions import Exclusion

UNENRICHED_MESSAGE = "the catalog is not enriched yet; run `trainer enrich derive` first"
"""Ticket 01's own wording for this state, reused verbatim -- a second
phrasing of the same precondition would be a second thing to keep in sync."""


class AdmissibleError(RuntimeError):
    """A precondition `admissible_set` cannot proceed without."""


def admissible_set(
    connection: sqlite3.Connection,
    exclusions: Sequence[Exclusion],
    equipment: Sequence[str],
    budget: int,
) -> tuple[Exercise, ...]:
    """The exercises compatible with every exclusion, today's equipment and
    the time available.

    `equipment` must name at least one value: an empty catalog of "what I
    can use today" is a different question (nothing is ever admissible) from
    one nobody asked, and conflating the two would make a caller's bug look
    like a legitimate, if severe, answer.
    """
    if not catalog.values(connection, "movement_pattern"):
        raise AdmissibleError(UNENRICHED_MESSAGE)
    if not equipment:
        raise AdmissibleError("equipment must name at least one value")

    for item in equipment:
        catalog.check_value(connection, "equipment", item)
    for exclusion in exclusions:
        _check_exclusion(connection, exclusion)

    excluded_patterns = sorted({e.value for e in exclusions if e.granularity == "pattern"})
    excluded_joints = sorted({e.value for e in exclusions if e.granularity == "joint"})

    conditions = [
        "movement_pattern IS NOT NULL",
        "setup_cost_min <= ?",
        f"equipment IN ({_placeholders(equipment)})",
    ]
    parameters: list[object] = [budget, *equipment]

    if excluded_patterns:
        conditions.append(f"movement_pattern NOT IN ({_placeholders(excluded_patterns)})")
        parameters.extend(excluded_patterns)

    # One `NOT EXISTS` per excluded joint, in the same query rather than a
    # table-wide `catalog.exercises_without_joint` scan per joint intersected
    # in Python afterwards -- the candidate rows are already narrowed by the
    # conditions above by the time this joins in, and SQLite does the set
    # arithmetic in one pass instead of several.
    for joint in excluded_joints:
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM json_each(exercises.loaded_joints) AS item "
            "WHERE item.value = ?)"
        )
        parameters.append(joint)

    rows = connection.execute(
        f"SELECT * FROM exercises WHERE {' AND '.join(conditions)} ORDER BY name, id",
        parameters,
    ).fetchall()
    return tuple(catalog.from_row(row) for row in rows)


def _placeholders(values: Sequence[str]) -> str:
    return ",".join("?" for _ in values)


def _check_exclusion(connection: sqlite3.Connection, exclusion: Exclusion) -> None:
    if exclusion.granularity == "pattern":
        catalog.check_value(connection, "movement_pattern", exclusion.value)
        return
    if exclusion.granularity == "joint":
        if exclusion.value not in catalog.joint_values(connection):
            raise AdmissibleError(f"no such joint: {exclusion.value!r}")
        return
    raise AdmissibleError(f"not a granularity: {exclusion.granularity!r}")
