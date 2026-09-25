"""The CLI, exercised end to end through the real entry point."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from conftest import serving
from langchain_core.messages import AIMessage

from trainer import __version__, cli
from trainer.cli import main
from trainer.coach import models
from trainer.engine import (
    catalog,
    database,
    duration,
    exclusions,
    graph,
    migrations,
    reference_set,
    residue,
    snapshot,
    state,
    workouts,
)


BLANK = "\n\n"
"""A blank line: what separates one stats block from the next."""


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


@pytest.fixture()
def enriched(runner: CliRunner, stocked: Path) -> Path:
    runner.invoke(main, ["enrich", "derive"])
    return stocked


def test_catalog_pattern_filters_the_listing(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["catalog", "--pattern", "hip hinge", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert "Barbell Deadlift" in result.output


def test_catalog_pattern_composes_with_a_native_filter(
    runner: CliRunner, enriched: Path
) -> None:
    without = runner.invoke(main, ["catalog", "--pattern", "hip hinge", "--limit", "0"])
    with_equipment = runner.invoke(
        main, ["catalog", "--pattern", "hip hinge", "--equipment", "barbell", "--limit", "0"]
    )

    def shown(output: str) -> int:
        return int(output.rsplit("showing ", 1)[1].split()[0])

    assert 0 < shown(with_equipment.output) < shown(without.output)


def test_catalog_pattern_rejects_an_unknown_value(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["catalog", "--pattern", "nonsense"])

    assert result.exit_code != 0
    assert "no such movement_pattern" in result.output
    assert "hip hinge" in result.output


def test_catalog_pattern_rejects_a_blank_value(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["catalog", "--pattern", ""])

    assert result.exit_code != 0
    assert "cannot be blank" in result.output


def test_catalog_pattern_before_deriving_says_what_to_do(
    runner: CliRunner, stocked: Path
) -> None:
    """Otherwise a correct pattern is rejected against an empty vocabulary --
    the same mistake `--values` was already fixed for in ticket 01."""
    result = runner.invoke(main, ["catalog", "--pattern", "hip hinge"])

    assert result.exit_code != 0
    assert "not enriched yet" in result.output
    assert "trainer enrich derive" in result.output
    assert "no such movement_pattern" not in result.output


def test_catalog_pattern_and_stats_together(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["catalog", "--pattern", "hip hinge", "--stats"])

    assert result.exit_code == 0, result.output
    assert "exercises" in result.output


def test_catalog_pattern_output_is_ascii(runner: CliRunner, enriched: Path) -> None:
    runner.invoke(main, ["catalog", "--pattern", "hip hinge"]).output.encode("ascii")


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


def test_catalog_values_of_an_unenriched_field_says_so(
    runner: CliRunner, stocked: Path
) -> None:
    """A missing precondition, named -- not a vocabulary that happens to be empty."""
    result = runner.invoke(main, ["catalog", "--values", "movement_pattern"])

    assert result.exit_code != 0
    assert "not enriched yet" in result.output
    assert "trainer enrich derive" in result.output


def test_catalog_values_lists_a_pattern_once_something_is_enriched(
    runner: CliRunner, stocked: Path
) -> None:
    with closing(database.connect(stocked)) as connection:
        connection.execute(
            "UPDATE exercises SET movement_pattern = 'core rotation', "
            "movement_pattern_source = 'rule' WHERE id = "
            "(SELECT id FROM exercises LIMIT 1)"
        )

    result = runner.invoke(main, ["catalog", "--values", "movement_pattern"])

    assert result.exit_code == 0, result.output
    assert "core rotation" in result.output
    assert "875 exercises have no movement_pattern recorded" in result.output


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


def test_stats_reports_the_number_the_session_exists_for(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--stats"])

    assert result.exit_code == 0, result.output
    assert "876 exercises" in result.output
    assert "of which strength  584" in result.output
    assert "everything else    292" in result.output


def test_stats_breaks_every_scalar_field_down(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--stats"])

    for field in catalog.SCALAR_FILTERS:
        assert f"{field}:" in result.output


def test_stats_shows_the_rows_with_no_value(runner: CliRunner, stocked: Path) -> None:
    """Coverage of the thin fields, which is what makes them worth checking."""
    result = runner.invoke(main, ["catalog", "--stats"])

    assert "(none)   30" in result.output  # force
    assert "(none)      87" in result.output  # mechanic


def test_stats_breaks_every_enrichment_field_down_by_source(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--stats"])

    for field in catalog.ENRICHMENT_FIELDS:
        assert f"{field}:" in result.output
    assert "rule" in result.output
    assert "curated" in result.output


def test_stats_shows_the_whole_catalog_unenriched(runner: CliRunner, stocked: Path) -> None:
    """Nothing has run `enrich derive` yet -- every field is `(none)` for all 876."""
    result = runner.invoke(main, ["catalog", "--stats"])

    blocks = result.output.split(BLANK)
    enrichment_blocks = [
        block
        for block in blocks
        if block.strip().splitlines() and block.strip().splitlines()[0].rstrip(":") in catalog.ENRICHMENT_FIELDS
    ]
    assert len(enrichment_blocks) == len(catalog.ENRICHMENT_FIELDS)
    for block in enrichment_blocks:
        lines = block.strip().splitlines()[1:]
        counted = {line.split()[0]: int(line.rsplit(None, 1)[1]) for line in lines}
        assert counted == {"rule": 0, "curated": 0, "(none)": 876}


def test_every_column_of_stats_adds_up_to_the_total(
    runner: CliRunner, stocked: Path
) -> None:
    """The reader can check the arithmetic, which is why (none) is always shown."""
    blocks = runner.invoke(main, ["catalog", "--stats"]).output.split(BLANK)

    counted = 0
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        assert lines[0].endswith(":"), lines[0]
        assert sum(int(line.rsplit("  ", 1)[1]) for line in lines[1:]) == 876
        counted += 1
    assert counted == len(catalog.SCALAR_FILTERS) + len(catalog.ENRICHMENT_FIELDS)


def test_stats_counts_the_rows_the_filters_leave(
    runner: CliRunner, stocked: Path
) -> None:
    """A filtered question must not get an answer about the whole catalog."""
    result = runner.invoke(main, ["catalog", "--equipment", "dumbbell", "--stats"])

    assert result.exit_code == 0, result.output
    assert "123 exercises" in result.output
    assert "876" not in result.output


def test_stats_rejects_a_near_miss_like_the_listing_does(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(main, ["catalog", "--equipment", "dumbbells", "--stats"])

    assert result.exit_code != 0
    assert "no such equipment: 'dumbbells'" in result.output


def test_stats_says_so_when_the_filters_match_nothing(
    runner: CliRunner, stocked: Path
) -> None:
    result = runner.invoke(
        main, ["catalog", "--equipment", "foam roll", "--category", "cardio", "--stats"]
    )

    assert result.exit_code == 0, result.output
    assert "no exercise matches" in result.output


def test_stats_and_values_together_are_refused(
    runner: CliRunner, stocked: Path
) -> None:
    """Both print and stop; running one and ignoring the other would be a lie."""
    result = runner.invoke(main, ["catalog", "--stats", "--values", "force"])

    assert result.exit_code != 0
    assert "not both" in result.output


def test_stats_before_import_says_what_to_do(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["catalog", "--stats"])

    assert result.exit_code != 0
    assert "run `trainer db import` first" in result.output


def test_stats_output_is_ascii(runner: CliRunner, stocked: Path) -> None:
    runner.invoke(main, ["catalog", "--stats"]).output.encode("ascii")


def test_stats_refuses_a_limit_rather_than_discarding_it(
    runner: CliRunner, stocked: Path
) -> None:
    """--limit bounds a listing, and counting is not listing."""
    result = runner.invoke(main, ["catalog", "--stats", "--limit", "5"])

    assert result.exit_code != 0
    assert "--limit bounds a listing" in result.output


def test_the_default_limit_does_not_count_as_asking_for_one(
    runner: CliRunner, stocked: Path
) -> None:
    """--limit is always present, so only the command line may trigger the guard."""
    result = runner.invoke(main, ["catalog", "--stats"])

    assert result.exit_code == 0, result.output
    assert "876 exercises" in result.output


# --- enrich derive ------------------------------------------------------------


def test_enrich_derive_reports_coverage(runner: CliRunner, stocked: Path) -> None:
    result = runner.invoke(main, ["enrich", "derive"])

    assert result.exit_code == 0, result.output
    assert "584 strength rows considered" in result.output
    assert "decided" in result.output
    assert "undecided" in result.output


def test_enrich_derive_beats_the_measured_floor(runner: CliRunner, stocked: Path) -> None:
    result = runner.invoke(main, ["enrich", "derive"])

    assert result.exit_code == 0, result.output
    # "decided    546 (93.5%)" -- parsed rather than matched as a substring,
    # so this fails loudly the day the rules regress instead of a percentage
    # nobody is reading drifting under the floor unnoticed.
    line = next(line for line in result.output.splitlines() if line.strip().startswith("decided"))
    percentage = float(line.split("(")[1].rstrip("%)\n"))
    assert percentage > 90.0


def test_enrich_derive_lists_the_undecided_rows_by_name(
    runner: CliRunner, stocked: Path
) -> None:
    """ticket 04's reading list -- named, not just counted."""
    result = runner.invoke(main, ["enrich", "derive"])

    assert result.exit_code == 0, result.output
    assert "Spell_Caster" in result.output


def test_enrich_derive_twice_reports_the_same_coverage(runner: CliRunner, stocked: Path) -> None:
    first = runner.invoke(main, ["enrich", "derive"])
    second = runner.invoke(main, ["enrich", "derive"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert first.output == second.output


def test_enrich_derive_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path
) -> None:
    result = runner.invoke(main, ["enrich", "derive"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output


def test_enrich_derive_on_an_empty_catalog_says_to_import(
    runner: CliRunner, database_file: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(main, ["enrich", "derive"])

    assert result.exit_code != 0
    assert "run `trainer db import` first" in result.output


def test_enrich_derive_leaves_a_curated_value_alone(runner: CliRunner, stocked: Path) -> None:
    with closing(database.connect(stocked)) as connection:
        connection.execute(
            "UPDATE exercises SET movement_pattern = 'isolation', "
            "movement_pattern_source = 'curated' WHERE id = 'Barbell_Deadlift'"
        )

    runner.invoke(main, ["enrich", "derive"])

    with closing(database.connect(stocked)) as connection:
        row = connection.execute(
            "SELECT movement_pattern, movement_pattern_source FROM exercises "
            "WHERE id = 'Barbell_Deadlift'"
        ).fetchone()
    assert row["movement_pattern"] == "isolation"
    assert row["movement_pattern_source"] == "curated"


def test_enrich_derive_output_is_ascii(runner: CliRunner, stocked: Path) -> None:
    runner.invoke(main, ["enrich", "derive"]).output.encode("ascii")
    runner.invoke(main, ["enrich", "derive", "--help"]).output.encode("ascii")


# --- enrich check ---------------------------------------------------------


@pytest.fixture()
def reference_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway reference set, pointed at by the documented env var --
    the same shape `database_file` gives `TRAINER_DB`."""
    path = tmp_path / "reference-set.md"
    path.write_text(
        "| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| Barbell_Deadlift | Barbell Deadlift | barbell | hip hinge | hip, lumbar spine "
        "| yes | medium | 3 | | . |\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(reference_set.REFERENCE_SET_ENV_VAR, str(path))
    return path


def test_enrich_check_reports_movement_pattern_first(
    runner: CliRunner, enriched: Path, reference_file: Path
) -> None:
    result = runner.invoke(main, ["enrich", "check"])

    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.endswith(":")]
    assert lines[0] == "movement_pattern:"


def test_enrich_check_counts_a_correct_derivation_as_a_match(
    runner: CliRunner, enriched: Path, reference_file: Path
) -> None:
    result = runner.invoke(main, ["enrich", "check"])

    assert result.exit_code == 0, result.output
    assert "matches        1 of 1 (100.0%)" in result.output


def test_enrich_check_names_a_disagreement(
    runner: CliRunner, stocked: Path, reference_file: Path
) -> None:
    with closing(database.connect(stocked)) as connection:
        connection.execute(
            "UPDATE exercises SET movement_pattern = 'isolation', "
            "movement_pattern_source = 'rule' WHERE id = 'Barbell_Deadlift'"
        )

    result = runner.invoke(main, ["enrich", "check"])

    assert result.exit_code == 0, result.output
    assert "disagreements  1" in result.output
    assert "Barbell_Deadlift" in result.output


def test_enrich_check_before_deriving_reports_everything_undecided(
    runner: CliRunner, stocked: Path, reference_file: Path
) -> None:
    result = runner.invoke(main, ["enrich", "check"])

    assert result.exit_code == 0, result.output
    assert "not yet decided  1" in result.output


def test_enrich_check_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path, reference_file: Path
) -> None:
    result = runner.invoke(main, ["enrich", "check"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output


def test_enrich_check_without_a_reference_set_says_so(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(reference_set.REFERENCE_SET_ENV_VAR, str(tmp_path / "missing.md"))

    result = runner.invoke(main, ["enrich", "check"])

    assert result.exit_code != 0
    assert "the reference set is unusable" in result.output
    assert "Traceback" not in result.output


def test_enrich_check_output_is_ascii(
    runner: CliRunner, enriched: Path, reference_file: Path
) -> None:
    runner.invoke(main, ["enrich", "check"]).output.encode("ascii")
    runner.invoke(main, ["enrich", "check", "--help"]).output.encode("ascii")


def test_catalog_values_reads_what_enrich_derive_wrote(
    runner: CliRunner, stocked: Path
) -> None:
    """The precondition from ticket 01 lifts once this ticket runs."""
    runner.invoke(main, ["enrich", "derive"])

    result = runner.invoke(main, ["catalog", "--values", "movement_pattern"])

    assert result.exit_code == 0, result.output
    assert "not enriched yet" not in result.output
    assert "hip hinge" in result.output


# --- enrich curated ---------------------------------------------------------


def test_enrich_curated_reports_residue_and_graph(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["enrich", "curated"])

    assert result.exit_code == 0, result.output
    assert "residue:" in result.output
    assert "decided" in result.output
    assert "graph:" in result.output
    assert "variant_of rows written" in result.output


def test_enrich_curated_closes_every_remaining_strength_row(
    runner: CliRunner, enriched: Path
) -> None:
    runner.invoke(main, ["enrich", "curated"])

    with closing(database.connect(enriched)) as connection:
        left = connection.execute(
            "SELECT COUNT(*) AS total FROM exercises WHERE category = 'strength' "
            "AND movement_pattern_source IS NULL"
        ).fetchone()
    assert left["total"] == 0


def test_enrich_curated_resolves_trainers_running_example(
    runner: CliRunner, enriched: Path
) -> None:
    runner.invoke(main, ["enrich", "curated"])

    with closing(database.connect(enriched)) as connection:
        rows = {
            str(r["id"]): r["variant_of"]
            for r in connection.execute(
                "SELECT id, variant_of FROM exercises WHERE id IN "
                "('Arnold_Dumbbell_Press', 'Kettlebell_Arnold_Press', "
                "'Standing_Military_Press')"
            )
        }
    assert rows["Arnold_Dumbbell_Press"] == rows["Kettlebell_Arnold_Press"]
    assert rows["Arnold_Dumbbell_Press"] == "Standing_Military_Press"


def test_enrich_curated_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path
) -> None:
    result = runner.invoke(main, ["enrich", "curated"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output


def test_enrich_curated_without_a_residue_file_says_so(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(residue.RESIDUE_ENV_VAR, str(tmp_path / "missing.md"))

    result = runner.invoke(main, ["enrich", "curated"])

    assert result.exit_code != 0
    assert "the residue file is unusable" in result.output
    assert "Traceback" not in result.output


def test_enrich_curated_without_a_graph_file_says_so(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(graph.GRAPH_ENV_VAR, str(tmp_path / "missing.md"))

    result = runner.invoke(main, ["enrich", "curated"])

    assert result.exit_code != 0
    assert "the graph file is unusable" in result.output
    assert "Traceback" not in result.output


def test_enrich_curated_reports_residue_before_a_later_graph_failure(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """residue and graph are two separate commits: a graph.md that fails
    must not read as though the residue load never happened either."""
    monkeypatch.setenv(graph.GRAPH_ENV_VAR, str(tmp_path / "missing.md"))

    result = runner.invoke(main, ["enrich", "curated"])

    assert result.exit_code != 0
    assert "residue: 38 rows read" in result.output
    assert "decided  36" in result.output
    with closing(database.connect(enriched)) as connection:
        left = connection.execute(
            "SELECT COUNT(*) AS total FROM exercises WHERE category = 'strength' "
            "AND movement_pattern_source IS NULL"
        ).fetchone()
    assert left["total"] == 0  # the residue commit landed despite the later failure


def test_enrich_curated_twice_reports_the_same_result(runner: CliRunner, enriched: Path) -> None:
    first = runner.invoke(main, ["enrich", "curated"])
    second = runner.invoke(main, ["enrich", "curated"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert first.output == second.output


def test_enrich_curated_output_is_ascii(runner: CliRunner, enriched: Path) -> None:
    runner.invoke(main, ["enrich", "curated"]).output.encode("ascii")
    runner.invoke(main, ["enrich", "curated", "--help"]).output.encode("ascii")


# --- admissible ---------------------------------------------------------


def test_admissible_answers_on_equipment_and_time(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "5"])

    assert result.exit_code == 0, result.output
    assert "Standing Military Press" in result.output
    assert "showing" in result.output


def test_admissible_excludes_by_pattern(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(
        main,
        ["admissible", "--equipment", "barbell", "--time", "5", "--exclude", "vertical push"],
    )

    assert result.exit_code == 0, result.output
    assert "Standing Military Press" not in result.output


def test_admissible_excludes_by_joint(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(
        main,
        ["admissible", "--equipment", "barbell", "--time", "5", "--exclude", "shoulder"],
    )

    assert result.exit_code == 0, result.output
    assert "Standing Military Press" not in result.output


def test_admissible_combines_several_equipment_values(
    runner: CliRunner, enriched: Path
) -> None:
    only_barbell = runner.invoke(
        main, ["admissible", "--equipment", "barbell", "--time", "5"]
    )
    barbell_and_dumbbell = runner.invoke(
        main,
        ["admissible", "--equipment", "barbell", "--equipment", "dumbbell", "--time", "5"],
    )

    def shown(output: str) -> int:
        return int(output.rsplit("showing ", 1)[1].split()[0])

    assert shown(barbell_and_dumbbell.output) > shown(only_barbell.output)


def test_admissible_rejects_an_unknown_equipment_value(
    runner: CliRunner, enriched: Path
) -> None:
    result = runner.invoke(main, ["admissible", "--equipment", "dumbbells", "--time", "5"])

    assert result.exit_code != 0
    assert "no such equipment: 'dumbbells'" in result.output
    assert "dumbbell" in result.output


def test_admissible_rejects_an_exercise_id_as_an_exclusion(
    runner: CliRunner, enriched: Path
) -> None:
    result = runner.invoke(
        main,
        [
            "admissible",
            "--equipment",
            "barbell",
            "--time",
            "5",
            "--exclude",
            "Standing_Military_Press",
        ],
    )

    assert result.exit_code != 0
    assert "not a movement pattern or a loaded joint" in result.output


def test_admissible_rejects_an_unknown_exclude_value(
    runner: CliRunner, enriched: Path
) -> None:
    result = runner.invoke(
        main, ["admissible", "--equipment", "barbell", "--time", "5", "--exclude", "nonsense"]
    )

    assert result.exit_code != 0
    assert "not a movement pattern or a loaded joint" in result.output


def test_admissible_refuses_a_time_over_the_declared_cap(
    runner: CliRunner, enriched: Path
) -> None:
    """The cap is a ceiling on any workout, and this command answers *what can
    I do today* -- answered against 90 minutes it describes a workout the
    declaration says never happens."""
    result = runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "90"])

    assert result.exit_code != 0
    assert "over the 60" in result.output


def test_admissible_reads_a_stored_exclusion_automatically(
    runner: CliRunner, enriched: Path
) -> None:
    """A persisted exclusion applies without being repeated on the command
    line -- `--exclude` is for an ad-hoc addition, not the only way in."""
    with closing(database.connect(enriched)) as connection:
        connection.execute(
            "INSERT INTO exclusions (granularity, value, retest_date) "
            "VALUES ('pattern', 'vertical push', '2099-01-01')"
        )

    result = runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "5"])

    assert result.exit_code == 0, result.output
    assert "Standing Military Press" not in result.output


def test_admissible_an_expired_stored_exclusion_stops_excluding(
    runner: CliRunner, enriched: Path
) -> None:
    with closing(database.connect(enriched)) as connection:
        connection.execute(
            "INSERT INTO exclusions (granularity, value, retest_date) "
            "VALUES ('pattern', 'vertical push', '2000-01-01')"
        )

    result = runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "5"])

    assert result.exit_code == 0, result.output
    assert "Standing Military Press" in result.output


def test_admissible_says_so_when_nothing_matches(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["admissible", "--equipment", "foam roll", "--time", "0"])

    assert result.exit_code == 0, result.output
    assert "no exercise is admissible" in result.output


def test_admissible_requires_equipment(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["admissible", "--time", "5"])

    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_admissible_requires_time(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["admissible", "--equipment", "barbell"])

    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_admissible_before_deriving_names_the_state(runner: CliRunner, stocked: Path) -> None:
    result = runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "5"])

    assert result.exit_code != 0
    assert "not enriched yet" in result.output
    assert "trainer enrich derive" in result.output


def test_admissible_before_init_says_what_to_do(
    runner: CliRunner, database_file: Path
) -> None:
    result = runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "5"])

    assert result.exit_code != 0
    assert "run `trainer db init` first" in result.output


def test_admissible_output_is_ascii(runner: CliRunner, enriched: Path) -> None:
    runner.invoke(main, ["admissible", "--equipment", "barbell", "--time", "5"]).output.encode(
        "ascii"
    )
    runner.invoke(main, ["admissible", "--help"]).output.encode("ascii")


def test_catalog_stats_shows_real_coverage_after_deriving(
    runner: CliRunner, stocked: Path
) -> None:
    runner.invoke(main, ["enrich", "derive"])

    result = runner.invoke(main, ["catalog", "--stats"])

    assert result.exit_code == 0, result.output
    assert "movement_pattern:" in result.output
    assert "rule     546" in result.output


# -- `trainer config`: what the user declares ---------------------------------


def test_config_shows_what_was_declared(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    declared = tmp_path / "training.toml"
    declared.write_text(
        'cycle_length = 2\nduration_cap_min = 45\nvolume_denominator = "cycle"\n'
        'split = [["chest", "arms"], ["legs", "core"]]\nequipment = ["barbell"]\n'
        'goal = "strength"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAINER_CONFIG", str(declared))

    result = runner.invoke(main, ["config"])

    assert result.exit_code == 0, result.output
    assert "cycle length: 2 workouts" in result.output
    assert "duration cap: 45 min" in result.output
    assert "volume counted per: cycle" in result.output
    assert "equipment: barbell" in result.output
    assert "goal: strength" in result.output
    assert "1. chest, arms" in result.output
    assert "2. legs, core" in result.output


def test_a_file_with_no_goal_is_reported_as_that_state(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    declared = tmp_path / "training.toml"
    declared.write_text(
        'cycle_length = 1\nduration_cap_min = 45\nvolume_denominator = "cycle"\n'
        'split = [["chest"]]\nequipment = ["barbell"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAINER_CONFIG", str(declared))

    result = runner.invoke(main, ["config"])

    assert result.exit_code == 1
    assert "no goal declared yet" in result.output
    assert "unusable" not in result.output


def test_config_reports_the_missing_state_and_not_a_field_error(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "training.toml"))

    result = runner.invoke(main, ["config"])

    assert result.exit_code != 0
    assert "no training configuration yet" in result.output
    assert "training.example.toml" in result.output
    assert "cycle_length" not in result.output


def test_config_reports_a_broken_file_as_a_broken_file(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    declared = tmp_path / "training.toml"
    declared.write_text(
        'cycle_length = 3\nduration_cap_min = 45\nvolume_denominator = "cycle"\n'
        'split = [["chest"]]\nequipment = ["barbell"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAINER_CONFIG", str(declared))

    result = runner.invoke(main, ["config"])

    assert result.exit_code != 0
    assert "the training configuration is unusable" in result.output
    assert "1 workout(s)" in result.output and "3 workout(s)" in result.output


def test_config_muscle_groups_prints_all_seventeen(runner: CliRunner) -> None:
    result = runner.invoke(main, ["config", "--muscle-groups"])

    assert result.exit_code == 0, result.output
    assert "core: abdominals, lower back" in result.output
    assert "(no group): neck" in result.output
    listed = sum(
        len(line.split(":", 1)[1].split(","))
        for line in result.output.splitlines()
        if line and not line.startswith("mapping:")
    )
    assert listed == 17


def test_config_muscle_groups_prints_no_empty_group_line(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The day `neck` is assigned somewhere, `(no group)` has no members and a
    bare line ending in a colon is a line about nobody."""
    from trainer.engine import muscle_groups

    everything_grouped = muscle_groups.parse(
        "| muscle | group | why |\n"
        "|---|---|---|\n"
        "| `neck` | `shoulders` | suppose it were |\n"
    )
    monkeypatch.setattr(muscle_groups, "committed", lambda: everything_grouped)

    result = runner.invoke(main, ["config", "--muscle-groups"])

    assert result.exit_code == 0, result.output
    assert "(no group)" not in result.output
    assert "shoulders: neck" in result.output


# --- plan --------------------------------------------------------------------
#
# Against the real catalog, because the ids in a plan file are the real ones
# and a fixture catalog would let a plan pass here that no user could write.


def write_plan(tmp_path: Path, *blocks: dict[str, object]) -> str:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"blocks": list(blocks)}), encoding="utf-8")
    return str(path)


def squat_block(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "items": [{"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}],
        "rounds": 10,
        "rest": 210,
        "reason": "the heaviest lift while fresh",
    }
    base.update(overrides)
    return base


def test_plan_renders_a_valid_plan(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output
    assert "Barbell Squat" in result.output
    assert "10 rounds, 210s rest" in result.output
    assert "why: the heaviest lift while fresh" in result.output
    assert "of 45" in result.output
    assert result.output.isascii()


def test_plan_rejects_an_exercise_todays_equipment_does_not_reach(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    plan_file = write_plan(
        tmp_path,
        squat_block(items=[{"exercise_id": "Dumbbell_Bicep_Curl", "prescription": {"unit": "reps", "amount": 12}}]),
    )

    result = runner.invoke(
        main,
        ["plan", "--from", plan_file, "--equipment", "barbell", "--time", "45",
         "--group", "arms"],
    )

    assert result.exit_code != 0
    assert "Dumbbell_Bicep_Curl" in result.output
    assert "dumbbell" in result.output


def test_plan_rejects_an_over_budget_plan_and_prints_no_workout(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """A rendered plan under a refusal reads as a workout with a footnote."""
    plan_file = write_plan(tmp_path, squat_block(rounds=20, rest=180))

    result = runner.invoke(
        main,
        ["plan", "--from", plan_file, "--equipment", "barbell", "--time", "45",
         "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "45" in result.output
    assert "over" in result.output
    assert "Barbell Squat" not in result.output


def test_plan_honours_an_exclusion_given_on_the_command_line(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    plan_file = write_plan(tmp_path, squat_block())

    result = runner.invoke(
        main,
        ["plan", "--from", plan_file, "--equipment", "barbell", "--time", "45",
         "--exclude", "squat"],
    )

    assert result.exit_code != 0
    assert "excluded" in result.output


def test_plan_reports_a_file_that_is_not_a_plan_as_a_shape_error(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"blocks": [{"rounds": 4, "rest": 150}]}), encoding="utf-8")

    result = runner.invoke(
        main, ["plan", "--from", str(path), "--equipment", "barbell", "--time", "45"]
    )

    assert result.exit_code != 0
    assert "items" in result.output
    assert "Traceback" not in result.output


def test_plan_on_an_unenriched_catalog_names_that_state(
    runner: CliRunner, stocked: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "trainer enrich derive" in result.output


def test_plan_with_an_exclusion_on_an_unenriched_catalog_names_that_state(
    runner: CliRunner, stocked: Path, tmp_path: Path
) -> None:
    """`exclusions.classify` reads its vocabulary from the table, so against
    an unenriched catalog it rejects `squat` as neither a pattern nor a joint
    -- a correct value reported as a typo. The state has to be checked before
    any value is classified against it, not after."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--exclude", "squat"],
    )

    assert result.exit_code != 0
    assert "trainer enrich derive" in result.output


def test_plan_on_a_database_with_no_catalog_names_that_state(
    runner: CliRunner, database_file: Path, tmp_path: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "trainer db import" in result.output


def test_plan_needs_a_file_that_exists(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", str(tmp_path / "absent.json"),
         "--equipment", "barbell", "--time", "45"],
    )

    assert result.exit_code != 0
    assert "Traceback" not in result.output


# --- plan, persisted ---------------------------------------------------------
#
# `trainer plan` writes the workout it prescribes, in the command and nowhere
# else. What is asserted here is the row; that the agent cannot reach the
# writer is `test_agent.py`'s.


def workout_rows(path: Path) -> list[sqlite3.Row]:
    with closing(database.connect(path)) as connection:
        return connection.execute("SELECT * FROM workouts ORDER BY id").fetchall()


def test_plan_leaves_the_workout_it_prescribed(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output
    (row,) = workout_rows(enriched)
    assert row["state"] == "prescribed"
    assert row["prescribed_on"] == date.today().isoformat()
    assert row["performed_on"] is None

    with closing(database.connect(enriched)) as connection:
        prescribed = workouts.prescribed(connection, int(row["id"]))
    (block,) = prescribed
    assert block.reason == "the heaviest lift while fresh"
    assert block.block.rounds == 10
    assert block.block.rest == 210
    assert [item.exercise_id for item in block.block.items] == ["Barbell_Squat"]


def test_plan_from_the_graph_writes_one_workout_through_the_resume(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The graph stops at the plan and the node after the resume writes it
    (ADR-0005). The command has no buttons, so it resumes immediately -- and
    what must not happen is the workout being written twice, once by the node
    and once by the command that used to own the write."""
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")])

    result = runner.invoke(
        main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"]
    )

    assert result.exit_code == 0, result.output
    (row,) = workout_rows(enriched)
    assert row["state"] == "prescribed"
    with closing(database.connect(enriched)) as connection:
        (block,) = workouts.prescribed(connection, int(row["id"]))
    assert [item.exercise_id for item in block.block.items] == ["Barbell_Squat"]


def test_plan_the_validator_refuses_to_the_end_writes_nothing(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There is nothing to accept, so there is nothing to write."""
    from trainer.coach import planner

    from test_planner import plan_of

    scripted_graph(
        monkeypatch, documents=[plan_of("Dumbbell_Bench_Press")] * planner.ATTEMPTS
    )

    result = runner.invoke(
        main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"]
    )

    assert result.exit_code != 0
    assert workout_rows(enriched) == []


def test_plan_still_renders_exactly_as_before(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Persisting is a side effect, not a change to the command's output."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output
    assert "Barbell Squat" in result.output
    assert "10 rounds, 210s rest" in result.output
    assert "why: the heaviest lift while fresh" in result.output
    assert "of 45" in result.output
    assert result.output.isascii()


def test_planning_twice_leaves_two_workouts(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Two prescriptions, not one overwritten: the second is not a correction
    of the first, and an upsert would lose a deviation nobody could account
    for afterwards."""
    arguments = ["plan", "--from", write_plan(tmp_path, squat_block()),
                 "--equipment", "barbell", "--time", "45", "--group", "legs"]

    assert runner.invoke(main, arguments).exit_code == 0
    assert runner.invoke(main, arguments).exit_code == 0

    assert len(workout_rows(enriched)) == 2


def test_a_rejected_plan_writes_nothing_at_all(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """No workout row, and no orphaned blocks under one."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block(rounds=20, rest=180)),
         "--equipment", "barbell", "--time", "45"],
    )

    assert result.exit_code != 0
    with closing(database.connect(enriched)) as connection:
        for table in ("workouts", "workout_blocks", "workout_exercises"):
            total = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            assert total["n"] == 0, table


def test_a_plan_that_cannot_be_recorded_is_still_printed(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database that cannot be written to is worth an error; it is not worth
    throwing the workout away to report one. On the model path that plan cost
    a real run, and before persistence existed any plan that validated was
    printed."""

    def refuse(*args: object, **kwargs: object) -> int:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(workouts, "record_prescribed", refuse)

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "Barbell Squat" in result.output
    assert "disk I/O error" in result.output


def test_a_plan_the_shape_check_refuses_writes_nothing(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    path = tmp_path / "plan.json"
    path.write_text('{"blocks": [{"rounds": 3}]}', encoding="utf-8")

    result = runner.invoke(
        main, ["plan", "--from", str(path), "--equipment", "barbell", "--time", "45"]
    )

    assert result.exit_code != 0
    assert workout_rows(enriched) == []


# --- plan, with a model ------------------------------------------------------
#
# The model is a stand-in: `conftest.py` takes sockets and credentials away
# from the whole suite, and `trainer eval` is where the real one runs.


def scripted_graph(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> Any:
    """Put a scripted chat model where the planner graph builds a real one.

    `models.chat` is the one seam `trainer plan` comes through, and the
    provider and the model name travel with it into the run record.

    Each scripted turn must be a message of its own. `add_messages` keys on
    the message id, so the same `AIMessage` handed back twice is read as an
    edit of the first rather than a new turn -- and the run ends an exchange
    early, having apparently spent one fewer tool call than it did.
    """
    from trainer.coach import models

    from test_planner import Scripted

    model = Scripted(**kwargs)  # type: ignore[arg-type]
    monkeypatch.setattr(
        models, "chat", lambda: models.Chat(model, "scripted", "a-stand-in")
    )
    return model


def test_plan_asks_a_model_when_no_file_is_given(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import calling, plan_of

    scripted_graph(
        monkeypatch,
        turns=[calling("admissible_set", equipment=["barbell"], budget_min=45)],
        documents=[plan_of("Barbell_Squat")],
    )

    result = runner.invoke(
        main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"]
    )

    assert result.exit_code == 0, result.output
    assert "Barbell Squat" in result.output
    assert "1 of 12 tool calls" in result.output
    assert "a-stand-in on scripted" in result.output
    assert result.output.isascii()


def test_plan_prints_a_reason_the_console_cannot_encode(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every block carries a reason the model wrote, and a local model reaches
    for typography a cp1252 console cannot encode. A valid plan from
    `gpt-oss:20b` was lost to a non-breaking hyphen on its way to the screen."""
    from test_planner import plan_of

    scripted_graph(
        monkeypatch,
        documents=[plan_of("Barbell_Squat", reason="squat‑first, then the rest")],
    )

    result = runner.invoke(
        main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"]
    )

    assert result.exit_code == 0, result.output
    assert result.output.isascii()
    assert "squat-first, then the rest" in result.output


def test_plan_reports_a_plan_refused_on_its_last_attempt_and_prints_no_workout(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan the model emitted needs dumbbells nobody has today. The
    refusal goes back to the planner (ADR-0004), and when the attempts run out
    the workout is refused, not trimmed, and not shown."""
    from test_planner import plan_of
    from trainer.coach import planner

    model = scripted_graph(
        monkeypatch, documents=[plan_of("Dumbbell_Bicep_Curl") for _ in range(planner.ATTEMPTS)]
    )

    result = runner.invoke(
        main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"]
    )

    assert result.exit_code != 0
    assert "Dumbbell_Bicep_Curl" in result.output
    assert "Barbell Squat" not in result.output
    assert model.documents == [], "the refusal never went back to the planner"


def test_plan_writes_the_run_record_when_asked(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import calling, plan_of

    scripted_graph(
        monkeypatch,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )
    record = tmp_path / "run.json"

    result = runner.invoke(
        main,
        ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs",
         "--record", str(record)],
    )

    assert result.exit_code == 0, result.output
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["ending"] == "accepted"
    assert {node["provider"] for node in written["nodes"]} == {"scripted"}
    assert [call["name"] for call in written["calls"]] == ["allocate"]
    assert written["plan"]["blocks"][0]["items"][0]["exercise_id"] == "Barbell_Squat"


def test_plan_writes_the_record_even_when_the_plan_is_refused(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is exactly the case you open the record for, and it is the
    record that says which rule refused which attempt."""
    from test_planner import plan_of
    from trainer.coach import planner

    scripted_graph(
        monkeypatch,
        documents=[plan_of("Dumbbell_Bicep_Curl") for _ in range(planner.ATTEMPTS)],
    )
    record = tmp_path / "run.json"

    result = runner.invoke(
        main,
        ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs",
         "--record", str(record)],
    )

    assert result.exit_code != 0
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["ending"] == "refused"
    assert len(written["attempts"]) == planner.ATTEMPTS
    assert written["attempts"][-1]["violations"], "a refused run recorded no violation"
    assert written["plan"]["blocks"][0]["items"][0]["exercise_id"] == "Dumbbell_Bicep_Curl"


def test_plan_says_when_the_budget_ran_out(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import calling, plan_of

    scripted_graph(
        monkeypatch,
        turns=[calling("pattern_history", pattern="squat", cycles=3) for _ in range(10)],
        documents=[plan_of("Barbell_Squat")],
    )

    result = runner.invoke(
        main,
        ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs",
         "--call-budget", "2"],
    )

    assert result.exit_code == 0, result.output
    assert "budget spent" in result.output
    assert "Barbell Squat" in result.output, "it did not emit anyway"


def test_plan_with_a_file_asks_no_model(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--from` is the no-model path, and it has to stay one: a model built
    behind it would make the offline door depend on a provider."""
    from trainer.coach import models

    def refuse() -> object:
        raise AssertionError("--from must not reach a model")

    monkeypatch.setattr(models, "chat", refuse)

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output
    assert "tool calls" not in result.output


def test_plan_refuses_call_budget_with_a_hand_written_plan(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """`--from` asks no model, so there are no tool calls to bound. Ignored
    silently, the option reads as one that took effect."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--call-budget", "3"],
    )

    assert result.exit_code != 0
    assert "--call-budget" in result.output


def test_plan_refuses_record_with_a_hand_written_plan(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Exiting zero having written no file reads exactly like a record that
    was written."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--record", str(tmp_path / "run.json")],
    )

    assert result.exit_code != 0
    assert "--record" in result.output


def test_plan_refuses_a_record_path_it_cannot_write_before_calling_a_model(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record is the artefact the run exists to produce. Finding out the
    path is unwritable afterwards throws away a run that was paid for."""
    from trainer.coach import models

    def refuse() -> object:
        raise AssertionError("the model was called before the path was checked")

    monkeypatch.setattr(models, "chat", refuse)

    result = runner.invoke(
        main,
        ["plan", "--equipment", "barbell", "--time", "45",
         "--record", str(tmp_path / "absent" / "run.json")],
    )

    assert result.exit_code != 0
    assert "no directory" in result.output


def test_admissible_narrows_to_the_groups_asked_for(
    runner: CliRunner, enriched: Path
) -> None:
    """A leg day has no business seeing the curls."""
    whole = runner.invoke(main, ["admissible", "--equipment", "dumbbell", "--time", "45"])
    legs = runner.invoke(
        main,
        ["admissible", "--equipment", "dumbbell", "--time", "45", "--group", "legs"],
    )

    def shown(output: str) -> int:
        return int(output.rsplit("showing ", 1)[1].split()[0])

    assert legs.exit_code == 0, legs.output
    assert shown(legs.output) < shown(whole.output)
    assert "Dumbbell Squat" in legs.output
    assert "Dumbbell Bicep Curl" not in legs.output


def test_admissible_rejects_a_muscle_where_a_group_belongs(
    runner: CliRunner, enriched: Path
) -> None:
    result = runner.invoke(
        main,
        ["admissible", "--equipment", "dumbbell", "--time", "45", "--group", "quadriceps"],
    )

    assert result.exit_code != 0
    assert "not a muscle group" in result.output


def test_plan_checks_a_hand_written_plan_against_what_today_trains(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """A curl on a leg day is refused, and the refusal says which of the two
    it is rather than calling it a bad choice."""
    plan_file = write_plan(
        tmp_path,
        squat_block(items=[{"exercise_id": "Dumbbell_Bicep_Curl", "prescription": {"unit": "reps", "amount": 12}}]),
    )

    result = runner.invoke(
        main,
        ["plan", "--from", plan_file, "--equipment", "dumbbell", "--time", "45",
         "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "biceps" in result.output
    assert "legs" in result.output


# --- the request the agent is actually asked ---------------------------------

SPLIT = """\
cycle_length = 4
duration_cap_min = 60
volume_denominator = "cycle"
goal = "hypertrophy"
equipment = ["barbell"]
split = [
    ["chest", "shoulders", "arms"],
    ["back", "arms"],
    ["legs", "core"],
    ["chest", "back", "shoulders"],
]
"""


@pytest.fixture()
def declared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    written = tmp_path / "training.toml"
    written.write_text(SPLIT, encoding="utf-8")
    monkeypatch.setenv("TRAINER_CONFIG", str(written))
    return written


def test_plan_takes_its_groups_from_the_workout_of_the_split(
    runner: CliRunner, enriched: Path, declared: Path, tmp_path: Path
) -> None:
    """Workout 3 of that cycle is legs and core, so a curl is not today."""
    plan_file = write_plan(
        tmp_path,
        squat_block(items=[{"exercise_id": "Dumbbell_Bicep_Curl",
                            "prescription": {"unit": "reps", "amount": 12}}]),
    )

    result = runner.invoke(
        main,
        ["plan", "--from", plan_file, "--equipment", "dumbbell", "--workout", "3"],
    )

    assert result.exit_code != 0
    assert "biceps" in result.output
    assert "legs" in result.output


def test_plan_defaults_the_time_to_the_declared_cap(
    runner: CliRunner, enriched: Path, declared: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block(rounds=14)),
         "--equipment", "barbell", "--workout", "3"],
    )

    assert result.exit_code == 0, result.output
    assert "of 60" in result.output


def test_plan_refuses_a_time_over_the_declared_cap(
    runner: CliRunner, enriched: Path, declared: Path, tmp_path: Path
) -> None:
    """Refused and not clamped: quietly planning 60 minutes for someone who
    asked for 90 is the engine deciding how long to train."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--workout", "3", "--time", "90"],
    )

    assert result.exit_code != 0
    assert "over the 60" in result.output


def test_plan_reports_a_workout_outside_the_cycle_as_a_state(
    runner: CliRunner, enriched: Path, declared: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--workout", "9"],
    )

    assert result.exit_code != 0
    assert "outside a cycle of 4" in result.output
    assert "1 to 4" in result.output


def test_plan_with_no_training_config_names_that_state(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never a complaint about a missing field: nobody has declared anything
    yet, and the way out is copying the example."""
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--workout", "2"],
    )

    assert result.exit_code != 0
    assert "no training configuration yet" in result.output
    assert "training.example.toml" in result.output


def test_plan_refuses_a_workout_and_a_group_together(
    runner: CliRunner, enriched: Path, declared: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--workout", "3", "--group", "arms"],
    )

    assert result.exit_code != 0
    assert "one or the other" in result.output


def test_plan_refuses_a_time_over_the_cap_without_a_workout_too(
    runner: CliRunner, enriched: Path, declared: Path, tmp_path: Path
) -> None:
    """The cap is a ceiling on any workout, not one that only applies when the
    rotation is named. Loading the configuration only when `--workout` was
    given let `--time 500` straight through."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "500"],
    )

    assert result.exit_code != 0
    assert "over the 60" in result.output


def test_plan_works_with_no_training_config_when_time_is_given(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No declared rotation is a state, not a failure: `--time` and `--group`
    name everything a plan needs, so somebody who has not written the file yet
    can still ask for a workout."""
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output
    assert "of 45" in result.output


def test_plan_reports_a_mistyped_group_in_words(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """`trainer admissible` answers the same typo cleanly, so a traceback here
    would be the two commands disagreeing about one mistake."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "chets"],
    )

    assert result.exit_code != 0
    assert "not a muscle group" in result.output
    assert "Traceback" not in result.output


def test_plan_survives_the_same_group_named_twice(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Left in, the even division sums to half a workout -- arithmetic nobody
    wrote, blamed on the person who typed the flag twice."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output


def test_plan_refuses_a_preference_that_names_no_exercise(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """A mistyped id is the worst outcome available: the preference is
    silently unenforced, and the typo travels to the model as something it
    must not prescribe."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--avoid", "Barbel_Squat"],
    )

    assert result.exit_code != 0
    assert "no such exercise: 'Barbel_Squat'" in result.output


# --- eval --------------------------------------------------------------------
#
# The command itself, not a pass of it: the suite has no sockets and no
# credentials, so what is checked here is that it stops at that state rather
# than reaching for a provider, and that its arguments behave.


def test_eval_stops_at_the_credentials_state_rather_than_a_socket(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`conftest.py` takes both away from every test. If this ever reached the
    network the no-network fixture would fail the run instead -- which is the
    point: a suite that could quietly start spending money is not a suite.

    The provider is checked **once, before anything runs**, so what comes out
    is the state and its fix rather than eighteen rows of *not run* under a
    matrix of dashes.
    """
    monkeypatch.setenv("LLM_BACKEND", "groq")

    result = runner.invoke(main, ["eval", "--repetitions", "1"])

    assert result.exit_code != 0
    assert "no Groq credentials" in result.output
    assert "no-equipment" not in result.output, "it ran the pass anyway"


def test_eval_names_the_situations_when_one_is_mistyped(
    runner: CliRunner, enriched: Path
) -> None:
    result = runner.invoke(main, ["eval", "--only", "no-equipmnet"])

    assert result.exit_code != 0
    assert "no situation called" in result.output
    assert "no-equipment" in result.output


def test_eval_leaves_no_records_directory_behind_when_it_never_runs(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The suite invokes this command to check it stops at the credentials
    state. A directory made before the first request is litter in whatever
    working directory pytest happened to start in."""
    monkeypatch.setenv("LLM_BACKEND", "groq")
    records = tmp_path / "eval-runs"

    runner.invoke(main, ["eval", "--repetitions", "1", "--records", str(records)])

    assert not records.exists()


def test_eval_runs_a_situation_named_twice_only_once(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Left in, it runs twice the repetitions against a paid provider and
    prints two identical rows."""
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")] * 10)

    result = runner.invoke(
        main,
        ["eval", "--repetitions", "1", "--records", str(tmp_path / "records"),
         "--only", "no-equipment", "--only", "no-equipment"],
    )

    # The invariant matrix only: the planner's own figures are a second table
    # with a row per situation, and counting both would count one run twice.
    invariants = result.output.split("what the planner spent")[0]
    rows = [
        line for line in invariants.splitlines() if line.startswith("no-equipment")
    ]
    assert len(rows) == 1, result.output
    assert "of 1 runs" in result.output, "it ran the situation more than once"


# --- eval --suite log --------------------------------------------------------
#
# The log set the command scores against is a document, and `TRAINER_LOG_SET`
# points these tests at a small one written here: what is covered is the
# command -- the pre-flight, the selector, the arguments -- and not the
# committed thirty rows, which `test_log_set.py` reads and the closing report
# runs. The ids are real ones, and their pattern and muscles are the real
# catalog's, because the volume figures below are checked against it.

LOG_SET = """# A log set, for the command's own tests

## What the runner has to set up

- **`today` is `2026-09-10`** for every row.
- **The bar: the unambiguous half holds at 80%, the must-ask half at 60%**.
- **One prior performed workout supplies the load history**:
  `Barbell_Squat` last recorded at **80 kg**.

## 1. The prescriptions

### P1 — leg day

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 4 | 180 | `Barbell_Squat` | 5 reps | squat | quadriceps |

## 2. One unambiguous report

### U1 — perfect adherence — P1

> tutto liscio, fatto come sta scritto

```json
{
  "workout_id": 1,
  "blocks": [],
  "proposed_exclusion": null
}
```

- **volume (pattern):** squat 4
- **volume (muscle):** quadriceps 4

## 3. One report that must make it ask

### A1 — how many rounds — P1

> ho tolto qualche serie di squat

- **unknowable:** "qualche serie" gives a direction and no number.
- **wrong answer:** `rounds: 3` on the squat block.
"""


@pytest.fixture()
def log_set_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "eval-set.md"
    path.write_text(LOG_SET, encoding="utf-8")
    monkeypatch.setenv("TRAINER_LOG_SET", str(path))
    return path


def test_the_log_suite_stops_at_the_credentials_state_too(
    runner: CliRunner,
    enriched: Path,
    log_set_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Everything before the provider has to work for this message to be the
    one that comes out: the set parses, the fixture is built, and the rows
    agree with the catalog. Then it stops, because there are no credentials --
    with the state and its fix, and no matrix of dashes under it."""
    monkeypatch.setenv("LLM_BACKEND", "groq")

    result = runner.invoke(main, ["eval", "--suite", "log", "--repetitions", "1"])

    assert result.exit_code != 0
    assert "no Groq credentials" in result.output
    assert "the report determines" not in result.output, "it ran the pass anyway"


def test_the_log_suite_names_the_reports_when_one_is_mistyped(
    runner: CliRunner, enriched: Path, log_set_file: Path
) -> None:
    result = runner.invoke(main, ["eval", "--suite", "log", "--only", "U7"])

    assert result.exit_code != 0
    assert "no report called 'U7'" in result.output
    assert "U1" in result.output and "A1" in result.output


def test_a_set_that_disagrees_with_the_catalog_is_refused_before_it_spends(
    runner: CliRunner, enriched: Path, log_set_file: Path
) -> None:
    """A volume figure its own expected document does not produce would fail a
    correct agent three runs at a time. It costs nothing to catch here, and
    the message is what proves nothing was spent -- the credentials state is
    further down."""
    log_set_file.write_text(
        LOG_SET.replace("**volume (pattern):** squat 4", "**volume (pattern):** squat 9"),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["eval", "--suite", "log", "--repetitions", "1"])

    assert result.exit_code != 0
    assert "U1 says it produces squat 9" in result.output
    assert "no Groq credentials" not in result.output


def test_a_set_naming_an_exercise_the_catalog_does_not_have(
    runner: CliRunner, enriched: Path, log_set_file: Path
) -> None:
    log_set_file.write_text(
        LOG_SET.replace("`Barbell_Squat` | 5 reps", "`Barbell_Sqaut` | 5 reps"),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["eval", "--suite", "log", "--repetitions", "1"])

    assert result.exit_code != 0
    assert "the set names Barbell_Sqaut, which this catalog does not have" in result.output


def test_a_log_set_that_cannot_be_read_says_so_as_a_state(
    runner: CliRunner, enriched: Path, log_set_file: Path
) -> None:
    log_set_file.write_text(
        LOG_SET.replace("- **unknowable:**", "- **hunch:**"), encoding="utf-8"
    )

    result = runner.invoke(main, ["eval", "--suite", "log", "--repetitions", "1"])

    assert result.exit_code != 0
    assert "the log set is unusable" in result.output
    assert "unknowable" in result.output


def test_the_plan_suite_is_what_the_command_still_means_by_default(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Session 4's measurement is reachable and unchanged: the same six rows,
    whether the suite is asked for or not."""
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")] * 60)
    written = ["--records", str(tmp_path / "records")]

    default = runner.invoke(main, ["eval", "--repetitions", "1", *written])
    asked_for = runner.invoke(
        main, ["eval", "--suite", "plan", "--repetitions", "1", *written]
    )

    for output in (default.output, asked_for.output):
        for situation in ("no-equipment", "half-refused", "contradictory", "refused"):
            assert situation in output
    assert "not degenerate" in default.output


def test_the_plan_suite_reports_what_the_planner_itself_spent(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whether this model can plan on this laptop is a question about attempts
    and minutes, and the invariant matrix says nothing about either."""
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")] * 10)

    result = runner.invoke(
        main,
        ["eval", "--repetitions", "1", "--records", str(tmp_path / "records"),
         "--only", "no-equipment"],
    )

    assert "what the planner spent getting there:" in result.output
    for column in ("attempts", "seconds", "tool calls", "refused by"):
        assert column in result.output
    assert result.output.isascii()


# --- log ---------------------------------------------------------------------
#
# Against the real catalog, for the reason the plan tests are: the ids in a
# report are the real ones, and a fixture catalog would let a document pass
# here that no user could write.


def write_report(tmp_path: Path, **fields: object) -> str:
    base: dict[str, object] = {"blocks": [], "report": "went fine"}
    base.update(fields)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    return str(path)


def performed_block(*items: dict[str, object], **fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "items": list(items),
        "rounds": 3,
        "rounds_source": "reported",
        "rest": 90,
        "rest_source": "reported",
    }
    base.update(fields)
    return base


def performed_item(exercise_id: str, **fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "exercise_id": exercise_id,
        "unit": "reps",
        "amount": 8,
        "amount_source": "reported",
    }
    base.update(fields)
    return base


def prescribed_workout(runner: CliRunner, tmp_path: Path) -> int:
    """One squat block on the real catalog, prescribed through the command
    that prescribes it. Its id, which a report names."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45", "--group", "legs"],
    )
    assert result.exit_code == 0, result.output
    return int(workout_rows(database.database_path())[-1]["id"])


def test_log_sets_prescribed_against_performed(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    identifier = prescribed_workout(runner, tmp_path)

    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            workout_id=identifier,
            blocks=[performed_block(performed_item("Barbell_Squat", amount=5))],
            report="only three sets, the knee was noisy",
        )],
    )

    assert result.exit_code == 0, result.output
    assert f"prescribed (workout {identifier}):" in result.output
    assert "block 1 -- 10 rounds, 210s rest" in result.output
    assert "performed:" in result.output
    assert "Barbell Squat" in result.output
    assert "said: only three sets, the knee was noisy" in result.output
    assert result.output.isascii()


def test_log_writes_the_workout_it_understood(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    identifier = prescribed_workout(runner, tmp_path)

    runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            workout_id=identifier,
            blocks=[performed_block(
                performed_item("Barbell_Squat", amount=5, load_kg=100, load_kg_source="reported")
            )],
            report="heavy",
        )],
    )

    with closing(database.connect(enriched)) as connection:
        written = workouts.workout(connection, identifier)
        assert written is not None
        assert written.state == "performed"
        assert written.report == "heavy"
        # Both phases, side by side. Deviation is the difference between them.
        assert len(workouts.prescribed(connection, identifier)) == 1
        performed = workouts.performed(connection, identifier)
        assert performed[0].items[0].load_kg == 100.0


def test_log_fills_in_what_the_report_did_not_mention(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Adherence: what a report does not mention was done as prescribed, and
    every number it filled in is printed marked."""
    identifier = prescribed_workout(runner, tmp_path)

    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path, workout_id=identifier, report="tutto come previsto"
        )],
    )

    assert result.exit_code == 0, result.output
    assert "8 reps (assumed)" in result.output
    assert "10 rounds (assumed)" in result.output
    with closing(database.connect(enriched)) as connection:
        performed = workouts.performed(connection, identifier)
    assert performed[0].items[0].amount_source == "assumed"


def test_log_refuses_an_exercise_the_catalog_does_not_have(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path, blocks=[performed_block(performed_item("Barbel_Squat"))]
        )],
    )

    assert result.exit_code != 0
    assert "Barbel_Squat" in result.output
    assert "Traceback" not in result.output


def test_log_writes_an_exercise_performed_under_an_exclusion(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """The row this ticket exists to protect. Recorded and flagged, never
    refused: an exclusion the user trained straight through is what session 9
    forms a hypothesis about."""
    with closing(database.connect(enriched)) as connection:
        exclusions.add(
            connection, exclusions.Exclusion("pattern", "vertical push"), "2099-01-01"
        )
        connection.commit()

    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            blocks=[performed_block(performed_item("Standing_Military_Press", amount=10))],
            report="ho spinto lo stesso",
        )],
    )

    assert result.exit_code == 0, result.output
    assert "! is under an exclusion on pattern 'vertical push'" in result.output
    with closing(database.connect(enriched)) as connection:
        written = connection.execute(
            "SELECT COUNT(*) AS total FROM workout_exercises "
            "WHERE exercise_id = 'Standing_Military_Press' AND phase = 'performed'"
        ).fetchone()
    assert written["total"] == 1


def test_log_records_a_workout_nobody_planned(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Training nobody planned is still training. Every value in it is the
    user's, because there was nothing to assume against."""
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            blocks=[performed_block(performed_item("Barbell_Squat", amount_source="asked"))],
            report="palestra di un amico",
        )],
    )

    assert result.exit_code == 0, result.output
    assert "prescribed: nothing -- this workout was not planned" in result.output
    assert "! this reports no prescribed workout" in result.output
    with closing(database.connect(enriched)) as connection:
        row = connection.execute("SELECT * FROM workouts").fetchone()
        sources = {
            found["amount_source"]
            for found in connection.execute(
                "SELECT amount_source FROM workout_exercises WHERE phase = 'performed'"
            )
        }
    assert row["prescribed_on"] is None and row["state"] == "performed"
    assert sources == {"asked"}


def test_log_writes_the_exclusion_the_report_proposes(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            blocks=[performed_block(performed_item("Barbell_Squat"))],
            proposed_exclusion={
                "value": "shoulder",
                "retest_date": "2099-01-01",
                "why": "tirava sotto il bilanciere",
            },
            report="la spalla tirava",
        )],
    )

    assert result.exit_code == 0, result.output
    assert "proposes excluding joint 'shoulder' until 2099-01-01" in result.output
    with closing(database.connect(enriched)) as connection:
        assert exclusions.active(connection, "2026-09-09") == (
            exclusions.Exclusion("joint", "shoulder"),
        )


def test_log_refuses_a_proposed_exclusion_that_is_neither_granularity(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            blocks=[performed_block(performed_item("Barbell_Squat"))],
            proposed_exclusion={
                "value": "Barbell_Squat",
                "retest_date": "2099-01-01",
                "why": "non mi piace",
            },
        )],
    )

    assert result.exit_code != 0
    assert "movement pattern" in result.output and "joint" in result.output
    assert "never an exercise id" in result.output


def test_log_reports_a_file_that_is_not_a_performed_workout_as_a_shape_error(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps({"blocks": [{"items": [], "rounds": 3}], "report": "x"}),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["log", "--from", str(path)])

    assert result.exit_code != 0
    assert "that is not a performed workout" in result.output
    assert "blocks.0.items" in result.output
    assert "Traceback" not in result.output


def test_log_reports_a_refused_workout_and_writes_nothing(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            workout_id=404,
            blocks=[performed_block(performed_item("Barbell_Squat"))],
        )],
    )

    assert result.exit_code != 0
    assert "no workout 404" in result.output
    assert workout_rows(enriched) == []


def test_log_on_an_unenriched_catalog_names_that_state(
    runner: CliRunner, stocked: Path, tmp_path: Path
) -> None:
    """`exclusions.classify` reads its vocabulary from the table, so against
    an unenriched catalog it would reject `vertical push` as neither. The
    state is checked before any value is classified against it."""
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path, blocks=[performed_block(performed_item("Barbell_Squat"))]
        )],
    )

    assert result.exit_code != 0
    assert "trainer enrich derive" in result.output


def test_log_on_a_database_with_no_catalog_names_that_state(
    runner: CliRunner, database_file: Path, tmp_path: Path
) -> None:
    runner.invoke(main, ["db", "init"])

    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path, blocks=[performed_block(performed_item("Barbell_Squat"))]
        )],
    )

    assert result.exit_code != 0
    assert "trainer db import" in result.output


def test_log_needs_a_file_that_exists(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(main, ["log", "--from", str(tmp_path / "absent.json")])

    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_log_with_no_file_reaches_for_a_model_rather_than_a_file(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare `trainer log` is the interactive path, and it runs on whichever
    provider `LLM_BACKEND` names now. The suite has no credentials, so it gets
    as far as the state that says so -- which is the proof it went looking for
    a model and not for `--from`.

    And it says so **before** asking for the report. Prompting first means the
    user writes out their whole workout and then loses it to an error that was
    already true when they started typing.
    """
    monkeypatch.setenv("LLM_BACKEND", "groq")

    result = runner.invoke(main, ["log"], input="panca bene, tutto come scritto\n")

    assert "no Groq credentials" in result.output
    assert "What did you do" not in result.output


# --- log, with a model -------------------------------------------------------
#
# The stand-in again: `conftest.py` takes sockets and credentials away from the
# whole suite, and `trainer eval` is where the real one runs. What is covered
# here is the command -- which workout it opens with, what it prints, what it
# asks before writing, and the fact that nothing is written until it is done.


def logged(
    monkeypatch: pytest.MonkeyPatch, emitted: Any, turns: Any = None
) -> Any:
    """A scripted logging model, holding the document it will emit.

    The same seam as the planner's: `trainer log` runs the logger graph on
    whatever `models.chat` answers, which is what makes both commands one
    thing with two prompts. The document is emitted on every attempt, so a
    refused one is refused to the end.
    """
    from langchain_core.messages import AIMessage

    from trainer.coach import logger

    return scripted_graph(
        monkeypatch,
        turns=list(turns or [AIMessage(content="tutto chiaro")]),
        raw=[emitted.model_dump_json()] * logger.ATTEMPTS,
    )


def asking(question: str) -> Any:
    """A turn that calls `ask_user`, which is how the graph is asked to ask."""
    from langchain_core.messages import AIMessage

    from trainer.coach import logger

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": logger.ask_user.__name__,
                "args": {"question": question},
                "id": "call_ask",
                "type": "tool_call",
            }
        ],
    )


def briefed(model: Any) -> str:
    """Everything the model was shown on its first turn."""
    return "\n".join(message.text for message in model.seen[0])


def report_of(**fields: object) -> object:
    from trainer import log as logs

    base: dict[str, object] = {"report": "fatto"}
    base.update(fields)
    return logs.PerformedWorkout(**base)  # type: ignore[arg-type]


def performed_document_block(exercise_id: str, **fields: object) -> object:
    from trainer import log as logs

    item: dict[str, object] = {
        "exercise_id": exercise_id,
        "unit": "reps",
        "amount": 8,
        "amount_source": "reported",
    }
    item.update(
        {
            key: fields.pop(key)
            for key in ("amount", "amount_source")
            if key in fields
        }
    )
    base: dict[str, object] = {
        "items": [logs.PerformedItem(**item)],  # type: ignore[arg-type]
        "rounds": 3,
        "rounds_source": "reported",
        "rest": 150,
        "rest_source": "reported",
    }
    base.update(fields)
    return logs.PerformedBlock(**base)  # type: ignore[arg-type]


def test_log_reads_what_you_said_against_what_was_prescribed(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TRAINER.md's own sentence, end to end: the deviation is recorded and
    the state moves on both axes."""
    identifier = prescribed_workout(runner, tmp_path)
    logged(
        monkeypatch,
        report_of(
            workout_id=identifier,
            blocks=[performed_document_block("Barbell_Squat", rounds=3)],
            report="panca bene, solo 3 serie di squat perche la spalla tirava",
        ),
    )

    result = runner.invoke(
        main,
        ["log", "--say", "panca bene, solo 3 serie di squat perche la spalla tirava"],
    )

    assert result.exit_code == 0, result.output
    assert f"prescribed (workout {identifier}):" in result.output
    assert "block 1 -- 3 rounds" in result.output
    assert "said: panca bene" in result.output
    with closing(database.connect(enriched)) as connection:
        found = workouts.workout(connection, identifier)
        assert found is not None and found.state == "performed"


def test_log_opens_with_the_workout_that_is_waiting_for_a_report(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which workout is open is a fact and the command resolves it. Which
    workout the report is *about* stays the model's reading of the sentence."""
    identifier = prescribed_workout(runner, tmp_path)
    model = logged(
        monkeypatch,
        report_of(workout_id=identifier, report="tutto come scritto"),
    )

    result = runner.invoke(main, ["log", "--say", "tutto come scritto"])

    assert result.exit_code == 0, result.output
    written = briefed(model)
    assert f"prescribed_workout({identifier})" in written
    assert "tutto come scritto" in written


def test_log_asks_what_you_did_when_you_do_not_say(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = prescribed_workout(runner, tmp_path)
    model = logged(monkeypatch, report_of(workout_id=identifier, report="andata bene"))

    result = runner.invoke(main, ["log"], input="andata bene\n")

    assert result.exit_code == 0, result.output
    assert "What did you do" in result.output
    assert "andata bene" in briefed(model)


def test_log_puts_the_clarifying_question_to_you_and_keeps_the_answer(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer lands with a provenance of `asked` -- which is the column
    that separates a number the user gave from one the system supplied."""
    identifier = prescribed_workout(runner, tmp_path)
    logged(
        monkeypatch,
        report_of(
            workout_id=identifier,
            blocks=[
                performed_document_block(
                    "Barbell_Squat", amount=5, amount_source="asked"
                )
            ],
            report="squat, 4 su 10",
        ),
        turns=[asking("Quel 4 e' fatica o fastidio?"), AIMessage(content="chiaro")],
    )

    result = runner.invoke(main, ["log", "--say", "squat, 4 su 10"], input="fastidio\n")

    assert result.exit_code == 0, result.output
    assert "? Quel 4 e' fatica o fastidio?" in result.output
    assert "5 reps (asked)" in result.output
    assert "1 question(s) asked" in result.output
    with closing(database.connect(enriched)) as connection:
        (block,) = workouts.performed(connection, identifier)
        assert block.items[0].amount_source == "asked"


def test_log_prints_a_question_and_a_report_the_console_can_show(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`trainer log` is the first command that prints prose this project did
    not write -- the user's own report, and a model's question. A run of it put
    an accented word and an em dash on a code-page-437 console as replacement
    characters, which is the standing rule's own failure arriving by a route
    nothing guarded.

    Presentation only: the report is **stored** exactly as it was typed.
    """
    identifier = prescribed_workout(runner, tmp_path)
    said = "panca bene \u2014 perch\u00e9 la spalla non tirava"
    logged(
        monkeypatch,
        report_of(workout_id=identifier, report=said),
        turns=[
            asking("Quanto pesava \u2014 pi\u00f9 o meno?"),
            AIMessage(content="fine"),
        ],
    )

    result = runner.invoke(main, ["log", "--say", said], input="60 kg\n")

    assert result.exit_code == 0, result.output
    assert result.output.isascii(), result.output
    assert "Quanto pesava -- piu o meno?" in result.output
    assert "said: panca bene -- perche la spalla non tirava" in result.output
    with closing(database.connect(enriched)) as connection:
        found = workouts.workout(connection, identifier)
        assert found is not None
        assert found.report == said, "the row keeps the user's own words"


def test_log_writes_the_exclusion_the_model_proposes_only_once_you_confirm(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = prescribed_workout(runner, tmp_path)
    logged(monkeypatch, _with_a_proposal(identifier))

    result = runner.invoke(main, ["log", "--say", "la spalla tirava"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "proposes excluding joint 'shoulder' until 2099-01-01" in result.output
    assert "Stop prescribing joint 'shoulder'" in result.output
    with closing(database.connect(enriched)) as connection:
        assert exclusions.active(connection, "2026-09-09") == (
            exclusions.Exclusion("joint", "shoulder"),
        )


def test_log_declining_the_proposal_writes_the_workout_and_no_exclusion(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report keeps the user's words either way, so the remark that
    prompted the proposal is still on the row."""
    identifier = prescribed_workout(runner, tmp_path)
    logged(monkeypatch, _with_a_proposal(identifier))

    result = runner.invoke(main, ["log", "--say", "la spalla tirava"], input="n\n")

    assert result.exit_code == 0, result.output
    with closing(database.connect(enriched)) as connection:
        assert exclusions.active(connection, "2026-09-09") == ()
        found = workouts.workout(connection, identifier)
        assert found is not None and found.state == "performed"
        assert found.report == "la spalla tirava sui military"


def _with_a_proposal(identifier: int) -> object:
    from trainer import log as logs

    return report_of(
        workout_id=identifier,
        blocks=[performed_document_block("Barbell_Squat")],
        report="la spalla tirava sui military",
        proposed_exclusion=logs.ProposedExclusion(
            value="shoulder", retest_date="2099-01-01", why="la spalla tirava"
        ),
    )


def test_log_writes_nothing_when_the_conversation_is_interrupted(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C at a question, which the runner delivers as no input at all.
    The workout is still prescribed and nothing about the report is stored."""
    identifier = prescribed_workout(runner, tmp_path)
    logged(
        monkeypatch,
        report_of(workout_id=identifier, report="4 su 10"),
        turns=[asking("Fatica o fastidio?")],
    )

    result = runner.invoke(main, ["log", "--say", "4 su 10"], input="")

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    with closing(database.connect(enriched)) as connection:
        found = workouts.workout(connection, identifier)
        assert found is not None and found.state == "prescribed"
        assert workouts.performed(connection, identifier) == ()


def test_log_reports_a_refused_document_and_writes_nothing(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An id the model remembered rather than read. The refusal names it, and
    the workout stays prescribed."""
    identifier = prescribed_workout(runner, tmp_path)
    logged(
        monkeypatch,
        report_of(
            workout_id=identifier,
            blocks=[performed_document_block("Barbell_Squat_Deep_Pause")],
            report="squat",
        ),
    )

    result = runner.invoke(main, ["log", "--say", "squat"])

    assert result.exit_code != 0
    assert "Barbell_Squat_Deep_Pause" in result.output
    with closing(database.connect(enriched)) as connection:
        found = workouts.workout(connection, identifier)
        assert found is not None and found.state == "prescribed"


def test_log_writes_the_run_record_when_asked(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = prescribed_workout(runner, tmp_path)
    logged(
        monkeypatch,
        report_of(workout_id=identifier, report="4 su 10"),
        turns=[asking("Fatica o fastidio?"), AIMessage(content="chiaro")],
    )
    record = tmp_path / "run.json"

    result = runner.invoke(
        main, ["log", "--say", "4 su 10", "--record", str(record)], input="fastidio\n"
    )

    assert result.exit_code == 0, result.output
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["questions"] == [["Fatica o fastidio?", "fastidio"]]
    assert written["performed"]["workout_id"] == identifier
    assert written["ending"] == "done"


def test_log_from_a_file_refuses_the_options_that_ask_a_model(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """`--from` is the no-model path, so there is no run to record and nothing
    to say to anybody. Silently ignored, the command exits zero having written
    no file, which reads exactly like a record that was written."""
    result = runner.invoke(
        main,
        ["log", "--from", write_report(tmp_path), "--record", str(tmp_path / "r.json")],
    )

    assert result.exit_code != 0
    assert "--record has no meaning with --from" in result.output


def test_log_from_a_file_still_writes_its_exclusion_without_being_asked(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """The author of a hand-written document wrote the proposal themselves.
    The confirmation exists because a *model* read one out of a passing
    remark, and asking somebody to confirm the line they just typed is noise.
    """
    result = runner.invoke(
        main,
        ["log", "--from", write_report(
            tmp_path,
            blocks=[performed_block(performed_item("Barbell_Squat"))],
            proposed_exclusion={
                "value": "vertical push",
                "retest_date": "2099-01-01",
                "why": "scritto a mano",
            },
        )],
    )

    assert result.exit_code == 0, result.output
    assert "Stop prescribing" not in result.output


# --- `trainer state`: what has been trained, and what has not ----------------


def performed_workout(
    runner: CliRunner, tmp_path: Path, **report: Any
) -> None:
    """Prescribe a squat workout and report it, both through the commands."""
    identifier = prescribed_workout(runner, tmp_path)
    report.setdefault("blocks", [performed_block(performed_item("Barbell_Squat"))])
    report.setdefault("report", "done")
    result = runner.invoke(
        main,
        ["log", "--from", write_report(tmp_path, workout_id=identifier, **report)],
    )
    assert result.exit_code == 0, result.output


def test_state_on_a_database_nobody_has_trained_against(
    runner: CliRunner, enriched: Path
) -> None:
    """Every figure is a state and none of them is an error: nobody having
    trained yet is the first thing this command ever prints."""
    result = runner.invoke(main, ["state"])

    assert result.exit_code == 0, result.output
    assert "rotation: workout 1 of 4, cycle 1 -- 0 workout(s) performed" in result.output
    assert "nothing performed and nothing waiting" in result.output
    assert "unreported, whenever prescribed: none" in result.output
    assert result.output.isascii()


def test_state_counts_the_rounds_that_were_performed(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    performed_workout(runner, tmp_path)

    result = runner.invoke(main, ["state"])

    assert result.exit_code == 0, result.output
    assert "rotation: workout 2 of 4, cycle 1 -- 1 workout(s) performed" in result.output
    assert "adherence: 1 performed, 0 unreported, 0 nobody planned" in result.output


def test_state_reports_both_axes(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Neither catches the other's degeneration, so an answer giving one of
    them would be read as the whole picture (ADR-0001)."""
    performed_workout(runner, tmp_path)

    result = runner.invoke(main, ["state"])

    assert "volume per pattern, in rounds performed:" in result.output
    assert "volume per muscle, in rounds performed:" in result.output
    assert "squat" in result.output
    assert "quadriceps" in result.output


def test_state_shows_the_rounds_a_shortened_workout_did_not_do(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Ten rounds prescribed, two performed: the deficit is the eight nobody
    did, and it is the same number a substitution or a skipped workout would
    have produced."""
    performed_workout(
        runner,
        tmp_path,
        blocks=[performed_block(performed_item("Barbell_Squat"), rounds=2)],
    )

    result = runner.invoke(main, ["state"])

    squat = next(line for line in result.output.splitlines() if "  squat" in line)
    assert squat.split() == ["squat", "2", "10", "8", "-"]


def test_state_says_that_the_unreported_list_is_not_windowed(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """The adherence line counts the unreported workouts *of the window*; the
    list names every one there is. Printed under one word, the two numbers
    would contradict each other on the same screen."""
    old = prescribed_workout(runner, tmp_path)
    with closing(database.connect(database.database_path())) as connection:
        connection.execute(
            "UPDATE workouts SET prescribed_on = '2020-01-01' WHERE id = ?", (old,)
        )
        connection.commit()
    # A full cycle of workouts since, all today, so the window starts today
    # and the 2020 prescription is outside it.
    for _ in range(4):
        performed_workout(runner, tmp_path)

    result = runner.invoke(main, ["state"])

    assert "adherence: 4 performed, 0 unreported, 0 nobody planned" in result.output
    assert "unreported, whenever prescribed:" in result.output
    assert f"workout {old}, prescribed 2020-01-01" in result.output


def test_state_leaves_out_the_workout_you_have_not_done_yet(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """`trainer plan` writes a prescribed row every time it runs, and nobody
    has failed to do a workout they are about to do."""
    prescribed_workout(runner, tmp_path)

    result = runner.invoke(main, ["state"])

    assert "nothing planned and nothing performed in this window" in result.output
    assert "unreported, whenever prescribed: none" in result.output


def test_state_takes_a_window_of_cycles(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(main, ["state", "--cycles", "3"])

    assert result.exit_code == 0, result.output
    assert "window: 3 cycle(s), 12 workouts" in result.output


def test_state_on_an_unenriched_catalog_names_that_state(
    runner: CliRunner, stocked: Path
) -> None:
    """Half the answer is the pattern axis, and an unenriched catalog carries
    no patterns -- so the table would print as *nothing performed* for a body
    that had trained."""
    result = runner.invoke(main, ["state"])

    assert result.exit_code != 0
    assert "trainer enrich derive" in result.output


def test_state_needs_the_declared_rotation(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cycle is as long as the user said it is, and nothing else knows."""
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))

    result = runner.invoke(main, ["state"])

    assert result.exit_code != 0
    assert "no training configuration yet" in result.output


def test_state_writes_nothing(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Read-only, including the unreported workouts it lists: nothing closes
    one automatically and nothing assumes it happened."""
    performed_workout(runner, tmp_path)
    before = workout_rows(database.database_path())

    runner.invoke(main, ["state"])

    assert workout_rows(database.database_path()) == before


def test_a_stated_state_failure_reaches_the_terminal_as_a_sentence() -> None:
    """Every module that states a failure in words has a clause in
    `reported()`, and the state module was the last one without: `trainer
    state` is the first command to ask it anything, and its reachable failures
    are all guarded upstream -- which is exactly how a missing clause survives
    until the day something new can reach it."""
    with pytest.raises(click.ClickException, match="a window of 0 cycles"):
        with cli.reported():
            raise state.StateError("a window of 0 cycles asks about nothing")


# --- the rotation, derived ---------------------------------------------------


def test_plan_takes_its_groups_from_where_the_rotation_is(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """`--workout N` was a flag nobody computed. The position is the count of
    performed workouts against the declared cycle length, and workout 1 of the
    declared split is chest and arms."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45"],
    )

    assert result.exit_code != 0
    assert "rotation: workout 1 of 4, cycle 1 (0 performed) -- chest, arms" in result.output
    assert "today's workout is chest, arms" in result.output


def test_a_performed_workout_moves_the_plan_on_to_the_next_split(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    performed_workout(runner, tmp_path)

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45"],
    )

    assert "rotation: workout 2 of 4, cycle 1 (1 performed) -- back, core" in result.output


def test_the_workout_flag_still_overrides_the_rotation(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """Planning the leg day again is a legitimate thing to want."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block(rounds=14)),
         "--equipment", "barbell", "--workout", "3"],
    )

    assert result.exit_code == 0, result.output
    assert "rotation:" not in result.output


def test_nothing_is_derived_without_a_declared_split(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody planning with `--time` alone and no `training.toml` gets what
    they always got: the whole admissible space."""
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "barbell", "--time", "45"],
    )

    assert result.exit_code == 0, result.output
    assert "rotation:" not in result.output


# --- today's equipment, declared ---------------------------------------------


def test_plan_takes_its_equipment_from_the_declaration(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """`--equipment` is no longer required: what you own is declared once, and
    the suite's declaration says barbell. The plan is a barbell squat, so a
    run that had no equipment at all would refuse it."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--time", "45", "--group", "legs"],
    )

    assert result.exit_code == 0, result.output
    assert "Barbell Squat" in result.output


def test_the_equipment_named_today_wins_over_the_declaration(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    """A hotel room with nothing in it is the case the override exists for: the
    declared barbell is not there, and the barbell squat is not admissible."""
    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--equipment", "body only", "--time", "45", "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "Barbell_Squat" in result.output


def test_plan_with_no_equipment_and_no_declaration_is_that_state(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to derive it from, reported as the state it is."""
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))

    result = runner.invoke(
        main,
        ["plan", "--from", write_plan(tmp_path, squat_block()),
         "--time", "45", "--group", "legs"],
    )

    assert result.exit_code != 0
    assert "no training configuration yet" in result.output
    assert "training.example.toml" in result.output


# -- the bot -------------------------------------------------------------------


def test_bot_with_no_token_names_the_variable_and_the_example(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state a fresh clone hits. `conftest.py` takes every credential away,
    so this is the state under test rather than something about this machine."""
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "6421")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code != 0
    assert "TELEGRAM_BOT_TOKEN" in result.output
    assert ".env.example" in result.output


def test_bot_with_no_owner_names_the_variable_and_the_example(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:a-stand-in")
    monkeypatch.delenv("TELEGRAM_OWNER_ID", raising=False)

    result = runner.invoke(main, ["bot"])

    assert result.exit_code != 0
    assert "TELEGRAM_OWNER_ID" in result.output
    assert ".env.example" in result.output


def test_bot_reports_a_username_where_the_owner_id_goes_as_a_state(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The obvious mistake: the handle you know yourself by, where the number
    Telegram knows you by belongs. Left to `int` it is a traceback about base
    10, naming neither the variable nor where the number comes from."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:a-stand-in")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "@daniele")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code != 0
    assert "TELEGRAM_OWNER_ID" in result.output
    assert "@userinfobot" in result.output


@pytest.fixture()
def healthy_bot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[object]:
    """Every check `trainer bot` makes, passing; returns what `serve` was handed."""
    import ollama
    from telegram import Bot, User

    from trainer.coach import bot

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:a-stand-in")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "6421")
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:20b")
    monkeypatch.setenv("OLLAMA_CONTEXT_LENGTH", "8192")
    monkeypatch.setenv("TRAINER_CHECKPOINTS", str(tmp_path / "checkpoints.sqlite"))

    class Listing:
        """Both models this machine would need: the planner's and the entrance's."""

        models = [
            type("Listed", (), {"model": "gpt-oss:20b"})(),
            type("Listed", (), {"model": models.DEFAULT_ENTRANCE_MODEL})(),
        ]

    monkeypatch.setattr(ollama.Client, "list", lambda self: Listing())

    async def known(self: Any, *args: Any, **kwargs: Any) -> User:
        return User(id=1, is_bot=True, first_name="REPS", username="reps_coach_bot")

    monkeypatch.setattr(Bot, "get_me", known)
    polled: list[object] = []
    monkeypatch.setattr(
        bot, "serve", lambda declared, front, on, logs, saver: polled.append(declared)
    )
    return polled


def test_bot_says_what_it_runs_on_before_it_polls(
    runner: CliRunner, healthy_bot: list[object]
) -> None:
    """Nothing polls: long polling needs a network the suite does not have."""
    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 0, result.output
    assert "provider:    ollama" in result.output
    assert "model:       gpt-oss:20b" in result.output
    assert "context:     8192 tokens" in result.output
    assert "bot:         @reps_coach_bot" in result.output
    assert "thread chat:6421" in result.output
    assert result.output.isascii()
    assert [getattr(declared, "owner_id") for declared in healthy_bot] == [6421]


def test_bot_opens_its_log_in_the_home_and_says_where(
    runner: CliRunner, healthy_bot: list[object], machine_home: Path
) -> None:
    """The block names the file, because the terminal is where an absolute
    path belongs: the person reading it is at the machine."""
    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 0, result.output
    assert f"log:         {machine_home / 'trainer.log'}" in result.output
    assert (machine_home / "trainer.log").exists()


def test_bot_with_ollama_down_stops_with_the_fix(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    import ollama

    def unreachable(self: Any) -> Any:
        raise ConnectionError("Failed to connect to Ollama.")

    monkeypatch.setattr(ollama.Client, "list", unreachable)

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 1
    assert "start Ollama" in result.output
    assert "provider:" not in result.output
    assert healthy_bot == []


def test_bot_with_the_model_not_pulled_names_the_pull(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 1
    assert "ollama pull qwen3.5:9b" in result.output
    assert healthy_bot == []


def test_bot_with_no_context_length_says_what_a_short_context_does(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    monkeypatch.delenv("OLLAMA_CONTEXT_LENGTH")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 1
    assert "OLLAMA_CONTEXT_LENGTH" in result.output
    assert "truncated" in result.output
    assert healthy_bot == []


def test_bot_on_groq_with_no_key_stops_with_the_groq_state(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    monkeypatch.setenv("LLM_BACKEND", "groq")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 1
    assert "GROQ_API_KEY" in result.output
    assert healthy_bot == []


def test_bot_on_groq_with_a_key_never_asks_ollama(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    import ollama

    def refuse(self: Any) -> Any:
        raise AssertionError("Groq must not be checked against a local server")

    monkeypatch.setattr(ollama.Client, "list", refuse)
    serving(monkeypatch, models.DEFAULT_GROQ_MODEL)  # noqa: F821 -- see conftest
    monkeypatch.setenv("LLM_BACKEND", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "a-stand-in")
    monkeypatch.delenv("OLLAMA_CONTEXT_LENGTH")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 0, result.output
    assert "provider:    groq" in result.output
    assert len(healthy_bot) == 1


def test_bot_with_a_token_telegram_refuses_names_botfather(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    from telegram import Bot
    from telegram.error import InvalidToken

    async def refused(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise InvalidToken("The token `123:a-stand-in` was rejected by the server.")

    monkeypatch.setattr(Bot, "get_me", refused)

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 1
    assert "@BotFather" in result.output
    assert "Traceback" not in result.output
    assert "a-stand-in" not in result.output
    assert healthy_bot == []


def test_runs_list_names_the_negotiation_a_plan_left_behind(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")])
    runner.invoke(main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"])

    result = runner.invoke(main, ["runs", "list"])

    assert result.exit_code == 0, result.output
    assert "1 run" in result.output
    assert "accepted" in result.output
    assert "a-stand-in" not in result.output, "a listing names no model"
    assert result.output.isascii()


def test_runs_show_prints_the_record_trainer_plan_wrote_for_the_same_run(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One definition of how a record is written: `--record` and the read-back
    are the same document or one of them is drifting."""
    from test_planner import calling, plan_of

    scripted_graph(
        monkeypatch,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )
    record = tmp_path / "run.json"
    runner.invoke(
        main,
        ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs",
             "--record", str(record)],
    )
    negotiation = runner.invoke(main, ["runs", "list"]).output.split()[0]

    result = runner.invoke(main, ["runs", "show", negotiation, "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [json.loads(record.read_text(encoding="utf-8"))]


def test_runs_show_summarises_the_run_for_the_terminal(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import calling, plan_of

    scripted_graph(
        monkeypatch,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )
    runner.invoke(main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"])
    negotiation = runner.invoke(main, ["runs", "list"]).output.split()[0]

    result = runner.invoke(main, ["runs", "show", negotiation])

    assert result.exit_code == 0, result.output
    assert "1 of 12 tool calls" in result.output
    assert "tokens in" in result.output
    assert "emit" in result.output, "the per-node seconds are not there"
    assert "wrote prescribed workout" in result.output
    assert result.output.isascii()


def test_runs_show_names_the_listing_when_the_name_is_unknown(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")])
    runner.invoke(main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"])

    result = runner.invoke(main, ["runs", "show", "chat:404"])

    assert result.exit_code != 0
    assert "trainer runs list" in result.output


def test_runs_list_shows_an_evening_of_refusals_as_one_negotiation(
    runner: CliRunner, enriched: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two plans turned down and one accepted are one ask, not three rows.

    The documents are written here rather than negotiated, because `trainer
    plan` has no buttons: printing a plan has always meant keeping it, and the
    refusing is the chat's (ADR-0005). What is under test is the listing.
    """
    from trainer.coach import record

    for minute, (run, ending) in enumerate(
        [("aaa", record.TURNED_DOWN), ("bbb", record.TURNED_DOWN), ("ccc", record.ACCEPTED)]
    ):
        record.keep(
            {
                "negotiation": "20260918-190000-abcd",
                "run": run,
                "began": f"2026-09-18T19:0{minute}:00+02:00",
                "ended": f"2026-09-18T19:0{minute}:30+02:00",
                "ending": ending,
            },
            12,
            record.archive(),
        )

    result = runner.invoke(main, ["runs", "list"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [result.output.strip()], "one ask, one row"
    assert "20260918-190000-abcd" in result.output
    assert "3 runs" in result.output
    assert "accepted" in result.output


def test_runs_answers_with_a_provider_that_cannot_be_built(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reader is what you reach for when the provider is what is wrong, so
    it must not need one (ADR-0007, item 9)."""
    from test_planner import plan_of

    scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat")])
    runner.invoke(main, ["plan", "--equipment", "barbell", "--time", "45", "--group", "legs"])
    monkeypatch.setenv("LLM_BACKEND", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    listed = runner.invoke(main, ["runs", "list"])
    shown = runner.invoke(main, ["runs", "show", listed.output.split()[0]])

    assert listed.exit_code == 0, listed.output
    assert shown.exit_code == 0, shown.output
    assert "accepted" in shown.output


def test_runs_report_an_empty_history_as_a_state_and_write_no_file(
    runner: CliRunner, enriched: Path
) -> None:
    """A missing precondition is a state with a fix, and a reader must not
    leave a checkpointer behind where it found none."""
    from trainer.coach import checkpoints

    result = runner.invoke(main, ["runs", "list"])

    assert result.exit_code == 0, result.output
    assert "no negotiation yet" in result.output
    assert "trainer plan" in result.output
    assert not checkpoints.checkpoints_path().exists()


def test_runs_list_says_so_when_the_checkpointer_is_there_but_empty(
    runner: CliRunner, enriched: Path
) -> None:
    """`trainer bot` opens the checkpointer before it answers anything, so a
    file with no run in it is a state that happens."""
    from trainer.coach import checkpoints

    with checkpoints.saver():
        pass

    result = runner.invoke(main, ["runs", "list"])

    assert result.exit_code == 0, result.output
    assert "no negotiation yet" in result.output
    assert "trainer plan" in result.output


def test_bot_says_which_model_answers_the_entrance(
    runner: CliRunner, healthy_bot: list[object]
) -> None:
    """Two nodes, two models (ADR-0006). The block says both, because which one
    is answering hello is the thing latency is felt on."""
    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 0, result.output
    assert f"entrance:    {models.DEFAULT_ENTRANCE_MODEL} on ollama" in result.output
    assert result.output.isascii()


def test_bot_checks_the_entrance_model_before_it_starts(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, healthy_bot: list[object]
) -> None:
    """Knowable before anything is typed. Left to the first message, a model
    nobody pulled arrives as a run that fell over on the greeting."""
    monkeypatch.setenv(models.ENTRANCE_MODEL_ENV, "a-model-nobody-pulled")

    result = runner.invoke(main, ["bot"])

    assert result.exit_code == 1
    assert "ollama pull a-model-nobody-pulled" in result.output
    assert healthy_bot == [], "it polled anyway"


# -- trainer plan --mesocycle ----------------------------------------------------


def test_plan_mesocycle_proposes_one_workout_per_slot_and_keeps_it(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_planner import LEGS_AND_SHOULDERS, mesocycle_of, plan_of

    from trainer.engine import mesocycles

    declared_training.write_text(LEGS_AND_SHOULDERS, encoding="utf-8")
    offered = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"), cycles=3)
    scripted_graph(monkeypatch, raw=[offered.model_dump_json()])

    result = runner.invoke(main, ["plan", "--mesocycle"])

    assert result.exit_code == 0, result.output
    assert "workout 1 of 2 -- legs" in result.output
    assert "workout 2 of 2 -- shoulders" in result.output
    assert "Barbell Squat" in result.output and "Standing Military Press" in result.output
    assert "3 cycles" in result.output
    assert result.output.isascii()
    with closing(database.connect(enriched)) as connection:
        kept = mesocycles.active(connection)
        assert kept is not None and kept.cycles == 3
        assert workout_rows(enriched) == []


@pytest.mark.parametrize("flag", [["--workout", "2"], ["--group", "legs"]])
def test_plan_mesocycle_plans_every_slot_so_it_names_none(
    runner: CliRunner, enriched: Path, flag: list[str]
) -> None:
    result = runner.invoke(main, ["plan", "--mesocycle", *flag])

    assert result.exit_code != 0
    assert "every slot" in result.output


# -- trainer plan, off the mesocycle ---------------------------------------------


def kept_mesocycle(path: Path, declared_training: Path) -> None:
    """Legs then shoulders, accepted, with a squat at 100 kg performed before it."""
    from test_planner import LEGS_AND_SHOULDERS

    from trainer.engine import mesocycles

    declared_training.write_text(LEGS_AND_SHOULDERS, encoding="utf-8")

    def one(exercise_id: str) -> tuple[workouts.PrescribedBlock, ...]:
        return (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(duration.BlockItem(exercise_id=exercise_id, reps=5),),
                    rounds=3,
                    rest=120,
                ),
                reason="the lift of the day",
            ),
        )

    with closing(database.connect(path)) as connection:
        for _ in range(2):
            workouts.record_performed(
                connection,
                (
                    workouts.PerformedBlock(
                        items=(
                            workouts.PerformedItem(
                                exercise_id="Barbell_Squat",
                                unit="reps",
                                amount=5,
                                amount_source="reported",
                                load_kg=100.0,
                                load_kg_source="reported",
                            ),
                        ),
                        rounds=3,
                        rounds_source="reported",
                        rest=120,
                        rest_source="reported",
                    ),
                ),
                on="2026-09-01",
                report="squats",
            )
        mesocycles.record_mesocycle(
            connection,
            (one("Barbell_Squat"), one("Standing_Military_Press")),
            cycles=3,
            why="settle the loads",
            on="2026-09-02",
        )


def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused() -> None:
        raise AssertionError("a model was asked for a workout the mesocycle holds")

    monkeypatch.setattr(models, "chat", refused)


def test_plan_reads_todays_workout_off_the_mesocycle_with_the_last_load(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept_mesocycle(enriched, declared_training)
    no_model(monkeypatch)

    result = runner.invoke(main, ["plan"])

    assert result.exit_code == 0, result.output
    assert "mesocycle: workout 1 of 2, cycle 1 of 3" in result.output
    assert "Barbell Squat" in result.output
    assert "last 100 kg" in result.output
    assert result.output.isascii()
    (_, _, served) = workout_rows(enriched)
    assert served["state"] == "prescribed"


def test_plan_says_when_nothing_was_ever_lifted_on_an_exercise(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept_mesocycle(enriched, declared_training)
    no_model(monkeypatch)
    runner.invoke(main, ["plan"])
    with closing(database.connect(enriched)) as connection:
        (served,) = connection.execute("SELECT id FROM workouts WHERE state = 'prescribed'")
        workouts.record_performed(
            connection,
            (
                workouts.PerformedBlock(
                    items=(
                        workouts.PerformedItem(
                            exercise_id="Barbell_Squat", unit="reps", amount=5, amount_source="reported"
                        ),
                    ),
                    rounds=3,
                    rounds_source="reported",
                    rest=120,
                    rest_source="reported",
                ),
            ),
            on="2026-09-03",
            report="squats",
            workout_id=int(served["id"]),
        )

    result = runner.invoke(main, ["plan"])

    assert result.exit_code == 0, result.output
    assert "mesocycle: workout 2 of 2" in result.output
    assert "Standing Military Press" in result.output
    assert "last load: not recorded" in result.output


def test_plan_served_twice_is_one_prescribed_workout(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept_mesocycle(enriched, declared_training)
    no_model(monkeypatch)

    first = runner.invoke(main, ["plan"])
    second = runner.invoke(main, ["plan"])

    assert first.exit_code == second.exit_code == 0, second.output
    assert [row["state"] for row in workout_rows(enriched)] == [
        "performed",
        "performed",
        "prescribed",
    ]


def test_plan_with_no_mesocycle_names_the_state_and_the_fix(
    runner: CliRunner, enriched: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_model(monkeypatch)

    result = runner.invoke(main, ["plan"])

    assert result.exit_code == 1
    assert "no mesocycle has been accepted" in result.output
    assert "trainer plan --mesocycle" in result.output
    assert workout_rows(enriched) == []


def test_plan_off_the_mesocycle_has_no_run_to_record(
    runner: CliRunner, enriched: Path, tmp_path: Path
) -> None:
    result = runner.invoke(main, ["plan", "--record", str(tmp_path / "run.json")])

    assert result.exit_code == 2
    assert "asks no model" in result.output


# -- trainer plan: an adaptation and a change (ADR-0008 item 6) ------------------


def test_an_option_shaping_today_adapts_the_mesocycles_workout(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_planner import plan_of

    from trainer.engine import mesocycles

    kept_mesocycle(enriched, declared_training)
    with closing(database.connect(enriched)) as connection:
        before = mesocycles.active(connection)
    model = scripted_graph(monkeypatch, documents=[plan_of("Barbell_Squat", rounds=2, minutes=30)])

    result = runner.invoke(main, ["plan", "--time", "30"])

    assert result.exit_code == 0, result.output
    assert "adapting mesocycle workout 1 of 2, cycle 1 of 3 -- legs" in result.output
    briefed = "\n".join(message.text for message in model.seen[0])
    assert "Today's workout in the mesocycle" in briefed and "30 minutes" in briefed
    with closing(database.connect(enriched)) as connection:
        assert mesocycles.active(connection) == before
    no_model(monkeypatch)
    served = runner.invoke(main, ["plan"])
    assert "block 1 -- 2 rounds" in served.output, served.output
    assert [row["state"] for row in workout_rows(enriched)] == [
        "performed",
        "performed",
        "prescribed",
    ]


def test_naming_another_workout_still_plans_one_from_nothing(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_planner import plan_of

    kept_mesocycle(enriched, declared_training)
    model = scripted_graph(monkeypatch, documents=[plan_of("Standing_Military_Press", minutes=30)])

    result = runner.invoke(main, ["plan", "--workout", "2", "--time", "30"])

    assert result.exit_code == 0, result.output
    assert "adapting" not in result.output
    assert "Today's workout in the mesocycle" not in "\n".join(
        message.text for message in model.seen[0]
    )


def test_plan_change_rewrites_the_mesocycle_and_keeps_its_count(
    runner: CliRunner,
    enriched: Path,
    declared_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_planner import mesocycle_of, plan_of

    from trainer.engine import mesocycles

    kept_mesocycle(enriched, declared_training)
    changed = mesocycle_of(plan_of("Barbell_Squat", rounds=2), plan_of("Standing_Military_Press"), cycles=3)
    model = scripted_graph(monkeypatch, raw=[changed.model_dump_json()])

    result = runner.invoke(main, ["plan", "--change", "meno giri di squat"])

    assert result.exit_code == 0, result.output
    assert "meno giri di squat" in "\n".join(message.text for message in model.seen[0])
    with closing(database.connect(enriched)) as connection:
        kept = mesocycles.active(connection)
        assert kept is not None and kept.accepted_after == 2
        assert kept.slots[0][0].block.rounds == 2


def test_plan_change_with_no_mesocycle_names_the_state_and_the_fix(
    runner: CliRunner, enriched: Path, declared_training: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_planner import LEGS_AND_SHOULDERS

    declared_training.write_text(LEGS_AND_SHOULDERS, encoding="utf-8")
    no_model(monkeypatch)

    result = runner.invoke(main, ["plan", "--change", "basta squat"])

    assert result.exit_code == 1
    assert "trainer plan --mesocycle" in result.output


@pytest.mark.parametrize("flag", [["--workout", "2"], ["--group", "legs"], ["--mesocycle"]])
def test_plan_change_names_no_workout_and_is_not_a_new_mesocycle(
    runner: CliRunner, enriched: Path, flag: list[str]
) -> None:
    result = runner.invoke(main, ["plan", "--change", "basta squat", *flag])

    assert result.exit_code == 2


def test_plan_change_that_says_nothing_is_refused(runner: CliRunner, enriched: Path) -> None:
    result = runner.invoke(main, ["plan", "--change", "  "])

    assert result.exit_code == 2
    assert "--change" in result.output
