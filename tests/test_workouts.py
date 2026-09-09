"""The write path for a workout in either of its states, and reading it back.

The database's own refusals are `test_workouts_schema.py`; what is here is the
module's contract -- one workout per call, whole or not at all, and a plan that
comes back out the shape it went in.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import make_exercise
from trainer.engine import (
    catalog,
    database,
    duration,
    exclusions,
    migrations,
    workouts,
)
from trainer.engine.exclusions import Exclusion

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat"),
    make_exercise(id="Dumbbell_Row", name="Dumbbell Row", equipment="dumbbell"),
    make_exercise(id="Farmers_Walk", name="Farmers Walk", equipment="dumbbell"),
)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(opened, CATALOG)
        yield opened


def squat_block(rounds: int = 4, rest: int = 150) -> workouts.PrescribedBlock:
    return workouts.PrescribedBlock(
        block=duration.Block(
            items=(duration.BlockItem(exercise_id="Barbell_Squat", reps=8),),
            rounds=rounds,
            rest=rest,
        ),
        reason="the heaviest lift while fresh",
    )


def superset() -> workouts.PrescribedBlock:
    return workouts.PrescribedBlock(
        block=duration.Block(
            items=(
                duration.BlockItem(exercise_id="Dumbbell_Row", reps=12),
                duration.BlockItem(exercise_id="Farmers_Walk", seconds=45),
            ),
            rounds=3,
            rest=90,
        ),
        reason="pull and carry, nothing competing for the same joint",
    )


def counted(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"])


def test_a_prescribed_workout_is_written_with_its_children(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_prescribed(
        connection, (squat_block(), superset()), on="2026-09-09"
    )

    written = workouts.workout(connection, identifier)
    assert written is not None
    assert written.state == "prescribed"
    assert written.prescribed_on == "2026-09-09"
    assert written.performed_on is None
    assert counted(connection, "workout_blocks") == 2
    assert counted(connection, "workout_exercises") == 3


def test_the_plan_reads_back_the_shape_it_went_in_as(
    connection: sqlite3.Connection,
) -> None:
    """Including the order, the units, and the reason -- a plan whose reasons
    were dropped on the way in is prose beside the plan a week later."""
    written = (squat_block(), superset())
    identifier = workouts.record_prescribed(connection, written, on="2026-09-09")

    assert workouts.prescribed(connection, identifier) == written


def test_seconds_and_reps_survive_the_round_trip(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_prescribed(connection, (superset(),), on="2026-09-09")

    (block,) = workouts.prescribed(connection, identifier)
    assert [(item.reps, item.seconds) for item in block.block.items] == [(12, None), (None, 45)]


def test_running_it_twice_leaves_two_workouts(connection: sqlite3.Connection) -> None:
    """Asked for a plan twice, the user was prescribed twice. An upsert would
    make two prescriptions into one and lose a deviation nobody could account
    for afterwards."""
    first = workouts.record_prescribed(connection, (squat_block(),), on="2026-09-09")
    second = workouts.record_prescribed(
        connection, (squat_block(rounds=5),), on="2026-09-09"
    )

    assert first != second
    assert counted(connection, "workouts") == 2
    assert workouts.prescribed(connection, first) != workouts.prescribed(connection, second)


def test_a_workout_with_no_blocks_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(workouts.WorkoutError):
        workouts.record_prescribed(connection, (), on="2026-09-09")

    assert counted(connection, "workouts") == 0


def test_an_exercise_prescribed_twice_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """`check_plan`'s invariant, enforced by the writer rather than trusted:
    the shape the engine calls impossible must not become a row."""
    with pytest.raises(duration.DurationError):
        workouts.record_prescribed(
            connection, (squat_block(), squat_block(rounds=2)), on="2026-09-09"
        )

    assert counted(connection, "workouts") == 0


def test_a_write_that_fails_partway_leaves_nothing_behind(
    connection: sqlite3.Connection,
) -> None:
    """The second block names an exercise the catalog does not have, so it is
    refused after the workout row and the first block are already inserted."""
    orphan = workouts.PrescribedBlock(
        block=duration.Block(
            items=(duration.BlockItem(exercise_id="Not_An_Exercise", reps=5),),
            rounds=3,
            rest=60,
        ),
        reason="a plan naming something nobody has",
    )

    with pytest.raises(sqlite3.IntegrityError):
        workouts.record_prescribed(connection, (squat_block(), orphan), on="2026-09-09")

    assert counted(connection, "workouts") == 0
    assert counted(connection, "workout_blocks") == 0
    assert counted(connection, "workout_exercises") == 0


def test_a_failed_write_leaves_the_connection_usable(
    connection: sqlite3.Connection,
) -> None:
    """A rollback that left the transaction open would turn one bad plan into
    every later write failing for a reason nobody could see."""
    with pytest.raises(workouts.WorkoutError):
        workouts.record_prescribed(connection, (), on="2026-09-09")

    workouts.record_prescribed(connection, (squat_block(),), on="2026-09-09")
    assert counted(connection, "workouts") == 1


def test_asking_for_a_workout_that_is_not_there(
    connection: sqlite3.Connection,
) -> None:
    assert workouts.workout(connection, 404) is None
    assert workouts.prescribed(connection, 404) == ()


def test_a_workout_nobody_planned_has_no_prescribed_phase(
    connection: sqlite3.Connection,
) -> None:
    """Training nobody planned is still training. It reads back as a workout
    with an empty prescription, not as a missing row."""
    connection.execute(
        "INSERT INTO workouts (state, performed_on) VALUES ('performed', '2026-09-08')"
    )
    identifier = int(
        connection.execute("SELECT id FROM workouts").fetchone()["id"]
    )

    written = workouts.workout(connection, identifier)
    assert written is not None
    assert written.state == "performed"
    assert written.prescribed_on is None
    assert workouts.prescribed(connection, identifier) == ()


def test_a_stored_block_with_no_exercises_is_refused_not_skipped(
    connection: sqlite3.Connection,
) -> None:
    """Read with an inner join it would simply not come back, and the plan
    read out would be silently shorter than the plan stored. No writer
    produces this row today; the read is what would have to notice if one
    ever did."""
    identifier = workouts.record_prescribed(connection, (squat_block(),), on="2026-09-09")
    connection.execute(
        "INSERT INTO workout_blocks (workout_id, phase, position, rounds, rest, reason) "
        "VALUES (?, 'prescribed', 2, 3, 60, 'a block nothing was written under')",
        (identifier,),
    )

    with pytest.raises(workouts.WorkoutError, match="position 2"):
        workouts.prescribed(connection, identifier)


def test_the_connection_survives_a_write_that_failed_partway(
    connection: sqlite3.Connection,
) -> None:
    """The rollback path's claim, asserted rather than assumed: a transaction
    left open would turn one bad plan into every later write failing with a
    message about transactions instead of about the plan."""
    orphan = workouts.PrescribedBlock(
        block=duration.Block(
            items=(duration.BlockItem(exercise_id="Not_An_Exercise", reps=5),),
            rounds=3,
            rest=60,
        ),
        reason="a plan naming something nobody has",
    )

    with pytest.raises(sqlite3.IntegrityError):
        workouts.record_prescribed(connection, (squat_block(), orphan), on="2026-09-09")

    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-10"
    )
    assert counted(connection, "workouts") == 1
    assert len(workouts.prescribed(connection, identifier)) == 1


# -- the performed phase ------------------------------------------------------


def squat_performed(**overrides: object) -> workouts.PerformedBlock:
    fields: dict[str, object] = {
        "items": (
            workouts.PerformedItem(
                exercise_id="Barbell_Squat",
                unit="reps",
                amount=5,
                amount_source="reported",
                load_kg=100.0,
                load_kg_source="reported",
            ),
        ),
        "rounds": 3,
        "rounds_source": "reported",
        "rest": 150,
        "rest_source": "assumed",
    }
    fields.update(overrides)
    return workouts.PerformedBlock(**fields)  # type: ignore[arg-type]


def test_a_performed_workout_is_written_with_its_children(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_performed(
        connection,
        (squat_performed(),),
        on="2026-09-09",
        report="squats felt heavy",
    )

    written = workouts.workout(connection, identifier)
    assert written is not None
    assert written.state == "performed"
    assert written.performed_on == "2026-09-09"
    assert written.prescribed_on is None
    assert written.report == "squats felt heavy"
    assert counted(connection, "workout_blocks") == 1
    assert counted(connection, "workout_exercises") == 1


def test_the_workout_reads_back_the_shape_it_went_in_as(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_performed(
        connection, (squat_performed(),), on="2026-09-09", report="ok"
    )

    assert workouts.performed(connection, identifier) == (squat_performed(),)


def test_a_prescribed_workout_transitions_in_place(
    connection: sqlite3.Connection,
) -> None:
    """Deviation is the difference between the two phases, so both stay. The
    prescribed rows are not overwritten and no second workout appears."""
    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-08"
    )

    reported = workouts.record_performed(
        connection,
        (squat_performed(),),
        on="2026-09-09",
        report="three sets, not four",
        workout_id=identifier,
    )

    assert reported == identifier
    assert counted(connection, "workouts") == 1
    written = workouts.workout(connection, identifier)
    assert written is not None
    assert written.state == "performed"
    assert written.prescribed_on == "2026-09-08"
    assert written.performed_on == "2026-09-09"
    assert workouts.prescribed(connection, identifier) == (squat_block(),)
    assert workouts.performed(connection, identifier) == (squat_performed(),)


def test_a_workout_nobody_reported_has_no_performed_phase(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-08"
    )

    assert workouts.performed(connection, identifier) == ()


def test_a_report_against_a_workout_nobody_has_is_refused(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(workouts.WorkoutError, match="no workout 404"):
        workouts.record_performed(
            connection, (squat_performed(),), on="2026-09-09", report="ok", workout_id=404
        )

    assert counted(connection, "workouts") == 0


def test_a_workout_cannot_be_reported_twice(connection: sqlite3.Connection) -> None:
    """One training session is one workout. A second report would leave two
    sets of performed children under it and count the same rounds twice."""
    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-08"
    )
    workouts.record_performed(
        connection, (squat_performed(),), on="2026-09-09", report="ok", workout_id=identifier
    )

    with pytest.raises(workouts.WorkoutError, match="already reported"):
        workouts.record_performed(
            connection,
            (squat_performed(),),
            on="2026-09-10",
            report="again",
            workout_id=identifier,
        )

    assert len(workouts.performed(connection, identifier)) == 1


def test_a_performed_workout_is_at_least_one_block(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(workouts.WorkoutError, match="at least one block"):
        workouts.record_performed(connection, (), on="2026-09-09", report="nothing")

    assert counted(connection, "workouts") == 0


def test_the_proposed_exclusion_is_written_with_the_workout(
    connection: sqlite3.Connection,
) -> None:
    """It is the one thing in a report that changes what may be prescribed
    tomorrow."""
    workouts.record_performed(
        connection,
        (squat_performed(),),
        on="2026-09-09",
        report="the shoulder was pulling",
        exclusion=Exclusion("pattern", "vertical push"),
        retest_date="2026-10-01",
    )

    assert exclusions.active(connection, "2026-09-09") == (
        Exclusion("pattern", "vertical push"),
    )


def test_an_exclusion_with_no_way_back_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """A re-test date is not optional: a wall with no way back is the one
    failure TRAINER.md says this state cannot afford."""
    with pytest.raises(workouts.WorkoutError, match="re-test date"):
        workouts.record_performed(
            connection,
            (squat_performed(),),
            on="2026-09-09",
            report="ok",
            exclusion=Exclusion("pattern", "vertical push"),
        )

    assert counted(connection, "workouts") == 0


def test_an_exclusion_that_cannot_be_written_takes_the_workout_with_it(
    connection: sqlite3.Connection,
) -> None:
    """One transaction. A workout recorded without the exclusion it proposed
    would go on offering the movement that caused it."""
    with pytest.raises(exclusions.ExclusionError):
        workouts.record_performed(
            connection,
            (squat_performed(),),
            on="2026-09-09",
            report="ok",
            exclusion=Exclusion("exercise", "Barbell_Squat"),
            retest_date="2026-10-01",
        )

    assert counted(connection, "workouts") == 0
    assert counted(connection, "workout_blocks") == 0


def test_a_report_that_fails_partway_leaves_the_database_as_it_was(
    connection: sqlite3.Connection,
) -> None:
    """The workout row is written before its children, so a failure between
    the two is exactly the case a transaction exists for. Injected here as an
    exercise nobody has, which the foreign key refuses."""
    orphan = squat_performed(
        items=(
            workouts.PerformedItem(
                exercise_id="Not_An_Exercise",
                unit="reps",
                amount=5,
                amount_source="reported",
            ),
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        workouts.record_performed(
            connection, (squat_performed(), orphan), on="2026-09-09", report="ok"
        )

    assert counted(connection, "workouts") == 0
    assert counted(connection, "workout_blocks") == 0
    assert counted(connection, "workout_exercises") == 0


def test_a_failed_report_leaves_a_prescribed_workout_prescribed(
    connection: sqlite3.Connection,
) -> None:
    """The transition is an UPDATE, so a failure after it would leave a
    workout marked performed with nothing under it -- a workout that happened
    and in which nothing was done."""
    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-08"
    )
    orphan = squat_performed(
        items=(
            workouts.PerformedItem(
                exercise_id="Not_An_Exercise",
                unit="reps",
                amount=5,
                amount_source="reported",
            ),
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        workouts.record_performed(
            connection, (orphan,), on="2026-09-09", report="ok", workout_id=identifier
        )

    written = workouts.workout(connection, identifier)
    assert written is not None
    assert written.state == "prescribed"
    assert written.performed_on is None
    assert written.report is None
    assert workouts.performed(connection, identifier) == ()


def test_the_connection_survives_a_report_that_failed_partway(
    connection: sqlite3.Connection,
) -> None:
    orphan = squat_performed(
        items=(
            workouts.PerformedItem(
                exercise_id="Not_An_Exercise",
                unit="reps",
                amount=5,
                amount_source="reported",
            ),
        )
    )
    with pytest.raises(sqlite3.IntegrityError):
        workouts.record_performed(connection, (orphan,), on="2026-09-09", report="ok")

    workouts.record_performed(connection, (squat_performed(),), on="2026-09-09", report="ok")
    assert counted(connection, "workouts") == 1


def test_a_stored_performed_block_with_no_exercises_is_refused_not_skipped(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_performed(
        connection, (squat_performed(),), on="2026-09-09", report="ok"
    )
    connection.execute(
        "INSERT INTO workout_blocks "
        "(workout_id, phase, position, rounds, rounds_source, rest, rest_source) "
        "VALUES (?, 'performed', 2, 3, 'reported', 60, 'reported')",
        (identifier,),
    )

    with pytest.raises(workouts.WorkoutError, match="position 2"):
        workouts.performed(connection, identifier)


def test_reportable_answers_for_a_workout_that_can_take_one(
    connection: sqlite3.Connection,
) -> None:
    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-08"
    )

    assert workouts.reportable(connection, identifier).state == "prescribed"


def test_the_transition_refuses_a_workout_that_moved_under_it(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`reportable` runs before the transaction opens, so two runs reporting
    the same workout both pass it and only then serialise on the write. The
    condition on the UPDATE is what actually decides -- and without it the
    loser's UPDATE would match nothing while its blocks landed as a second set
    of performed children, doubling that session in every cycle that counts
    volume.

    The race is staged by taking the pre-check away, which is exactly what it
    is worth in a race: nothing.
    """
    identifier = workouts.record_prescribed(
        connection, (squat_block(),), on="2026-09-08"
    )
    workouts.record_performed(
        connection, (squat_performed(),), on="2026-09-09", report="first", workout_id=identifier
    )
    monkeypatch.setattr(workouts, "reportable", lambda connection, workout_id: None)

    with pytest.raises(workouts.WorkoutError):
        workouts.record_performed(
            connection,
            (squat_performed(),),
            on="2026-09-10",
            report="second",
            workout_id=identifier,
        )

    assert len(workouts.performed(connection, identifier)) == 1
    assert counted(connection, "workout_blocks") == 2  # one prescribed, one performed
    written = workouts.workout(connection, identifier)
    assert written is not None
    assert written.report == "first"
