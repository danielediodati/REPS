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
from trainer.engine import catalog, database, migrations, snapshot


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
    except OSError as error:
        # A read-only volume, a TRAINER_SNAPSHOT pointing at a directory, a
        # dataset the account cannot read: the user caused it and can fix it,
        # so it is a message. Last, because sqlite3.Error is not an OSError.
        raise click.ClickException(f"a file could not be used: {error}") from error


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="trainer")
def main() -> None:
    """REPS - Reasoning Engine for Personal Strength."""


@main.group()
def db() -> None:
    """Inspect, migrate and dump the database."""


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


@db.command("snapshot")
def db_snapshot() -> None:
    """Regenerate the readable markdown snapshot of the catalog.

    The database is the truth and the snapshot is the history of it, so this
    only ever writes: an edit made to the file by hand is lost here.
    """
    # Both paths, because the committed file is only as trustworthy as the
    # database it came from, and TRAINER_DB can point anywhere.
    click.echo(f"database: {database.database_path()}")
    path = snapshot.snapshot_path()
    click.echo(f"snapshot: {path}")

    with _opened() as connection:
        changed = snapshot.write(connection, path)

    if changed:
        click.echo("regenerated")
    else:
        # The normal outcome, and the one worth naming: an unchanged file is
        # the evidence that the snapshot does not churn.
        click.echo("unchanged, nothing to commit")


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
    # Ahead is worth saying wherever this check runs: `db import` writes into
    # the schema, and `catalog` reads columns it may not understand.
    _warn_if_ahead(current, latest)


@main.command("catalog")
@click.option("--name", help="Match part of the exercise name, case-insensitively.")
@click.option("--force", "force_", metavar="VALUE", help="push, pull, static.")
@click.option("--level", metavar="VALUE", help="beginner, intermediate, expert.")
@click.option("--mechanic", metavar="VALUE", help="compound, isolation.")
@click.option("--equipment", metavar="VALUE", help="barbell, dumbbell, cable.")
@click.option("--category", metavar="VALUE", help="strength, stretching, cardio.")
@click.option("--primary-muscle", metavar="VALUE", help="Worked as a primary muscle.")
@click.option("--secondary-muscle", metavar="VALUE", help="Worked as a secondary muscle.")
@click.option(
    "--limit",
    type=click.IntRange(min=0),
    default=100,
    show_default=True,
    help="Show at most this many rows; 0 for all of them.",
)
@click.option(
    "--values",
    "show_values",
    type=click.Choice(catalog.FILTERABLE),
    help="List what this field holds, and stop.",
)
def catalog_command(
    name: str | None,
    force_: str | None,
    level: str | None,
    mechanic: str | None,
    equipment: str | None,
    category: str | None,
    primary_muscle: str | None,
    secondary_muscle: str | None,
    limit: int,
    show_values: str | None,
) -> None:
    """List exercises, filtered on the catalog's own fields.

    Filters compose: every one given has to match. Values are the source's own
    -- `dumbbell`, not `dumbbells` -- and `--values FIELD` prints them.
    """
    filters = {
        field: value
        for field, value in (
            ("force", force_),
            ("level", level),
            ("mechanic", mechanic),
            ("equipment", equipment),
            ("category", category),
            ("primary_muscles", primary_muscle),
            ("secondary_muscles", secondary_muscle),
        )
        if value is not None
    }

    with _opened() as connection:
        if show_values is not None:
            _print_values(connection, show_values)
            return
        try:
            found = catalog.search(
                connection,
                name=name,
                filters=filters,
                limit=limit or None,
            )
        except catalog.UnknownFilterValue as error:
            raise _rejected(error) from error

        if not found.total:
            click.echo("no exercise matches those filters")
            return
        _print_table(found.exercises)
        shown = len(found.exercises)
        if shown < found.total:
            # Never just "showing 100": a listing that stops at its limit
            # without saying so is lying about the size of the answer.
            click.echo(f"showing {shown} of {found.total} (--limit 0 for all)")
        else:
            click.echo(f"showing {shown}")


@contextmanager
def _opened() -> Iterator[sqlite3.Connection]:
    """Open the database for reading, refusing the states that are not ready."""
    path = database.database_path()
    if not path.exists():
        raise click.ClickException(
            "the database does not exist yet; run `trainer db init` first"
        )
    with reported():
        with closing(database.connect(path)) as connection:
            _require_current_schema(connection)
            # An empty catalog would otherwise answer every query as though the
            # user had mistyped: the vocabulary read from an empty table is
            # empty, so a correct value gets rejected against nothing at all.
            if catalog.count(connection) == 0:
                raise click.ClickException(
                    "the catalog is empty; run `trainer db import` first"
                )
            yield connection


def _rejected(error: catalog.UnknownFilterValue) -> click.ClickException:
    """Say what the field holds, so a typo cannot look like an empty result."""
    lines = [
        f"no such {error.field}: {error.value!r}",
        f"valid values: {', '.join(error.valid)}",
    ]
    if error.missing:
        # Says why the values above do not add up to the size of the catalog.
        lines.append(f"{error.missing} exercises have no {error.field} recorded")
    return click.ClickException("\n".join(lines))


def _print_values(connection: sqlite3.Connection, field: str) -> None:
    with reported():
        for value in catalog.values(connection, field):
            click.echo(value)
        if field in catalog.SCALAR_FILTERS:
            absent = catalog.missing_count(connection, field)
            if absent:
                click.echo(f"({absent} exercises have no {field} recorded)")


def _print_table(found: tuple[catalog.Exercise, ...]) -> None:
    rows = [
        (
            exercise.name,
            exercise.equipment or "-",
            exercise.force or "-",
            exercise.mechanic or "-",
            exercise.level,
            exercise.category,
        )
        for exercise in found
    ]
    headers = ("name", "equipment", "force", "mechanic", "level", "category")
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]
    click.echo(_line(headers, widths))
    for row in rows:
        click.echo(_line(row, widths))


def _line(cells: tuple[str, ...], widths: list[int]) -> str:
    """Padded columns, but no trailing run of spaces at the end of the line."""
    return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths)).rstrip()
