"""`plan_duration`: how long a selection actually takes.

The first number in this project a person can be held to. No LLM and no
network anywhere in this file -- the formula is arithmetic over a small,
hand-built catalog, and every expectation below is written out in seconds
rather than asserted against a second implementation of the same sum.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, duration, migrations
from trainer.engine.catalog import Exercise
from trainer.engine.duration import SelectionItem
from trainer.engine.enrichment import MOVEMENT_PATTERNS


def exercise(**overrides: object) -> Exercise:
    base: dict[str, object] = {
        "id": "Some_Exercise",
        "name": "Some Exercise",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("shoulders",),
        "secondary_muscles": (),
        "instructions": (),
        "images": (),
    }
    base.update(overrides)
    return Exercise(**base)  # type: ignore[arg-type]


CATALOG = (
    exercise(
        id="Standing_Military_Press",
        name="Standing Military Press",
        equipment="barbell",
    ),
    exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        primary_muscles=("quadriceps",),
    ),
    exercise(
        id="Dumbbell_Bicep_Curl",
        name="Dumbbell Bicep Curl",
        equipment="dumbbell",
        primary_muscles=("biceps",),
    ),
    exercise(
        id="Spell_Caster",
        name="Spell Caster",
        equipment="dumbbell",
        primary_muscles=("abdominals",),
    ),
)

# id -> (movement_pattern, loaded_joints, axial, stability, setup_cost_min).
# `Spell_Caster` is absent on purpose: it is one of the rows the rules leave
# undecided, and it is what the unenriched error is tested against.
_PATTERNS = {
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
    "Dumbbell_Bicep_Curl": ("isolation", "elbow", "no", "medium", 1),
}


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(opened, CATALOG, allow_pruning=True)
        for exercise_id, (pattern, joints, axial, stability, setup) in _PATTERNS.items():
            opened.execute(
                "UPDATE exercises SET movement_pattern = ?, movement_pattern_source = 'rule', "
                "loaded_joints = ?, loaded_joints_source = 'rule', "
                "spinal_axial_load = ?, spinal_axial_load_source = 'rule', "
                "required_stability = ?, required_stability_source = 'rule', "
                "setup_cost_min = ?, setup_cost_min_source = 'rule' WHERE id = ?",
                (
                    pattern,
                    json.dumps([joint.strip() for joint in joints.split(",")]),
                    axial,
                    stability,
                    setup,
                    exercise_id,
                ),
            )
        yield opened


# --- the three rest buckets ----------------------------------------------


def test_a_low_rep_compound_rests_the_strength_bucket(
    connection: sqlite3.Connection,
) -> None:
    """5 reps on a vertical push: 180 s setup + 5 x (15 s work + 180 s rest)."""
    seconds = duration.plan_seconds(
        connection, [SelectionItem("Standing_Military_Press", sets=5, reps=5)]
    )

    assert seconds == 180 + 5 * (15 + 180)


def test_a_high_rep_compound_rests_the_hypertrophy_bucket(
    connection: sqlite3.Connection,
) -> None:
    """10 reps on a squat: no setup at all + 3 x (30 s work + 120 s rest)."""
    seconds = duration.plan_seconds(
        connection, [SelectionItem("Bodyweight_Squat", sets=3, reps=10)]
    )

    assert seconds == 0 + 3 * (30 + 120)


def test_isolation_rests_sixty_seconds_on_high_reps(
    connection: sqlite3.Connection,
) -> None:
    seconds = duration.plan_seconds(
        connection, [SelectionItem("Dumbbell_Bicep_Curl", sets=3, reps=15)]
    )

    assert seconds == 60 + 3 * (45 + 60)


def test_isolation_rests_sixty_seconds_on_low_reps_too(
    connection: sqlite3.Connection,
) -> None:
    """The reps bucket never reaches an isolation item: TRAINER.md gives it
    one value, not a range, so 5 reps of curls still rests 60 s and not 180."""
    seconds = duration.plan_seconds(
        connection, [SelectionItem("Dumbbell_Bicep_Curl", sets=3, reps=5)]
    )

    assert seconds == 60 + 3 * (15 + 60)


@pytest.mark.parametrize(
    ("reps", "rest"),
    [(1, 180), (5, 180), (6, 180), (7, 120), (8, 120), (20, 120)],
)
def test_six_is_the_strength_hypertrophy_boundary(reps: int, rest: int) -> None:
    assert duration.rest_seconds("vertical push", reps) == rest


def test_every_pattern_but_isolation_takes_the_reps_bucket() -> None:
    """No pattern falls through the rule: the twelve values the catalog can
    hold are covered, and none of them lands on a default nobody chose."""
    for pattern in MOVEMENT_PATTERNS:
        expected = 60 if pattern == "isolation" else 180
        assert duration.rest_seconds(pattern, 5) == expected


def test_the_rest_values_are_the_top_of_each_band() -> None:
    """TRAINER.md gives ranges; this picks the upper bound of each, so a
    selection that is reported to fit cannot then run long."""
    assert duration.REST_SECONDS == {
        "strength": 180,
        "hypertrophy": 120,
        "isolation": 60,
    }


# --- setup cost -----------------------------------------------------------


def test_setup_is_spent_once_per_item_not_once_per_set(
    connection: sqlite3.Connection,
) -> None:
    """Three sets of the military press pay its 3 minutes once, not nine."""
    seconds = duration.plan_seconds(
        connection, [SelectionItem("Standing_Military_Press", sets=3, reps=5)]
    )

    assert seconds == 180 + 3 * (15 + 180)
    assert seconds != 3 * 180 + 3 * (15 + 180)


def test_an_exercise_cannot_appear_twice_in_a_selection(
    connection: sqlite3.Connection,
) -> None:
    """One line per exercise. Two entries on the same bar leave `setup_cost_min`
    with no honest answer -- charged once it undercounts, charged twice it
    overcounts -- so the shape is refused rather than costed either way."""
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(
            connection,
            [
                SelectionItem("Standing_Military_Press", sets=3, reps=5),
                SelectionItem("Standing_Military_Press", sets=2, reps=12),
            ],
        )

    assert "Standing_Military_Press" in str(raised.value)


def test_the_uniqueness_rule_is_checkable_on_its_own(
    connection: sqlite3.Connection,
) -> None:
    """Ticket 02's cut has to preserve the invariant, so it can ask for it
    without computing a total."""
    fine = [
        SelectionItem("Standing_Military_Press", sets=3, reps=5),
        SelectionItem("Bodyweight_Squat", sets=3, reps=10),
    ]

    duration.check_selection(fine)

    with pytest.raises(duration.DurationError):
        duration.check_selection([*fine, SelectionItem("Bodyweight_Squat", sets=1, reps=5)])


# --- whole selections -----------------------------------------------------


def test_a_selection_spanning_several_exercises_sums_its_items(
    connection: sqlite3.Connection,
) -> None:
    selection = [
        SelectionItem("Standing_Military_Press", sets=4, reps=5),
        SelectionItem("Bodyweight_Squat", sets=3, reps=12),
        SelectionItem("Dumbbell_Bicep_Curl", sets=2, reps=12),
    ]

    seconds = duration.plan_seconds(connection, selection)

    assert seconds == 180 + 4 * (15 + 180) + 0 + 3 * (36 + 120) + 60 + 2 * (36 + 60)


def test_an_empty_selection_takes_no_time(connection: sqlite3.Connection) -> None:
    assert duration.plan_seconds(connection, []) == 0
    assert duration.plan_duration(connection, []) == 0


def test_plan_duration_reports_minutes(connection: sqlite3.Connection) -> None:
    selection = [SelectionItem("Bodyweight_Squat", sets=4, reps=10)]

    assert duration.plan_seconds(connection, selection) == 4 * (30 + 120)
    assert duration.plan_duration(connection, selection) == 10


def test_a_part_minute_rounds_up_rather_than_away(
    connection: sqlite3.Connection,
) -> None:
    """7.5 minutes is 8, not 7: a budget is spoken in whole minutes and the
    half that would be dropped is real time the workout still takes."""
    selection = [SelectionItem("Bodyweight_Squat", sets=3, reps=10)]

    assert duration.plan_seconds(connection, selection) == 450
    assert duration.plan_duration(connection, selection) == 8


def test_order_does_not_change_the_total(connection: sqlite3.Connection) -> None:
    first = SelectionItem("Standing_Military_Press", sets=4, reps=5)
    second = SelectionItem("Dumbbell_Bicep_Curl", sets=2, reps=12)

    assert duration.plan_seconds(connection, [first, second]) == duration.plan_seconds(
        connection, [second, first]
    )


# --- the states this refuses to guess at ----------------------------------


def test_an_unknown_exercise_id_is_named(connection: sqlite3.Connection) -> None:
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(connection, [SelectionItem("Nope", sets=3, reps=5)])

    assert "Nope" in str(raised.value)


def test_an_unenriched_exercise_is_a_state_not_a_default(
    connection: sqlite3.Connection,
) -> None:
    """No rest value is invented for a row whose pattern nobody decided --
    the error names the row and the command that fixes it."""
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(
            connection, [SelectionItem("Spell_Caster", sets=3, reps=5)]
        )

    assert "Spell_Caster" in str(raised.value)
    assert "enrich" in str(raised.value)


def test_a_selection_is_refused_whole(connection: sqlite3.Connection) -> None:
    """A partial total over the items that did resolve would be a number
    smaller than the truth, quietly."""
    with pytest.raises(duration.DurationError):
        duration.plan_seconds(
            connection,
            [
                SelectionItem("Bodyweight_Squat", sets=3, reps=10),
                SelectionItem("Nope", sets=3, reps=5),
            ],
        )


def test_rest_seconds_refuses_a_pattern_the_catalog_cannot_hold() -> None:
    with pytest.raises(duration.DurationError):
        duration.rest_seconds("interpretive dance", 5)


def test_a_pattern_outside_the_vocabulary_names_the_row_it_came_from(
    connection: sqlite3.Connection,
) -> None:
    """`movement_pattern` has no CHECK constraint, so a typo in a curated
    residue decision -- `hinge` for `hip hinge` -- arrives here as a real
    stored value. The error has to say which of the 876 rows holds it."""
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'hinge' WHERE id = ?",
        ("Bodyweight_Squat",),
    )

    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(
            connection, [SelectionItem("Bodyweight_Squat", sets=3, reps=5)]
        )

    assert "Bodyweight_Squat" in str(raised.value)
    assert "hinge" in str(raised.value)


def test_a_selection_that_can_only_be_walked_once_is_still_counted(
    connection: sqlite3.Connection,
) -> None:
    """The selection is walked twice -- once to resolve ids, once to sum.
    A generator would be empty by the second pass and cost 0, silently, in
    the one direction this number must never err in.

    `Selection` is a `Sequence`, so the annotation already forbids this and
    mypy stops it repo-wide; the ignore below is the point of the test. The
    guard is for the caller who is not type-checked -- an MCP client in
    ticket 05, decoding JSON into whatever it decodes into.
    """
    item = SelectionItem("Standing_Military_Press", sets=3, reps=5)

    once_only = (entry for entry in [item])

    assert duration.plan_seconds(
        connection, once_only  # type: ignore[arg-type]
    ) == duration.plan_seconds(connection, [item])


@pytest.mark.parametrize(("sets", "reps"), [(0, 5), (-1, 5), (3, 0), (3, -2)])
def test_a_selection_item_refuses_a_count_below_one(sets: int, reps: int) -> None:
    """Zero sets is not an item, it is an item that was removed, and a
    negative one would subtract time from the workout."""
    with pytest.raises(ValueError):
        SelectionItem("Bodyweight_Squat", sets=sets, reps=reps)
