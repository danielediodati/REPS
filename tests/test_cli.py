"""The CLI, exercised end to end through the real entry point."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from trainer import __version__
from trainer.cli import main
from trainer.engine import catalog, database, migrations, snapshot


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_creates_the_database_and_migrates(
    runner: CliRunner, database_file: Path
) -> None:
    assert not database_file.exists()

    result = runner.invoke(main, ["db", "init"])

    assert result.exit_code == 0, result.output
    assert database_file.exists()
    latest = migrations.latest_version(migrations.discover())
    assert "applied migration 0001" in result.output
    assert f"now at schema version {latest}" in result.output


def test_init_a_second_time_changes_nothing_and_says_so(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])
    before = database_file.read_bytes()

    result = runner.invoke(main, ["db", "init"])

    assert result.exit_code == 0, result.output
    assert "nothing to do" in result.output
    assert database_file.read_bytes() == before


def test_status_on_a_database_that_does_not_exist(
    runner: CliRunner, database_file: Path
) -> None:
    result = runner.invoke(main, ["db", "status"])

    assert result.exit_code == 0, result.output
    assert "not created yet" in result.output
    assert not database_file.exists(), "status must not create the database"


def test_status_reports_the_applied_version(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["db", "status"])

    assert result.exit_code == 0, result.output
    latest = migrations.latest_version(migrations.discover())
    assert f"schema version: {latest}" in result.output
    assert f"latest available: {latest}" in result.output


def test_the_database_path_is_overridable(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "nested" / "custom.sqlite"
    monkeypatch.setenv(database.DATABASE_ENV_VAR, str(elsewhere))

    result = runner.invoke(main, ["db", "init"])

    assert result.exit_code == 0, result.output
    assert elsewhere.exists()


def test_a_broken_migration_set_is_a_message_not_a_traceback(
    runner: CliRunner, database_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An engine exception reaching the terminal raw is the boundary leaking."""
    monkeypatch.setattr(
        migrations, "discover", lambda *args, **kwargs: _raise_migration_error()
    )

    result = runner.invoke(main, ["db", "init"])

    assert result.exit_code != 0
    assert "the migration set is unusable" in result.output
    assert "Traceback" not in result.output


def _raise_migration_error() -> tuple[migrations.Migration, ...]:
    raise migrations.MigrationError("no migration directory at nowhere")


def test_a_database_ahead_of_the_checkout_is_flagged(
    runner: CliRunner, database_file: Path
) -> None:
    """Behind is a prompt. Ahead is a warning, and silence would look like health."""
    runner.invoke(main, ["db", "init"])
    with closing(database.connect(database_file)) as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) "
            "VALUES (99, 'from-the-future', '2030-01-01T00:00:00+00:00')"
        )

    result = runner.invoke(main, ["db", "status"])

    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output
    assert "newer version of trainer" in result.output


def test_import_reports_the_number_of_records(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["db", "import"])

    assert result.exit_code == 0, result.output
    expected = len(catalog.load())
    assert f"read {expected} records" in result.output
    assert f"{expected} exercises in the catalog" in result.output


def test_importing_twice_reports_no_growth(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])
    runner.invoke(main, ["db", "import"])

    result = runner.invoke(main, ["db", "import"])

    assert result.exit_code == 0, result.output
    assert "inserted" not in result.output
    assert "removed" not in result.output
    with closing(database.connect(database_file)) as connection:
        assert catalog.count(connection) == len(catalog.load())


def test_importing_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path
) -> None:
    result = runner.invoke(main, ["db", "import"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output
    assert "Traceback" not in result.output


def test_a_broken_dataset_is_a_message_not_a_traceback(
    runner: CliRunner, database_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(main, ["db", "init"])
    absent = tmp_path / "gone.json"
    monkeypatch.setattr(catalog, "DATASET_PATH", absent)
    monkeypatch.setattr(catalog, "load", lambda path=absent: _load_missing(path))

    result = runner.invoke(main, ["db", "import"])

    assert result.exit_code != 0
    assert "the dataset is unusable" in result.output
    assert "Traceback" not in result.output


def _load_missing(path: Path) -> tuple[catalog.Exercise, ...]:
    raise catalog.CatalogError(f"no dataset at {path}")


def test_import_into_a_database_that_does_not_exist_leaves_no_file(
    runner: CliRunner, database_file: Path
) -> None:
    """Connecting would create it, and a stray empty file reads as version 0."""
    result = runner.invoke(main, ["db", "import"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output
    assert not database_file.exists()


def test_an_import_that_would_gut_the_catalog_is_refused(
    runner: CliRunner, database_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(main, ["db", "init"])
    runner.invoke(main, ["db", "import"])

    truncated = tmp_path / "truncated.json"
    truncated.write_text(json.dumps([_as_record(catalog.load()[0])]), encoding="utf-8")

    # Captured before the patch: resolving it afterwards would find the patch.
    real_load = catalog.load
    monkeypatch.setattr(catalog, "load", lambda *a, **k: real_load(truncated))

    result = runner.invoke(main, ["db", "import"])

    assert result.exit_code != 0
    assert "looks more like a truncated dataset" in result.output
    with closing(database.connect(database_file)) as connection:
        assert catalog.count(connection) > 1


def _as_record(exercise: catalog.Exercise) -> dict[str, object]:
    return {
        "id": exercise.id,
        "name": exercise.name,
        "force": exercise.force,
        "level": exercise.level,
        "mechanic": exercise.mechanic,
        "equipment": exercise.equipment,
        "category": exercise.category,
        "primaryMuscles": list(exercise.primary_muscles),
        "secondaryMuscles": list(exercise.secondary_muscles),
        "instructions": list(exercise.instructions),
        "images": list(exercise.images),
    }


@pytest.fixture()
def stocked(runner: CliRunner, database_file: Path) -> Path:
    runner.invoke(main, ["db", "init"])
    runner.invoke(main, ["db", "import"])
    return database_file


def test_catalog_lists_matching_exercises(runner: CliRunner, stocked: Path) -> None:
    result = runner.invoke(main, ["catalog", "--equipment", "dumbbell", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert "dumbbell" in result.output
    assert "showing 5" in result.output


def test_catalog_rejects_a_near_miss_with_the_real_values(
    runner: CliRunner, stocked: Path
) -> None:
    """`dumbbells` is the trap this command exists to spring."""
    result = runner.invoke(main, ["catalog", "--equipment", "dumbbells"])

    assert result.exit_code != 0
    assert "no such equipment: 'dumbbells'" in result.output
    assert "dumbbell" in result.output
    assert "e-z curl bar" in result.output
    assert "77 exercises have no equipment recorded" in result.output


def test_catalog_says_so_when_nothing_matches(runner: CliRunner, stocked: Path) -> None:
    result = runner.invoke(
        main, ["catalog", "--equipment", "foam roll", "--category", "cardio"]
    )

    assert result.exit_code == 0, result.output
    assert "no exercise matches" in result.output


def test_catalog_values_prints_what_a_field_holds(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--values", "equipment"])

    assert result.exit_code == 0, result.output
    assert "e-z curl bar" in result.output
    assert "77 exercises have no equipment recorded" in result.output


def test_catalog_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path
) -> None:
    result = runner.invoke(main, ["catalog"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output
    assert not database_file.exists()


def test_catalog_output_is_ascii(runner: CliRunner, stocked: Path) -> None:
    """An em dash renders as a replacement character in the Windows console."""
    result = runner.invoke(main, ["catalog", "--limit", "20"])
    result.output.encode("ascii")


def test_catalog_help_is_ascii(runner: CliRunner) -> None:
    runner.invoke(main, ["catalog", "--help"]).output.encode("ascii")


def test_catalog_on_an_empty_database_says_to_import(
    runner: CliRunner, database_file: Path
) -> None:
    """Otherwise a correct value is rejected against an empty vocabulary."""
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["catalog", "--equipment", "dumbbell"])

    assert result.exit_code != 0
    assert "run `trainer db import` first" in result.output
    assert "no such equipment" not in result.output


def test_catalog_unfiltered_on_an_empty_database_says_to_import(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["catalog"])

    assert result.exit_code != 0
    assert "run `trainer db import` first" in result.output


def test_a_field_that_is_not_filterable_is_rejected_as_a_bad_argument(
    runner: CliRunner, stocked: Path
) -> None:
    """User input, not a corrupt dataset -- and it must not read like one."""
    result = runner.invoke(main, ["catalog", "--values", "nonsense"])
    assert result.exit_code != 0
    assert "the dataset is unusable" not in result.output
    assert "Invalid value" in result.output


def test_the_listing_is_ordered_by_the_column_it_shows(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--category", "cardio"])

    names = [line.split("  ")[0].strip() for line in result.output.splitlines()[1:-1]]
    assert names == sorted(names)


def test_every_catalog_output_is_ascii(runner: CliRunner, stocked: Path) -> None:
    for arguments in (
        ["catalog"],
        ["catalog", "--values", "equipment"],
        ["catalog", "--equipment", "dumbbells"],
        ["catalog", "--help"],
    ):
        runner.invoke(main, arguments).output.encode("ascii")


def test_the_listing_stops_at_a_hundred_by_default(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog"])

    assert result.exit_code == 0, result.output
    assert "showing 100 of 876" in result.output
    assert len(result.output.splitlines()) == 102  # header + 100 rows + footer


def test_limit_zero_shows_everything(runner: CliRunner, stocked: Path) -> None:
    result = runner.invoke(main, ["catalog", "--limit", "0"])

    assert result.exit_code == 0, result.output
    assert "showing 876" in result.output
    assert "of 876" not in result.output, "nothing was withheld, so say nothing"


def test_a_short_result_does_not_pretend_to_be_truncated(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--category", "cardio"])

    assert "showing 14" in result.output
    assert "of" not in result.output.splitlines()[-1]


@pytest.fixture()
def snapshot_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never the repo's own snapshot: a test must not rewrite what git carries."""
    path = tmp_path / "snapshots" / "catalog.md"
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV_VAR, str(path))
    return path


def test_snapshot_writes_the_file(
    runner: CliRunner, stocked: Path, snapshot_file: Path
) -> None:
    result = runner.invoke(main, ["db", "snapshot"])

    assert result.exit_code == 0, result.output
    assert "regenerated" in result.output
    assert snapshot_file.read_text(encoding="utf-8").startswith("# Catalog snapshot")


def test_snapshot_a_second_time_writes_nothing_and_says_so(
    runner: CliRunner, stocked: Path, snapshot_file: Path
) -> None:
    """The whole mechanism: unchanged database, empty `git diff`."""
    runner.invoke(main, ["db", "snapshot"])
    before = snapshot_file.read_bytes()

    result = runner.invoke(main, ["db", "snapshot"])

    assert result.exit_code == 0, result.output
    assert "unchanged" in result.output
    assert snapshot_file.read_bytes() == before


def test_snapshot_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path, snapshot_file: Path
) -> None:
    result = runner.invoke(main, ["db", "snapshot"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output
    assert not snapshot_file.exists()


def test_snapshot_on_an_empty_catalog_says_to_import(
    runner: CliRunner, database_file: Path, snapshot_file: Path
) -> None:
    """A snapshot of nothing would read as a catalog that had been emptied."""
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["db", "snapshot"])

    assert result.exit_code != 0
    assert "run `trainer db import` first" in result.output
    assert not snapshot_file.exists()


def test_snapshot_output_is_ascii(
    runner: CliRunner, stocked: Path, snapshot_file: Path
) -> None:
    runner.invoke(main, ["db", "snapshot"]).output.encode("ascii")
    runner.invoke(main, ["db", "snapshot", "--help"]).output.encode("ascii")


def test_a_snapshot_that_cannot_be_written_is_a_message_not_a_traceback(
    runner: CliRunner, stocked: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only volume or a path pointing at a directory is still user error."""
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV_VAR, str(tmp_path))  # a directory

    result = runner.invoke(main, ["db", "snapshot"])

    assert result.exit_code != 0
    assert "a file could not be used" in result.output
    assert "Traceback" not in result.output


def test_snapshot_names_the_database_it_read(
    runner: CliRunner, stocked: Path, snapshot_file: Path
) -> None:
    """The committed file is only as trustworthy as the database behind it."""
    result = runner.invoke(main, ["db", "snapshot"])

    assert str(stocked) in result.output
