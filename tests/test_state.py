"""`pattern_history` and `last_performed_load`, against state that is empty.

Every test here runs on the current schema, which nothing writes into: that is
the point of the ticket. The assertions are that a well-formed question comes
back as a typed *«I don't know»* and never as an exception, and that a
malformed one comes back as an exception and never as *«I don't know»*.

No LLM and no network -- both are taken away in `conftest.py`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich, make_exercise
from trainer.engine import catalog, database, migrations, state

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Barbell_Deadlift",
        name="Barbell Deadlift",
        primary_muscles=("hamstrings",),
    ),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Barbell_Deadlift": ("hip hinge", "hip, knee, lumbar spine", "yes", "high", 3),
}


@pytest.fixture()
def empty(database_file: Path) -> Iterator[sqlite3.Connection]:
    """The migrated schema with nothing in it at all -- not even a catalog."""
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection, migrations.discover())
        yield connection


@pytest.fixture()
def connection(empty: sqlite3.Connection) -> sqlite3.Connection:
    """A catalog, enriched, and `pattern_state` still empty -- today's state."""
    catalog.import_exercises(empty, CATALOG)
    enrich(empty, _PATTERNS)
    return empty


# -- the answer shape ---------------------------------------------------------


def test_a_pattern_nobody_has_trained_is_unknown_and_does_not_raise(
    connection: sqlite3.Connection,
) -> None:
    answer = state.pattern_history(connection, "squat", 3)

    assert answer.known is False
    assert answer.value is None


def test_an_unknown_answer_still_says_what_was_asked(
    connection: sqlite3.Connection,
) -> None:
    """An agent holding this can say what it asked and got nothing for, which
    is a fact it can plan around rather than a hole in its context."""
    answer = state.pattern_history(connection, "hip hinge", 2)

    assert "hip hinge" in answer.about
    assert "2 cycle(s)" in answer.about


def test_pattern_state_being_entirely_empty_is_the_same_answer(
    connection: sqlite3.Connection,
) -> None:
    """A genuinely empty table and a pattern with no row in a populated one are
    the same fact to the caller, and the query distinguishes neither by
    inspecting a result set for emptiness."""
    rows = connection.execute("SELECT COUNT(*) AS total FROM pattern_state").fetchone()
    assert rows["total"] == 0

    assert state.pattern_history(connection, "squat", 1).known is False


def test_real_history_comes_back_through_the_same_query(
    connection: sqlite3.Connection,
) -> None:
    """What session 5 will write, written by hand. Nothing in this module
    changes when it starts arriving for real."""
    connection.execute(
        "INSERT INTO pattern_state (movement_pattern, cycle_volume, load_trend, pain) "
        "VALUES ('squat', 42, 'up', 'none')"
    )

    answer = state.pattern_history(connection, "squat", 3)

    assert answer.known is True
    assert answer.value is not None
    assert answer.value.volume == 42
    assert answer.value.load_trend == "up"
    assert answer.value.pain == "none"
    assert answer.value.axis == "pattern"
    assert answer.value.key == "squat"
    assert answer.value.cycles == 3


def test_a_row_with_no_volume_yet_is_known_but_carries_nothing(
    connection: sqlite3.Connection,
) -> None:
    """Pain can be recorded against a pattern before any volume is counted for
    it. The row existing is what `known` is about; the fields are separately
    nullable."""
    connection.execute(
        "INSERT INTO pattern_state (movement_pattern, pain) VALUES ('squat', 'left knee')"
    )

    answer = state.pattern_history(connection, "squat", 1)

    assert answer.known is True
    assert answer.value is not None
    assert answer.value.volume is None
    assert answer.value.pain == "left knee"


def test_the_denominator_is_the_cycle(connection: sqlite3.Connection) -> None:
    """The column the answer reads is `cycle_volume`. A weekly figure would
    move because the calendar moved rather than because the training did."""
    connection.execute(
        "INSERT INTO pattern_state (movement_pattern, cycle_volume) VALUES ('squat', 7)"
    )

    answer = state.pattern_history(connection, "squat", 4)

    assert answer.value is not None
    assert answer.value.volume == 7
    assert answer.value.cycles == 4


# -- the questions that cannot be asked ---------------------------------------


def test_an_unknown_pattern_is_a_caller_error_not_an_unknown_answer(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(state.StateError, match="no such pattern"):
        state.pattern_history(connection, "vertical yeet", 3)


def test_the_pattern_vocabulary_is_the_catalog_s_own(
    connection: sqlite3.Connection,
) -> None:
    """Rejected against `catalog.values`, the same way `admissible_set` does
    it -- never a copy of the twelve patterns kept in this module."""
    with pytest.raises(state.StateError) as raised:
        state.pattern_history(connection, "isolation", 1)

    # `isolation` is a real pattern in the taxonomy but no row in this
    # catalog carries it, so the catalog's own vocabulary is what refuses it.
    assert "squat" in str(raised.value)
    assert "hip hinge" in str(raised.value)


def test_an_unenriched_catalog_is_a_state_and_not_a_typo(
    empty: sqlite3.Connection,
) -> None:
    """A vocabulary read from an unenriched catalog is empty, and every
    correct pattern checked against it would be refused as a typo."""
    catalog.import_exercises(empty, CATALOG)

    with pytest.raises(state.StateError, match="not enriched yet"):
        state.pattern_history(empty, "squat", 3)


def test_an_empty_catalog_is_a_state_and_names_its_remedy(
    empty: sqlite3.Connection,
) -> None:
    with pytest.raises(state.StateError, match="trainer db import"):
        state.pattern_history(empty, "squat", 3)


@pytest.mark.parametrize("cycles", [0, -1])
def test_a_window_of_no_cycles_is_refused(
    connection: sqlite3.Connection, cycles: int
) -> None:
    with pytest.raises(state.StateError, match="asks about nothing"):
        state.pattern_history(connection, "squat", cycles)


# -- the second axis ----------------------------------------------------------


def test_the_muscle_axis_is_a_named_state_not_a_fabricated_unknown(
    connection: sqlite3.Connection,
) -> None:
    """ADR-0001 counts the deficit per pattern *and* per muscle. `pattern_state`
    is keyed by pattern and has no room for the second, so session 5 adds a
    counterpart table. Until it does, asking says so."""
    with pytest.raises(state.StateError, match="not counted per muscle yet"):
        state.volume_history(connection, "muscle", "biceps", 3)


def test_an_axis_that_is_not_one_of_the_two_is_refused(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(state.StateError, match="not an axis"):
        state.volume_history(connection, "mood", "cheerful", 3)


def test_the_result_type_carries_the_axis(connection: sqlite3.Connection) -> None:
    """The same type answers both axes, so an answer that did not say which
    one it was about could be filed under the wrong one."""
    connection.execute(
        "INSERT INTO pattern_state (movement_pattern, cycle_volume) VALUES ('squat', 3)"
    )

    answer = state.volume_history(connection, "pattern", "squat", 1)

    assert answer.value is not None
    assert answer.value.axis == "pattern"


# -- last_performed_load ------------------------------------------------------


def test_no_workouts_table_is_unknown_and_does_not_raise(
    connection: sqlite3.Connection,
) -> None:
    """There is no `workouts` table at all yet. That is «I don't know», and it
    is the same answer the table will give for an exercise it holds nothing
    for."""
    assert not state._has_source(connection, state.LOAD_SOURCE)

    answer = state.last_performed_load(connection, "Barbell_Squat")

    assert answer.known is False
    assert answer.value is None


def test_an_unknown_exercise_id_is_a_caller_error(
    connection: sqlite3.Connection,
) -> None:
    """Distinct from and never confused with «unknown, no history»: letting a
    typo return the unknown answer turns it into a silent «you have never done
    this»."""
    with pytest.raises(state.StateError, match="no such exercise"):
        state.last_performed_load(connection, "Barbell_Sqvat")


def test_an_empty_catalog_is_a_state_for_loads_too(empty: sqlite3.Connection) -> None:
    with pytest.raises(state.StateError, match="trainer db import"):
        state.last_performed_load(empty, "Barbell_Squat")


def create_workouts(connection: sqlite3.Connection) -> None:
    """Session 5's table, in the minimal shape `LOAD_SOURCE` names.

    Written here so the query is exercised rather than dead: this is the
    contract session 5 either meets or changes in one place.
    """
    connection.execute(
        f"CREATE TABLE {state.LOAD_SOURCE.table} ("
        f"  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        f"  {state.LOAD_SOURCE.key_column} TEXT NOT NULL,"
        f"  {state.LOAD_SOURCE.load_column} REAL,"
        f"  {state.LOAD_SOURCE.order_column} TEXT NOT NULL)"
    )


def test_a_logged_load_comes_back_through_the_same_call(
    connection: sqlite3.Connection,
) -> None:
    create_workouts(connection)
    connection.execute(
        "INSERT INTO workouts (exercise_id, load_kg, performed_on) "
        "VALUES ('Barbell_Squat', 80.0, '2026-08-01'), "
        "('Barbell_Squat', 92.5, '2026-08-20')"
    )

    answer = state.last_performed_load(connection, "Barbell_Squat")

    assert answer.known is True
    assert answer.value == 92.5


def test_a_table_that_exists_but_holds_nothing_for_this_exercise_is_unknown(
    connection: sqlite3.Connection,
) -> None:
    """The same answer as no table at all -- which is what makes session 5's
    arrival a change of data and not of contract."""
    create_workouts(connection)
    connection.execute(
        "INSERT INTO workouts (exercise_id, load_kg, performed_on) "
        "VALUES ('Barbell_Deadlift', 100.0, '2026-08-01')"
    )

    answer = state.last_performed_load(connection, "Barbell_Squat")

    assert answer.known is False


def test_a_bodyweight_row_with_no_load_does_not_count_as_a_load(
    connection: sqlite3.Connection,
) -> None:
    """A performed workout that recorded no load is not a load of zero, and
    the most recent row having none must not hide the last one that did."""
    create_workouts(connection)
    connection.execute(
        "INSERT INTO workouts (exercise_id, load_kg, performed_on) "
        "VALUES ('Barbell_Squat', 60.0, '2026-08-01'), "
        "('Barbell_Squat', NULL, '2026-08-20')"
    )

    answer = state.last_performed_load(connection, "Barbell_Squat")

    assert answer.value == 60.0
