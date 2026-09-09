"""Ticket 05's schema: `profile`, `pattern_state` and `exclusions`.

Nothing here exercises `admissible_set` -- that is `test_admissible.py`'s
job. This only holds the shape everything else in the ticket depends on:
the singleton profile, the per-pattern state, and the closed vocabulary and
required re-test date on every exclusion.

`pattern_state` was a table when this was written and is a view as of
migration 0007. What it answers is `test_state.py`'s subject; what is left
here is that it is a view at all, and that nothing can write to it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import database, migrations


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        yield opened


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def view_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
    return {row["name"] for row in rows}


def test_the_two_tables_exist(connection: sqlite3.Connection) -> None:
    present = table_names(connection)
    assert {"profile", "exclusions"} <= present


# --- profile: one row, always -----------------------------------------


def test_profile_is_seeded_with_one_empty_row(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT * FROM profile").fetchall()
    (row,) = rows
    assert row["id"] == 1
    assert row["primary_goal"] is None
    assert row["base_equipment"] == "[]"
    assert row["permanent_constraints"] == "[]"


def test_a_second_profile_row_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO profile (id) VALUES (2)")


def test_profile_equipment_and_constraints_must_be_json_arrays(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE profile SET base_equipment = '\"dumbbell\"' WHERE id = 1"
        )  # a bare string is valid JSON but not an array


def test_profile_can_be_updated(connection: sqlite3.Connection) -> None:
    connection.execute(
        "UPDATE profile SET primary_goal = 'strength', "
        "base_equipment = '[\"dumbbell\", \"bands\"]' WHERE id = 1"
    )

    row = connection.execute("SELECT * FROM profile").fetchone()
    assert row["primary_goal"] == "strength"
    assert row["base_equipment"] == '["dumbbell", "bands"]'


# --- pattern_state: a view over the performed workouts ------------------


def test_pattern_state_is_a_view(connection: sqlite3.Connection) -> None:
    """A stored aggregate cannot answer for a window of cycles, and would go
    silently wrong the moment `cycle_length` was edited in a file nothing in
    the engine watches (ROADMAP.md, session 5)."""
    assert "pattern_state" in view_names(connection)
    assert "pattern_state" not in table_names(connection)


def test_the_muscle_axis_has_its_counterpart(connection: sqlite3.Connection) -> None:
    """ADR-0001 counts the deficit on two axes, and neither catches the
    other's degeneration."""
    assert {"pattern_state", "muscle_state"} <= view_names(connection)


def test_pattern_state_starts_empty(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT COUNT(*) AS total FROM pattern_state").fetchone()
    assert row["total"] == 0


def test_nothing_can_be_written_to_it(connection: sqlite3.Connection) -> None:
    """Which is the point of a view: there is one place a round is recorded --
    `workout_blocks` -- and no second one that could disagree with it."""
    with pytest.raises(sqlite3.OperationalError, match="view"):
        connection.execute(
            "INSERT INTO pattern_state (movement_pattern, rounds) VALUES ('hip hinge', 12)"
        )


# --- exclusions: closed vocabulary, mandatory re-test date --------------


def test_exclusions_starts_empty(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT COUNT(*) AS total FROM exclusions").fetchone()
    assert row["total"] == 0


def test_a_pattern_exclusion_can_be_inserted(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO exclusions (granularity, value, retest_date) "
        "VALUES ('pattern', 'vertical push', '2026-10-01')"
    )

    row = connection.execute("SELECT * FROM exclusions").fetchone()
    assert row["granularity"] == "pattern"
    assert row["value"] == "vertical push"
    assert row["retest_date"] == "2026-10-01"


def test_a_joint_exclusion_can_be_inserted(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO exclusions (granularity, value, retest_date) "
        "VALUES ('joint', 'shoulder', '2026-10-01')"
    )  # does not raise


def test_a_third_granularity_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO exclusions (granularity, value, retest_date) "
            "VALUES ('exercise', 'Barbell_Deadlift', '2026-10-01')"
        )


def test_a_missing_retest_date_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO exclusions (granularity, value) VALUES ('pattern', 'vertical push')"
        )
