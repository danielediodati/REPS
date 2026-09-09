"""Migration 0006's shape: the two states, the two phases, and provenance.

Nothing here goes through `workouts.py` -- that is `test_workouts.py`'s job.
This holds only what the database itself refuses, because the rule this ticket
is judged on is that a fourth provenance is rejected **by the database** and
not by a Python guard somebody can forget to call.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import make_exercise
from trainer.engine import catalog, database, migrations


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(
            opened, (make_exercise(id="Barbell_Squat", name="Barbell Squat"),)
        )
        yield opened


def workout(connection: sqlite3.Connection, **overrides: object) -> int:
    """A workout row, prescribed unless the test says otherwise."""
    values: dict[str, object] = {
        "state": "prescribed",
        "prescribed_on": "2026-09-01",
        "performed_on": None,
        "report": None,
    }
    values.update(overrides)
    cursor = connection.execute(
        "INSERT INTO workouts (state, prescribed_on, performed_on, report) "
        "VALUES (:state, :prescribed_on, :performed_on, :report)",
        values,
    )
    return int(cursor.lastrowid or 0)


def block(connection: sqlite3.Connection, workout_id: int, **overrides: object) -> int:
    values: dict[str, object] = {
        "workout_id": workout_id,
        "phase": "prescribed",
        "position": 1,
        "rounds": 4,
        "rounds_source": None,
        "rest": 150,
        "rest_source": None,
        "reason": "the heaviest lift while fresh",
        "rpe": None,
    }
    values.update(overrides)
    cursor = connection.execute(
        "INSERT INTO workout_blocks (workout_id, phase, position, rounds, "
        "rounds_source, rest, rest_source, reason, rpe) "
        "VALUES (:workout_id, :phase, :position, :rounds, :rounds_source, "
        ":rest, :rest_source, :reason, :rpe)",
        values,
    )
    return int(cursor.lastrowid or 0)


def exercise(connection: sqlite3.Connection, block_id: int, **overrides: object) -> int:
    values: dict[str, object] = {
        "block_id": block_id,
        "phase": "prescribed",
        "position": 1,
        "exercise_id": "Barbell_Squat",
        "unit": "reps",
        "amount": 8,
        "amount_source": None,
        "load_kg": None,
        "load_kg_source": None,
    }
    values.update(overrides)
    cursor = connection.execute(
        "INSERT INTO workout_exercises (block_id, phase, position, exercise_id, "
        "unit, amount, amount_source, load_kg, load_kg_source) "
        "VALUES (:block_id, :phase, :position, :exercise_id, :unit, :amount, "
        ":amount_source, :load_kg, :load_kg_source)",
        values,
    )
    return int(cursor.lastrowid or 0)


PERFORMED_BLOCK = {
    "phase": "performed",
    "rounds_source": "reported",
    "rest_source": "assumed",
    "reason": None,
}
PERFORMED_EXERCISE = {"phase": "performed", "amount_source": "reported"}


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_the_three_tables_exist(connection: sqlite3.Connection) -> None:
    assert {"workouts", "workout_blocks", "workout_exercises"} <= table_names(connection)


def test_db_status_reports_a_version_the_suite_never_spells_out(
    connection: sqlite3.Connection,
) -> None:
    """CLAUDE.md's standing rule: an assertion about today's schema version is
    not an assertion about behaviour. The number comes from the migration set,
    so a seventh migration does not break this."""
    assert migrations.applied_version(connection) == migrations.latest_version(
        migrations.discover()
    )


# --- the two states -----------------------------------------------------


def test_a_prescribed_workout_has_no_performed_date(
    connection: sqlite3.Connection,
) -> None:
    workout(connection)  # does not raise

    row = connection.execute("SELECT * FROM workouts").fetchone()
    assert row["state"] == "prescribed"
    assert row["performed_on"] is None


def test_a_third_state_is_refused(connection: sqlite3.Connection) -> None:
    """`unreported` is a reading of a prescribed workout, not a state anything
    sets: stored, something would have to go and write it, and nothing does."""
    with pytest.raises(sqlite3.IntegrityError):
        workout(connection, state="unreported")


def test_a_prescribed_workout_with_a_performed_date_is_refused(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        workout(connection, state="prescribed", performed_on="2026-09-02")


def test_a_performed_workout_without_a_performed_date_is_refused(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        workout(connection, state="performed", performed_on=None)


def test_a_workout_nobody_planned_is_still_a_workout(
    connection: sqlite3.Connection,
) -> None:
    workout(
        connection, state="performed", prescribed_on=None, performed_on="2026-09-02"
    )  # does not raise


def test_a_prescribed_workout_must_say_when_it_was_prescribed(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        workout(connection, prescribed_on=None)


def test_only_a_performed_workout_carries_the_users_words(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        workout(connection, report="panca bene")

    workout(
        connection,
        state="performed",
        performed_on="2026-09-02",
        report="panca bene, solo 3 serie di military",
    )  # does not raise


# --- both phases, side by side ------------------------------------------


def test_both_phases_of_one_workout_read_back_as_two_distinct_sets(
    connection: sqlite3.Connection,
) -> None:
    """Deviation is the difference between them, so neither may overwrite the
    other."""
    identifier = workout(connection, state="performed", performed_on="2026-09-02")
    prescribed = block(connection, identifier, rounds=4)
    exercise(connection, prescribed, amount=8)
    performed = block(connection, identifier, rounds=3, **PERFORMED_BLOCK)
    exercise(connection, performed, amount=8, **PERFORMED_EXERCISE)

    rows = connection.execute(
        "SELECT b.phase, b.rounds, e.amount FROM workout_blocks AS b "
        "JOIN workout_exercises AS e ON e.block_id = b.id "
        "WHERE b.workout_id = ? ORDER BY b.phase",
        (identifier,),
    ).fetchall()

    assert [(row["phase"], row["rounds"]) for row in rows] == [
        ("performed", 3),
        ("prescribed", 4),
    ]


def test_a_block_belongs_to_one_position_of_one_phase(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection)
    block(connection, identifier, position=1)

    with pytest.raises(sqlite3.IntegrityError):
        block(connection, identifier, position=1)


def test_an_exercise_cannot_be_filed_under_a_block_of_the_other_phase(
    connection: sqlite3.Connection,
) -> None:
    """`phase` is repeated on the child row so a CHECK can reach it; the
    composite foreign key is what keeps the repetition honest."""
    identifier = workout(connection)
    prescribed = block(connection, identifier)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, prescribed, **PERFORMED_EXERCISE)


def test_deleting_a_workout_takes_its_children_with_it(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection)
    exercise(connection, block(connection, identifier))

    connection.execute("DELETE FROM workouts WHERE id = ?", (identifier,))

    assert connection.execute(
        "SELECT COUNT(*) AS total FROM workout_exercises"
    ).fetchone()["total"] == 0


# --- provenance, per field ----------------------------------------------


def test_a_performed_row_takes_each_of_the_three_provenances(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection, state="performed", performed_on="2026-09-02")
    for position, source in enumerate(("reported", "assumed", "asked"), start=1):
        performed = block(
            connection, identifier, position=position, **{**PERFORMED_BLOCK, "rounds_source": source}
        )
        exercise(
            connection, performed, **{**PERFORMED_EXERCISE, "amount_source": source}
        )  # does not raise


def test_a_fourth_provenance_is_refused_by_the_database(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection, state="performed", performed_on="2026-09-02")
    performed = block(connection, identifier, **PERFORMED_BLOCK)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, performed, phase="performed", amount_source="guessed")

    with pytest.raises(sqlite3.IntegrityError):
        block(
            connection,
            identifier,
            position=2,
            **{**PERFORMED_BLOCK, "rounds_source": "inferred"},
        )


def test_a_performed_row_must_say_where_every_value_came_from(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection, state="performed", performed_on="2026-09-02")

    with pytest.raises(sqlite3.IntegrityError):
        block(connection, identifier, **{**PERFORMED_BLOCK, "rounds_source": None})

    performed = block(connection, identifier, **PERFORMED_BLOCK)
    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, performed, phase="performed", amount_source=None)


def test_a_prescribed_row_carries_no_provenance_and_no_rpe(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection)

    with pytest.raises(sqlite3.IntegrityError):
        block(connection, identifier, rounds_source="assumed")

    with pytest.raises(sqlite3.IntegrityError):
        block(connection, identifier, position=2, rpe=8)

    prescribed = block(connection, identifier, position=3)
    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, prescribed, amount_source="assumed")


def test_a_performed_load_says_where_it_came_from(
    connection: sqlite3.Connection,
) -> None:
    """A provenance describing nothing is not a provenance, and a load that was
    performed always says how it got here."""
    identifier = workout(connection, state="performed", performed_on="2026-09-02")
    performed = block(connection, identifier, **PERFORMED_BLOCK)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, performed, **PERFORMED_EXERCISE, load_kg=60.0)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(
            connection,
            performed,
            position=2,
            **PERFORMED_EXERCISE,
            load_kg=None,
            load_kg_source="reported",
        )

    exercise(
        connection,
        performed,
        position=3,
        **PERFORMED_EXERCISE,
        load_kg=60.0,
        load_kg_source="reported",
    )  # does not raise


def test_rpe_sits_on_the_performed_block_and_is_optional(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection, state="performed", performed_on="2026-09-02")
    block(connection, identifier, rpe=8.5, **PERFORMED_BLOCK)  # does not raise
    block(connection, identifier, position=2, rpe=None, **PERFORMED_BLOCK)

    with pytest.raises(sqlite3.IntegrityError):
        block(connection, identifier, position=3, rpe=11, **PERFORMED_BLOCK)


def test_a_performed_block_has_no_reason(connection: sqlite3.Connection) -> None:
    """Nobody justifies what already happened."""
    identifier = workout(connection, state="performed", performed_on="2026-09-02")

    with pytest.raises(sqlite3.IntegrityError):
        block(
            connection,
            identifier,
            **{**PERFORMED_BLOCK, "reason": "because it felt right"},
        )


# --- the vocabulary the exercise row is held to -------------------------


def test_an_exercise_id_the_catalog_does_not_have_is_refused(
    connection: sqlite3.Connection,
) -> None:
    identifier = workout(connection)
    prescribed = block(connection, identifier)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, prescribed, exercise_id="Not_An_Exercise")


def test_a_third_unit_is_refused(connection: sqlite3.Connection) -> None:
    identifier = workout(connection)
    prescribed = block(connection, identifier)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, prescribed, unit="metres")


def test_an_amount_of_nothing_is_refused(connection: sqlite3.Connection) -> None:
    """Zero is not a prescription, it is one that was removed --
    `duration.BlockItem` refuses it on the way in for the same reason."""
    identifier = workout(connection)
    prescribed = block(connection, identifier)

    with pytest.raises(sqlite3.IntegrityError):
        exercise(connection, prescribed, amount=0)


# --- pain is gone -------------------------------------------------------


def test_pattern_state_no_longer_has_a_pain_column(
    connection: sqlite3.Connection,
) -> None:
    """Nothing will ever write it: pain is prose the agent reads, and its only
    structured outcome is an exclusion the user confirms.

    Migration 0007 has since replaced the table with a view, and the column is
    still not there -- which is the stronger version of the same statement: no
    view could compute it, so nothing could have brought it back."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(pattern_state)")}

    assert "pain" not in columns
    assert {"movement_pattern", "rounds"} <= columns


def test_a_prescribed_block_must_say_why_it_is_there(
    connection: sqlite3.Connection,
) -> None:
    """A stored block with no reason reads back as a plan whose `why` line is
    empty -- the prose-beside-the-plan failure the wire shape exists to
    prevent, arriving a week later through the database."""
    identifier = workout(connection)

    with pytest.raises(sqlite3.IntegrityError):
        block(connection, identifier, reason=None)
