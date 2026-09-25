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
from trainer.engine import exclusions as exclusion_state
from trainer.engine import muscle_groups
from trainer.engine.catalog import Exercise
from trainer.engine.exclusions import Exclusion

UNENRICHED_MESSAGE = "the catalog is not enriched yet; run `trainer enrich derive` first"
"""Ticket 01's own wording for this state, reused verbatim -- a second
phrasing of the same precondition would be a second thing to keep in sync."""


class AdmissibleError(RuntimeError):
    """A precondition `admissible_set` cannot proceed without."""


def muscles_of(groups: Sequence[str]) -> tuple[str, ...]:
    """The catalog's own muscles that a slot's groups and muscles cover.

    Read from the committed mapping rather than from a copy: the six names and
    the seventeen assignments live in `muscle-groups.md` and nowhere else.
    """
    try:
        return muscle_groups.committed().muscles_in(groups)
    except muscle_groups.MuscleGroupError as error:
        raise AdmissibleError(f"the muscle groups cannot be read: {error}") from error
    except ValueError as error:
        raise AdmissibleError(str(error)) from error


def admissible_set(
    connection: sqlite3.Connection,
    exclusions: Sequence[Exclusion],
    equipment: Sequence[str],
    budget: int,
    groups: Sequence[str] = (),
) -> tuple[Exercise, ...]:
    """The exercises compatible with every exclusion, today's equipment, the
    time available, and the muscle groups today's workout trains.

    `equipment` must name at least one value: an empty catalog of "what I
    can use today" is a different question (nothing is ever admissible) from
    one nobody asked, and conflating the two would make a caller's bug look
    like a legitimate, if severe, answer.

    `groups` is different: empty means *the whole space*, because a caller
    that has not said which workout this is has not narrowed anything. Given,
    it keeps the exercises whose **primary** muscles fall in those groups.
    Primary and not secondary, for the reason volume is counted on the
    primaries and time is allocated to the groups: a curl that happens to load
    the forearms is not a forearm exercise, and a leg day that admitted every
    lift with a leg somewhere in it would be the whole catalog again.

    This is a constraint and not a choice of method, which is what keeps it on
    the right side of ADR-0001: the split is declared by the user in
    `training.toml`, so *today trains legs and core* is a fact about today in
    the same way today's equipment is. What the engine still does not decide is
    which of the admissible exercises to prescribe, in what order, or for how
    long.
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

    # The same `json_each` mechanism the joints use, over `primary_muscles`:
    # keep the row if any of its primaries is a muscle today's groups cover.
    if groups:
        wanted = muscles_of(groups)
        conditions.append(
            f"EXISTS (SELECT 1 FROM json_each(exercises.primary_muscles) AS muscle "
            f"WHERE muscle.value IN ({_placeholders(wanted)}))"
        )
        parameters.extend(wanted)

    rows = connection.execute(
        f"SELECT * FROM exercises WHERE {' AND '.join(conditions)} ORDER BY name, id",
        parameters,
    ).fetchall()
    return tuple(catalog.from_row(row) for row in rows)


def rejection(
    connection: sqlite3.Connection,
    exercise_id: str,
    exclusions: Sequence[Exclusion],
    equipment: Sequence[str],
    budget: int,
    groups: Sequence[str] = (),
) -> str | None:
    """Why `admissible_set` left this exercise out, or `None` if it did not.

    The explanation, and only the explanation. `admissible_set` decides, and a
    caller asking *is this admissible* asks the set: two functions answering
    one question is one function too many, and the day they disagree a plan is
    checked against whichever of them is wrong. This is asked afterwards,
    about an id already known to be out.

    It lives here, beside the query it explains, for exactly that reason: the
    conditions it walks are the conditions in the `WHERE` above, and a filter
    added there without a clause here comes back as *not in the admissible
    set*, the sentence this function exists to replace. The two are the same
    set of conditions and deliberately not the same order -- reading them off
    in step is not what keeps them in step, the property test is.

    The user's own constraints come first, an exclusion they set and then the
    equipment they said they have, and the clock last. Several can be true at
    once; the first is the one reported, because a rejection is read to decide
    what to prescribe instead, not to enumerate what is wrong with a choice
    already discarded.
    """
    try:
        profile = catalog.enrichment(connection, exercise_id)
    except catalog.CatalogError as error:
        # Unknown id, a row outside what enrichment covers, a row decided to
        # have no honest pattern: three states with three different sentences,
        # and `catalog.enrichment` is where they are worded. Restating them
        # here would give the same state two phrasings that drift apart.
        return str(error)

    # `exclusions.covering` decides which of them reach this exercise; the
    # wording is this function's. Session 5 flags a performed exercise the same
    # way, and the two must never be able to disagree about what an exclusion
    # reaches -- only about what to say when it does.
    for exclusion in exclusion_state.covering(connection, exclusions, exercise_id):
        if exclusion.granularity == "pattern":
            return f"is a {exclusion.value} movement, which is excluded"
        return f"loads the {exclusion.value}, which is excluded"

    found = catalog.exercise(connection, exercise_id)
    assert found is not None  # `catalog.enrichment` above found the same row

    if groups and not set(found.primary_muscles) & set(muscles_of(groups)):
        trains = ", ".join(found.primary_muscles) or "nothing recorded"
        return (
            f"trains {trains}, and today's workout is {', '.join(groups)}"
        )

    if found.equipment is None:
        return "has no equipment recorded, so it matches nothing available today"
    if found.equipment not in equipment:
        return (
            f"needs {found.equipment}, and today's equipment is "
            f"{', '.join(equipment)}"
        )

    if profile.setup_cost_min > budget:
        return (
            f"costs {profile.setup_cost_min} min to set up, which is over the "
            f"{budget} min available"
        )
    return None


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
