"""Loading `docs/enrichment/residue.md`'s hand-read decisions into the catalog.

Small throwaway tables exercise the writer's own behaviour, the same way
`test_reference_set.py` never depends on the real 60-80 movements to test its
parser. The committed file gets its own, narrower set of tests at the bottom.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, enrichment, migrations, residue
from trainer.engine.catalog import Exercise
from trainer.engine.reference_set import parse

TABLE_HEADER = (
    "| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |\n"
    "|---|---|---|---|---|---|---|---|---|---|\n"
)


def table(*rows: str) -> str:
    return TABLE_HEADER + "\n".join(rows) + "\n"


def row(
    exercise_id: str,
    pattern: str = "isolation",
    joints: str = "lumbar spine",
    axial: str = "no",
    stability: str = "medium",
    setup: str = "0",
    uncertain: str = "",
    note: str = "note",
    name: str = "Some Exercise",
    equipment: str = "body only",
) -> str:
    return (
        f"| {exercise_id} | {name} | {equipment} | {pattern} | {joints} | {axial} "
        f"| {stability} | {setup} | {uncertain} | {note} |"
    )


def exercise(**overrides: object) -> Exercise:
    base: dict[str, object] = {
        "id": "Some_Exercise",
        "name": "Some Exercise",
        "force": None,
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "body only",
        "category": "strength",
        "primary_muscles": ("abdominals",),
        "secondary_muscles": (),
        "instructions": ("Do the thing.",),
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


# --- path resolution ----------------------------------------------------------


def test_the_default_path_is_under_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(residue.RESIDUE_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert residue.residue_path() == tmp_path / "docs" / "enrichment" / "residue.md"


def test_the_path_is_overridable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.md"
    monkeypatch.setenv(residue.RESIDUE_ENV_VAR, str(elsewhere))

    assert residue.residue_path() == elsewhere


def test_loading_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(residue.ResidueError):
        residue.load(tmp_path / "nope.md")


def test_loading_a_file_with_no_data_rows_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text(TABLE_HEADER, encoding="utf-8")

    with pytest.raises(residue.ResidueError):
        residue.load(empty)


def test_a_malformed_file_is_a_residue_error_not_a_reference_set_error(
    tmp_path: Path,
) -> None:
    """`load` reuses `reference_set.parse`, and wraps its own error type --
    callers only need to know about one exception from this module."""
    broken = tmp_path / "broken.md"
    broken.write_text(table(row("Dup"), row("Dup")), encoding="utf-8")

    with pytest.raises(residue.ResidueError):
        residue.load(broken)


# --- writing --------------------------------------------------------------


def test_a_decided_row_is_written_curated_on_all_five_fields(
    connection: sqlite3.Connection,
) -> None:
    """`enrichment.run` skips a curated row entirely -- it never falls
    through to fill the other four once `movement_pattern_source` is
    `curated` -- so this has to write all five itself."""
    stock(connection, exercise())
    rows = parse(
        table(
            row(
                "Some_Exercise",
                pattern="core rotation",
                joints="lumbar spine",
                axial="no",
                stability="low",
                setup="2",
            )
        )
    )

    report = residue.apply(connection, rows)

    row_data = connection.execute(
        "SELECT movement_pattern, movement_pattern_source, loaded_joints, "
        "loaded_joints_source, spinal_axial_load, spinal_axial_load_source, "
        "required_stability, required_stability_source, setup_cost_min, "
        "setup_cost_min_source FROM exercises WHERE id = 'Some_Exercise'"
    ).fetchone()
    assert row_data["movement_pattern"] == "core rotation"
    assert row_data["movement_pattern_source"] == "curated"
    assert json.loads(row_data["loaded_joints"]) == ["lumbar spine"]
    assert row_data["loaded_joints_source"] == "curated"
    assert row_data["spinal_axial_load"] == "no"
    assert row_data["spinal_axial_load_source"] == "curated"
    assert row_data["required_stability"] == "low"
    assert row_data["required_stability_source"] == "curated"
    assert row_data["setup_cost_min"] == 2
    assert row_data["setup_cost_min_source"] == "curated"
    assert report.decided == ("Some_Exercise",)
    assert report.null == ()


def test_a_null_decision_writes_only_the_pattern_source(
    connection: sqlite3.Connection,
) -> None:
    """B6: the pattern is decided to be null, on purpose. The other four
    fields have no honest basis without a pattern and stay untouched."""
    stock(connection, exercise())
    rows = parse(table(row("Some_Exercise", pattern="-")))

    report = residue.apply(connection, rows)

    row_data = connection.execute(
        "SELECT movement_pattern, movement_pattern_source, loaded_joints_source, "
        "spinal_axial_load_source, required_stability_source, setup_cost_min_source "
        "FROM exercises WHERE id = 'Some_Exercise'"
    ).fetchone()
    assert row_data["movement_pattern"] is None
    assert row_data["movement_pattern_source"] == "curated"
    assert row_data["loaded_joints_source"] is None
    assert row_data["spinal_axial_load_source"] is None
    assert row_data["required_stability_source"] is None
    assert row_data["setup_cost_min_source"] is None
    assert report.decided == ()
    assert report.null == ("Some_Exercise",)


def test_curated_overwrites_a_rule_value(connection: sqlite3.Connection) -> None:
    """Curated always wins -- the trigger only refuses the other direction."""
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'rule' WHERE id = 'Some_Exercise'"
    )
    rows = parse(table(row("Some_Exercise", pattern="core rotation")))

    residue.apply(connection, rows)

    row_data = connection.execute(
        "SELECT movement_pattern, movement_pattern_source FROM exercises "
        "WHERE id = 'Some_Exercise'"
    ).fetchone()
    assert row_data["movement_pattern"] == "core rotation"
    assert row_data["movement_pattern_source"] == "curated"


def test_applying_twice_changes_nothing(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())
    rows = parse(table(row("Some_Exercise", pattern="core rotation")))

    residue.apply(connection, rows)
    before = connection.execute("SELECT * FROM exercises WHERE id = 'Some_Exercise'").fetchone()
    residue.apply(connection, rows)
    after = connection.execute("SELECT * FROM exercises WHERE id = 'Some_Exercise'").fetchone()

    assert tuple(before) == tuple(after)


def test_an_id_the_catalog_does_not_have_is_refused(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())
    rows = parse(table(row("Not_A_Real_Id")))

    with pytest.raises(residue.ResidueError):
        residue.apply(connection, rows)


def test_a_pattern_with_no_joints_axial_stability_or_setup_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """A decided pattern with an undecided secondary field is a broken row in
    the file, not a state to write -- the five are decided together."""
    stock(connection, exercise())
    rows = parse(table(row("Some_Exercise", pattern="core rotation", setup="-")))

    with pytest.raises(residue.ResidueError):
        residue.apply(connection, rows)


def test_a_rule_can_never_overwrite_a_curated_residue_value(
    connection: sqlite3.Connection,
) -> None:
    """The migration's own trigger, exercised from this side of the door."""
    stock(connection, exercise())
    rows = parse(table(row("Some_Exercise", pattern="core rotation")))
    residue.apply(connection, rows)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE exercises SET movement_pattern = 'isolation', "
            "movement_pattern_source = 'rule' WHERE id = 'Some_Exercise'"
        )


# --- against the committed file ------------------------------------------

COMMITTED = Path(__file__).resolve().parents[1] / "docs" / "enrichment" / "residue.md"


def test_the_committed_file_loads() -> None:
    rows = residue.load(COMMITTED)

    assert len(rows) > 0
    assert len({row.id for row in rows}) == len(rows)


def test_the_committed_file_names_no_id_the_rule_can_already_decide(
    connection: sqlite3.Connection,
) -> None:
    """The whole point of reconciling against the real rules: a row the
    rule now reaches has to leave this file, not sit here unused."""
    stock(connection, *catalog.load())
    enrichment.run(connection)
    rows = residue.load(COMMITTED)

    still_undecided = {
        str(r["id"])
        for r in connection.execute(
            "SELECT id FROM exercises WHERE category = 'strength' "
            "AND movement_pattern_source IS NULL"
        )
    }
    assert {row.id for row in rows} == still_undecided


def test_applying_the_committed_file_decides_every_strength_row(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, *catalog.load())
    enrichment.run(connection)

    residue.apply(connection, residue.load(COMMITTED))

    left = connection.execute(
        "SELECT COUNT(*) AS total FROM exercises WHERE category = 'strength' "
        "AND movement_pattern_source IS NULL"
    ).fetchone()
    assert left["total"] == 0


def test_applying_the_committed_file_does_not_touch_non_strength_rows(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, *catalog.load())
    enrichment.run(connection)

    residue.apply(connection, residue.load(COMMITTED))

    touched = connection.execute(
        "SELECT COUNT(*) AS total FROM exercises WHERE category != 'strength' "
        "AND movement_pattern_source IS NOT NULL"
    ).fetchone()
    assert touched["total"] == 0
