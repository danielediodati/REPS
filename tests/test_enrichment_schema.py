"""Session 2's schema: six enrichment fields, plus demo_url, and the guarantees
that stop a cheap mistake from destroying work that does not regenerate.

Nothing here writes a real enrichment value -- that is ticket 02 and ticket
04's job. This is the shape everything downstream writes into: the columns
exist, the provenance vocabulary is closed, a rule can never overwrite a
curated value, a dangling regression_of/variant_of is refused, loaded_joints
is queryable as a set in both directions, and a re-import cannot touch any
of it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, migrations


def exercise(**overrides: object) -> catalog.Exercise:
    base: dict[str, object] = {
        "id": "Bench_Press",
        "name": "Bench Press",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("chest",),
        "secondary_muscles": ("triceps",),
        "instructions": ("Lie on the bench.", "Press."),
        "images": ("Bench_Press/0.jpg",),
    }
    base.update(overrides)
    return catalog.Exercise(**base)  # type: ignore[arg-type]


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        yield opened


def stock(connection: sqlite3.Connection, *exercises: catalog.Exercise) -> None:
    catalog.import_exercises(connection, exercises, allow_pruning=True)


def columns(connection: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in connection.execute("PRAGMA table_info(exercises)")}


# --- the shape --------------------------------------------------------------


def test_the_six_fields_and_demo_url_exist(connection: sqlite3.Connection) -> None:
    present = columns(connection)
    for field in (
        "movement_pattern",
        "loaded_joints",
        "spinal_axial_load",
        "required_stability",
        "setup_cost_min",
        "regression_of",
        "variant_of",
        "demo_url",
    ):
        assert field in present


def test_every_enrichable_field_has_a_source_column(connection: sqlite3.Connection) -> None:
    present = columns(connection)
    for field in catalog.ENRICHMENT_FIELDS:
        assert f"{field}_source" in present


def test_demo_url_carries_no_source_column(connection: sqlite3.Connection) -> None:
    """It is always curated when it holds a value -- there is nothing to record."""
    assert "demo_url_source" not in columns(connection)


def test_876_rows_arrive_unenriched(connection: sqlite3.Connection) -> None:
    stock(connection, *catalog.load())

    row = connection.execute(
        "SELECT COUNT(*) AS total FROM exercises WHERE movement_pattern IS NOT NULL"
    ).fetchone()
    assert row["total"] == 0


def test_no_required_rom_surface_exists(connection: sqlite3.Connection) -> None:
    """Removed from v1: TRAINER.md Appendix and ROADMAP.md Session 2 carry why."""
    present = columns(connection)
    assert not any("rom" in name.lower() for name in present)

    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert not any("rom" in name.lower() for name in tables)


# --- provenance is closed ----------------------------------------------------


def test_a_source_must_be_rule_or_curated(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE exercises SET movement_pattern = 'squat', "
            "movement_pattern_source = 'guess' WHERE id = 'Bench_Press'"
        )


def test_a_null_source_is_allowed(connection: sqlite3.Connection) -> None:
    """The unenriched state, and the default every one of the 876 rows starts in."""
    stock(connection, exercise())

    connection.execute(
        "UPDATE exercises SET movement_pattern = NULL, movement_pattern_source = NULL "
        "WHERE id = 'Bench_Press'"
    )  # does not raise


_A_VALID_VALUE: dict[str, object] = {
    "movement_pattern": "isolation",
    "loaded_joints": '["shoulder"]',
    "spinal_axial_load": "no",
    "required_stability": "low",
    "setup_cost_min": 2,
    "regression_of": "Other_Exercise",
    "variant_of": "Other_Exercise",
}
"""One value of the right type per enrichable field, valid enough to store --
`regression_of` and `variant_of` need a real id, everything else just needs
to satisfy its own CHECK constraint."""


@pytest.mark.parametrize("field", catalog.ENRICHMENT_FIELDS)
def test_a_rule_cannot_overwrite_a_curated_value(
    connection: sqlite3.Connection, field: str
) -> None:
    """The one guarantee that must not depend on a caller remembering to check.

    A hand decision does not regenerate; a rule silently overwriting one is
    the failure this session cannot afford.
    """
    stock(connection, exercise(), exercise(id="Other_Exercise", name="Other Exercise"))
    source_column = f"{field}_source"
    value = _A_VALID_VALUE[field]

    connection.execute(
        f"UPDATE exercises SET {field} = ?, {source_column} = 'curated' "
        f"WHERE id = 'Bench_Press'",
        (value,),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"UPDATE exercises SET {field} = ?, {source_column} = 'rule' "
            f"WHERE id = 'Bench_Press'",
            (value,),
        )
    # the curated value survives the rejected write
    row = connection.execute(
        f"SELECT {source_column} AS source FROM exercises WHERE id = 'Bench_Press'"
    ).fetchone()
    assert row["source"] == "curated"


@pytest.mark.parametrize("field", catalog.ENRICHMENT_FIELDS)
def test_a_rule_may_write_onto_an_unenriched_row(
    connection: sqlite3.Connection, field: str
) -> None:
    stock(connection, exercise(), exercise(id="Other_Exercise", name="Other Exercise"))
    source_column = f"{field}_source"
    value = _A_VALID_VALUE[field]

    connection.execute(
        f"UPDATE exercises SET {field} = ?, {source_column} = 'rule' WHERE id = 'Bench_Press'",
        (value,),
    )  # does not raise


@pytest.mark.parametrize("field", catalog.ENRICHMENT_FIELDS)
def test_a_curated_value_may_be_corrected_by_hand(
    connection: sqlite3.Connection, field: str
) -> None:
    """A person revising their own earlier decision is not a rule overwriting one."""
    stock(connection, exercise(), exercise(id="Other_Exercise", name="Other Exercise"))
    source_column = f"{field}_source"
    value = _A_VALID_VALUE[field]

    connection.execute(
        f"UPDATE exercises SET {field} = ?, {source_column} = 'curated' "
        f"WHERE id = 'Bench_Press'",
        (value,),
    )
    connection.execute(
        f"UPDATE exercises SET {field} = ?, {source_column} = 'curated' "
        f"WHERE id = 'Bench_Press'",
        (value,),
    )  # does not raise


# --- regression_of / variant_of are real references -------------------------


def test_pointing_at_nothing_is_refused(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE exercises SET variant_of = 'Nonexistent_Id' WHERE id = 'Bench_Press'"
        )


def test_pointing_at_a_real_row_is_stored(connection: sqlite3.Connection) -> None:
    stock(connection, exercise(), exercise(id="Incline_Bench_Press", name="Incline Bench Press"))

    connection.execute(
        "UPDATE exercises SET variant_of = 'Bench_Press' WHERE id = 'Incline_Bench_Press'"
    )

    row = connection.execute(
        "SELECT variant_of FROM exercises WHERE id = 'Incline_Bench_Press'"
    ).fetchone()
    assert row["variant_of"] == "Bench_Press"


# --- loaded_joints: a set, queryable in both directions ---------------------


def test_loaded_joints_defaults_to_an_empty_set(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())

    row = connection.execute(
        "SELECT loaded_joints FROM exercises WHERE id = 'Bench_Press'"
    ).fetchone()
    assert json.loads(row["loaded_joints"]) == []


def test_exercises_loading_a_joint_come_back(connection: sqlite3.Connection) -> None:
    stock(
        connection,
        exercise(id="Military_Press", name="Military Press"),
        exercise(id="Leg_Curl", name="Leg Curl"),
    )
    connection.execute(
        "UPDATE exercises SET loaded_joints = '[\"shoulder\", \"elbow\"]' "
        "WHERE id = 'Military_Press'"
    )
    connection.execute(
        "UPDATE exercises SET loaded_joints = '[\"knee\"]' WHERE id = 'Leg_Curl'"
    )

    assert catalog.exercises_with_joint(connection, "shoulder") == ("Military_Press",)


def test_exercises_not_loading_a_joint_come_back_too(connection: sqlite3.Connection) -> None:
    stock(
        connection,
        exercise(id="Military_Press", name="Military Press"),
        exercise(id="Leg_Curl", name="Leg Curl"),
    )
    connection.execute(
        "UPDATE exercises SET loaded_joints = '[\"shoulder\", \"elbow\"]' "
        "WHERE id = 'Military_Press'"
    )
    connection.execute(
        "UPDATE exercises SET loaded_joints = '[\"knee\"]' WHERE id = 'Leg_Curl'"
    )

    assert catalog.exercises_without_joint(connection, "shoulder") == ("Leg_Curl",)


def test_an_unenriched_row_does_not_load_any_joint(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())

    assert catalog.exercises_with_joint(connection, "shoulder") == ()
    assert catalog.exercises_without_joint(connection, "shoulder") == ("Bench_Press",)


def test_a_malformed_loaded_joints_value_is_refused(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE exercises SET loaded_joints = '\"shoulder\"' WHERE id = 'Bench_Press'"
        )  # a bare string is valid JSON but not an array


# --- re-import leaves enrichment untouched -----------------------------------


def test_a_reimport_does_not_touch_enrichment(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """This failure is silent, and it would throw away hand decisions that,
    unlike a rule, do not regenerate."""
    stock(connection, exercise())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'horizontal push', "
        "movement_pattern_source = 'curated' WHERE id = 'Bench_Press'"
    )

    # a real re-import: same exercise, changed native field, via the catalog API
    stock(connection, exercise(level="intermediate"))

    row = connection.execute(
        "SELECT level, movement_pattern, movement_pattern_source "
        "FROM exercises WHERE id = 'Bench_Press'"
    ).fetchone()
    assert row["level"] == "intermediate"  # the native field did update
    assert row["movement_pattern"] == "horizontal push"  # enrichment did not move
    assert row["movement_pattern_source"] == "curated"


def test_the_vendored_reimport_does_not_touch_enrichment(
    connection: sqlite3.Connection,
) -> None:
    """The same guarantee, against the real dataset rather than a synthetic row."""
    stock(connection, *catalog.load())
    one = catalog.load()[0]
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'curated' WHERE id = ?",
        (one.id,),
    )

    stock(connection, *catalog.load())  # a full re-import, unchanged dataset

    row = connection.execute(
        "SELECT movement_pattern_source FROM exercises WHERE id = ?", (one.id,)
    ).fetchone()
    assert row["movement_pattern_source"] == "curated"
