"""`admissible_set`: the exercises today's equipment, the time available and
every exclusion leave standing. No LLM anywhere in this file -- every
property here is deterministic and checked against a small, hand-built
catalog rather than the real 876 rows.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import admissible, catalog, database, enrichment, graph, migrations, residue
from trainer.engine.catalog import Exercise
from trainer.engine.exclusions import Exclusion


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
)

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
                    _as_json(joints),
                    axial,
                    stability,
                    setup,
                    exercise_id,
                ),
            )
        yield opened


def _as_json(joints: str) -> str:
    return json.dumps([j.strip() for j in joints.split(",")])


def ids(exercises: tuple[Exercise, ...]) -> set[str]:
    return {e.id for e in exercises}


# --- equipment ---------------------------------------------------------


def test_only_the_named_equipment_appears(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(connection, [], ["barbell"], 10)

    assert ids(found) == {"Standing_Military_Press"}


def test_several_equipment_values_compose_as_or(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(connection, [], ["barbell", "dumbbell"], 10)

    assert ids(found) == {"Standing_Military_Press", "Dumbbell_Bicep_Curl"}


def test_absent_equipment_never_shows_up(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(connection, [], ["body only"], 10)

    assert "Standing_Military_Press" not in ids(found)
    assert "Dumbbell_Bicep_Curl" not in ids(found)


def test_an_unknown_equipment_value_is_rejected(connection: sqlite3.Connection) -> None:
    with pytest.raises(catalog.UnknownFilterValue):
        admissible.admissible_set(connection, [], ["dumbbells"], 10)


def test_equipment_must_name_at_least_one_value(connection: sqlite3.Connection) -> None:
    with pytest.raises(admissible.AdmissibleError):
        admissible.admissible_set(connection, [], [], 10)


# --- budget --------------------------------------------------------------


def test_setup_cost_over_budget_is_excluded(connection: sqlite3.Connection) -> None:
    """Standing_Military_Press costs 3 minutes to set up."""
    found = admissible.admissible_set(
        connection, [], ["barbell", "dumbbell", "body only"], 2
    )

    assert "Standing_Military_Press" not in ids(found)


def test_setup_cost_at_budget_is_included(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(
        connection, [], ["barbell", "dumbbell", "body only"], 3
    )

    assert "Standing_Military_Press" in ids(found)


# --- exclusions: pattern and joint ------------------------------------


def test_an_excluded_pattern_never_shows_up(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(
        connection,
        [Exclusion("pattern", "vertical push")],
        ["barbell", "dumbbell", "body only"],
        10,
    )

    assert "Standing_Military_Press" not in ids(found)
    assert ids(found) == {"Bodyweight_Squat", "Dumbbell_Bicep_Curl"}


def test_an_excluded_joint_never_shows_up(connection: sqlite3.Connection) -> None:
    """Standing_Military_Press loads shoulder and elbow; excluding shoulder
    also removes it, and Dumbbell_Bicep_Curl (elbow only) survives."""
    found = admissible.admissible_set(
        connection,
        [Exclusion("joint", "shoulder")],
        ["barbell", "dumbbell", "body only"],
        10,
    )

    assert "Standing_Military_Press" not in ids(found)
    assert "Dumbbell_Bicep_Curl" in ids(found)


def test_excluding_the_elbow_removes_every_row_that_loads_it(
    connection: sqlite3.Connection,
) -> None:
    found = admissible.admissible_set(
        connection,
        [Exclusion("joint", "elbow")],
        ["barbell", "dumbbell", "body only"],
        10,
    )

    assert ids(found) == {"Bodyweight_Squat"}


def test_pattern_and_joint_exclusions_compose(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(
        connection,
        [Exclusion("pattern", "squat"), Exclusion("joint", "elbow")],
        ["barbell", "dumbbell", "body only"],
        10,
    )

    assert found == ()


def test_an_unknown_excluded_pattern_is_rejected(connection: sqlite3.Connection) -> None:
    with pytest.raises(catalog.UnknownFilterValue):
        admissible.admissible_set(
            connection, [Exclusion("pattern", "nonsense")], ["barbell"], 10
        )


def test_an_unknown_excluded_joint_is_rejected(connection: sqlite3.Connection) -> None:
    with pytest.raises(admissible.AdmissibleError):
        admissible.admissible_set(
            connection, [Exclusion("joint", "nonsense")], ["barbell"], 10
        )


# --- preconditions --------------------------------------------------------


def test_against_an_empty_profile_it_answers_on_equipment_and_budget(
    connection: sqlite3.Connection,
) -> None:
    """No exclusions stored, nothing about the user known -- still answers."""
    found = admissible.admissible_set(connection, [], ["barbell"], 10)

    assert found != ()


def test_against_an_unenriched_catalog_it_names_the_state(database_file: Path) -> None:
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection)
        catalog.import_exercises(connection, CATALOG, allow_pruning=True)

        with pytest.raises(admissible.AdmissibleError, match="not enriched yet"):
            admissible.admissible_set(connection, [], ["barbell"], 10)


# --- ordering and shape -----------------------------------------------


def test_the_result_is_ordered_by_name_then_id(connection: sqlite3.Connection) -> None:
    found = admissible.admissible_set(
        connection, [], ["barbell", "dumbbell", "body only"], 10
    )

    names = [e.name for e in found]
    assert names == sorted(names)


def test_the_result_holds_whole_exercises(connection: sqlite3.Connection) -> None:
    (found,) = admissible.admissible_set(connection, [], ["barbell"], 10)

    assert found.id == "Standing_Military_Press"
    assert found.equipment == "barbell"


# --- against the real catalog ------------------------------------------


def test_against_the_real_enriched_catalog(database_file: Path) -> None:
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection)
        catalog.import_exercises(connection, catalog.load(), allow_pruning=True)
        enrichment.run(connection)
        residue.apply(connection, residue.load())
        graph.apply(connection, *graph.load())

        found = admissible.admissible_set(connection, [], ["body only"], 45)

        assert found
        assert all(e.equipment == "body only" for e in found)
        assert all(e.category == catalog.STRENGTH_CATEGORY for e in found)
