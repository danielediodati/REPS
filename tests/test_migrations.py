"""The migration runner, tested against migration sets built for the test.

Using throwaway `.sql` files rather than the real ones keeps these tests honest
as the schema grows: they check the mechanism, not today's schema.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import database, migrations


def write_migrations(directory: Path, *bodies: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for index, body in enumerate(bodies, start=1):
        (directory / f"{index:04d}_step_{index}.sql").write_text(body, encoding="utf-8")
    return directory


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_a_fresh_database_reports_version_zero(database_file: Path) -> None:
    with closing(database.connect(database_file)) as connection:
        assert migrations.applied_version(connection) == 0


def test_asking_the_version_does_not_create_anything(database_file: Path) -> None:
    with closing(database.connect(database_file)) as connection:
        migrations.applied_version(connection)
        assert table_names(connection) == set()


def test_migrations_apply_in_order(database_file: Path, tmp_path: Path) -> None:
    directory = write_migrations(
        tmp_path / "m",
        "CREATE TABLE first (id INTEGER PRIMARY KEY);",
        "CREATE TABLE second (id INTEGER PRIMARY KEY);",
        "ALTER TABLE first ADD COLUMN label TEXT;",
    )
    available = migrations.discover(directory)

    with closing(database.connect(database_file)) as connection:
        applied = migrations.migrate(connection, available)
        assert applied == (1, 2, 3)
        assert migrations.applied_version(connection) == 3
        assert {"first", "second"} <= table_names(connection)


def test_re_running_applies_nothing(database_file: Path, tmp_path: Path) -> None:
    directory = write_migrations(tmp_path / "m", "CREATE TABLE only (id INTEGER);")
    available = migrations.discover(directory)

    with closing(database.connect(database_file)) as connection:
        assert migrations.migrate(connection, available) == (1,)
        assert migrations.migrate(connection, available) == ()
        assert migrations.applied_version(connection) == 1


def test_a_new_migration_applies_only_the_new_one(
    database_file: Path, tmp_path: Path
) -> None:
    directory = write_migrations(tmp_path / "m", "CREATE TABLE first (id INTEGER);")
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection, migrations.discover(directory))

    write_migrations(
        directory,
        "CREATE TABLE first (id INTEGER);",
        "CREATE TABLE second (id INTEGER);",
    )
    with closing(database.connect(database_file)) as connection:
        assert migrations.migrate(connection, migrations.discover(directory)) == (2,)


def test_a_failing_migration_leaves_no_trace(
    database_file: Path, tmp_path: Path
) -> None:
    """A half-applied migration is worse than none: it cannot be re-run."""
    directory = write_migrations(
        tmp_path / "m",
        "CREATE TABLE fine (id INTEGER);",
        "CREATE TABLE good (id INTEGER); CREATE TABLE good (id INTEGER);",
    )
    available = migrations.discover(directory)

    with closing(database.connect(database_file)) as connection:
        with pytest.raises(sqlite3.OperationalError):
            migrations.migrate(connection, available)
        assert migrations.applied_version(connection) == 1
        assert "good" not in table_names(connection)


def test_a_gap_in_the_versions_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "m"
    directory.mkdir()
    (directory / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (directory / "0003_third.sql").write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(migrations.MigrationError):
        migrations.discover(directory)


def test_an_unparseable_file_name_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "m"
    directory.mkdir()
    (directory / "initial.sql").write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(migrations.MigrationError):
        migrations.discover(directory)


def test_the_shipped_migrations_are_discoverable_and_ordered() -> None:
    available = migrations.discover()
    assert available, "the project ships at least one migration"
    assert [m.version for m in available] == list(range(1, len(available) + 1))
    assert migrations.latest_version(available) == len(available)


def test_the_shipped_migrations_apply_to_an_empty_database(database_file: Path) -> None:
    available = migrations.discover()
    with closing(database.connect(database_file)) as connection:
        applied = migrations.migrate(connection, available)
        assert applied == tuple(m.version for m in available)
        assert migrations.applied_version(connection) == migrations.latest_version(
            available
        )


def test_statements_splits_on_statement_boundaries_not_lines() -> None:
    script = "CREATE TABLE a (id INTEGER); CREATE TABLE b (id INTEGER);"
    assert list(migrations.statements(script)) == [
        "CREATE TABLE a (id INTEGER);",
        "CREATE TABLE b (id INTEGER);",
    ]


def test_statements_ignores_semicolons_inside_string_literals() -> None:
    script = "INSERT INTO meta (key, value) VALUES ('note', 'a; b');"
    assert list(migrations.statements(script)) == [script]


def test_statements_keeps_a_multi_line_statement_whole() -> None:
    script = "CREATE TABLE a (\n  id INTEGER,\n  label TEXT\n);\n"
    assert list(migrations.statements(script)) == [script.strip()]


def test_an_unterminated_statement_is_refused() -> None:
    with pytest.raises(migrations.MigrationError):
        list(migrations.statements("CREATE TABLE a (id INTEGER)"))


def test_a_trailing_line_comment_is_not_an_incomplete_statement() -> None:
    """Migrations in this repo explain themselves; a closing remark is legal."""
    script = "CREATE TABLE a (id INTEGER);\n-- everything else arrives later\n"
    assert list(migrations.statements(script)) == ["CREATE TABLE a (id INTEGER);"]


def test_a_trailing_block_comment_is_not_an_incomplete_statement() -> None:
    script = "CREATE TABLE a (id INTEGER);\n/* see ticket 02;\n   still a comment */\n"
    assert list(migrations.statements(script)) == ["CREATE TABLE a (id INTEGER);"]


def test_a_migration_ending_in_a_comment_still_applies(
    database_file: Path, tmp_path: Path
) -> None:
    directory = write_migrations(
        tmp_path / "m", "CREATE TABLE a (id INTEGER);\n-- and that is all\n"
    )
    with closing(database.connect(database_file)) as connection:
        assert migrations.migrate(connection, migrations.discover(directory)) == (1,)
        assert "a" in table_names(connection)


def test_a_missing_migration_directory_is_refused(tmp_path: Path) -> None:
    """Silently reporting version 0 would make a broken install look healthy."""
    with pytest.raises(migrations.MigrationError):
        migrations.discover(tmp_path / "not-there")


def test_another_connection_sees_the_migration_as_already_applied(
    database_file: Path, tmp_path: Path
) -> None:
    """The read that closes the race: it must see committed work, not a snapshot.

    `migrate` re-reads the version inside `BEGIN IMMEDIATE` precisely so that a
    process which decided what was pending a moment ago does not apply a
    migration another process has since committed. This checks the read that
    decision rests on; the interleaving itself is not reachable from a test
    without a hook inside the transaction, and that is not worth adding.
    """
    directory = write_migrations(tmp_path / "m", "CREATE TABLE a (id INTEGER);")
    available = migrations.discover(directory)

    with closing(database.connect(database_file)) as first:
        with closing(database.connect(database_file)) as second:
            assert migrations.migrate(second, available) == (1,)

        first.execute("BEGIN IMMEDIATE")
        try:
            assert migrations.applied_version(first) == 1
        finally:
            first.execute("COMMIT")

        assert migrations.migrate(first, available) == ()
