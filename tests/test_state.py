"""What the state answers, against rows that exist.

The fixtures are inserted directly rather than through `workouts.py`: this
module reads rows and does not care who wrote them, and a read test that went
through the writer would fail twice for one bug and pass for a view that only
happens to agree with the writer's own assumptions.

The two answers that were built against nothing still answer *«I don't know»*
where nothing is recorded, and that is asserted here as deliberately as the
numbers are -- it is the contract session 4's agent was written against.

No LLM and no network -- both are taken away in `conftest.py`, which also
declares the four-workout rotation every window here is measured in.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich, make_exercise
from trainer.engine import catalog, config, database, migrations, state

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Barbell_Deadlift",
        name="Barbell Deadlift",
        primary_muscles=("hamstrings",),
    ),
    make_exercise(id="Barbell_Curl", name="Barbell Curl", primary_muscles=("biceps",)),
    make_exercise(
        id="Triceps_Pushdown",
        name="Triceps Pushdown",
        primary_muscles=("triceps",),
    ),
    make_exercise(
        id="Standing_Calf_Raise",
        name="Standing Calf Raise",
        primary_muscles=("calves",),
    ),
    make_exercise(
        id="Bench_Press",
        name="Bench Press",
        primary_muscles=("chest", "triceps"),
    ),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Barbell_Deadlift": ("hip hinge", "hip, knee, lumbar spine", "yes", "high", 3),
    "Barbell_Curl": ("isolation", "elbow", "no", "low", 1),
    "Triceps_Pushdown": ("isolation", "elbow", "no", "low", 1),
    "Standing_Calf_Raise": ("isolation", "ankle", "no", "low", 1),
    "Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 2),
}


@pytest.fixture()
def empty(database_file: Path) -> Iterator[sqlite3.Connection]:
    """The migrated schema with nothing in it at all -- not even a catalog."""
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection, migrations.discover())
        yield connection


@pytest.fixture()
def connection(empty: sqlite3.Connection) -> sqlite3.Connection:
    """A catalog, enriched, and no workout recorded yet."""
    catalog.import_exercises(empty, CATALOG)
    enrich(empty, _PATTERNS)
    return empty


# -- writing a workout by hand ------------------------------------------------
#
# Directly, in SQL. `Block` is a rounds count and the exercises it holds, with
# an optional load on each, which is everything any view below reads.

Item = tuple[str, float | None]
Block = tuple[int, Sequence[Item]]


def performed(
    connection: sqlite3.Connection,
    on: str,
    blocks: Sequence[Block],
    *,
    prescribed_on: str | None = None,
    prescription: Sequence[Block] | None = None,
) -> int:
    """One performed workout, optionally with the plan it was reported against."""
    cursor = connection.execute(
        "INSERT INTO workouts (state, prescribed_on, performed_on, report) "
        "VALUES ('performed', ?, ?, 'did it')",
        (prescribed_on, on),
    )
    workout_id = int(cursor.lastrowid or 0)
    if prescription is not None:
        _blocks(connection, workout_id, "prescribed", prescription)
    _blocks(connection, workout_id, "performed", blocks)
    return workout_id


def prescribed(
    connection: sqlite3.Connection, on: str, blocks: Sequence[Block]
) -> int:
    """One prescribed workout nobody has reported."""
    cursor = connection.execute(
        "INSERT INTO workouts (state, prescribed_on) VALUES ('prescribed', ?)", (on,)
    )
    workout_id = int(cursor.lastrowid or 0)
    _blocks(connection, workout_id, "prescribed", blocks)
    return workout_id


def _blocks(
    connection: sqlite3.Connection,
    workout_id: int,
    phase: str,
    blocks: Sequence[Block],
) -> None:
    for position, (rounds, items) in enumerate(blocks, start=1):
        cursor = connection.execute(
            "INSERT INTO workout_blocks "
            "(workout_id, phase, position, rounds, rounds_source, rest, rest_source, reason) "
            "VALUES (?, ?, ?, ?, ?, 90, ?, ?)",
            (
                workout_id,
                phase,
                position,
                rounds,
                "reported" if phase == "performed" else None,
                "reported" if phase == "performed" else None,
                "because" if phase == "prescribed" else None,
            ),
        )
        block_id = int(cursor.lastrowid or 0)
        for item_position, (exercise_id, load) in enumerate(items, start=1):
            connection.execute(
                "INSERT INTO workout_exercises "
                "(block_id, phase, position, exercise_id, unit, amount, amount_source, "
                "load_kg, load_kg_source) VALUES (?, ?, ?, ?, 'reps', 10, ?, ?, ?)",
                (
                    block_id,
                    phase,
                    item_position,
                    exercise_id,
                    "reported" if phase == "performed" else None,
                    load,
                    "reported" if phase == "performed" and load is not None else None,
                ),
            )


def straight(exercise_id: str, rounds: int, load: float | None = None) -> Block:
    """Straight sets: one exercise, on its own, for so many rounds."""
    return (rounds, [(exercise_id, load)])


# -- the shape of an answer ---------------------------------------------------


def test_pattern_state_is_a_view(connection: sqlite3.Connection) -> None:
    """A table could not answer for a window, and would go stale the moment
    `cycle_length` was edited in a file nothing in the engine watches."""
    row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name = 'pattern_state'"
    ).fetchone()

    assert row["type"] == "view"


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


def test_a_performed_workout_is_what_makes_the_answer_known(
    connection: sqlite3.Connection,
) -> None:
    performed(connection, "2026-09-01", [straight("Barbell_Squat", 4)])

    answer = state.pattern_history(connection, "squat", 1)

    assert answer.known is True
    assert answer.value is not None
    assert answer.value.volume == 4
    assert answer.value.axis == "pattern"
    assert answer.value.key == "squat"
    assert answer.value.cycles == 1


def test_volume_is_rounds_performed(connection: sqlite3.Connection) -> None:
    """Not reps, not rounds times reps, not tonnage (CONTEXT.md). Every block
    here prescribes 10 reps and the answer counts rounds."""
    performed(
        connection,
        "2026-09-01",
        [straight("Barbell_Squat", 4), straight("Barbell_Squat", 3)],
    )

    answer = state.pattern_history(connection, "squat", 1)

    assert answer.value is not None
    assert answer.value.volume == 7


# -- the window ---------------------------------------------------------------


def four_cycles(connection: sqlite3.Connection) -> None:
    """Eight workouts over two four-workout cycles, squatting more lately.

    Dated one a week apart, newest last. The rotation advances when a workout
    is performed, so eight performed workouts are exactly two cycles.
    """
    for week, rounds in enumerate((1, 1, 1, 1, 5, 5, 5, 5)):
        performed(
            connection,
            f"2026-07-{week + 1:02d}",
            [straight("Barbell_Squat", rounds)],
        )


def test_a_wider_window_covers_more_of_the_history(
    connection: sqlite3.Connection,
) -> None:
    """The window narrows the query for real: one cycle is the last four
    workouts, two cycles is all eight."""
    four_cycles(connection)

    one = state.pattern_history(connection, "squat", 1)
    two = state.pattern_history(connection, "squat", 2)

    assert one.value is not None and two.value is not None
    assert one.value.volume == 20
    assert two.value.volume == 24


def test_a_window_reaching_further_back_than_the_training_covers_all_of_it(
    connection: sqlite3.Connection,
) -> None:
    """Fewer workouts performed than the window asks for is not an error and
    not an empty answer: the window starts at the beginning."""
    four_cycles(connection)

    assert state.window(connection, 9).start is None
    answer = state.pattern_history(connection, "squat", 9)

    assert answer.value is not None
    assert answer.value.volume == 24


def test_changing_the_cycle_length_changes_what_a_window_covers(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """No migration and no recompute. `cycle_length` lives in a file the user
    edits, and a stored aggregate would be silently wrong from the edit
    onwards, because nothing in the engine watches that file."""
    four_cycles(connection)
    assert state.pattern_history(connection, "squat", 1).value.volume == 20  # type: ignore[union-attr]

    declared_training.write_text(
        'cycle_length = 2\nduration_cap_min = 60\nvolume_denominator = "cycle"\n'
        'split = [["chest"], ["legs"]]\nequipment = ["barbell"]\n',
        encoding="utf-8",
    )

    assert state.pattern_history(connection, "squat", 1).value.volume == 10  # type: ignore[union-attr]


def test_the_window_is_measured_in_workouts_performed(
    connection: sqlite3.Connection,
) -> None:
    """A cycle advances when a workout is performed, never when a date passes,
    so a month off does not move the window past anything."""
    four_cycles(connection)

    covered = state.window(connection, 1)

    assert covered.workouts == 4
    assert covered.start == "2026-07-05"


@pytest.mark.parametrize("cycles", [0, -1])
def test_a_window_of_no_cycles_is_refused(
    connection: sqlite3.Connection, cycles: int
) -> None:
    with pytest.raises(state.StateError, match="asks about nothing"):
        state.pattern_history(connection, "squat", cycles)


def test_a_mistyped_pattern_is_refused_before_the_configuration_is_read(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo is a typo on a machine that has not declared a rotation yet.
    Reported the other way round, the reader is sent to write a file that has
    nothing to do with what they got wrong."""
    monkeypatch.setenv("TRAINER_CONFIG", str(Path("nowhere") / "training.toml"))

    with pytest.raises(state.StateError, match="no such pattern"):
        state.pattern_history(connection, "vertical yeet", 3)


def test_a_window_needs_the_declared_rotation_and_says_so_in_its_own_words(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A question about cycles cannot be answered without knowing how long one
    is. That is the configuration's own state, and it reaches the reader with
    the file's name and the copy-this remedy in it, not as a `StateError`
    re-wording it."""
    monkeypatch.setenv("TRAINER_CONFIG", str(Path("nowhere") / "training.toml"))

    with pytest.raises(config.NoTrainingConfig, match="no training configuration"):
        state.pattern_history(connection, "squat", 1)


# -- the two axes -------------------------------------------------------------


def test_both_axes_have_somewhere_to_read(connection: sqlite3.Connection) -> None:
    assert sorted(state._SOURCES) == ["muscle", "pattern"]


def test_the_muscle_axis_answers(connection: sqlite3.Connection) -> None:
    """ADR-0001 counts the deficit per pattern *and* per muscle, and asking for
    the second used to be a named gap."""
    performed(connection, "2026-09-01", [straight("Barbell_Curl", 3)])

    answer = state.volume_history(connection, "muscle", "biceps", 1)

    assert answer.known is True
    assert answer.value is not None
    assert answer.value.volume == 3
    assert answer.value.axis == "muscle"


def test_a_muscle_nobody_has_trained_is_unknown_and_does_not_raise(
    connection: sqlite3.Connection,
) -> None:
    answer = state.volume_history(connection, "muscle", "calves", 2)

    assert answer.known is False


def test_an_unknown_muscle_is_a_caller_error(connection: sqlite3.Connection) -> None:
    with pytest.raises(state.StateError, match="no such muscle"):
        state.volume_history(connection, "muscle", "gluteus enormous", 1)


def test_the_muscle_vocabulary_is_the_catalog_s_own(
    connection: sqlite3.Connection,
) -> None:
    """Read from `primary_muscles`, never from a copy of the seventeen values.
    `lats` is a real muscle in the catalog at large and in no row of this one,
    so it is the catalog's own vocabulary doing the refusing."""
    with pytest.raises(state.StateError) as raised:
        state.volume_history(connection, "muscle", "lats", 1)

    assert "biceps" in str(raised.value)
    assert "quadriceps" in str(raised.value)


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
        state.pattern_history(connection, "carry", 1)

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


def test_the_muscle_axis_needs_no_enrichment(empty: sqlite3.Connection) -> None:
    """`primary_muscles` comes from the import, so the unenriched state is not
    a distinguishable one on this axis -- an empty catalog is."""
    catalog.import_exercises(empty, CATALOG)

    assert state.volume_history(empty, "muscle", "biceps", 1).known is False


def test_an_empty_catalog_is_a_state_and_names_its_remedy(
    empty: sqlite3.Connection,
) -> None:
    with pytest.raises(state.StateError, match="trainer db import"):
        state.pattern_history(empty, "squat", 3)


def test_an_empty_catalog_is_a_state_on_the_muscle_axis_too(
    empty: sqlite3.Connection,
) -> None:
    with pytest.raises(state.StateError, match="trainer db import"):
        state.volume_history(empty, "muscle", "biceps", 3)


def test_an_axis_that_is_not_one_of_the_two_is_refused(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(state.StateError, match="not an axis"):
        state.volume_history(connection, "mood", "cheerful", 3)


# -- a round counts whole, to every label the exercise carries ----------------


def test_a_superset_is_four_rounds_of_each_exercise(
    connection: sqlite3.Connection,
) -> None:
    """CONTEXT.md § Volume: a block of two exercises for four rounds is four
    rounds of *each*, not two. Nothing is divided."""
    performed(
        connection,
        "2026-09-01",
        [(4, [("Barbell_Squat", None), ("Barbell_Deadlift", None)])],
    )

    squat = state.pattern_history(connection, "squat", 1)
    hinge = state.pattern_history(connection, "hip hinge", 1)

    assert squat.value is not None and hinge.value is not None
    assert (squat.value.volume, hinge.value.volume) == (4, 4)


def test_a_superset_counts_four_rounds_to_each_primary_muscle(
    connection: sqlite3.Connection,
) -> None:
    performed(
        connection,
        "2026-09-01",
        [(4, [("Barbell_Squat", None), ("Barbell_Deadlift", None)])],
    )

    quadriceps = state.volume_history(connection, "muscle", "quadriceps", 1)
    hamstrings = state.volume_history(connection, "muscle", "hamstrings", 1)

    assert quadriceps.value is not None and hamstrings.value is not None
    assert (quadriceps.value.volume, hamstrings.value.volume) == (4, 4)


def test_an_exercise_with_two_primary_muscles_counts_whole_to_both(
    connection: sqlite3.Connection,
) -> None:
    """The bench press is chest and triceps, and three rounds of it is three
    rounds of each -- the question is what is accumulating, not how the effort
    splits."""
    performed(connection, "2026-09-01", [straight("Bench_Press", 3)])

    for muscle in ("chest", "triceps"):
        answer = state.volume_history(connection, "muscle", muscle, 1)
        assert answer.value is not None
        assert answer.value.volume == 3


# -- an unreported workout is not adherence -----------------------------------


def test_an_unreported_workout_contributes_no_volume(
    connection: sqlite3.Connection,
) -> None:
    """Assuming a silent workout was performed inflates the volume at exactly
    the moment training stopped, which is the one direction the error must
    never run."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    performed(connection, "2026-09-03", [straight("Barbell_Curl", 2)])

    assert state.pattern_history(connection, "squat", 1).known is False


def test_an_unreported_workout_is_the_one_a_later_workout_overtook(
    connection: sqlite3.Connection,
) -> None:
    """CONTEXT.md § Unreported. A plan emitted this morning is not unreported;
    it is a workout still to do."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    later = prescribed(connection, "2026-09-05", [straight("Barbell_Squat", 5)])

    assert [found.workout_id for found in state.unreported(connection, "2026-09-06")] == []

    performed(connection, "2026-09-04", [straight("Barbell_Curl", 2)])

    overtaken = state.unreported(connection, "2026-09-06")
    assert [found.workout_id for found in overtaken] != [later]
    assert [found.prescribed_on for found in overtaken] == ["2026-09-01"]


def test_an_unreported_workout_states_how_long_it_has_been_waiting(
    connection: sqlite3.Connection,
) -> None:
    """The fact, and nothing else: *«there is a prescribed workout from twelve
    days ago with no report»*. Whether to ask about it is the agent's call."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    performed(connection, "2026-09-05", [straight("Barbell_Curl", 2)])

    (found,) = state.unreported(connection, "2026-09-13")

    assert found.prescribed_on == "2026-09-01"
    assert found.days_ago == 12


def test_reading_the_unreported_workouts_changes_nothing(
    connection: sqlite3.Connection,
) -> None:
    """Nothing closes it automatically and nothing assumes it happened."""
    identifier = prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    performed(connection, "2026-09-05", [straight("Barbell_Curl", 2)])

    state.unreported(connection, "2026-09-13")

    row = connection.execute(
        "SELECT state, report FROM workouts WHERE id = ?", (identifier,)
    ).fetchone()
    assert (row["state"], row["report"]) == ("prescribed", None)


# -- adherence ----------------------------------------------------------------


def test_adherence_distinguishes_the_three_things_that_happen_to_a_workout(
    connection: sqlite3.Connection,
) -> None:
    performed(
        connection,
        "2026-09-01",
        [straight("Barbell_Squat", 3)],
        prescribed_on="2026-09-01",
        prescription=[straight("Barbell_Squat", 3)],
    )
    prescribed(connection, "2026-09-02", [straight("Barbell_Deadlift", 3)])
    performed(connection, "2026-09-05", [straight("Barbell_Curl", 3)])

    answer = state.adherence_history(connection, 1)

    assert answer.value is not None
    assert answer.value.performed == 2
    assert answer.value.unreported == 1
    assert answer.value.unplanned == 1


def test_adherence_against_nothing_at_all_is_unknown(
    connection: sqlite3.Connection,
) -> None:
    """*«Nobody has trained yet»* is a fact to plan around, and it is not
    zero-percent adherence."""
    answer = state.adherence_history(connection, 2)

    assert answer.known is False
    assert "2 cycle(s)" in answer.about


def test_an_unreported_workout_is_not_counted_as_adherence(
    connection: sqlite3.Connection,
) -> None:
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    performed(connection, "2026-09-03", [straight("Barbell_Curl", 2)])

    answer = state.adherence_history(connection, 1)

    assert answer.value is not None
    assert answer.value.performed == 1


# -- the volume deficit -------------------------------------------------------


def deficits(
    connection: sqlite3.Connection, axis: str, cycles: int = 1
) -> dict[str, int]:
    return {
        found.key: found.deficit
        for found in state.volume_deficit(connection, cycles)
        if found.axis == axis
    }


def test_a_leg_workout_of_calf_raises_shows_on_the_pattern_axis(
    connection: sqlite3.Connection,
) -> None:
    """The squat and the hinge were planned and nothing was squatted or hinged
    -- which is what an axis of twelve patterns is for (ADR-0001)."""
    performed(
        connection,
        "2026-09-01",
        [straight("Standing_Calf_Raise", 4)],
        prescribed_on="2026-09-01",
        prescription=[straight("Barbell_Squat", 4), straight("Barbell_Deadlift", 4)],
    )

    assert deficits(connection, "pattern")["squat"] == 4
    assert deficits(connection, "pattern")["hip hinge"] == 4


def test_an_arm_workout_of_curls_shows_only_on_the_muscle_axis(
    connection: sqlite3.Connection,
) -> None:
    """Biceps, triceps and forearms are all `isolation`, so the pattern axis
    sees one undifferentiated bucket and the substitution vanishes into it.
    The muscle axis is the one that catches it."""
    performed(
        connection,
        "2026-09-01",
        [straight("Barbell_Curl", 8)],
        prescribed_on="2026-09-01",
        prescription=[straight("Barbell_Curl", 4), straight("Triceps_Pushdown", 4)],
    )

    assert deficits(connection, "pattern")["isolation"] == 0
    assert deficits(connection, "muscle")["triceps"] == 4
    assert deficits(connection, "muscle")["biceps"] == -4


def test_a_skipped_workout_is_the_whole_of_its_prescription(
    connection: sqlite3.Connection,
) -> None:
    """One of the four mechanisms the deficit absorbs, and the one a window
    counted in performed rows would be blind to."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    performed(connection, "2026-09-03", [straight("Barbell_Curl", 2)])

    assert deficits(connection, "pattern")["squat"] == 5


def test_a_workout_still_to_do_is_not_a_deficit(
    connection: sqlite3.Connection,
) -> None:
    """`trainer plan` writes a prescribed row every time it runs. Counted as a
    shortfall, the planner would read its own last prescription as volume it
    owes and add more to cover volume already scheduled."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])

    assert "squat" not in deficits(connection, "pattern")


def test_it_becomes_a_deficit_the_moment_it_becomes_unreported(
    connection: sqlite3.Connection,
) -> None:
    """The same row, the same window, and the only thing that changed is that
    a later workout was performed without it. The deficit and the unreported
    list read the same definition, so they cannot disagree about which
    prescriptions have had their chance."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 5)])
    performed(connection, "2026-09-03", [straight("Barbell_Curl", 2)])

    assert deficits(connection, "pattern")["squat"] == 5
    assert [found.prescribed_on for found in state.unreported(connection, "2026-09-04")] == [
        "2026-09-01"
    ]


def test_a_workout_cut_short_is_the_rounds_that_were_not_done(
    connection: sqlite3.Connection,
) -> None:
    performed(
        connection,
        "2026-09-01",
        [straight("Barbell_Squat", 2)],
        prescribed_on="2026-09-01",
        prescription=[straight("Barbell_Squat", 5)],
    )

    assert deficits(connection, "pattern")["squat"] == 3


def test_training_nobody_planned_is_a_negative_deficit(
    connection: sqlite3.Connection,
) -> None:
    """Left signed rather than clamped: the other half of the same fact."""
    performed(connection, "2026-09-01", [straight("Barbell_Curl", 6)])

    assert deficits(connection, "pattern")["isolation"] == -6


def test_the_deficit_is_reported_on_both_axes_in_one_call(
    connection: sqlite3.Connection,
) -> None:
    """Neither axis catches the other's degeneration, so an answer giving one
    of them would be read as the whole picture."""
    performed(connection, "2026-09-01", [straight("Barbell_Squat", 3)])

    axes = {found.axis for found in state.volume_deficit(connection, 1)}

    assert axes == {"pattern", "muscle"}


def test_a_movement_this_training_has_never_touched_is_not_a_deficit(
    connection: sqlite3.Connection,
) -> None:
    """Otherwise every listing would carry the hundreds of patterns and muscles
    nobody has planned or performed anything against."""
    performed(connection, "2026-09-01", [straight("Barbell_Squat", 3)])

    assert "carry" not in deficits(connection, "pattern")


def test_the_deficit_is_largest_first(connection: sqlite3.Connection) -> None:
    prescribed(
        connection,
        "2026-09-01",
        [straight("Barbell_Squat", 2), straight("Barbell_Deadlift", 9)],
    )
    performed(connection, "2026-09-03", [straight("Barbell_Curl", 1)])

    patterns = [
        found.key for found in state.volume_deficit(connection, 1) if found.axis == "pattern"
    ]

    assert patterns == ["hip hinge", "squat", "isolation"]


# -- the load trend -----------------------------------------------------------


def loads(connection: sqlite3.Connection, *kilos: float) -> None:
    """One workout per load, a week apart, all on the same exercise."""
    for week, load in enumerate(kilos, start=1):
        performed(
            connection, f"2026-08-{week:02d}", [straight("Barbell_Squat", 3, load)]
        )


def trend(connection: sqlite3.Connection, cycles: int = 2) -> str | None:
    answer = state.pattern_history(connection, "squat", cycles)
    assert answer.value is not None
    return answer.value.load_trend


def test_loads_that_climbed_trend_up(connection: sqlite3.Connection) -> None:
    loads(connection, 80.0, 85.0, 90.0)

    assert trend(connection) == "up"


def test_loads_that_fell_trend_down(connection: sqlite3.Connection) -> None:
    loads(connection, 90.0, 85.0, 80.0)

    assert trend(connection) == "down"


def test_a_load_that_did_not_move_is_flat(connection: sqlite3.Connection) -> None:
    loads(connection, 80.0, 80.0, 80.0)

    assert trend(connection) == "flat"


def test_a_move_smaller_than_the_band_is_still_flat(
    connection: sqlite3.Connection,
) -> None:
    """1 kg on an 80 kg squat is under the 2.5% the rule calls a move."""
    loads(connection, 80.0, 81.0)

    assert trend(connection) == "flat"


def test_one_recorded_load_says_nothing_about_a_direction(
    connection: sqlite3.Connection,
) -> None:
    """A first entry has nothing to have moved from, and `flat` would be an
    opinion about a single number."""
    loads(connection, 80.0)

    assert trend(connection) is None


def test_volume_with_no_load_behind_it_leaves_the_trend_unknown(
    connection: sqlite3.Connection,
) -> None:
    """Bodyweight training records no load at all. `known` is about the key,
    and the trend is separately nullable."""
    performed(connection, "2026-09-01", [straight("Barbell_Squat", 4)])
    performed(connection, "2026-09-02", [straight("Barbell_Squat", 4)])

    answer = state.pattern_history(connection, "squat", 1)

    assert answer.value is not None
    assert answer.value.volume == 8
    assert answer.value.load_trend is None


def test_a_warm_up_and_a_work_set_are_one_session_not_a_climb(
    connection: sqlite3.Connection,
) -> None:
    """Two blocks of the same exercise in one workout are one day's training.
    Read as two points they would say the loads nearly doubled, on a Tuesday."""
    performed(
        connection,
        "2026-09-01",
        [straight("Barbell_Squat", 2, 60.0), straight("Barbell_Squat", 3, 100.0)],
    )

    assert trend(connection, cycles=1) is None


def test_the_last_load_of_a_workout_is_the_one_that_counts(
    connection: sqlite3.Connection,
) -> None:
    """Warm up at 60 and work at 100 twice over, and the loads did not move."""
    for day in (1, 8):
        performed(
            connection,
            f"2026-09-{day:02d}",
            [straight("Barbell_Squat", 2, 60.0), straight("Barbell_Squat", 3, 100.0)],
        )

    assert trend(connection, cycles=1) == "flat"


def test_the_trend_is_a_ratio_so_the_heaviest_exercise_does_not_decide_it(
    connection: sqlite3.Connection,
) -> None:
    """The deadlift lost 5 kg off 200 and the squat gained 10 off 50. Averaged
    in kilos that is a wash; as a change per exercise it is clearly up."""
    performed(connection, "2026-08-01", [straight("Barbell_Curl", 3, 10.0)])
    performed(connection, "2026-08-08", [straight("Barbell_Curl", 3, 20.0)])
    performed(connection, "2026-08-15", [straight("Triceps_Pushdown", 3, 200.0)])
    performed(connection, "2026-08-22", [straight("Triceps_Pushdown", 3, 195.0)])

    answer = state.pattern_history(connection, "isolation", 1)

    assert answer.value is not None
    assert answer.value.load_trend == "up"


def test_the_trend_only_reads_inside_the_window(
    connection: sqlite3.Connection,
) -> None:
    """A load lifted five cycles ago is not what the last cycle trended."""
    loads(connection, 60.0, 65.0, 70.0, 75.0, 100.0, 100.0, 100.0, 100.0)

    assert trend(connection, cycles=1) == "flat"
    assert trend(connection, cycles=2) == "up"


# -- where in the rotation ----------------------------------------------------


def test_the_rotation_starts_at_the_first_workout_of_the_first_cycle(
    connection: sqlite3.Connection,
) -> None:
    where = state.rotation(connection)

    assert (where.performed, where.cycle, where.position) == (0, 1, 1)


def test_a_performed_workout_advances_the_rotation(
    connection: sqlite3.Connection,
) -> None:
    performed(connection, "2026-09-01", [straight("Barbell_Squat", 3)])

    where = state.rotation(connection)

    assert (where.performed, where.cycle, where.position) == (1, 1, 2)


def test_the_rotation_wraps_into_the_next_cycle(
    connection: sqlite3.Connection,
) -> None:
    """Four performed workouts of a four-workout cycle leave the next one at
    the first position of the second cycle."""
    for day in range(1, 5):
        performed(connection, f"2026-09-{day:02d}", [straight("Barbell_Squat", 3)])

    where = state.rotation(connection)

    assert (where.performed, where.cycle, where.position) == (4, 2, 1)


def test_a_prescribed_workout_does_not_advance_the_rotation(
    connection: sqlite3.Connection,
) -> None:
    """A cycle advances when a workout is performed, never when a date passes
    -- and a plan nobody did is not a workout done."""
    prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 3)])

    assert state.rotation(connection).position == 1


def test_the_rotation_is_as_long_as_the_declared_cycle(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    declared_training.write_text(
        'cycle_length = 2\nduration_cap_min = 60\nvolume_denominator = "cycle"\n'
        'split = [["chest"], ["legs"]]\nequipment = ["barbell"]\n',
        encoding="utf-8",
    )
    for day in range(1, 3):
        performed(connection, f"2026-09-{day:02d}", [straight("Barbell_Squat", 3)])

    where = state.rotation(connection)

    assert (where.cycle_length, where.cycle, where.position) == (2, 2, 1)


# -- last_performed_load ------------------------------------------------------


def test_a_recorded_load_comes_back(connection: sqlite3.Connection) -> None:
    """The answer that was *«I don't know»* for two sessions, because the
    columns `LOAD_SOURCE` named were on a table the load never moved to."""
    performed(connection, "2026-08-01", [straight("Barbell_Squat", 3, 80.0)])
    performed(connection, "2026-08-20", [straight("Barbell_Squat", 3, 92.5)])

    answer = state.last_performed_load(connection, "Barbell_Squat")

    assert answer.known is True
    assert answer.value == 92.5


def test_the_load_source_is_where_the_load_is_read_from(
    connection: sqlite3.Connection,
) -> None:
    """The constant is the contract with the view, and `_has_source` is what
    would notice if the two disagreed."""
    assert state._has_source(connection, state.LOAD_SOURCE)


def test_an_exercise_with_nothing_recorded_is_unknown(
    connection: sqlite3.Connection,
) -> None:
    performed(connection, "2026-08-01", [straight("Barbell_Deadlift", 3, 100.0)])

    assert state.last_performed_load(connection, "Barbell_Squat").known is False


def test_a_prescribed_workout_carries_no_load_anybody_lifted(
    connection: sqlite3.Connection,
) -> None:
    """A plan prescribes no load, and a prescribed row read as one would answer
    with a number nobody lifted."""
    identifier = prescribed(connection, "2026-09-01", [straight("Barbell_Squat", 3)])
    connection.execute(
        "UPDATE workout_exercises SET load_kg = 300 WHERE block_id IN "
        "(SELECT id FROM workout_blocks WHERE workout_id = ?)",
        (identifier,),
    )

    assert state.last_performed_load(connection, "Barbell_Squat").known is False


def test_a_bodyweight_workout_does_not_hide_the_last_one_that_had_a_load(
    connection: sqlite3.Connection,
) -> None:
    """A performed workout that recorded no load is not a load of zero."""
    performed(connection, "2026-08-01", [straight("Barbell_Squat", 3, 60.0)])
    performed(connection, "2026-08-20", [straight("Barbell_Squat", 3, None)])

    assert state.last_performed_load(connection, "Barbell_Squat").value == 60.0


def test_two_workouts_on_one_day_are_ordered_by_which_was_written_second(
    connection: sqlite3.Connection,
) -> None:
    """*The load this exercise was last performed with* is a fact, not
    whichever row SQLite reached first."""
    performed(connection, "2026-08-01", [straight("Barbell_Squat", 3, 60.0)])
    performed(connection, "2026-08-01", [straight("Barbell_Squat", 3, 70.0)])

    assert state.last_performed_load(connection, "Barbell_Squat").value == 70.0


def test_the_last_load_is_not_narrowed_by_a_window(
    connection: sqlite3.Connection,
) -> None:
    """Coming back after two months, what the bar had on it in June is the only
    number anybody has."""
    performed(connection, "2026-01-01", [straight("Barbell_Squat", 3, 60.0)])
    for day in range(1, 9):
        performed(connection, f"2026-09-{day:02d}", [straight("Barbell_Curl", 3, 10.0)])

    assert state.last_performed_load(connection, "Barbell_Squat").value == 60.0


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


def test_no_view_to_read_is_unknown_and_does_not_raise(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There being nowhere a load could have been recorded is a different fact
    from a view holding nothing for this exercise, and both are honestly *«I
    don't know»* to the caller rather than a traceback about a missing view."""
    monkeypatch.setattr(state, "LOAD_SOURCE", state._LoadSource(table="nowhere_at_all"))

    answer = state.last_performed_load(connection, "Barbell_Squat")

    assert answer.known is False
    assert answer.value is None
