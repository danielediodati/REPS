"""Where the rotation is, and which groups that makes today's.

No LLM and no network. The workouts are inserted directly: the rotation counts
performed rows and does not care who wrote them, and going through the writer
would fail twice for one bug.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import config, constraints, database, migrations

DECLARED = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
goal = "hypertrophy"
split = [["legs"], ["shoulders"]]
equipment = ["barbell"]
"""


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        yield opened


@pytest.fixture()
def declared(declared_training: Path) -> config.TrainingConfig:
    declared_training.write_text(DECLARED, encoding="utf-8")
    return config.load()


def performed(connection: sqlite3.Connection, on: str) -> None:
    connection.execute(
        "INSERT INTO workouts (state, performed_on, report) "
        "VALUES ('performed', ?, 'fatto')",
        (on,),
    )


def test_the_groups_come_from_the_workout_the_rotation_is_at(
    connection: sqlite3.Connection, declared: config.TrainingConfig
) -> None:
    turn = constraints.rotated(connection, declared)

    assert turn.groups == ("legs",)
    assert turn.where is not None
    assert (turn.where.position, turn.where.performed) == (1, 0)


def test_a_performed_workout_moves_it_on_to_the_next_entry_of_the_split(
    connection: sqlite3.Connection, declared: config.TrainingConfig
) -> None:
    """A cycle advances when a workout is performed, never when a date passes."""
    performed(connection, "2026-09-01")

    turn = constraints.rotated(connection, declared)

    assert turn.groups == ("shoulders",)
    assert turn.where is not None
    assert turn.where.position == 2


def test_a_prescribed_workout_nobody_did_moves_nothing(
    connection: sqlite3.Connection, declared: config.TrainingConfig
) -> None:
    connection.execute(
        "INSERT INTO workouts (state, prescribed_on) VALUES ('prescribed', '2026-09-01')"
    )

    assert constraints.rotated(connection, declared).groups == ("legs",)


def test_the_rotation_wraps_and_the_split_starts_again(
    connection: sqlite3.Connection, declared: config.TrainingConfig
) -> None:
    performed(connection, "2026-09-01")
    performed(connection, "2026-09-03")

    turn = constraints.rotated(connection, declared)

    assert turn.groups == ("legs",)
    assert turn.where is not None
    assert (turn.where.cycle, turn.where.position) == (2, 1)


def test_nothing_is_derived_over_groups_a_caller_already_named(
    connection: sqlite3.Connection, declared: config.TrainingConfig
) -> None:
    """And `where` says so, which is what lets a door print the rotation only
    when the rotation is where the groups came from."""
    turn = constraints.rotated(connection, declared, ("chest", "arms"))

    assert turn.groups == ("chest", "arms")
    assert turn.where is None


def test_nothing_is_derived_without_a_declared_split(
    connection: sqlite3.Connection,
) -> None:
    """Somebody planning with a time alone and no `training.toml` gets the
    whole admissible space, which is what they always got."""
    turn = constraints.rotated(connection, None)

    assert turn.groups == ()
    assert turn.where is None
