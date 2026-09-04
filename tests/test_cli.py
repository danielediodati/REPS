"""The CLI, exercised end to end through the real entry point."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from trainer import __version__
from trainer.cli import main
from trainer.engine import catalog, database, graph, migrations, reference_set, residue, snapshot


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
        'split = [["chest", "arms"], ["legs", "core"]]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAINER_CONFIG", str(declared))

    result = runner.invoke(main, ["config"])

    assert result.exit_code == 0, result.output
    assert "cycle length: 2 workouts" in result.output
    assert "duration cap: 45 min" in result.output
    assert "volume counted per: cycle" in result.output
    assert "1. chest, arms" in result.output
    assert "2. legs, core" in result.output


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
        'split = [["chest"]]\n',
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
