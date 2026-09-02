"""The CLI: argument parsing and formatting, nothing else.

Every decision here belongs to the engine. If a function in this module starts
computing something rather than displaying it, it is in the wrong file.

That includes failure. An engine exception arriving at the terminal as a
traceback is the boundary leaking: the engine states what went wrong, the CLI
decides how a person should read it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager

import click

from trainer import __version__
from trainer.engine import catalog, database, migrations


@contextmanager
def reported() -> Iterator[None]:
    """Turn the failures a person can actually cause into clean messages."""
    try:
        yield
    except migrations.MigrationError as error:
        raise click.ClickException(f"the migration set is unusable: {error}") from error
    except catalog.CatalogError as error:
        raise click.ClickException(f"the dataset is unusable: {error}") from error
    except sqlite3.Error as error:
        raise click.ClickException(f"the database could not be used: {error}") from error


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="trainer")
def main() -> None:
    """REPS - Reasoning Engine for Personal Strength."""


@main.group()
def db() -> None:
    """Inspect and migrate the database."""


@db.command("init")
def db_init() -> None:
    """Create the database if needed and bring it to the current schema."""
    path = database.database_path()
    click.echo(f"database: {path}")

    with reported():
        available = migrations.discover()
        with closing(database.connect(path)) as connection:
            applied = migrations.migrate(connection, available)
            current = migrations.applied_version(connection)

    for version in applied:
        click.echo(f"  applied migration {version:04d}")
    if applied:
        click.echo(f"now at schema version {current}")
    else:
        click.echo(f"already at schema version {current}, nothing to do")
    _warn_if_ahead(current, migrations.latest_version(available))


@db.command("status")
def db_status() -> None:
    """Report the schema version this database is on."""
    path = database.database_path()
    click.echo(f"database: {path}")

    with reported():
        latest = migrations.latest_version(migrations.discover())

        if not path.exists():
            click.echo("not created yet; run `trainer db init`")
            click.echo(f"latest available: {latest}")
            return

        with closing(database.connect(path)) as connection:
            current = migrations.applied_version(connection)

    click.echo(f"schema version: {current}")
    click.echo(f"latest available: {latest}")
    if current < latest:
        click.echo("behind; run `trainer db init`")
    _warn_if_ahead(current, latest)


def _warn_if_ahead(current: int, latest: int) -> None:
    """A database from a newer checkout is the dangerous direction.

    Behind is a prompt to migrate. Ahead means this code is about to read a
    schema written by a version that knew more than it does, and saying nothing
    would let that look like everything is fine.
    """
    if current > latest:
        click.echo(
            f"WARNING: this database is at version {current}, "
            f"but this checkout only knows up to {latest}. "
            "It was written by a newer version of trainer."
        )


@db.command("import")
@click.option(
    "--allow-pruning",
    is_flag=True,
    help="Permit an import that removes most of the catalog.",
)
def db_import(allow_pruning: bool) -> None:
    """Load the vendored exercise catalog into the database."""
    path = database.database_path()
    click.echo(f"database: {path}")
    click.echo(f"dataset:  {catalog.DATASET_PATH}")

    # Checked before connecting: connecting would create an empty database, and
    # a stray one reports as "schema version: 0" rather than "not created yet".
    if not path.exists():
        raise click.ClickException(
            "the database does not exist yet; run `trainer db init` first"
        )

    with reported():
        exercises = catalog.load()
        with closing(database.connect(path)) as connection:
            _require_current_schema(connection)
            result = catalog.import_exercises(
                connection, exercises, allow_pruning=allow_pruning
            )

    click.echo(f"read {len(exercises)} records")
    if result.inserted:
        click.echo(f"  inserted {result.inserted}")
    if result.updated:
        click.echo(f"  updated  {result.updated}")
    if result.removed:
        click.echo(f"  removed  {result.removed}")
    click.echo(f"{result.total} exercises in the catalog")


def _require_current_schema(connection: sqlite3.Connection) -> None:
    """Refuse to write into a schema this checkout has not finished building.

    Migrating implicitly here would hide the fact that the database was behind,
    and `db init` is one command away.
    """
    current = migrations.applied_version(connection)
    latest = migrations.latest_version(migrations.discover())
    if current < latest:
        raise click.ClickException(
            f"the database is at schema version {current} and this checkout "
            f"expects {latest}; run `trainer db init` first"
        )
    # Ahead is the direction that matters more here than anywhere else: this
    # command writes, and `db status` already warns for merely reading.
    _warn_if_ahead(current, latest)
