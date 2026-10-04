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
goal = "hypertrophy"
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


THREE_SLOTS = """cycle_length = 3
duration_cap_min = 45
volume_denominator = "cycle"
goal = "hypertrophy"
split = [["core"], ["legs"], ["core"]]
equipment = ["barbell"]
"""


def three_accepted(connection: sqlite3.Connection, declared_training: Path) -> None:
    declared_training.write_text(THREE_SLOTS, encoding="utf-8")
    mesocycles.record_mesocycle(
        connection,
        (slot("Plank"), slot("Barbell_Squat"), slot("Plank", reps=None, seconds=45)),
        cycles=2,
        why="settle the loads",
        on=TODAY,
    )


def performed_as(connection: sqlite3.Connection, slot_number: int) -> None:
    """The mesocycle's workout at this slot served and performed, whatever the count says."""
    found = mesocycles.today(connection)
    workout_id = mesocycles.record_adapted(
        connection,
        mesocycles.active(connection).slots[slot_number - 1],  # type: ignore[union-attr]
        on=TODAY,
        mesocycle=found.mesocycle,
        served_after=found.performed,
        slot=slot_number,
    )
    performed(connection, workout_id)


def test_the_next_is_the_first_of_the_cycle_not_yet_performed(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """A, legs, B: A then B performed, and the next is legs, then A of the next cycle."""
    three_accepted(connection, declared_training)
    performed_as(connection, 1)
    performed_as(connection, 3)

    found, _ = mesocycles.record_served(connection, TODAY)
    assert (found.slot, found.cycle) == (2, 1)
    assert found.blocks == slot("Barbell_Squat")

    performed_as(connection, 2)
    assert (mesocycles.today(connection).slot, mesocycles.today(connection).cycle) == (1, 2)


def test_another_of_the_cycle_adapted_is_recorded_as_that_slot(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """A due, B asked for instead: served as B, and A is still next once it is performed."""
    three_accepted(connection, declared_training)
    found = mesocycles.today(connection)

    workout_id = mesocycles.record_adapted(
        connection,
        slot("Plank", reps=None, seconds=20),
        on=TODAY,
        mesocycle=found.mesocycle,
        served_after=found.performed,
        slot=3,
    )

    served, again = mesocycles.record_served(connection, TODAY)
    assert (again, served.slot) == (workout_id, 3)
    performed(connection, workout_id)
    assert (mesocycles.today(connection).slot, mesocycles.today(connection).done) == (1, (3,))


def test_training_nobody_planned_takes_the_first_slot_still_free(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """B performed, then a workout off the plan: it counts as A, and legs is next."""
    three_accepted(connection, declared_training)
    performed_as(connection, 3)
    performed(connection)

    assert mesocycles.today(connection).slot == 2


def test_a_workout_done_twice_leaves_its_cycle_ending_on_the_count(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """Legs twice, then A: three performed close the cycle, and B was skipped."""
    three_accepted(connection, declared_training)
    performed_as(connection, 2)
    performed_as(connection, 2)
    assert mesocycles.today(connection).slot == 1

    performed_as(connection, 1)
    assert (mesocycles.today(connection).slot, mesocycles.today(connection).cycle) == (1, 2)


def test_a_finished_mesocycle_names_the_slots_that_were_performed(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    three_accepted(connection, declared_training)
    for number in (1, 3, 2, 2, 1, 3):
        performed_as(connection, number)

    ended = mesocycles.finished(connection)

    assert ended is not None
    assert [trained.slot for trained in ended.trained] == [1, 3, 2, 2, 1, 3]


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


def adapted(connection: sqlite3.Connection, **where: int) -> int:
    """Today's slot adapted to a plank, as the planner writes an accepted adaptation."""
    found = mesocycles.today(connection)
    return mesocycles.record_adapted(
        connection,
        slot("Plank", reps=None, seconds=20),
        on=TODAY,
        mesocycle=where.get("mesocycle", found.mesocycle),
        served_after=where.get("served_after", found.performed),
    )


def test_an_adaptation_is_todays_serving_and_leaves_the_mesocycle_alone(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection)
    kept = mesocycles.active(connection)

    workout_id = adapted(connection)

    _, served = mesocycles.record_served(connection, TODAY)
    assert served == workout_id
    assert workouts.prescribed(connection, workout_id) == slot("Plank", reps=None, seconds=20)
    assert mesocycles.active(connection) == kept


def test_an_adaptation_withdraws_the_serving_it_replaces(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """Served and then adapted, the unadapted prescription was never trained,
    and left standing it would read as a workout skipped."""
    accepted(connection)
    _, unadapted = mesocycles.record_served(connection, TODAY)

    workout_id = adapted(connection)

    assert workouts.workout(connection, unadapted) is None
    assert workouts.awaiting(connection) == workouts.workout(connection, workout_id)
    assert connection.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1


def test_an_adaptation_of_a_day_that_has_moved_on_is_a_state(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """Planned before a report moved the rotation, it is no longer today's."""
    accepted(connection)
    before = mesocycles.today(connection).performed
    performed(connection)

    with pytest.raises(mesocycles.MesocycleError, match="moved on"):
        adapted(connection, served_after=before)
    assert connection.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1


def test_a_change_continues_the_cycle_count(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection, cycles=3)
    for _ in range(3):
        _, served = mesocycles.record_served(connection, TODAY)
        performed(connection, served)
    old = mesocycles.active(connection)
    assert old is not None

    mesocycles.record_mesocycle(
        connection,
        (slot("Plank"), slot("Plank", reps=None, seconds=45)),
        cycles=3,
        why="no squats from here",
        on=TODAY,
        accepted_after=old.accepted_after,
    )

    found = mesocycles.today(connection)
    assert (found.cycle, found.slot) == (2, 2)
    assert found.blocks == slot("Plank", reps=None, seconds=45)


def test_accepting_one_withdraws_the_serving_of_the_one_it_ends(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection)
    _, old = mesocycles.record_served(connection, TODAY)

    accepted(connection)

    assert workouts.workout(connection, old) is None
    _, new = mesocycles.record_served(connection, TODAY)
    assert new != old


def test_accepting_one_keeps_a_serving_already_performed(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection)
    _, old = mesocycles.record_served(connection, TODAY)
    performed(connection, old)

    accepted(connection)

    kept = workouts.workout(connection, old)
    assert kept is not None and kept.state == "performed"


def test_served_after_an_adaptation_it_reads_as_the_adapted_workout(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection)
    adapted(connection)

    found, _ = mesocycles.record_served(connection, TODAY)

    assert found.blocks == slot("Plank", reps=None, seconds=20)


def test_a_mesocycle_still_running_has_not_finished(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    accepted(connection, cycles=1)
    _, served = mesocycles.record_served(connection, TODAY)
    performed(connection, served)

    assert mesocycles.finished(connection) is None


def test_the_report_that_completes_its_last_cycle_finishes_it(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """With what was performed against it, slot by slot, and nothing past its end."""
    performed(connection)
    identifier = accepted(connection, cycles=1)
    for _ in range(2):
        _, served = mesocycles.record_served(connection, TODAY)
        performed(connection, served)

    ended = mesocycles.finished(connection)

    assert ended is not None
    assert ended.mesocycle.id == identifier
    assert [trained.slot for trained in ended.trained] == [2, 1]
    assert all(trained.performed_on == TODAY for trained in ended.trained)
    assert ended.trained[0].blocks[0].items[0].exercise_id == "Plank"
    assert ended.past == 0


def test_a_workout_performed_after_its_end_is_counted_past_it(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """Which is what tells the report that finished it from every one after."""
    accepted(connection, cycles=1)
    for _ in range(3):
        performed(connection)

    ended = mesocycles.finished(connection)

    assert ended is not None
    assert ended.past == 1
    assert len(ended.trained) == 2


def test_with_none_accepted_nothing_has_finished(connection: sqlite3.Connection) -> None:
    assert mesocycles.finished(connection) is None


# -- directions and the history the supervisor reads ---------------------------

DIRECTION = mesocycles.Direction(
    theme="density", changes="rest shortened, exercises kept", why="two alike, time is short"
)


def test_a_direction_is_kept_with_the_mesocycle_it_shaped(connection: sqlite3.Connection) -> None:
    first = mesocycles.record_mesocycle(connection, (slot("Plank"),), cycles=1, why="a", on=TODAY)
    second = mesocycles.record_mesocycle(
        connection, (slot("Barbell_Squat"),), cycles=1, why="b", on=TODAY, direction=DIRECTION
    )

    kept = mesocycles.active(connection)
    assert kept is not None and kept.id == second
    assert kept.direction == DIRECTION
    assert mesocycles.direction_of(connection, first) is None


def test_the_history_is_every_mesocycle_oldest_first_with_its_count_and_direction(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    first = accepted(connection, cycles=1)
    for _ in range(2):
        _, served = mesocycles.record_served(connection, TODAY)
        performed(connection, served)
    second = mesocycles.record_mesocycle(
        connection, (slot("Barbell_Squat"), slot("Plank")), cycles=3, why="b", on=TODAY,
        direction=DIRECTION,
    )
    performed(connection)

    past = mesocycles.history(connection)

    assert [(one.id, one.workouts, one.performed, one.changed) for one in past] == [
        (first, 2, 2, False),
        (second, 6, 1, False),
    ]
    assert past[0].ended_on == TODAY and past[1].ended_on is None
    assert (past[0].direction, past[1].direction) == (None, DIRECTION)


def test_a_mesocycle_a_change_rewrote_was_followed_for_none_of_its_workouts(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    """The change keeps the count, so what was performed belongs to the rewritten one."""
    accepted(connection, cycles=2)
    performed(connection)
    mesocycles.record_mesocycle(
        connection, (slot("Barbell_Squat"), slot("Plank")), cycles=2, why="b", on=TODAY,
        accepted_after=0,
    )

    old, new = mesocycles.history(connection)

    assert (old.changed, old.performed) == (True, 0)
    assert (new.changed, new.performed) == (False, 1)


def test_what_a_mesocycle_held_is_read_back_by_id(connection: sqlite3.Connection) -> None:
    written = (slot("Barbell_Squat"),)
    identifier = mesocycles.record_mesocycle(connection, written, cycles=1, why="a", on=TODAY)
    mesocycles.record_mesocycle(connection, (slot("Plank"),), cycles=1, why="b", on=TODAY)

    assert mesocycles.held(connection, identifier) == written
    with pytest.raises(mesocycles.MesocycleError, match="mesocycle_history"):
        mesocycles.held(connection, 99)


def test_its_volume_is_one_cycle_planned_and_all_of_it_performed(
    connection: sqlite3.Connection, two_slots: Path
) -> None:
    connection.execute(
        "UPDATE exercises SET movement_pattern = CASE id WHEN 'Plank' THEN 'core' ELSE 'squat' END"
    )
    identifier = accepted(connection, cycles=1)
    for _ in range(2):
        _, served = mesocycles.record_served(connection, TODAY)
        performed(connection, served)

    found = {(one.axis, one.key): (one.per_cycle, one.performed) for one in mesocycles.volume(connection, identifier)}

    assert found[("pattern", "squat")] == (3, 0), "the squat was never performed"
    assert found[("pattern", "core")] == (3, 2), "the plank, once a workout, one round each"
    assert found[("muscle", "shoulders")] == (6, 2)
