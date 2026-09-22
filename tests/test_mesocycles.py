"""The accepted mesocycle, kept: what is written, what is read back, and what is ended."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import make_exercise
from trainer.engine import catalog, database, duration, mesocycles, migrations, workouts

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat"),
    make_exercise(id="Plank", name="Plank"),
)

TODAY = "2026-09-22"


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        yield opened


def slot(exercise_id: str, *, reps: int | None = 5, seconds: int | None = None) -> tuple[workouts.PrescribedBlock, ...]:
    return (
        workouts.PrescribedBlock(
            block=duration.Block(
                items=(duration.BlockItem(exercise_id=exercise_id, reps=reps, seconds=seconds),),
                rounds=3,
                rest=120,
            ),
            reason="the one lift of the day",
        ),
    )


def test_nothing_is_active_before_anything_is_accepted(connection: sqlite3.Connection) -> None:
    assert mesocycles.active(connection) is None


def test_an_accepted_mesocycle_reads_back_as_it_was_written(
    connection: sqlite3.Connection,
) -> None:
    written = (slot("Barbell_Squat"), slot("Plank", reps=None, seconds=45))

    identifier = mesocycles.record_mesocycle(connection, written, cycles=4, why="settle the loads", on=TODAY)

    kept = mesocycles.active(connection)
    assert kept is not None
    assert kept.id == identifier
    assert kept.slots == written
    assert (kept.cycles, kept.why, kept.accepted_on) == (4, "settle the loads", TODAY)


def test_it_remembers_how_many_workouts_had_been_performed(
    connection: sqlite3.Connection,
) -> None:
    """Its cycles are counted from here: the rotation it starts in is not reset."""
    for _ in range(3):
        workouts.record_performed(
            connection,
            (
                workouts.PerformedBlock(
                    items=(
                        workouts.PerformedItem(
                            exercise_id="Plank", unit="seconds", amount=30, amount_source="reported"
                        ),
                    ),
                    rounds=1,
                    rounds_source="reported",
                    rest=0,
                    rest_source="reported",
                ),
            ),
            on="2026-09-01",
            report="plank",
        )

    mesocycles.record_mesocycle(connection, (slot("Barbell_Squat"),), cycles=2, why="short", on=TODAY)

    kept = mesocycles.active(connection)
    assert kept is not None and kept.accepted_after == 3


def test_accepting_a_second_ends_the_first(connection: sqlite3.Connection) -> None:
    first = mesocycles.record_mesocycle(connection, (slot("Barbell_Squat"),), cycles=4, why="a", on=TODAY)
    second = mesocycles.record_mesocycle(connection, (slot("Plank"),), cycles=2, why="b", on=TODAY)

    kept = mesocycles.active(connection)
    assert kept is not None and kept.id == second != first


def test_accepting_one_prescribes_nothing(connection: sqlite3.Connection) -> None:
    """ADR-0008 item 4: a workout is prescribed when it is served, not when its mesocycle is accepted."""
    mesocycles.record_mesocycle(connection, (slot("Barbell_Squat"),), cycles=4, why="a", on=TODAY)

    assert connection.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 0


def test_a_slot_naming_an_exercise_twice_is_refused(connection: sqlite3.Connection) -> None:
    twice = (*slot("Barbell_Squat"), *slot("Barbell_Squat"))

    with pytest.raises(duration.DurationError):
        mesocycles.record_mesocycle(connection, (twice,), cycles=4, why="a", on=TODAY)
    assert mesocycles.active(connection) is None
