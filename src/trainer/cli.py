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

from trainer import __version__, agent, plan
from trainer.engine import (
    admissible,
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
    except duration.DurationError as error:
        # `trainer plan` is the first command that costs a plan. `tools.py`
        # has listed this among the engine's stated failures since the surface
        # existed; the terminal had no clause for it because nothing here
        # reached the costing path.
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
def admissible_command(
    equipment: tuple[str, ...], budget: int, exclude: tuple[str, ...]
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
                connection, [*standing, *classified], equipment, budget
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
    required=True,
    help="Minutes available. The plan is checked against this, never cut to fit.",
)
@click.option(
    "--exclude",
    "exclude",
    metavar="VALUE",
    multiple=True,
    help="A movement pattern or a loaded joint to keep out -- never an exercise id.",
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
    budget: int,
    exclude: tuple[str, ...],
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
    parsed: plan.WorkoutPlan | None = None
    if source is not None:
        _only_with_a_model(
            context, ("--call-budget", "call_budget"), ("--record", "record_path")
        )
        with reported():
            parsed = plan.parse(source.read_text(encoding="utf-8"))
            plan.to_blocks(parsed)
    elif record_path is not None:
        # Checked before the model is called rather than after. `--record` is
        # the artefact the run exists to produce, and a path that cannot be
        # written is worth finding out about while the run is still free.
        _writable(record_path)

    with _opened() as connection:
        _require_enrichment(connection)
        with reported():
            classified = [exclusions.classify(connection, value) for value in exclude]
            standing = exclusions.active(connection, date.today().isoformat())
            request = plan.Request(
                equipment=equipment,
                budget_min=budget,
                exclusions=(*standing, *classified),
            )
            try:
                if parsed is not None:
                    lines = _checked(connection, parsed, request, budget)
                else:
                    lines = _asked(connection, request, budget, call_budget, record_path)
            except catalog.UnknownFilterValue as error:
                raise _rejected(error) from error

    for line in lines:
        click.echo(line)


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
) -> list[str]:
    blocks = plan.to_blocks(parsed)
    plan.validate(connection, blocks, request)
    return plan.render(connection, parsed, blocks, budget)


def _asked(
    connection: sqlite3.Connection,
    request: plan.Request,
    budget: int,
    call_budget: int,
    record_path: Path | None,
) -> list[str]:
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
    return [
        *plan.render(connection, record.plan, blocks, request.budget_min),
        "",
        *agent.summary(record),
    ]


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
