"""Scoring the database against the hand-decided reference set.

This file never depends on what the real 60-80 movements say -- the parser
and the scoring logic are tested against small tables built for the
purpose, the same way test_migrations.py tests the migration mechanism
against throwaway `.sql` files rather than the real schema.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, enrichment, migrations, reference_set
from trainer.engine.catalog import Exercise
from trainer.engine.reference_set import ReferenceRow


def exercise(**overrides: object) -> Exercise:
    base: dict[str, object] = {
        "id": "Bench_Press",
        "name": "Bench Press",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("chest",),
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
        yield opened


def stock(connection: sqlite3.Connection, *exercises: Exercise) -> None:
    catalog.import_exercises(connection, exercises, allow_pruning=True)


TABLE_HEADER = (
    "| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |\n"
    "|---|---|---|---|---|---|---|---|---|---|\n"
)


def table(*rows: str) -> str:
    return TABLE_HEADER + "\n".join(rows) + "\n"


def row(
    exercise_id: str,
    pattern: str = "hip hinge",
    joints: str = "hip, lumbar spine",
    axial: str = "yes",
    stability: str = "medium",
    setup: str = "3",
    uncertain: str = "",
    note: str = "note",
    name: str = "Some Exercise",
    equipment: str = "barbell",
) -> str:
    return (
        f"| {exercise_id} | {name} | {equipment} | {pattern} | {joints} | {axial} "
        f"| {stability} | {setup} | {uncertain} | {note} |"
    )


# --- parsing ------------------------------------------------------------------


def test_a_well_formed_row_parses() -> None:
    (parsed,) = reference_set.parse(table(row("Barbell_Deadlift")))

    assert parsed == ReferenceRow(
        id="Barbell_Deadlift",
        movement_pattern="hip hinge",
        loaded_joints=("hip", "lumbar spine"),
        spinal_axial_load="yes",
        required_stability="medium",
        setup_cost_min=3,
        uncertain=False,
    )


def test_the_uncertain_marker_is_read() -> None:
    (parsed,) = reference_set.parse(table(row("Spell_Caster", uncertain="?")))

    assert parsed.uncertain is True


def test_bold_values_are_read_the_same_as_plain_ones() -> None:
    (parsed,) = reference_set.parse(table(row("Sled_Overhead_Backward_Walk", pattern="**carry**")))

    assert parsed.movement_pattern == "carry"


def test_a_dash_cell_is_absent_not_a_literal_dash() -> None:
    (parsed,) = reference_set.parse(table(row("Battling_Ropes", pattern="-")))

    assert parsed.movement_pattern is None


def test_an_empty_loaded_joints_cell_is_none_not_an_empty_set() -> None:
    """`None` (not decided) and `()` (decided to be empty) are different
    claims, and only the cell's own content says which one this is."""
    (parsed,) = reference_set.parse(table(row("Foo", joints="")))

    assert parsed.loaded_joints is None


def test_rows_are_returned_in_file_order() -> None:
    parsed = reference_set.parse(table(row("B_Exercise"), row("A_Exercise")))

    assert [r.id for r in parsed] == ["B_Exercise", "A_Exercise"]


def test_a_duplicate_id_is_refused() -> None:
    with pytest.raises(reference_set.ReferenceSetError):
        reference_set.parse(table(row("Barbell_Deadlift"), row("Barbell_Deadlift")))


def test_prose_between_tables_is_ignored() -> None:
    text = "Some explanation.\n\n" + table(row("Barbell_Deadlift")) + "\nMore prose after.\n"

    parsed = reference_set.parse(text)

    assert len(parsed) == 1


def test_a_table_with_no_data_rows_parses_to_empty() -> None:
    assert reference_set.parse(TABLE_HEADER) == ()


# --- loading --------------------------------------------------------------


def test_loading_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(reference_set.ReferenceSetError):
        reference_set.load(tmp_path / "nope.md")


def test_loading_a_file_with_no_data_rows_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text(TABLE_HEADER, encoding="utf-8")

    with pytest.raises(reference_set.ReferenceSetError):
        reference_set.load(empty)


def test_the_default_path_is_under_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(reference_set.REFERENCE_SET_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert reference_set.reference_set_path() == (
        tmp_path / "docs" / "enrichment" / "reference-set.md"
    )


def test_the_path_is_overridable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.md"
    monkeypatch.setenv(reference_set.REFERENCE_SET_ENV_VAR, str(elsewhere))

    assert reference_set.reference_set_path() == elsewhere


# --- checking ---------------------------------------------------------------


def test_a_matching_value_counts_as_a_match(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'horizontal push', "
        "movement_pattern_source = 'rule' WHERE id = 'Bench_Press'"
    )
    reference = reference_set.parse(table(row("Bench_Press", pattern="horizontal push")))

    (pattern_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "movement_pattern"
    ]

    assert pattern_check == reference_set.FieldCheck(
        field="movement_pattern", total=1, matches=1, disagreements=(), missing=()
    )
    assert pattern_check.accuracy == 1.0


def test_a_different_value_is_a_disagreement(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'rule' WHERE id = 'Bench_Press'"
    )
    reference = reference_set.parse(table(row("Bench_Press", pattern="horizontal push")))

    (pattern_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "movement_pattern"
    ]

    assert pattern_check.matches == 0
    assert pattern_check.disagreements == ("Bench_Press",)
    assert pattern_check.accuracy == 0.0


def test_a_null_value_in_the_database_is_missing_not_a_disagreement(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, exercise())
    reference = reference_set.parse(table(row("Bench_Press", pattern="horizontal push")))

    (pattern_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "movement_pattern"
    ]

    assert pattern_check.disagreements == ()
    assert pattern_check.missing == ("Bench_Press",)


def test_loaded_joints_agree_regardless_of_order(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET loaded_joints = '[\"elbow\", \"shoulder\"]', "
        "loaded_joints_source = 'rule' WHERE id = 'Bench_Press'"
    )
    reference = reference_set.parse(
        table(row("Bench_Press", joints="shoulder, elbow"))  # reversed order
    )

    (joints_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "loaded_joints"
    ]

    assert joints_check.matches == 1


def test_a_deliberately_empty_loaded_joints_is_a_decided_value_not_missing(
    connection: sqlite3.Connection,
) -> None:
    """A neck-isolation row's answer is `()` -- none of the seven joints --
    and that is a real, decided value, distinguished from "nothing has
    looked at this row" by `loaded_joints_source`, never by the value being
    empty. A bug here would silently score every such row as `missing`."""
    stock(connection, exercise(primary_muscles=("neck",)))
    connection.execute(
        "UPDATE exercises SET loaded_joints = '[]', loaded_joints_source = 'rule' "
        "WHERE id = 'Bench_Press'"
    )
    reference = (
        ReferenceRow(
            id="Bench_Press",
            movement_pattern=None,
            loaded_joints=(),
            spinal_axial_load=None,
            required_stability=None,
            setup_cost_min=None,
            uncertain=False,
        ),
    )

    (joints_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "loaded_joints"
    ]

    assert joints_check.matches == 1
    assert joints_check.missing == ()


def test_a_reference_id_unknown_to_the_catalog_is_refused(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, exercise())
    reference = reference_set.parse(table(row("Not_A_Real_Id")))

    with pytest.raises(reference_set.ReferenceSetError):
        reference_set.check(connection, reference)


def test_movement_pattern_is_scored_independently_of_the_other_fields(
    connection: sqlite3.Connection,
) -> None:
    """A perfect loaded_joints score must not hide a wrong movement_pattern
    -- the two are never combined into one figure anywhere in this module."""
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET "
        "movement_pattern = 'isolation', movement_pattern_source = 'rule', "
        "loaded_joints = '[\"shoulder\", \"elbow\"]', loaded_joints_source = 'rule' "
        "WHERE id = 'Bench_Press'"
    )
    reference = reference_set.parse(
        table(row("Bench_Press", pattern="horizontal push", joints="shoulder, elbow"))
    )

    results = {c.field: c for c in reference_set.check(connection, reference)}

    assert results["movement_pattern"].accuracy == 0.0
    assert results["loaded_joints"].accuracy == 1.0


def test_a_field_the_reference_never_names_has_no_total(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())
    reference = reference_set.parse(
        table(row("Bench_Press", setup="-"))  # every column but setup_cost_min
    )

    (setup_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "setup_cost_min"
    ]

    assert setup_check.total == 0
    assert setup_check.accuracy == 0.0


def test_a_curated_value_is_read_the_same_as_a_rule_value(connection: sqlite3.Connection) -> None:
    """`check` reports what is true now, not who decided it."""
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'horizontal push', "
        "movement_pattern_source = 'curated' WHERE id = 'Bench_Press'"
    )
    reference = reference_set.parse(table(row("Bench_Press", pattern="horizontal push")))

    (pattern_check,) = [
        c for c in reference_set.check(connection, reference) if c.field == "movement_pattern"
    ]

    assert pattern_check.matches == 1


def test_every_field_reconciles(connection: sqlite3.Connection) -> None:
    stock(
        connection,
        exercise(id="a"),
        exercise(id="b", name="Deadlift", primary_muscles=("lower back",)),
    )
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'horizontal push', "
        "movement_pattern_source = 'rule' WHERE id = 'a'"
    )
    reference = reference_set.parse(
        table(
            row("a", pattern="horizontal push"),
            row("b", pattern="isolation"),  # will disagree or be missing
        )
    )

    for one in reference_set.check(connection, reference):
        assert one.matches + len(one.disagreements) + len(one.missing) == one.total


# --- against the real, enriched catalog --------------------------------------


def test_the_check_runs_against_a_real_derived_catalog(connection: sqlite3.Connection) -> None:
    """Not an accuracy assertion -- the real reference set is ticket 03's own
    hand-curated deliverable, not this test suite's business -- only that
    the whole pipeline runs end to end without raising."""
    stock(connection, *catalog.load())
    enrichment.run(connection)
    reference = reference_set.parse(
        table(row("Barbell_Deadlift", pattern="hip hinge", joints="hip, lumbar spine"))
    )

    results = reference_set.check(connection, reference)

    assert len(results) == len(reference_set.FIELDS)


# --- the committed reference set ---------------------------------------------

COMMITTED = Path(__file__).resolve().parents[1] / "docs" / "enrichment" / "reference-set.md"


def test_the_committed_reference_set_has_60_to_80_distinct_movements() -> None:
    rows = reference_set.load(COMMITTED)

    assert 60 <= len(rows) <= 80
    assert len({row.id for row in rows}) == len(rows)


def test_the_committed_reference_set_spans_the_twelve_patterns() -> None:
    rows = reference_set.load(COMMITTED)

    patterns = {row.movement_pattern for row in rows if row.movement_pattern is not None}
    assert patterns >= set(enrichment.MOVEMENT_PATTERNS)


def test_the_committed_reference_set_measures_the_real_rules(
    connection: sqlite3.Connection,
) -> None:
    """The number this whole session exists to produce: how often the rules
    written blind of this file get `movement_pattern` right against it,
    written blind of the rules. Floored below the measured 94.2% rather than
    pinned to it exactly, so a harmless future rewording of a rule does not
    break this test -- an actual drop in accuracy still will."""
    stock(connection, *catalog.load())
    enrichment.run(connection)
    reference = reference_set.load(COMMITTED)

    results = {c.field: c for c in reference_set.check(connection, reference)}

    pattern = results["movement_pattern"]
    assert pattern.accuracy > 0.90
    assert pattern.disagreements == ()
