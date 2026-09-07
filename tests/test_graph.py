"""Loading the `variant_of` / `regression_of` graph from `docs/enrichment/graph.md`."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich
from trainer.engine import catalog, database, graph, migrations
from trainer.engine.catalog import Exercise

TEXT = """\
# A throwaway graph

## Variant groups

| representative | member | note |
|---|---|---|
| `Standing_Military_Press` | `Arnold_Dumbbell_Press` | same press |
| `Standing_Military_Press` | `Kettlebell_Arnold_Press` | same press, kettlebell |

## Regression edges

| easier | harder | note |
|---|---|---|
| `Band_Assisted_Pull-Up` | `Pullups` | the band removes bodyweight |
"""


def exercise(exercise_id: str, name: str) -> Exercise:
    return Exercise(
        id=exercise_id,
        name=name,
        force=None,
        level="beginner",
        mechanic="compound",
        equipment="body only",
        category="strength",
        primary_muscles=("shoulders",),
        secondary_muscles=(),
        instructions=(),
        images=(),
    )


THE_FOUR = (
    exercise("Standing_Military_Press", "Standing Military Press"),
    exercise("Arnold_Dumbbell_Press", "Arnold Dumbbell Press"),
    exercise("Kettlebell_Arnold_Press", "Kettlebell Arnold Press"),
    exercise("Band_Assisted_Pull-Up", "Band Assisted Pull-Up"),
    exercise("Pullups", "Pullups"),
)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(opened, THE_FOUR, allow_pruning=True)
        yield opened


# --- path resolution ------------------------------------------------------


def test_the_default_path_is_under_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(graph.GRAPH_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert graph.graph_path() == tmp_path / "docs" / "enrichment" / "graph.md"


def test_the_path_is_overridable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.md"
    monkeypatch.setenv(graph.GRAPH_ENV_VAR, str(elsewhere))

    assert graph.graph_path() == elsewhere


def test_loading_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(graph.GraphError):
        graph.load(tmp_path / "nope.md")


def test_a_file_naming_neither_table_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text(
        "## Variant groups\n\n| representative | member | note |\n|---|---|---|\n\n"
        "## Regression edges\n\n| easier | harder | note |\n|---|---|---|\n",
        encoding="utf-8",
    )

    with pytest.raises(graph.GraphError):
        graph.load(empty)


# --- parsing ----------------------------------------------------------------


def test_variant_rows_sharing_a_representative_group_together() -> None:
    variants, regressions = graph.parse(TEXT)

    assert len(variants) == 1
    (group,) = variants
    assert group.representative == "Standing_Military_Press"
    assert set(group.members) == {"Arnold_Dumbbell_Press", "Kettlebell_Arnold_Press"}


def test_regression_rows_are_read() -> None:
    _, regressions = graph.parse(TEXT)

    assert regressions == (graph.Regression("Band_Assisted_Pull-Up", "Pullups"),)


def test_a_missing_section_is_refused() -> None:
    with pytest.raises(graph.GraphError):
        graph.parse("## Variant groups\n\n| representative | member | note |\n|---|---|---|\n")


# --- validation ---------------------------------------------------------


def test_a_representative_that_is_also_a_member_is_a_chain_and_is_refused() -> None:
    variants = (
        graph.VariantGroup("A", ("B",)),
        graph.VariantGroup("B", ("C",)),
    )

    with pytest.raises(graph.GraphError):
        graph.validate(variants, ())


def test_a_member_of_two_groups_is_refused() -> None:
    variants = (
        graph.VariantGroup("A", ("C",)),
        graph.VariantGroup("B", ("C",)),
    )

    with pytest.raises(graph.GraphError):
        graph.validate(variants, ())


def test_a_direct_regression_cycle_is_refused() -> None:
    regressions = (graph.Regression("A", "B"), graph.Regression("B", "A"))

    with pytest.raises(graph.GraphError):
        graph.validate((), regressions)


def test_a_longer_regression_cycle_is_refused() -> None:
    regressions = (
        graph.Regression("A", "B"),
        graph.Regression("B", "C"),
        graph.Regression("C", "A"),
    )

    with pytest.raises(graph.GraphError):
        graph.validate((), regressions)


def test_two_edges_into_the_same_harder_row_is_not_a_cycle() -> None:
    regressions = (graph.Regression("A", "C"), graph.Regression("B", "C"))

    graph.validate((), regressions)  # does not raise


def test_a_valid_star_and_dag_pass() -> None:
    variants, regressions = graph.parse(TEXT)

    graph.validate(variants, regressions)  # does not raise


# --- writing ------------------------------------------------------------


def test_variant_of_is_written_curated(connection: sqlite3.Connection) -> None:
    variants, regressions = graph.parse(TEXT)

    graph.apply(connection, variants, regressions)

    rows = connection.execute(
        "SELECT id, variant_of, variant_of_source FROM exercises "
        "WHERE id IN ('Arnold_Dumbbell_Press', 'Kettlebell_Arnold_Press')"
    ).fetchall()
    for row in rows:
        assert row["variant_of"] == "Standing_Military_Press"
        assert row["variant_of_source"] == "curated"


def test_the_representative_itself_carries_no_variant_of(
    connection: sqlite3.Connection,
) -> None:
    variants, regressions = graph.parse(TEXT)

    graph.apply(connection, variants, regressions)

    row = connection.execute(
        "SELECT variant_of FROM exercises WHERE id = 'Standing_Military_Press'"
    ).fetchone()
    assert row["variant_of"] is None


def test_regression_of_points_from_easier_to_harder(connection: sqlite3.Connection) -> None:
    variants, regressions = graph.parse(TEXT)

    graph.apply(connection, variants, regressions)

    row = connection.execute(
        "SELECT regression_of, regression_of_source FROM exercises "
        "WHERE id = 'Band_Assisted_Pull-Up'"
    ).fetchone()
    assert row["regression_of"] == "Pullups"
    assert row["regression_of_source"] == "curated"


def test_applying_twice_changes_nothing(connection: sqlite3.Connection) -> None:
    variants, regressions = graph.parse(TEXT)

    graph.apply(connection, variants, regressions)
    before = connection.execute("SELECT * FROM exercises ORDER BY id").fetchall()
    graph.apply(connection, variants, regressions)
    after = connection.execute("SELECT * FROM exercises ORDER BY id").fetchall()

    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_an_unknown_id_is_refused(connection: sqlite3.Connection) -> None:
    variants = (graph.VariantGroup("Standing_Military_Press", ("Not_A_Real_Id",)),)

    with pytest.raises(graph.GraphError):
        graph.apply(connection, variants, ())


def test_a_dangling_reference_is_refused_at_the_database_too(
    connection: sqlite3.Connection,
) -> None:
    """The app-level check in `apply()` is the friendly message; the FK
    constraint from `0003_enrichment.sql` is the backstop `graph.py` does not
    have to reimplement, exercised here by going around `apply()` entirely."""
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE exercises SET variant_of = 'Nonexistent' WHERE id = 'Pullups'"
        )


def test_a_rule_can_never_overwrite_a_curated_variant_of(
    connection: sqlite3.Connection,
) -> None:
    variants, regressions = graph.parse(TEXT)
    graph.apply(connection, variants, regressions)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE exercises SET variant_of = 'Pullups', variant_of_source = 'rule' "
            "WHERE id = 'Arnold_Dumbbell_Press'"
        )


# --- against the committed file ------------------------------------------

COMMITTED = Path(__file__).resolve().parents[1] / "docs" / "enrichment" / "graph.md"


def test_the_committed_file_loads_and_validates() -> None:
    variants, regressions = graph.load(COMMITTED)

    graph.validate(variants, regressions)  # does not raise
    assert len(variants) > 0
    assert len(regressions) > 0


def test_the_committed_file_resolves_trainers_running_example(
    database_file: Path,
) -> None:
    """TRAINER.md's own case, by id: `Arnold_Dumbbell_Press`,
    `Kettlebell_Arnold_Press` and `Standing_Military_Press` are one group."""
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection)
        catalog.import_exercises(connection, catalog.load(), allow_pruning=True)

        variants, regressions = graph.load(COMMITTED)
        graph.apply(connection, variants, regressions)

        rows = {
            str(r["id"]): r["variant_of"]
            for r in connection.execute(
                "SELECT id, variant_of FROM exercises WHERE id IN "
                "('Arnold_Dumbbell_Press', 'Kettlebell_Arnold_Press', "
                "'Standing_Military_Press')"
            )
        }
    assert rows["Arnold_Dumbbell_Press"] == "Standing_Military_Press"
    assert rows["Kettlebell_Arnold_Press"] == "Standing_Military_Press"
    assert rows["Standing_Military_Press"] is None


# --- reading the graph back -----------------------------------------------


@pytest.fixture()
def applied(connection: sqlite3.Connection) -> sqlite3.Connection:
    """The throwaway graph above, written onto the five rows, and enriched.

    `compare` reads both halves -- the four fields TRAINER.md names come from
    `enrich derive`, the relation from the curated file -- so a fixture that
    applied only one of them would leave every case failing on the other.
    """
    enrich(
        connection,
        {
            "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
            "Arnold_Dumbbell_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 1),
            "Kettlebell_Arnold_Press": ("vertical push", "shoulder, elbow", "yes", "high", 1),
            "Band_Assisted_Pull-Up": ("vertical pull", "shoulder, elbow", "no", "medium", 2),
            "Pullups": ("vertical pull", "shoulder, elbow", "no", "high", 1),
        },
    )
    graph.apply(connection, *graph.parse(TEXT))
    return connection


def test_a_member_and_its_representative_are_the_same_movement(
    applied: sqlite3.Connection,
) -> None:
    found = graph.compare(applied, "Arnold_Dumbbell_Press", "Standing_Military_Press")

    assert found.same_movement is True
    assert found.easier is None
    assert found.a.movement_pattern == "vertical push"
    assert found.b.setup_cost_min == 3


def test_two_members_of_one_group_are_the_same_movement(
    applied: sqlite3.Connection,
) -> None:
    """TRAINER.md's running example, neither side of which is the
    representative -- the case a naive `a.variant_of == b.id` misses."""
    found = graph.compare(applied, "Arnold_Dumbbell_Press", "Kettlebell_Arnold_Press")

    assert found.same_movement is True


def test_the_easier_side_is_named_by_id_whichever_way_round_it_is_asked(
    applied: sqlite3.Connection,
) -> None:
    forwards = graph.compare(applied, "Band_Assisted_Pull-Up", "Pullups")
    backwards = graph.compare(applied, "Pullups", "Band_Assisted_Pull-Up")

    assert forwards.easier == backwards.easier == "Band_Assisted_Pull-Up"
    assert forwards.same_movement is False
    assert "regression" in forwards.summary


def test_an_unrelated_pair_says_so_rather_than_saying_nothing(
    applied: sqlite3.Connection,
) -> None:
    found = graph.compare(applied, "Standing_Military_Press", "Pullups")

    assert found.same_movement is False
    assert found.easier is None
    assert found.summary == "neither the same movement nor a regression of one another"
    assert found.a.movement_pattern != found.b.movement_pattern


def test_an_id_the_catalog_does_not_have_is_named(applied: sqlite3.Connection) -> None:
    with pytest.raises(catalog.CatalogError, match="Pullupz"):
        graph.compare(applied, "Pullups", "Pullupz")
