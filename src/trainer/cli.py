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
from datetime import date
from pathlib import Path

import click
from click.core import ParameterSource

from trainer import __version__, agent, evaluation, log, plan
from trainer.engine import (
    admissible,
    budget,
    catalog,
    config,
    database,
    duration,
    enrichment,
    exclusions,
    graph,
    migrations,
    muscle_groups,
    reference_set,
    residue,
    snapshot,
    workouts,
)


@contextmanager
def reported() -> Iterator[None]:
    """Turn the failures a person can actually cause into clean messages."""
    try:
        yield
    except migrations.MigrationError as error:
        raise click.ClickException(f"the migration set is unusable: {error}") from error
    except catalog.CatalogError as error:
        raise click.ClickException(f"the dataset is unusable: {error}") from error
    except reference_set.ReferenceSetError as error:
        raise click.ClickException(f"the reference set is unusable: {error}") from error
    except residue.ResidueError as error:
        raise click.ClickException(f"the residue file is unusable: {error}") from error
    except graph.GraphError as error:
        raise click.ClickException(f"the graph file is unusable: {error}") from error
    except config.NoTrainingConfig as error:
        # Before ConfigError, which it subclasses: the state has its own
        # wording and must not be dressed up as a broken file.
        raise click.ClickException(str(error)) from error
    except config.ConfigError as error:
        raise click.ClickException(
            f"the training configuration is unusable: {error}"
        ) from error
    except muscle_groups.MuscleGroupError as error:
        raise click.ClickException(f"the muscle group mapping is unusable: {error}") from error
    except exclusions.ExclusionError as error:
        raise click.ClickException(str(error)) from error
    except admissible.AdmissibleError as error:
        raise click.ClickException(str(error)) from error
    except budget.BudgetError as error:
        # `trainer plan` is the first command that divides the time. A
        # mistyped `--group` reaches `allocate`, which states the failure in
        # words, and without this clause those words arrive as a traceback --
        # while `trainer admissible` answers the same typo cleanly, so the two
        # commands disagree about the same mistake.
        raise click.ClickException(str(error)) from error
    except duration.DurationError as error:
        # `trainer plan` is the first command that costs a plan. `tools.py`
        # has listed this among the engine's stated failures since the surface
        # existed; the terminal had no clause for it because nothing here
        # reached the costing path.
        raise click.ClickException(str(error)) from error
    except workouts.WorkoutError as error:
        # Unreachable through a plan that passed the validator -- `WorkoutPlan`
        # already requires a block. Here so that the writer's own refusals
        # arrive as sentences if a later command reaches it another way.
        raise click.ClickException(str(error)) from error
    except log.LogRejected as error:
        # Before LogError, for the reason PlanRejected comes before PlanError:
        # a document the engine cannot resolve -- an id nobody has, an
        # exclusion naming neither granularity -- is not malformed JSON, and
        # dressing it as one sends the author to check their brackets.
        raise click.ClickException(str(error)) from error
    except log.LogError as error:
        raise click.ClickException(str(error)) from error
    except plan.PlanRejected as error:
        # Before PlanError, which it does not subclass but reads like: a plan
        # the rules refuse is not a malformed document, and dressing it as one
        # would send the author to check their JSON.
        raise click.ClickException(str(error)) from error
    except plan.PlanError as error:
        raise click.ClickException(str(error)) from error
    except agent.AgentError as error:
        # No credentials, or the provider refusing the request. A state the
        # user can act on, not a failure of the plan they asked for.
        raise click.ClickException(str(error)) from error
    except sqlite3.Error as error:
        raise click.ClickException(f"the database could not be used: {error}") from error
    except UnicodeDecodeError as error:
        # Every curated file this reads is UTF-8 by declaration, and an editor
        # that saved one as cp1252 is a thing a person did and can undo. Left
        # uncaught it arrives as a traceback about a codec, which names neither
        # the file nor the fix. `config` says this itself, with its own
        # wording; this catches the reference set, the residue and the graph.
        raise click.ClickException(
            f"a file is not UTF-8 ({error.reason}); the curated files are "
            "UTF-8, so re-save it in that encoding"
        ) from error
    except OSError as error:
        # A read-only volume, a TRAINER_SNAPSHOT pointing at a directory, a
        # dataset the account cannot read: the user caused it and can fix it,
        # so it is a message. Last, because sqlite3.Error is not an OSError.
        raise click.ClickException(f"a file could not be used: {error}") from error


def run() -> None:
    """The installed `trainer` command.

    `.env` is read here and nowhere else, which is deliberate. `main` is what
    the suite invokes, and a group that loaded credentials on the way in would
    put back the ones `conftest.py` takes away -- quietly turning the
    no-credentials guarantee into a guarantee about the machine.
    """
    from dotenv import find_dotenv, load_dotenv

    # `usecwd`, because the default walks up from *this file*. Under the
    # editable install that is the repo and it finds the right `.env` by
    # accident; installed as a tool, `cli.py` lives in site-packages and the
    # walk never reaches the user at all -- they follow `.env.example`, put
    # the file beside their database, and get told there are no credentials
    # with the file sitting right there.
    load_dotenv(find_dotenv(usecwd=True))
    main()


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


@main.group()
def enrich() -> None:
    """Fill the catalog's enrichment fields."""


@enrich.command("derive")
def enrich_derive() -> None:
    """Fill every field the rules can decide, across the strength rows.

    Deterministic and idempotent: running it again re-derives the same
    values and never overwrites a value a person decided by hand.
    docs/enrichment/definitions.md is what it executes.
    """
    click.echo(f"database: {database.database_path()}")

    with _opened() as connection:
        report = enrichment.run(connection)

    click.echo(f"{report.considered} strength rows considered")
    click.echo(f"  decided    {len(report.decided)} ({report.coverage:.1%})")
    click.echo(f"  undecided  {len(report.undecided)}")
    if report.skipped_curated:
        click.echo(f"  curated    {report.skipped_curated} (left alone)")

    if report.undecided:
        click.echo("")
        click.echo("left undecided, for a person to read:")
        for exercise_id in sorted(report.undecided):
            click.echo(f"  {exercise_id}")


@enrich.command("check")
def enrich_check() -> None:
    """Score the database against docs/enrichment/reference-set.md.

    `movement_pattern` is reported first and on its own, never averaged into
    the other four fields -- it is the number this session is measured by.
    Safe to run before and after a hand-reading pass: it only reads.
    """
    reference_path = reference_set.reference_set_path()
    click.echo(f"database:       {database.database_path()}")
    click.echo(f"reference set:  {reference_path}")

    with reported():
        reference = reference_set.load(reference_path)
        with _opened() as connection:
            results = reference_set.check(connection, reference)

    click.echo(f"{len(reference)} movements in the reference set")
    click.echo("")

    by_field = {result.field: result for result in results}
    pattern = by_field["movement_pattern"]
    _print_field_check(pattern)
    for field in reference_set.FIELDS:
        if field == "movement_pattern":
            continue
        click.echo("")
        _print_field_check(by_field[field])


@enrich.command("curated")
def enrich_curated() -> None:
    """Load the hand-read residue and the variant_of/regression_of graph.

    docs/enrichment/residue.md decides movement_pattern for the rows the
    rules could not, each quoting the instruction it rests on; docs/
    enrichment/graph.md is the variant_of/regression_of graph. Both are read
    by a person, once, and everything this writes carries `curated`
    provenance -- a rule can never overwrite it afterwards.
    """
    click.echo(f"database: {database.database_path()}")
    click.echo(f"residue:  {residue.residue_path()}")
    click.echo(f"graph:    {graph.graph_path()}")

    # residue.apply and graph.apply are each their own transaction -- two
    # independent, idempotent artifacts, safe to commit one at a time and to
    # re-run. Reporting each as soon as it lands means a later failure (a
    # broken graph.md, say) never reads as "nothing happened": the output
    # above the error already shows what did.
    with reported():
        residue_rows = residue.load()
        with _opened() as connection:
            residue_report = residue.apply(connection, residue_rows)

    click.echo("")
    click.echo(f"residue: {residue_report.considered} rows read")
    click.echo(f"  decided  {len(residue_report.decided)}")
    click.echo(f"  null     {len(residue_report.null)}")

    with reported():
        variants, regressions = graph.load()
        with _opened() as connection:
            graph_report = graph.apply(connection, variants, regressions)

    click.echo("")
    click.echo(f"graph: {graph_report.variant_groups} variant groups")
    click.echo(f"  variant_of rows written     {len(graph_report.variant_rows)}")
    click.echo(f"  regression_of rows written  {len(graph_report.regression_rows)}")


def _print_field_check(result: reference_set.FieldCheck) -> None:
    click.echo(f"{result.field}:")
    if not result.total:
        click.echo("  the reference set names no value for this field")
        return
    click.echo(f"  matches        {result.matches} of {result.total} ({result.accuracy:.1%})")
    if result.disagreements:
        click.echo(f"  disagreements  {len(result.disagreements)}")
        for exercise_id in sorted(result.disagreements):
            click.echo(f"    {exercise_id}")
    if result.missing:
        click.echo(f"  not yet decided  {len(result.missing)}")
        for exercise_id in sorted(result.missing):
            click.echo(f"    {exercise_id}")


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
@click.pass_context
@click.option("--name", help="Match part of the exercise name, case-insensitively.")
@click.option("--force", "force_", metavar="VALUE", help="push, pull, static.")
@click.option("--level", metavar="VALUE", help="beginner, intermediate, expert.")
@click.option("--mechanic", metavar="VALUE", help="compound, isolation.")
@click.option("--equipment", metavar="VALUE", help="barbell, dumbbell, cable.")
@click.option("--category", metavar="VALUE", help="strength, stretching, cardio.")
@click.option("--primary-muscle", metavar="VALUE", help="Worked as a primary muscle.")
@click.option("--secondary-muscle", metavar="VALUE", help="Worked as a secondary muscle.")
@click.option("--pattern", metavar="VALUE", help="hip hinge, squat, isolation, ...")
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
    type=click.Choice(catalog.FILTERABLE + catalog.ENRICHMENT_VALUE_FIELDS),
    help="List what this field holds, and stop.",
)
@click.option(
    "--stats",
    "show_stats",
    is_flag=True,
    help="Count what the catalog holds instead of listing it.",
)
def catalog_command(
    context: click.Context,
    name: str | None,
    force_: str | None,
    level: str | None,
    mechanic: str | None,
    equipment: str | None,
    category: str | None,
    primary_muscle: str | None,
    secondary_muscle: str | None,
    pattern: str | None,
    limit: int,
    show_values: str | None,
    show_stats: bool,
) -> None:
    """List exercises, filtered on the catalog's own fields.

    Filters compose: every one given has to match. Values are the source's own
    -- `dumbbell`, not `dumbbells` -- and `--values FIELD` prints them.

    `--pattern` is the one enriched filter here, and it reads `movement_pattern`
    the same way every other filter reads its own field -- run `trainer enrich
    derive` first.

    `--stats` counts the same rows instead of listing them, which is how you
    find out how much of the catalog is actually strength work.
    """
    if show_stats:
        # Every option that would be quietly discarded is named rather than
        # ignored. --limit bounds a listing and there is no listing here; the
        # source has to be asked, because its default makes it always present.
        if show_values is not None:
            raise click.UsageError("give one of --stats and --values, not both")
        if context.get_parameter_source("limit") is ParameterSource.COMMANDLINE:
            raise click.UsageError("--limit bounds a listing; --stats counts them all")

    if pattern is not None and not pattern.strip():
        raise click.UsageError("--pattern cannot be blank")

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
            ("movement_pattern", pattern),
        )
        if value is not None
    }

    with _opened() as connection:
        if show_values is not None:
            _print_values(connection, show_values)
            return
        # Checked once, ahead of both --stats and the listing: an
        # unenriched movement_pattern is a state to name, not a value to
        # reject, and the two callers below would otherwise report it as an
        # ordinary "no such pattern" against an empty vocabulary.
        if pattern is not None and not catalog.values(connection, "movement_pattern"):
            raise click.ClickException(
                "the catalog is not enriched yet; run `trainer enrich derive` first"
            )
        if show_stats:
            try:
                _print_stats(catalog.stats(connection, name=name, filters=filters))
            except catalog.UnknownFilterValue as error:
                raise _rejected(error) from error
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


@main.command("eval")
@click.option(
    "--repetitions",
    "repetitions",
    metavar="N",
    type=click.IntRange(min=1),
    default=evaluation.REPETITIONS,
    show_default=True,
    help="How many times each situation runs. A model is a distribution, so "
    "one run measures nothing.",
)
@click.option(
    "--only",
    "only",
    metavar="NAME",
    multiple=True,
    help="Run just these situations, by name. Every run still counts, so a "
    "partial pass is a partial answer.",
)
@click.option(
    "--records",
    "records",
    metavar="DIR",
    type=click.Path(file_okay=False, path_type=Path),
    default=evaluation.RECORDS,
    show_default=True,
    help="Where each run's record is written. A failure names the file.",
)
@click.option(
    "--call-budget",
    "call_budget",
    metavar="N",
    type=click.IntRange(min=1),
    default=agent.CALL_BUDGET,
    show_default=True,
    help="Tool calls each run may make before it is asked to emit anyway.",
)
def eval_command(
    repetitions: int, only: tuple[str, ...], records: Path, call_budget: int
) -> None:
    """Run the six adverse situations against the real agent, and check the
    six invariants over every run.

    Not *good plan / bad plan*: properties that must hold always, decided by
    code reading the run record. No model judges another model's output.

    **This is the one command in the project that reaches a provider**, and
    the only one that spends money. `pytest` never runs it: the suite has no
    sockets and no credentials, and the checks are covered there against
    recorded runs instead.

    The bar is 100%, and the command exits non-zero below it.
    """
    with _opened() as connection:
        _require_enrichment(connection)
        with reported():
            available = evaluation.situations(connection)
            chosen = _chosen(available, only)
            report = evaluation.run(
                connection,
                chosen,
                build=agent.groq,
                repetitions=repetitions,
                records=records,
                budget=call_budget,
            )

    for line in evaluation.render(report, chosen):
        click.echo(line)
    if not report.passed:
        raise SystemExit(1)


def _chosen(
    available: tuple[evaluation.Situation, ...], only: tuple[str, ...]
) -> tuple[evaluation.Situation, ...]:
    if not only:
        return available
    known = {situation.name: situation for situation in available}
    for name in only:
        if name not in known:
            raise click.ClickException(
                f"no situation called {name!r}; they are {', '.join(known)}"
            )
    # Named twice is named once. Left in, the situation runs twice the
    # repetitions against a paid provider and prints two identical rows.
    return tuple(known[name] for name in dict.fromkeys(only))


@main.command("mcp")
def mcp_command() -> None:
    """Serve the engine's tool surface over MCP, on stdio.

    Point a generic MCP client at `trainer mcp` and it lists the tools
    `trainer.tools` defines, and calls them against this database. That is the
    whole reason MCP is in the project this early: from session 4 on, the engine can be watched
    answering the same calls the agent is making, from an inspector rather
    than through the agent's own account of what happened.
    """
    # Imported here rather than at the top: the MCP SDK pulls in a web stack,
    # and `trainer --help` should not pay for a server nobody asked to start.
    from trainer import mcp_server

    mcp_server.main()


@main.command("config")
@click.option(
    "--muscle-groups",
    "show_groups",
    is_flag=True,
    help="Show the muscle group mapping instead: the catalog's seventeen "
    "primary muscles and the group each is allocated under.",
)
def config_command(show_groups: bool) -> None:
    """Show what the user has declared: cycle, duration cap, split, denominator.

    Read-only. Nothing in trainer writes this file; it is hand-edited until
    session 6's onboarding fills it by talking to you (ADR-0003).
    """
    with reported():
        if show_groups:
            _print_muscle_groups(muscle_groups.committed())
            return

        path = config.config_path()
        declared = config.load(path)

    click.echo(f"configuration: {path}")
    click.echo(f"cycle length: {declared.cycle_length} workouts")
    click.echo(f"duration cap: {declared.duration_cap_min} min")
    click.echo(f"volume counted per: {declared.volume_denominator}")
    click.echo("split:")
    for position, groups in enumerate(declared.split, start=1):
        click.echo(f"  {position}. {', '.join(groups)}")


def _print_muscle_groups(mapping: muscle_groups.MuscleGroups) -> None:
    """The mapping, grouped by group -- the shape a person reads it in.

    `(no group)` is printed rather than omitted, for the same reason a
    breakdown prints its `(none)` row: it is the line that makes the seventeen
    add up, and `neck` being in no group is a decision, not an absence of one.
    A group with no members is skipped, though -- the day `neck` is assigned
    somewhere, a bare `(no group):` with nothing after the colon would be a
    line about nobody.
    """
    click.echo(f"mapping: {muscle_groups.MUSCLE_GROUPS_PATH}")
    for group in [*mapping.groups, None]:
        members = [muscle for muscle, assigned in mapping.by_muscle if assigned == group]
        if not members:
            continue
        click.echo(f"{group or '(no group)'}: {', '.join(members)}")


@main.command("admissible")
@click.option(
    "--equipment",
    "equipment",
    metavar="VALUE",
    multiple=True,
    required=True,
    help="Today's equipment; repeat for more than one.",
)
@click.option(
    "--time",
    "budget",
    metavar="MINUTES",
    type=click.IntRange(min=0),
    required=True,
    help="Minutes available, compared against each exercise's setup cost.",
)
@click.option(
    "--exclude",
    "exclude",
    metavar="VALUE",
    multiple=True,
    help="A movement pattern or a loaded joint to keep out -- never an exercise id.",
)
@click.option(
    "--group",
    "groups",
    metavar="GROUP",
    multiple=True,
    help="A muscle group this workout trains; repeat for more than one. "
    "Left out, the whole admissible space is answered.",
)
def admissible_command(
    equipment: tuple[str, ...],
    budget: int,
    exclude: tuple[str, ...],
    groups: tuple[str, ...],
) -> None:
    """The exercises today's equipment, the time available and every active
    exclusion leave standing -- the answer to "what can I do today".

    `--exclude` classifies a value against the catalog's own vocabulary for
    this one query -- a movement pattern or a loaded joint, never an
    exercise id -- and is not persisted. An exclusion with a re-test date
    lives in the `exclusions` table instead, and is read automatically
    alongside it.
    """
    with _opened() as connection:
        _require_enrichment(connection)

        classified = [exclusions.classify(connection, value) for value in exclude]
        standing = exclusions.active(connection, date.today().isoformat())
        try:
            found = admissible.admissible_set(
                connection, [*standing, *classified], equipment, budget, groups
            )
        except catalog.UnknownFilterValue as error:
            raise _rejected(error) from error

    if not found:
        click.echo("no exercise is admissible under those constraints")
        return
    _print_table(found)
    click.echo(f"showing {len(found)}")


@main.command("plan")
@click.option(
    "--from",
    "source",
    metavar="FILE",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Check a plan written by hand instead of asking a model for one.",
)
@click.option(
    "--equipment",
    "equipment",
    metavar="VALUE",
    multiple=True,
    required=True,
    help="Today's equipment; repeat for more than one.",
)
@click.option(
    "--time",
    "budget",
    metavar="MINUTES",
    type=click.IntRange(min=0),
    help="Minutes available. Defaults to the duration cap you declared, and is "
    "refused above it. The plan is checked against this, never cut to fit.",
)
@click.option(
    "--workout",
    "workout",
    metavar="N",
    type=click.IntRange(min=1),
    help="Which workout of the declared rotation this is. Its muscle groups "
    "come from the split in training.toml, and the time divides over them.",
)
@click.option(
    "--exclude",
    "exclude",
    metavar="VALUE",
    multiple=True,
    help="A movement pattern or a loaded joint to keep out -- never an exercise id.",
)
@click.option(
    "--group",
    "groups",
    metavar="GROUP",
    multiple=True,
    help="A muscle group this workout trains; repeat for more than one. Use "
    "--workout to take them from the split instead.",
)
@click.option(
    "--avoid",
    "avoid",
    metavar="EXERCISE_ID",
    multiple=True,
    help="An exercise you would rather not do. A preference, not a safety "
    "exclusion: it stays admissible, and the agent may propose it if it says why.",
)
@click.option(
    "--refused",
    "refused_path",
    metavar="FILE",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A plan you have just turned down. Asks for a different one.",
)
@click.option(
    "--because",
    "because",
    metavar="TEXT",
    default="",
    help="Why you turned it down. Reaches the model; nothing is written down.",
)
@click.option(
    "--call-budget",
    "call_budget",
    metavar="N",
    type=click.IntRange(min=1),
    default=agent.CALL_BUDGET,
    show_default=True,
    help="Tool calls the model may make before it is asked to emit anyway.",
)
@click.option(
    "--record",
    "record_path",
    metavar="FILE",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the run record here: the calls, the budget spent, the plan.",
)
@click.pass_context
def plan_command(
    context: click.Context,
    source: Path | None,
    equipment: tuple[str, ...],
    budget: int | None,
    workout: int | None,
    exclude: tuple[str, ...],
    groups: tuple[str, ...],
    avoid: tuple[str, ...],
    refused_path: Path | None,
    because: str,
    call_budget: int,
    record_path: Path | None,
) -> None:
    """Plan a workout, and print it.

    A model is asked for the plan, using the same tools `trainer mcp` serves,
    inside a budget of tool calls; when the budget runs out it is asked to
    emit with what it has. With `--from FILE` no model is involved at all and
    a hand-written plan is checked instead -- the same rules, the same
    rendering, the agent left out.

    Either way the plan is **rejected** if it breaks a rule, naming the rule.
    Nothing is trimmed to fit and nothing is asked again (ADR-0001), and a
    rejected plan is not printed: half a workout with a refusal under it reads
    as a workout with a footnote.
    """
    if source is not None:
        _only_with_a_model(
            context,
            ("--call-budget", "call_budget"),
            ("--record", "record_path"),
            ("--refused", "refused_path"),
            ("--because", "because"),
        )
    elif record_path is not None:
        # Checked before the model is called rather than after. `--record` is
        # the artefact the run exists to produce, and a path that cannot be
        # written is worth finding out about while the run is still free.
        _writable(record_path)

    if because and refused_path is None:
        raise click.UsageError("--because says why you refused a plan; --refused says which")

    # The request first, and the plan after it. The plan is checked *against*
    # the request, so a workout outside the cycle or a time over the cap is
    # the more basic thing to be told about -- reported the other way round,
    # a mistyped file hides a mistyped rotation.
    with reported():
        declared = _declared()
        budget = _minutes(budget, declared)
        groups = _groups(workout, declared, groups)
        refused = (
            plan.parse(refused_path.read_text(encoding="utf-8"))
            if refused_path is not None
            else None
        )

    parsed: plan.WorkoutPlan | None = None
    if source is not None:
        with reported():
            parsed = plan.parse(source.read_text(encoding="utf-8"))
            plan.to_blocks(parsed)

    today = date.today().isoformat()
    with _opened() as connection:
        _require_enrichment(connection)
        with reported():
            classified = [exclusions.classify(connection, value) for value in exclude]
            standing = exclusions.active(connection, today)
            request = plan.Request(
                equipment=equipment,
                budget_min=budget,
                exclusions=(*standing, *classified),
                groups=groups,
                allocation=_divided(budget, groups),
                preferences=_preferred(connection, avoid),
                refused=refused,
                because=because,
            )
            try:
                if parsed is not None:
                    accepted, lines = _checked(connection, parsed, request, budget)
                else:
                    accepted, lines = _asked(
                        connection, request, budget, call_budget, record_path
                    )
            except catalog.UnknownFilterValue as error:
                raise _rejected(error) from error

            # Printed before it is written, and that order is the point. A
            # rejected plan is not printed at all -- the refusal above has
            # already raised -- but a plan that passed every rule is the
            # user's workout, and on the model path it cost a real run. A
            # database that cannot be written to is worth an error; it is not
            # worth throwing the workout away to report one.
            for line in lines:
                click.echo(line)

            # The workout is written **here**, in the command, and nowhere
            # else. Not in `plan.py` and not in `agent.py`: `trainer eval`
            # runs eighteen agent loops against the project database, and a
            # plan that persisted from inside the agent would leave eighteen
            # phantom prescribed workouts in the very state the measurement is
            # taken from. ROADMAP.md § Session 5.
            _recorded(connection, accepted, today)


def _declared() -> config.TrainingConfig | None:
    """The training configuration, or `None` when there is not one yet.

    Absent is a state rather than a failure *here*: `--time` and `--group`
    name everything a plan needs, so somebody who has not declared a rotation
    can still ask for a workout. It becomes a failure the moment something is
    asked for that only the file can answer, and then it is reported with the
    file's own wording rather than a second phrasing of it.

    Only `NoTrainingConfig` is caught. A file that exists and is wrong is a
    different thing entirely and must not be read as one that is not there.
    """
    try:
        return config.load()
    except config.NoTrainingConfig:
        return None


def _minutes(asked: int | None, declared: config.TrainingConfig | None) -> int:
    """Today's budget: what was asked for, or the cap that was declared.

    The cap is a ceiling and not a suggestion -- it is the one number in
    `training.toml` that says *a workout never runs longer than this* -- so a
    larger `--time` is refused rather than honoured, **whether or not
    `--workout` was given**. Refused and not clamped: quietly planning 60
    minutes for somebody who asked for 90 is the engine deciding how long they
    train.
    """
    if declared is None:
        if asked is None:
            raise config.NoTrainingConfig(config.config_path())
        return asked
    if asked is None:
        return declared.duration_cap_min
    if asked > declared.duration_cap_min:
        raise click.ClickException(
            f"{asked} minutes is over the {declared.duration_cap_min} you "
            f"declared as the cap in {config.config_path().name}. Raise the "
            "cap there if a longer workout is what you meant"
        )
    return asked


def _groups(
    workout: int | None,
    declared: config.TrainingConfig | None,
    given: tuple[str, ...],
) -> tuple[str, ...]:
    """The groups this workout trains: off the declared split, or named by hand.

    `--workout` is a flag rather than something derived because nothing tracks
    where in the rotation you are: `workouts` is session 5. Naming it here is
    what stops that session from inventing it.

    Repeats are dropped rather than refused. `--group legs --group legs` is a
    slip with one obvious reading, and left in it makes the even division sum
    to half a workout -- arithmetic nobody wrote, blamed on the person who
    typed the flag twice.
    """
    if workout is None:
        return tuple(dict.fromkeys(given))
    if given:
        raise click.UsageError(
            "--workout takes its groups from the split; --group names them by "
            "hand. Use one or the other"
        )
    if declared is None:
        raise config.NoTrainingConfig(config.config_path())
    try:
        return declared.groups_for(workout)
    except IndexError as error:
        raise click.ClickException(str(error)) from error


def _divided(minutes: int, groups: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    """The minutes over the groups, evenly.

    Offered rather than imposed, the way the rest bands are (ADR-0001): the
    agent has `allocate` and may divide the time on any proportions it can
    argue for. Even shares because this layer has no grounds for any other
    split -- *60-40 on two groups* is what one workout might look like, not a
    law, and it means nothing the moment a workout trains three.
    """
    if not groups:
        return ()
    share = 1 / len(groups)
    allocated = budget.allocate(minutes, {group: share for group in groups})
    return tuple((group, allocated[group]) for group in groups)


def _preferred(connection: sqlite3.Connection, avoid: tuple[str, ...]) -> tuple[str, ...]:
    """The exercises the user would rather not do, checked against the catalog.

    A mistyped id is the worst possible outcome here: the preference is
    silently unenforced, the plan comes back with the thing in it, and the
    typo also travels to the model as something it must not prescribe. Read
    from the data, the way every other vocabulary in this project is.
    """
    for exercise_id in avoid:
        if catalog.exercise(connection, exercise_id) is None:
            raise click.ClickException(
                f"no such exercise: {exercise_id!r}. A preference names an "
                "exercise by id, the way a plan does"
            )
    return tuple(dict.fromkeys(avoid))


def _only_with_a_model(context: click.Context, *options: tuple[str, str]) -> None:
    """Refuse an option that does nothing on the path being taken.

    `--from` is the no-model path, so a call budget has nothing to bound and
    there is no run to record. Silently ignored, `trainer plan --from ...
    --record run.json` exits zero having written no file, which reads exactly
    like a record that was written.

    The flag and the parameter it lands on are both given: `--record` is
    `record_path` here, and deriving one from the other would check a name
    click has never heard of and pass every time.
    """
    for option, name in options:
        if context.get_parameter_source(name) is ParameterSource.COMMANDLINE:
            raise click.UsageError(
                f"{option} has no meaning with --from: that path asks no model, "
                "so there are no tool calls to bound and no run to record"
            )


def _writable(path: Path) -> None:
    parent = path.parent if str(path.parent) else Path(".")
    if not parent.is_dir():
        raise click.ClickException(
            f"there is no directory {parent} to write {path.name} into"
        )


def _checked(
    connection: sqlite3.Connection,
    parsed: plan.WorkoutPlan,
    request: plan.Request,
    budget: int,
) -> tuple[plan.WorkoutPlan, list[str]]:
    """The plan that survived the rules, and how it reads.

    Both, because the caller has to write down the same plan it printed. A
    helper that returned only the lines would leave `plan_command` re-deciding
    which of the two paths produced the plan it is persisting, and the two
    answers would eventually differ.
    """
    blocks = plan.to_blocks(parsed)
    plan.validate(connection, blocks, request, parsed)
    return parsed, plan.render(connection, parsed, blocks, budget)


def _asked(
    connection: sqlite3.Connection,
    request: plan.Request,
    budget: int,
    call_budget: int,
    record_path: Path | None,
) -> tuple[plan.WorkoutPlan, list[str]]:
    """One run, with the record written whichever way it goes.

    Written *before* a refusal is raised, on purpose: the record is what you
    open to find out why the model emitted what it did, and a refusal is
    exactly the case you want it for.
    """
    record = agent.plan_workout(connection, request, budget=call_budget)
    if record_path is not None:
        record_path.write_text(record.model_dump_json(indent=1), encoding="utf-8")
    if record.refused is not None:
        raise click.ClickException(record.refused)

    blocks = plan.to_blocks(record.plan)
    return record.plan, [
        *plan.render(connection, record.plan, blocks, request.budget_min),
        "",
        *agent.summary(record),
    ]


def _recorded(
    connection: sqlite3.Connection, accepted: plan.WorkoutPlan, on: str
) -> int:
    """Write the workout that was just prescribed, and return its id.

    The one place the wire shape is paired with the costed one for the writer:
    `reason` lives on the document and the rest of the block lives on
    `duration.Block`, and `strict` is what stops a mismatched pair from
    persisting a workout whose reasons belong to different blocks.
    """
    return workouts.record_prescribed(
        connection,
        tuple(
            workouts.PrescribedBlock(block=costed, reason=shape.reason)
            for shape, costed in zip(
                accepted.blocks, plan.to_blocks(accepted), strict=True
            )
        ),
        on=on,
    )



@main.command("log")
@click.option(
    "--from",
    "source",
    metavar="FILE",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A performed workout written by hand, in the shape the agent will emit.",
)
def log_command(source: Path) -> None:
    """Report a workout you performed, and print what was understood.

    `--from FILE` is the whole of this command for now: a document somebody
    wrote by hand goes through the same validator, the same writer and the
    same renderer the logging agent will use. The interactive `trainer log`,
    where a model reads what you actually said, is session 5's issue 04.

    What you do not mention was done as prescribed -- that is adherence, and
    every value it fills in is printed marked `(assumed)`. Nothing here is
    refused for being a bad workout: a report is a **fact**, and an exercise
    you were told not to do is written, flagged, and kept.
    """
    with reported():
        performed = log.parse(source.read_text(encoding="utf-8"))

    today = date.today().isoformat()
    with _opened() as connection:
        _require_enrichment(connection)
        with reported():
            log.validate(connection, performed, today)
            blocks = log.to_performed(connection, performed)
            # The flags are read off `blocks` rather than off the document,
            # because `blocks` is what gets written: adherence fills in what
            # the report did not mention, and an exercise filled in that way
            # is as much a performed exercise as one the user named.
            flagged = log.flags(connection, performed, blocks, today)

            # Printed before it is written, for the reason `trainer plan`
            # gives: a database that cannot be written to is worth an error,
            # and it is not worth throwing away what the user reported in
            # order to report one.
            for line in log.render(connection, performed, blocks, flagged):
                click.echo(line)

            exclusion, retest_date = log.proposed(connection, performed)
            workouts.record_performed(
                connection,
                blocks,
                on=today,
                report=performed.report,
                workout_id=performed.workout_id,
                exclusion=exclusion,
                retest_date=retest_date,
            )


def _require_enrichment(connection: sqlite3.Connection) -> None:
    """Refuse before any value is classified against an empty vocabulary.

    `exclusions.classify` reads what `movement_pattern` and `loaded_joints`
    actually hold, so against an unenriched catalog it rejects `squat` as
    neither -- a correct value reported as a typo, which is the standing rule's
    own example. Every command that classifies a value calls this first; the
    check is here rather than in `_opened` because `db status` and `catalog
    --stats` are legitimate questions to ask of a catalog nobody has enriched.
    """
    if not catalog.values(connection, "movement_pattern"):
        raise click.ClickException(admissible.UNENRICHED_MESSAGE)


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
        found = catalog.values(connection, field)
        # Empty and enrichment-only means every row is null for this field --
        # a catalog that has not been enriched yet, not a field with a
        # legitimately empty vocabulary. The distinction matters the same way
        # it does for an empty database: a correct value must never be
        # rejected against a vocabulary that is empty because nobody has
        # written to it, rather than because it holds nothing.
        if not found and field in catalog.ENRICHMENT_VALUE_FIELDS:
            raise click.ClickException(
                "the catalog is not enriched yet; run `trainer enrich derive` first"
            )
        for value in found:
            click.echo(value)
        if field in catalog.SCALAR_FILTERS or field in catalog.ENRICHMENT_VALUE_FIELDS:
            absent = catalog.missing_count(connection, field)
            if absent:
                click.echo(f"({absent} exercises have no {field} recorded)")


def _print_stats(stats: catalog.CatalogStats) -> None:
    """Counts, and nothing derived from them.

    Every number here was computed by the engine. The `(none)` row is printed
    even when it is zero: it is the line that makes each column add up to the
    total, and a reader who cannot see it has to take the arithmetic on trust.
    """
    if not stats.total:
        click.echo("no exercise matches those filters")
        return

    click.echo(f"{stats.total} exercises")
    click.echo(
        "\n".join(
            _aligned(
                [("of which strength", stats.strength), ("everything else", stats.other)]
            )
        )
    )
    for breakdown in stats.breakdowns:
        click.echo("")
        click.echo(f"{breakdown.field}:")
        click.echo(
            "\n".join(_aligned([*breakdown.counts, ("(none)", breakdown.missing)]))
        )
    for coverage in stats.enrichment:
        click.echo("")
        click.echo(f"{coverage.field}:")
        click.echo(
            "\n".join(
                _aligned(
                    [
                        ("rule", coverage.rule),
                        ("curated", coverage.curated),
                        ("(none)", coverage.unfilled),
                    ]
                )
            )
        )


def _aligned(rows: list[tuple[str, int]]) -> list[str]:
    """Labels left, counts right, indented. Widths are per block, not global."""
    label_width = max(len(label) for label, _ in rows)
    count_width = max(len(str(count)) for _, count in rows)
    return [
        f"  {label.ljust(label_width)}  {str(count).rjust(count_width)}"
        for label, count in rows
    ]


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
