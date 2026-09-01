"""Versioned schema migrations.

Migrations are plain `.sql` files named `NNNN_description.sql`. They are applied
in version order, exactly once, and recorded in `schema_migrations`. There is no
down-migration: rolling back a schema by guesswork is how you lose data, and the
recovery path here is to delete the file and re-import.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIRECTORY = Path(__file__).parent / "migrations"

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    """The migration set on disk is not usable."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def discover(directory: Path = MIGRATIONS_DIRECTORY) -> tuple[Migration, ...]:
    """Read the migration set, newest last.

    Rejects duplicates and gaps rather than working around them: a missing
    version means a file was lost, and applying the rest would produce a schema
    that no other checkout can reproduce.
    """
    if not directory.is_dir():
        raise MigrationError(f"no migration directory at {directory}")

    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        prefix, separator, description = path.stem.partition("_")
        if not separator or not prefix.isdigit():
            raise MigrationError(
                f"{path.name}: expected a name like 0001_description.sql"
            )
        migrations.append(
            Migration(
                version=int(prefix),
                name=description,
                sql=path.read_text(encoding="utf-8"),
            )
        )

    migrations.sort(key=lambda migration: migration.version)
    for position, migration in enumerate(migrations, start=1):
        if migration.version != position:
            raise MigrationError(
                f"expected migration {position}, found {migration.version}"
            )
    return tuple(migrations)


def statements(script: str) -> Iterator[str]:
    """Split a migration into statements, one execute() at a time.

    `executescript` would be shorter, but it commits before it runs and leaves
    its DDL committed when a later statement fails — which turns a failed
    migration into a database that can neither be re-run nor rolled back.
    Splitting here keeps the whole file inside one transaction.
    """
    pending: list[str] = []
    for character in script:
        pending.append(character)
        if character != ";":
            continue
        buffer = "".join(pending)
        if sqlite3.complete_statement(buffer):
            yield buffer.strip()
            pending.clear()
    if _without_comments("".join(pending)):
        raise MigrationError("migration ends with an incomplete statement")


def _without_comments(sql: str) -> str:
    """What is left of a fragment once comments and whitespace are gone.

    Only ever applied to the tail after the last complete statement, to tell a
    closing remark apart from a truncated statement. Migrations in this repo
    explain themselves, so a trailing comment must not brick `db init`.
    """
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return without_line.strip()


def applied_version(connection: sqlite3.Connection) -> int:
    """The highest applied version; 0 for a database nothing has touched.

    A pure read: asking a database what version it is on must never change it.
    """
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if exists is None:
        return 0
    row = connection.execute(
        "SELECT MAX(version) AS version FROM schema_migrations"
    ).fetchone()
    return int(row["version"]) if row["version"] is not None else 0


def latest_version(migrations: tuple[Migration, ...]) -> int:
    return migrations[-1].version if migrations else 0


def migrate(
    connection: sqlite3.Connection,
    migrations: tuple[Migration, ...] | None = None,
) -> tuple[int, ...]:
    """Apply everything not yet applied. Returns the versions applied, in order.

    An empty result means the database was already current — that is the normal
    case, not an error.
    """
    if migrations is None:
        migrations = discover()

    connection.execute(_BOOTSTRAP)
    current = applied_version(connection)
    pending = [migration for migration in migrations if migration.version > current]

    applied: list[int] = []
    for migration in pending:
        # IMMEDIATE takes the write lock now rather than at the first write, so
        # two processes migrating at once cannot both read version 0 and both
        # decide to apply migration 1.
        connection.execute("BEGIN IMMEDIATE")
        try:
            if migration.version <= applied_version(connection):
                connection.execute("COMMIT")  # someone else got there first
                continue
            for statement in statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        except Exception:
            # SQLite rolls back by itself for some errors (a full disk, an I/O
            # failure). Rolling back again then raises, and that error would
            # replace the one that actually explains the failure.
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        connection.execute("COMMIT")
        applied.append(migration.version)
    return tuple(applied)
