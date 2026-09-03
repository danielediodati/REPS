"""What the catalog actually contains, counted.

The number this exists for is how many of the 876 are strength work. It is the
real size of the pool the admissible set is drawn from, and the multiplier on
session 2's enrichment -- deterministic rules and hand decisions, with no
model and no network anywhere in it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, enrichment, migrations


def record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "Bench_Press",
        "name": "Bench Press",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primaryMuscles": ["chest"],
        "secondaryMuscles": ["triceps"],
        "instructions": ["Press."],
        "images": ["Bench_Press/0.jpg"],
    }
    base.update(overrides)
    return base


def loaded(tmp_path: Path, *records: dict[str, object]) -> tuple[catalog.Exercise, ...]:
    path = tmp_path / "exercises.json"
    path.write_text(json.dumps(list(records)), encoding="utf-8")
    return catalog.load(path)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        yield opened


def stock(connection: sqlite3.Connection, *exercises: catalog.Exercise) -> None:
    catalog.import_exercises(connection, exercises, allow_pruning=True)


def breakdown(stats: catalog.CatalogStats, field: str) -> catalog.Breakdown:
    (found,) = [one for one in stats.breakdowns if one.field == field]
    return found


# --- the shape of the answer ------------------------------------------------


def test_every_scalar_field_gets_a_breakdown(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(connection, *loaded(tmp_path, record()))

    stats = catalog.stats(connection)

    assert [one.field for one in stats.breakdowns] == list(catalog.SCALAR_FILTERS)


def test_a_breakdown_counts_the_values_it_finds(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", equipment="barbell"),
            record(id="b", equipment="barbell"),
            record(id="c", equipment="dumbbell"),
        ),
    )

    assert breakdown(catalog.stats(connection), "equipment").counts == (
        ("barbell", 2),
        ("dumbbell", 1),
    )


def test_values_sharing_a_count_are_ordered_by_name(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Ties broken by value, so two runs cannot disagree about the order."""
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", equipment="zercher bar"),
            record(id="b", equipment="ab wheel"),
        ),
    )

    assert breakdown(catalog.stats(connection), "equipment").counts == (
        ("ab wheel", 1),
        ("zercher bar", 1),
    )


def test_the_rows_with_no_value_are_counted_separately(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Coverage is a fact about the field, and absence is not the same as zero."""
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", force="push", mechanic=None),
            record(id="b", force=None, mechanic=None),
        ),
    )

    stats = catalog.stats(connection)

    assert breakdown(stats, "force").missing == 1
    assert breakdown(stats, "mechanic").missing == 2
    assert breakdown(stats, "mechanic").counts == ()


# --- the number the session exists to produce -------------------------------


def test_strength_is_counted_against_everything_else(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", category="strength"),
            record(id="b", category="strength"),
            record(id="c", category="stretching"),
            record(id="d", category="cardio"),
        ),
    )

    stats = catalog.stats(connection)

    assert stats.total == 4
    assert stats.strength == 2
    assert stats.other == 2


def test_a_catalog_with_no_strength_in_it_says_zero(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(connection, *loaded(tmp_path, record(category="stretching")))

    stats = catalog.stats(connection)

    assert stats.strength == 0
    assert stats.other == 1


# --- the property that makes the numbers trustworthy ------------------------


def test_every_breakdown_reconciles_with_the_total(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A row has one value per scalar field or none, so nothing may go missing."""
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", force=None, mechanic="compound", equipment=None),
            record(id="b", force="pull", mechanic=None, equipment="cable"),
            record(id="c", force="pull", mechanic=None, equipment=None),
        ),
    )

    stats = catalog.stats(connection)

    for one in stats.breakdowns:
        counted = sum(count for _, count in one.counts) + one.missing
        assert counted == stats.total, f"{one.field} does not reconcile"


def test_the_vendored_catalog_reconciles_too(connection: sqlite3.Connection) -> None:
    """The synthetic case proves the arithmetic; this proves it on real data."""
    stock(connection, *catalog.load())

    stats = catalog.stats(connection)

    assert stats.total == len(catalog.load())
    assert stats.strength + stats.other == stats.total
    for one in stats.breakdowns:
        assert sum(count for _, count in one.counts) + one.missing == stats.total


def test_an_empty_catalog_counts_to_zero(connection: sqlite3.Connection) -> None:
    stats = catalog.stats(connection)

    assert stats.total == 0
    assert stats.strength == 0
    assert [one.counts for one in stats.breakdowns] == [()] * len(catalog.SCALAR_FILTERS)
    assert [
        (one.rule, one.curated, one.unfilled) for one in stats.enrichment
    ] == [(0, 0, 0)] * len(catalog.ENRICHMENT_FIELDS)


# --- enrichment coverage, by source ------------------------------------------


def coverage(stats: catalog.CatalogStats, field: str) -> catalog.EnrichmentCoverage:
    (found,) = [one for one in stats.enrichment if one.field == field]
    return found


def test_every_enrichable_field_gets_a_coverage_row(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(connection, *loaded(tmp_path, record()))

    stats = catalog.stats(connection)

    assert [one.field for one in stats.enrichment] == list(catalog.ENRICHMENT_FIELDS)


def test_an_unenriched_catalog_is_all_unfilled(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(connection, *loaded(tmp_path, record(id="a"), record(id="b")))

    stats = catalog.stats(connection)

    for one in stats.enrichment:
        assert (one.rule, one.curated, one.unfilled) == (0, 0, 2)


def test_coverage_counts_rule_and_curated_separately(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(
        connection,
        *loaded(tmp_path, record(id="a"), record(id="b"), record(id="c")),
    )
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'rule' WHERE id = 'a'"
    )
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'core rotation', "
        "movement_pattern_source = 'curated' WHERE id = 'b'"
    )

    stats = catalog.stats(connection)

    assert coverage(stats, "movement_pattern") == catalog.EnrichmentCoverage(
        field="movement_pattern", rule=1, curated=1, unfilled=1
    )


def test_enrichment_coverage_respects_the_active_filters(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """`catalog --equipment barbell --stats` must not answer for the whole table."""
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", equipment="barbell"),
            record(id="b", equipment="dumbbell"),
        ),
    )
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'rule' WHERE id = 'a'"
    )
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'rule' WHERE id = 'b'"
    )

    stats = catalog.stats(connection, filters={"equipment": "barbell"})

    assert coverage(stats, "movement_pattern") == catalog.EnrichmentCoverage(
        field="movement_pattern", rule=1, curated=0, unfilled=0
    )


def test_enrichment_coverage_reconciles_with_the_total(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(
        connection,
        *loaded(tmp_path, record(id="a"), record(id="b"), record(id="c")),
    )
    connection.execute(
        "UPDATE exercises SET spinal_axial_load = 'no', "
        "spinal_axial_load_source = 'rule' WHERE id = 'a'"
    )

    stats = catalog.stats(connection)

    for one in stats.enrichment:
        assert one.rule + one.curated + one.unfilled == stats.total


def test_the_vendored_catalog_enrichment_reconciles_too(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, *catalog.load())

    stats = catalog.stats(connection)

    for one in stats.enrichment:
        assert one.rule + one.curated + one.unfilled == stats.total
        assert one.rule == 0
        assert one.curated == 0


# --- the same rows the listing would show -----------------------------------


def test_the_counts_describe_the_filtered_set(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Otherwise `catalog --equipment barbell --stats` would silently answer
    a question nobody asked."""
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", equipment="barbell", category="strength"),
            record(id="b", equipment="barbell", category="stretching"),
            record(id="c", equipment="dumbbell", category="strength"),
        ),
    )

    stats = catalog.stats(connection, filters={"equipment": "barbell"})

    assert stats.total == 2
    assert stats.strength == 1
    assert breakdown(stats, "equipment").counts == (("barbell", 2),)


def test_a_pattern_filter_narrows_stats_too(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", name="Barbell Deadlift", primaryMuscles=["lower back"]),
            record(id="b", name="Bench Press", primaryMuscles=["chest"]),
        ),
    )
    enrichment.run(connection)

    stats = catalog.stats(connection, filters={"movement_pattern": "hip hinge"})

    assert stats.total == 1


def test_a_name_filter_narrows_the_counts_too(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(
        connection,
        *loaded(
            tmp_path,
            record(id="a", name="Barbell Curl"),
            record(id="b", name="Cable Curl"),
            record(id="c", name="Barbell Row"),
        ),
    )

    assert catalog.stats(connection, name="barbell").total == 2


def test_an_unknown_filter_value_is_refused_here_as_well(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A typo must not come back as a catalog that happens to hold nothing."""
    stock(connection, *loaded(tmp_path, record()))

    with pytest.raises(catalog.UnknownFilterValue):
        catalog.stats(connection, filters={"equipment": "barbells"})

# --- one state, not seven ---------------------------------------------------


def executed(connection: sqlite3.Connection) -> list[str]:
    """Record the SQL a connection runs, in order."""
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    return statements


def test_the_counts_are_read_inside_a_single_transaction(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Many queries against many states would not reconcile.

    Connections are autocommit, so without an explicit transaction an import
    landing between the total and a breakdown makes the printed arithmetic
    wrong -- and strength rows arriving after the total was counted would give
    a negative `everything else`.
    """
    stock(connection, *loaded(tmp_path, record()))
    statements = executed(connection)

    catalog.stats(connection)
    connection.set_trace_callback(None)

    assert statements[0].startswith("BEGIN")
    assert statements[-1] == "COMMIT"
    assert [one for one in statements if one.startswith("BEGIN")] == [statements[0]]


def test_the_listing_and_its_total_are_read_together(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """`search` counts then selects, and shares the same guarantee."""
    stock(connection, *loaded(tmp_path, record()))
    statements = executed(connection)

    catalog.search(connection, limit=1)
    connection.set_trace_callback(None)

    assert statements[0].startswith("BEGIN")
    assert statements[-1] == "COMMIT"


def test_the_transaction_is_closed_even_when_a_query_fails(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A read left open would hold a lock and block the next import."""
    stock(connection, *loaded(tmp_path, record()))
    connection.execute("DROP TABLE exercises")

    with pytest.raises(sqlite3.Error):
        catalog.stats(connection)

    assert not connection.in_transaction
