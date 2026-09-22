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


# -- today's workout, served off it --------------------------------------------

TWO_SLOTS = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
split = [["legs"], ["core"]]
equipment = ["barbell"]
"""


@pytest.fixture()
def two_slots(declared_training: Path) -> Path:
    declared_training.write_text(TWO_SLOTS, encoding="utf-8")
    return declared_training


def performed(connection: sqlite3.Connection, workout_id: int | None = None) -> int:
    """One workout performed: the served one when named, else training nobody planned."""
    return workouts.record_performed(
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
        on=TODAY,
        report="plank",
        workout_id=workout_id,
    )


def accepted(connection: sqlite3.Connection, cycles: int = 2) -> int:
    return mesocycles.record_mesocycle(
        connection,
        (slot("Barbell_Squat"), slot("Plank", reps=None, seconds=45)),
        cycles=cycles,
        why="settle the loads",
        on=TODAY,
    )


def test_with_none_accepted_today_is_a_state_naming_the_fix(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    with pytest.raises(mesocycles.MesocycleError, match="trainer plan --mesocycle"):
        mesocycles.today(connection)


def test_today_is_the_slot_the_rotation_is_at(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """The rotation is not reset by accepting: one workout performed before
    it, and the first thing served is the second slot."""
    performed(connection)
    identifier = accepted(connection)

    found = mesocycles.today(connection)

    assert (found.mesocycle, found.slot, found.slots) == (identifier, 2, 2)
    assert found.blocks == slot("Plank", reps=None, seconds=45)
    assert (found.cycle, found.cycles) == (1, 2)


def test_serving_prescribes_the_slot(connection: sqlite3.Connection, two_slots: Path) -> None:
    accepted(connection)

    _, workout_id = mesocycles.record_served(connection, TODAY)

    assert workouts.prescribed(connection, workout_id) == slot("Barbell_Squat")
    assert workouts.awaiting(connection) == workouts.workout(connection, workout_id)


def test_served_twice_before_it_is_performed_it_is_one_workout(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection)

    _, first = mesocycles.record_served(connection, TODAY)
    _, second = mesocycles.record_served(connection, "2026-09-23")

    assert first == second
    assert connection.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1


def test_performing_it_moves_the_next_serving_to_the_next_slot(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection)
    _, first = mesocycles.record_served(connection, TODAY)
    performed(connection, first)

    found, second = mesocycles.record_served(connection, TODAY)

    assert found.slot == 2 and second != first
    assert workouts.prescribed(connection, second) == slot("Plank", reps=None, seconds=45)


def test_after_its_last_cycle_nothing_is_served(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """Counted from the workouts performed at acceptance, never from dates."""
    accepted(connection, cycles=1)
    for _ in range(2):
        _, served = mesocycles.record_served(connection, TODAY)
        performed(connection, served)

    with pytest.raises(mesocycles.MesocycleError, match="trainer plan --mesocycle"):
        mesocycles.record_served(connection, TODAY)
    assert connection.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 2


def test_a_split_that_changed_since_acceptance_is_a_state(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """The suite's own declaration is four slots long; this mesocycle has two."""
    accepted(connection)

    with pytest.raises(mesocycles.MesocycleError, match="split"):
        mesocycles.today(connection)
