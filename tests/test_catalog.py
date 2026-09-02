"""Reading the vendored catalog, and storing it."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, migrations


@pytest.fixture()
def migrated(database_file: Path) -> Path:
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection)
    return database_file


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
        "secondaryMuscles": ["triceps", "shoulders"],
        "instructions": ["Lie on the bench.", "Press."],
        "images": ["Bench_Press/0.jpg", "Bench_Press/1.jpg"],
    }
    base.update(overrides)
    return base


def dataset(tmp_path: Path, *records: dict[str, object]) -> Path:
    path = tmp_path / "exercises.json"
    path.write_text(json.dumps(list(records)), encoding="utf-8")
    return path


# --- reading the dataset ----------------------------------------------------


VENDORED_RECORDS = 876
"""The number PROVENANCE.md records, and the multiplier on session 2's cost.

Asserted exactly rather than loosely: a re-vendor that silently drops seventy
records should fail here, together with the provenance record that claims it
did not."""


def test_the_vendored_dataset_loads() -> None:
    exercises = catalog.load()
    assert len(exercises) == VENDORED_RECORDS
    assert len({exercise.id for exercise in exercises}) == len(exercises)


def test_the_vendored_dataset_keeps_absent_fields_absent() -> None:
    """`force` and `mechanic` are empty for part of the source. That is data."""
    exercises = catalog.load()
    assert any(exercise.force is None for exercise in exercises)
    assert any(exercise.mechanic is None for exercise in exercises)
    assert any(exercise.equipment is None for exercise in exercises)
    assert not any(exercise.force == "" for exercise in exercises)


def test_the_vendored_dataset_carries_only_image_references() -> None:
    for exercise in catalog.load():
        for image in exercise.images:
            assert isinstance(image, str)
            assert not image.startswith("data:")


def test_a_record_becomes_an_exercise(tmp_path: Path) -> None:
    (loaded,) = catalog.load(dataset(tmp_path, record()))

    assert loaded.id == "Bench_Press"
    assert loaded.primary_muscles == ("chest",)
    assert loaded.secondary_muscles == ("triceps", "shoulders")
    assert loaded.instructions == ("Lie on the bench.", "Press.")
    assert loaded.images == ("Bench_Press/0.jpg", "Bench_Press/1.jpg")


def test_nulls_are_preserved_not_blanked(tmp_path: Path) -> None:
    (loaded,) = catalog.load(
        dataset(tmp_path, record(force=None, mechanic=None, equipment=None))
    )
    assert loaded.force is None
    assert loaded.mechanic is None
    assert loaded.equipment is None


def test_a_missing_dataset_is_refused(tmp_path: Path) -> None:
    with pytest.raises(catalog.CatalogError):
        catalog.load(tmp_path / "absent.json")


def test_malformed_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "exercises.json"
    path.write_text("404: Not Found", encoding="utf-8")
    with pytest.raises(catalog.CatalogError):
        catalog.load(path)


@pytest.mark.parametrize(
    "broken",
    [
        {"id": None},
        {"id": ""},
        {"name": 7},
        {"level": None},
        {"force": 3},
        {"primaryMuscles": "chest"},
        {"images": [1, 2]},
        {"instructions": None},
    ],
    ids=lambda case: str(sorted(case)),
)
def test_a_record_of_the_wrong_shape_is_refused(
    broken: dict[str, object], tmp_path: Path
) -> None:
    """A skipped record is an exercise that can never be prescribed again."""
    with pytest.raises(catalog.CatalogError):
        catalog.load(dataset(tmp_path, record(**broken)))


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    with pytest.raises(catalog.CatalogError):
        catalog.load(dataset(tmp_path, record(), record(name="Again")))


# --- storing it -------------------------------------------------------------


def test_importing_fills_the_table(migrated: Path, tmp_path: Path) -> None:
    exercises = catalog.load(dataset(tmp_path, record(), record(id="Squat")))

    with closing(database.connect(migrated)) as connection:
        result = catalog.import_exercises(connection, exercises)

        assert result.inserted == 2
        assert result.total == 2
        assert catalog.count(connection) == 2


def test_the_row_count_equals_the_record_count(migrated: Path) -> None:
    exercises = catalog.load()
    with closing(database.connect(migrated)) as connection:
        result = catalog.import_exercises(connection, exercises)
        assert result.total == len(exercises)
        assert catalog.count(connection) == len(exercises)


def test_importing_twice_changes_nothing(migrated: Path) -> None:
    exercises = catalog.load()
    with closing(database.connect(migrated)) as connection:
        first = catalog.import_exercises(connection, exercises)
        second = catalog.import_exercises(connection, exercises)

        assert second.inserted == 0
        assert second.removed == 0
        assert second.updated == len(exercises)
        assert second.total == first.total


def test_a_row_the_dataset_no_longer_carries_is_removed(
    migrated: Path, tmp_path: Path
) -> None:
    """The table is the dataset, not everything the dataset has ever said."""
    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(
            connection, catalog.load(dataset(tmp_path, record(), record(id="Squat")))
        )
        result = catalog.import_exercises(
            connection, catalog.load(dataset(tmp_path, record()))
        )

        assert result.removed == 1
        assert result.total == 1
        assert catalog.exercise(connection, "Squat") is None


def test_an_exercise_comes_back_whole(migrated: Path, tmp_path: Path) -> None:
    (original,) = catalog.load(dataset(tmp_path, record()))

    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, (original,))
        assert catalog.exercise(connection, "Bench_Press") == original


def test_nulls_survive_the_round_trip(migrated: Path, tmp_path: Path) -> None:
    (original,) = catalog.load(
        dataset(tmp_path, record(force=None, mechanic=None, equipment=None))
    )

    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, (original,))
        stored = catalog.exercise(connection, original.id)

    assert stored is not None
    assert (stored.force, stored.mechanic, stored.equipment) == (None, None, None)


def test_an_unknown_id_is_not_an_error(migrated: Path) -> None:
    with closing(database.connect(migrated)) as connection:
        assert catalog.exercise(connection, "no-such-exercise") is None


def test_nothing_binary_reaches_the_database(migrated: Path) -> None:
    """Images are references. A blob in here would be a repo nobody clones."""
    exercises = catalog.load()
    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, exercises)
        for row in connection.execute("SELECT * FROM exercises"):
            for value in tuple(row):
                assert not isinstance(value, (bytes, memoryview))


def test_a_failed_import_leaves_the_table_as_it_was(
    migrated: Path, tmp_path: Path
) -> None:
    exercises = catalog.load(dataset(tmp_path, record()))

    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, exercises)
        before = catalog.count(connection)

        broken = (*catalog.load(dataset(tmp_path, record(id="Squat"))),)
        connection.execute("DROP INDEX exercises_equipment")
        connection.execute("CREATE UNIQUE INDEX exercises_equipment ON exercises (equipment)")

        with pytest.raises(sqlite3.IntegrityError):
            catalog.import_exercises(connection, (*exercises, *broken))

        assert catalog.count(connection) == before


# --- the guards against a bad re-vendor -------------------------------------


def test_an_empty_dataset_is_refused(tmp_path: Path) -> None:
    """A catalog with no exercises is not a catalog; it is a failed download."""
    with pytest.raises(catalog.CatalogError):
        catalog.load(dataset(tmp_path))


def test_an_import_that_would_gut_the_catalog_is_refused(
    migrated: Path, tmp_path: Path
) -> None:
    """A truncated re-vendor removes rows and exits zero. That is the danger."""
    full = catalog.load()
    survivor = catalog.load(dataset(tmp_path, record(id=full[0].id, name=full[0].name)))

    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, full)

        with pytest.raises(catalog.CatalogError):
            catalog.import_exercises(connection, survivor)

        assert catalog.count(connection) == len(full), "the table must be untouched"


def test_a_deliberate_pruning_is_allowed(migrated: Path, tmp_path: Path) -> None:
    full = catalog.load()
    survivor = catalog.load(dataset(tmp_path, record(id=full[0].id, name=full[0].name)))

    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, full)
        result = catalog.import_exercises(connection, survivor, allow_pruning=True)

        assert result.total == 1


def test_a_small_removal_needs_no_permission(migrated: Path, tmp_path: Path) -> None:
    both = catalog.load(dataset(tmp_path, record(), record(id="Squat")))
    one = catalog.load(dataset(tmp_path, record()))

    with closing(database.connect(migrated)) as connection:
        catalog.import_exercises(connection, both)
        # Half is the limit, not a removal that merely reaches it.
        result = catalog.import_exercises(connection, one)
        assert result.removed == 1


def test_an_empty_string_is_stored_as_absent(migrated: Path, tmp_path: Path) -> None:
    """Otherwise it becomes a phantom value the moment the vocabulary is read
    out of the table."""
    (loaded,) = catalog.load(dataset(tmp_path, record(equipment="", force="")))
    assert loaded.equipment is None
    assert loaded.force is None


def test_a_json_object_cannot_be_stored_in_a_list_column(migrated: Path) -> None:
    """json_valid() accepts an object; the column must accept only an array."""
    with closing(database.connect(migrated)) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO exercises (
                    id, name, force, level, mechanic, equipment, category,
                    primary_muscles, secondary_muscles, instructions, images
                ) VALUES ('x', 'X', NULL, 'beginner', NULL, NULL, 'strength',
                          '{"a": 1}', '[]', '[]', '[]')
                """
            )
