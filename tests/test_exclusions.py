"""The exclusion state: classifying a value, persisting it, reading back
only what is still active."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, exclusions, migrations
from trainer.engine.catalog import Exercise
from trainer.engine.exclusions import Exclusion


def exercise(**overrides: object) -> Exercise:
    base: dict[str, object] = {
        "id": "Standing_Military_Press",
        "name": "Standing Military Press",
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


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(opened, (exercise(),), allow_pruning=True)
        opened.execute(
            "UPDATE exercises SET movement_pattern = 'vertical push', "
            "movement_pattern_source = 'rule', loaded_joints = '[\"shoulder\", \"elbow\"]', "
            "loaded_joints_source = 'rule' WHERE id = 'Standing_Military_Press'"
        )
        yield opened


# --- classify ------------------------------------------------------------


def test_a_real_pattern_classifies_as_a_pattern_exclusion(
    connection: sqlite3.Connection,
) -> None:
    assert exclusions.classify(connection, "vertical push") == Exclusion(
        "pattern", "vertical push"
    )


def test_a_real_joint_classifies_as_a_joint_exclusion(connection: sqlite3.Connection) -> None:
    assert exclusions.classify(connection, "shoulder") == Exclusion("joint", "shoulder")


def test_an_exercise_id_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(exclusions.ExclusionError):
        exclusions.classify(connection, "Standing_Military_Press")


def test_an_unknown_word_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(exclusions.ExclusionError):
        exclusions.classify(connection, "nonsense")


def test_a_preference_style_value_is_refused_like_anything_else(
    connection: sqlite3.Connection,
) -> None:
    """`classify` has no third granularity to sort a preference into -- it
    is refused the same way an exercise id is."""
    with pytest.raises(exclusions.ExclusionError):
        exclusions.classify(connection, "lunges")


def test_classify_against_an_unenriched_catalog_refuses_everything(
    database_file: Path,
) -> None:
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection)
        catalog.import_exercises(connection, (exercise(),), allow_pruning=True)

        with pytest.raises(exclusions.ExclusionError):
            exclusions.classify(connection, "vertical push")


# --- add / active ----------------------------------------------------------


def test_an_added_exclusion_is_active_before_its_retest_date(
    connection: sqlite3.Connection,
) -> None:
    exclusions.add(connection, Exclusion("pattern", "vertical push"), "2026-09-10")

    assert exclusions.active(connection, "2026-09-05") == (
        Exclusion("pattern", "vertical push"),
    )


def test_an_exclusion_stops_excluding_on_its_retest_date(
    connection: sqlite3.Connection,
) -> None:
    """The clock moves in the test, not the calendar."""
    exclusions.add(connection, Exclusion("pattern", "vertical push"), "2026-09-10")

    assert exclusions.active(connection, "2026-09-10") == ()
    assert exclusions.active(connection, "2026-09-11") == ()


def test_with_no_exclusions_stored_nothing_is_active(connection: sqlite3.Connection) -> None:
    assert exclusions.active(connection, "2026-09-05") == ()


def test_several_exclusions_all_come_back(connection: sqlite3.Connection) -> None:
    exclusions.add(connection, Exclusion("pattern", "vertical push"), "2026-09-10")
    exclusions.add(connection, Exclusion("joint", "shoulder"), "2026-09-10")

    active = exclusions.active(connection, "2026-09-01")

    assert set(active) == {
        Exclusion("pattern", "vertical push"),
        Exclusion("joint", "shoulder"),
    }


def test_add_refuses_a_bad_granularity(connection: sqlite3.Connection) -> None:
    with pytest.raises(exclusions.ExclusionError):
        exclusions.add(connection, Exclusion("exercise", "Standing_Military_Press"), "2026-09-10")


def test_a_bad_granularity_is_refused_at_the_database_too(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO exclusions (granularity, value, retest_date) "
            "VALUES ('exercise', 'Standing_Military_Press', '2026-09-10')"
        )
