"""The CLI: argument parsing and formatting, nothing else.

Every decision here belongs to the engine. If a function in this module starts
computing something rather than displaying it, it is in the wrong file.

That includes failure. An engine exception arriving at the terminal as a
traceback is the boundary leaking: the engine states what went wrong, the CLI
decides how a person should read it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

import click
from click.core import ParameterSource
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from trainer import (
    __version__,
    evaluation,
    log,
    log_evaluation,
    log_set,
    plan,
    tools,
)
from trainer.coach import (
    bot,
    checkpoints,
    logfile,
    logger,
    memory,
    models,
    planner,
    runs,
)
from trainer.coach import record as run_record
from trainer.engine import (
    admissible,
    budget,
    catalog,
    config,
    constraints,
    database,
    duration,
    enrichment,
    exclusions,
    graph,
    mesocycles,
    migrations,
    muscle_groups,
    reference_set,
    residue,
    snapshot,
    state,
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
    except log_set.LogSetError as error:
        raise click.ClickException(f"the log set is unusable: {error}") from error
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
    except constraints.ConstraintError as error:
        raise click.ClickException(str(error)) from error
    except admissible.AdmissibleError as error:
        raise click.ClickException(str(error)) from error
    except state.StateError as error:
        # `trainer state` is the first command to ask the state module
        # anything. Every sibling module's stated failure is translated here
        # and this one was not, which would have made it the only one to reach
        # the terminal as a traceback -- the reachable paths are all guarded
        # upstream today, and that is exactly how a gap like this survives.
        raise click.ClickException(str(error)) from error
    except mesocycles.MesocycleError as error:
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
    except models.ModelError as error:
        # No credentials, or the provider refusing the request. A state the
        # user can act on, not a failure of the plan they asked for.
        raise click.ClickException(str(error)) from error
    except models.ModelError as error:
        # The provider the graph runs on: a server nobody started, a model
        # nobody pulled, a backend nobody built. Each already carries its fix.
        raise click.ClickException(str(error)) from error
    except bot.BotError as error:
        # The Telegram settings: a token nobody set, an owner id given as the
        # username the user knows themselves by. Each already carries its fix.
        raise click.ClickException(str(error)) from error
    except checkpoints.CheckpointError as error:
        # `trainer bot` is the first command to open the checkpointer, so this
        # is the first path on which pointing TRAINER_CHECKPOINTS at the
        # training database can be said out loud rather than raised.
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


PLAN_SUITE, LOG_SUITE = "plan", "log"
"""The two measurements, under one command.

Session 4's six situations and session 5's thirty reports are checked on
different things -- properties that must hold always against a plan nobody
wrote down, and expected outcomes somebody did -- so they are two suites and
not one with a wider matrix. What they share is the loop, the cost, the
distribution over repetitions and the bar, which is why they share a command.

`plan` is the default because `trainer eval` meant the six before it meant
anything else, and a default that moved would change what a command in
somebody's notes does.
"""


@main.command("eval")
@click.option(
    "--suite",
    "suite",
    type=click.Choice((PLAN_SUITE, LOG_SUITE)),
    default=PLAN_SUITE,
    show_default=True,
    help="Which measurement to run: the six planning situations, or the "
    "logging set's thirty hand-written reports.",
)
@click.option(
    "--repetitions",
    "repetitions",
    metavar="N",
    type=click.IntRange(min=1),
    default=evaluation.REPETITIONS,
    show_default=True,
    help="How many times each situation or report runs. A model is a "
    "distribution, so one run measures nothing.",
)
@click.option(
    "--only",
    "only",
    metavar="NAME",
    multiple=True,
    help="Run just these situations or reports, by name. Every run still "
    "counts, so a partial pass is a partial answer.",
)
@click.option(
    "--records",
    "records",
    metavar="DIR",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where each run's record is written. A failure names the file. "
    "Defaults to eval-runs/ in TRAINER_HOME.",
)
@click.option(
    "--call-budget",
    "call_budget",
    metavar="N",
    type=click.IntRange(min=1),
    default=tools.CALL_BUDGET,
    show_default=True,
    help="Tool calls each run may make before it is asked to emit anyway.",
)
def eval_command(
    suite: str,
    repetitions: int,
    only: tuple[str, ...],
    records: Path,
    call_budget: int,
) -> None:
    """Run a measurement against the real model, and check it by code.

    `--suite plan` runs the planner graph over the six adverse situations, on
    the provider `LLM_BACKEND` names, and checks the six invariants over every
    run. Not *good plan / bad plan* -- properties that must hold always. It
    also reports what the planner itself spent: attempts to a valid plan, wall
    time, tool calls, and the rule still refusing a run that never got there.

    `--suite log` is session 5's: thirty hand-written reports, eighteen the
    sentence determines and twelve it does not. The first eighteen are scored
    by equality on the document the agent emitted and the volume it produces;
    the twelve on whether it asked, with a value written where a question was
    needed counted double against.

    No model judges another model's output in either of them.

    **This is the one command in the project that reaches a provider**, and
    the only one that spends money. `pytest` never runs it: the suite has no
    sockets and no credentials, and the checks are covered there against
    recorded runs instead.

    The plan suite's bar is 100%; the log suite's are the two its set declares.
    The command exits non-zero below either.
    """
    with _opened() as connection:
        _require_enrichment(connection)
        with reported():
            if suite == LOG_SUITE:
                lines, report = _log_suite(
                    connection, only, repetitions, records, call_budget
                )
            else:
                lines, report = _plan_suite(
                    connection, only, repetitions, records, call_budget
                )

    for line in lines:
        # The reports, the questions and the exclusions in this output were
        # written by a person and a model, not by this project. `trainer log`
        # folds them to ASCII for the same console and the same reason.
        click.echo(_ascii(line))
    if not report.passed:
        raise SystemExit(1)


def _plan_suite(
    connection: sqlite3.Connection,
    only: tuple[str, ...],
    repetitions: int,
    records: Path,
    call_budget: int,
) -> tuple[list[str], evaluation.Report]:
    """The six situations against the planner graph, on the provider `LLM_BACKEND` names.

    The provider's state is checked once, before anything runs. A server
    nobody started or a key nobody set is a precondition with a fix, not
    eighteen rows of *not run* under a matrix of dashes.

    What the pass costs this laptop is sampled while it runs, because on a
    local model the minutes and the memory are half of what ticket 01 set out
    to find out.
    """
    chosen = _chosen(evaluation.situations(connection), only, "situation")
    on = models.planner()
    models.ready(on)
    with evaluation.pointed_at_the_database(), memory.sampling(on) as sampled:
        report = evaluation.run(
            connection,
            chosen,
            on=on,
            repetitions=repetitions,
            records=records,
            budget=call_budget,
        )
    return [*evaluation.render(report, chosen), *sampled.lines()], report


def _log_suite(
    connection: sqlite3.Connection,
    only: tuple[str, ...],
    repetitions: int,
    records: Path,
    call_budget: int,
) -> tuple[list[str], evaluation.Report]:
    """The thirty reports, against a database built for them.

    Everything that can be wrong without a model is checked first: an id the
    catalog does not have, a row whose expected document reports against the
    wrong workout, a volume figure its own document does not produce. Thirty
    agent runs cost minutes and money, and every one of them measures nothing
    if the set and the catalog disagree.

    Then the provider, and only then, for the reason the plan suite checks it
    at all: a key nobody set is a precondition with a fix, not thirty rows of
    *not run* under a matrix of dashes. After the set, because a set that
    disagrees with the catalog is worth saying on a machine with no key.
    """
    holds = log_set.load()
    _refuse(log_evaluation.missing(connection, holds))
    chosen = _chosen(holds.rows, only, "report")
    with log_evaluation.prepared(connection, holds) as where:
        _refuse(log_evaluation.verify(where, holds))
        on = models.logger()
        models.ready(on)
        report = log_evaluation.run(
            where,
            chosen,
            on=on,
            repetitions=repetitions,
            records=records,
            budget=call_budget,
        )
    report = log_evaluation.barred(report, holds)
    return log_evaluation.render(report, chosen), report


def _refuse(problems: Sequence[str]) -> None:
    if problems:
        raise click.ClickException("\n".join(problems))


_Named = TypeVar("_Named", evaluation.Situation, log_set.Row)
"""What both suites' cases have in common at this boundary: a name typed at
`--only`. Two concrete types rather than a protocol, because there are two and
naming them is what makes the error message able to say which."""


def _chosen(
    available: Sequence[_Named], only: tuple[str, ...], what: str
) -> tuple[_Named, ...]:
    if not only:
        return tuple(available)
    known = {case.name: case for case in available}
    for name in only:
        if name not in known:
            raise click.ClickException(
                f"no {what} called {name!r}; they are {', '.join(known)}"
            )
    # Named twice is named once. Left in, the case runs twice the repetitions
    # against a paid provider and prints two identical rows.
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


@main.command("bot")
def bot_command() -> None:
    """Answer Telegram from the graph's process, until interrupted.

    Long polling, so there is no public IP, no tunnel and no cloud deploy
    (ADR-0004, item 6). The model, the checkpointer and the compiled graph are
    built once and held for the life of the process, and one chat is one
    thread: the conversation survives a restart, because the checkpointer is a
    file on disk.

    Only `TELEGRAM_OWNER_ID` is answered, and anything arriving from anybody
    else is ignored. Both settings are read from the environment, never from
    `training.toml`, which holds what you declare about your training.

    Two models answer it (ADR-0006): the entrance holds the conversation on
    the one `ENTRANCE_MODEL` names, and the planner and the logger it reaches
    run on `LLM_BACKEND`'s.

    Everything the bot needs is checked before it starts, and only for the
    providers selected: on Ollama the server, both models and
    `OLLAMA_CONTEXT_LENGTH`; on Groq the key; and the token, with Telegram.

    What happens then goes to a rotating log in the home, never to the token or
    the owner id, and it is the file the chat names when a run cannot start or
    falls over.
    """
    with reported():
        # First, so that everything the rest of this block decides is in the
        # file rather than in whatever terminal happened to be attached.
        log_file = logfile.start((bot.TOKEN_ENV, bot.OWNER_ENV))
        declared = bot.settings()
        on = models.planner()
        models.ready(on)
        context = models.context_length(on)
        # Every model, because every one is asked for in the conversation: the
        # entrance answers the turn and a subgraph does the work, and a model
        # nobody pulled is knowable now rather than mid-conversation.
        logs = models.logger()
        models.ready(logs)
        front = models.entrance()
        models.ready(front)
        name = bot.identified(declared)

        # Opened before the block is printed, not after: a block that says
        # where the checkpoints go, immediately before saying they cannot go
        # there, is worse than no block at all.
        with checkpoints.saver() as saver:
            click.echo(f"provider:    {on.provider}")
            click.echo(f"model:       {on.name}")
            click.echo(f"logger:      {logs.name}")
            click.echo(f"entrance:    {front.name} on {front.provider}")
            click.echo(
                f"context:     {context} tokens"
                if context is not None
                else f"context:     {on.provider}'s own"
            )
            click.echo(f"checkpoints: {checkpoints.checkpoints_path()}")
            click.echo(f"log:         {log_file}")
            click.echo(f"bot:         {name}")
            # The owner's chat id is their user id, a private chat being
            # between the two of them, so the thread is knowable before
            # anybody has written anything.
            click.echo(
                f"owner:       {declared.owner_id} -> "
                f"thread {bot.thread_for(declared.owner_id)}"
            )
            click.echo("long-polling; ctrl-c to stop")

            bot.serve(declared, front, on, logs, saver)


@main.group("runs")
def runs_group() -> None:
    """Read back what the coach did: the negotiations it held, and how each one ended.

    Documents in the home, written the moment a run ended, plus whichever run
    the checkpointer is still carrying. Nothing here builds a graph or names a
    model, so it answers with the provider unreachable -- which is the state
    you reach for it in (ADR-0007, item 9).
    """


@runs_group.command("list")
def runs_list() -> None:
    """List the negotiations, most recently moved first."""
    with reported():
        held = _negotiations()
    if not held:
        click.echo(
            f"{run_record.archive()} holds no negotiation yet; run `trainer "
            "plan` or `trainer bot` first"
        )
        return
    width = max(len(negotiation.negotiation) for negotiation in held)
    for negotiation in held:
        click.echo(runs.line(negotiation, width))


@runs_group.command("show")
@click.argument("name")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print the whole document instead of the summary: every call with "
    "its arguments, every violation, the plan.",
)
def runs_show(name: str, as_json: bool) -> None:
    """Print a negotiation's runs, or one run of it, by name.

    A run with no document beside it is one that was cut, and it is printed
    off the checkpointer from where it stopped: the calls it had made, the
    attempts it had spent and the nodes that finished.
    """
    with reported():
        held = _negotiations()
    found = runs.named(held, name)
    if found is None:
        raise click.ClickException(
            f"there is no negotiation or run named {name}; `trainer runs "
            "list` names the ones there are"
        )
    one = runs.run_named(found, name)
    if as_json:
        click.echo(_documents(found, one))
        return
    click.echo(runs.line(found))
    for written in (one,) if one is not None else found.runs:
        click.echo("")
        said = written.document.get("because") or ""
        click.echo(
            f"{written.run}  {runs.moment(written.ended)}  {written.ending}"
            + (f" -- {said}" if said else "")
        )
        for said in run_record.summary(written.document):
            click.echo(said)
    if one is None and found.open:
        assert found.live is not None
        click.echo("")
        click.echo(
            f"{found.live.run}  {runs.moment(found.live.moved)}  {found.outcome}"
        )
        for said in run_record.summary(runs.of(found.live, tools.CALL_BUDGET)):
            click.echo(said)


def _documents(found: runs.Negotiation, one: runs.Run | None) -> str:
    """What `--json` prints: one run's document, or every document of a negotiation."""
    if one is not None:
        return run_record.document(one.document)
    held: list[Mapping[str, object]] = [written.document for written in found.runs]
    if found.open and found.live is not None:
        held.append(runs.of(found.live, tools.CALL_BUDGET))
    return json.dumps(held, indent=1)


def _negotiations() -> list[runs.Negotiation]:
    """Every negotiation, from the archive and from whatever the checkpointer still holds.

    The checkpointer is opened only if it is already there: `saver` creates
    the file, so a reader pointed at the wrong home would make an empty one
    and report it as a history with nothing in it.
    """
    closed = runs.kept(run_record.archive())
    path = checkpoints.checkpoints_path()
    if not path.exists():
        return runs.negotiations(closed, ())
    with checkpoints.saver() as saver:
        return runs.negotiations(closed, runs.live(saver))


@main.command("config")
@click.option(
    "--muscle-groups",
    "show_groups",
    is_flag=True,
    help="Show the muscle group mapping instead: the catalog's seventeen "
    "primary muscles and the group each is allocated under.",
)
def config_command(show_groups: bool) -> None:
    """Show what the user has declared: cycle, cap, split, denominator, equipment.

    Read-only. Nothing in trainer writes this file; it is hand-edited until
    onboarding fills it by talking to you (ADR-0003).
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
    click.echo(f"equipment: {', '.join(declared.equipment)}")
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

    `--time` over the cap declared in `training.toml` is refused rather than
    answered: a workout that long is one the declaration says never happens.
    """
    with _opened() as connection:
        _require_enrichment(connection)

        classified = [exclusions.classify(connection, value) for value in exclude]
        todays = constraints.constraining_today(
            connection,
            date.today().isoformat(),
            budget_min=budget,
            groups=groups,
            given=classified,
        )
        try:
            found = admissible.admissible_set(
                connection, todays.exclusions, equipment, todays.budget_min, todays.groups
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
    help="Today's equipment; repeat for more than one. Defaults to what you "
    "declared in training.toml, which is what you own -- name it here for "
    "where you actually are today.",
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
    help="A muscle group this workout trains; repeat for more than one. Left "
    "out, the groups come from where the rotation is; --workout names a "
    "position in the split instead.",
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
    "--call-budget",
    "call_budget",
    metavar="N",
    type=click.IntRange(min=1),
    default=tools.CALL_BUDGET,
    show_default=True,
    help="Tool calls the model may make before it is asked to emit anyway.",
)
@click.option(
    "--record",
    "record_path",
    metavar="FILE",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the run record here: the calls, the attempts, what each node cost.",
)
@click.option(
    "--mesocycle",
    "mesocycle",
    is_flag=True,
    help="Plan a mesocycle instead: one workout for every slot of the split, "
    "repeated for as many cycles as the agent says and why. Accepted, it is "
    "kept; nothing is prescribed until a workout is served (ADR-0008).",
)
@click.option(
    "--change",
    "change",
    metavar="TEXT",
    help="Rewrite the accepted mesocycle for the cycles left, as TEXT asks, "
    "keeping the count already done (ADR-0008).",
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
    call_budget: int,
    record_path: Path | None,
    mesocycle: bool,
    change: str | None,
) -> None:
    """Plan a workout, and print it.

    With no options at all it reads today's workout off the accepted
    mesocycle: the slot the rotation is at, prescribed when it is first
    served, with the load each exercise was last performed with. No model is
    asked (ADR-0008). With none accepted it says so and names `--mesocycle`.

    An option that shapes today's workout adapts that slot of the mesocycle
    for today and leaves the mesocycle alone. With no mesocycle, or with
    `--workout` or `--group`, it plans one from nothing instead: the groups off
    the declared split at the position the performed workouts put it, the
    minutes off the declared cap, and the equipment off what you declared you
    have. Every option below overrides one of those for today.

    The planner graph is asked for the plan, on the provider `LLM_BACKEND`
    names, using the same tools `trainer mcp` serves and inside a budget of
    tool calls; when the budget runs out it is asked to emit with what it has.
    With `--from FILE` no model is involved at all and a hand-written plan is
    checked instead -- the same rules, the same rendering, the agent left out.

    Either way the plan is **rejected** if it breaks a rule, naming the rule,
    and nothing is trimmed to fit (ADR-0001). On the graph's path a refusal
    goes back to the planner with its reasons for a bounded number of attempts
    (ADR-0004), and what is printed is a plan that passed every rule or
    nothing at all: half a workout with a refusal under it reads as a workout
    with a footnote.
    """
    if change is not None and not change.strip():
        raise click.UsageError("--change says what to change: it cannot be blank")
    if change is not None and mesocycle:
        raise click.UsageError(
            "--change rewrites the accepted mesocycle and --mesocycle plans a new "
            "one: give one or the other"
        )
    if change is not None and (workout is not None or groups):
        raise click.UsageError(
            "--change rewrites every slot of the mesocycle, so it names none: drop "
            "--workout and --group"
        )
    if mesocycle and (workout is not None or groups):
        raise click.UsageError(
            "--mesocycle plans every slot of the split, so it names none: drop "
            "--workout and --group"
        )
    if (mesocycle or change is not None) and source is not None:
        raise click.UsageError(
            "--from checks one hand-written workout; --mesocycle and --change ask "
            "a model for every slot"
        )
    served = not mesocycle and change is None and source is None and workout is None and budget is None
    served = served and not (equipment or exclude or groups or avoid)
    if source is not None or served:
        _only_with_a_model(
            context,
            "--from" if source is not None else "today's workout off the mesocycle",
            ("--call-budget", "call_budget"),
            ("--record", "record_path"),
        )
    elif record_path is not None:
        # Checked before the model is called rather than after. `--record` is
        # the artefact the run exists to produce, and a path that cannot be
        # written is worth finding out about while the run is still free.
        _writable(record_path)

    today = date.today().isoformat()
    if served:
        with _opened() as connection, reported():
            for line in _served(connection, today):
                click.echo(_ascii(line))
        return
    if mesocycle or change is not None:
        with _opened() as connection, reported():
            shaped = plan.Asked(equipment=equipment, minutes=budget, exclude=exclude, avoid=avoid)
            asked = (
                plan.mesocycle_requested(connection, today, shaped)
                if change is None
                else plan.change_requested(connection, today, change, shaped)
            )
            try:
                lines = _asked_mesocycle(connection, asked, call_budget, record_path)
            except catalog.UnknownFilterValue as error:
                raise _rejected(error) from error
            for line in lines:
                click.echo(_ascii(line))
        return
    with _opened() as connection:
        with reported():
            # The request first, and the plan after it. The plan is checked
            # *against* the request, so a workout outside the cycle or a time
            # over the cap is the more basic thing to be told about --
            # reported the other way round, a mistyped file hides a mistyped
            # rotation.
            shaping = plan.Asked(
                equipment=equipment,
                minutes=budget,
                workout=workout,
                groups=groups,
                exclude=exclude,
                avoid=avoid,
            )
            adapting = (
                _adaptable(connection) if source is None and workout is None and not groups else None
            )
            if adapting is not None:
                request = plan.adaptation_requested(connection, today, shaping)
                click.echo(
                    f"adapting mesocycle workout {adapting.slot} of {adapting.slots}, "
                    f"cycle {adapting.cycle} of {adapting.cycles} -- {', '.join(request.groups)}"
                )
            else:
                assembled = plan.requested(connection, today, shaping)
                request = assembled.request
                if assembled.rotation is not None:
                    click.echo(_rotation(assembled.rotation, request.groups))

            parsed: plan.WorkoutPlan | None = None
            if source is not None:
                parsed = plan.parse(source.read_text(encoding="utf-8"))
                plan.to_blocks(parsed)

            try:
                if parsed is not None:
                    accepted, lines = _checked(
                        connection, parsed, request, request.budget_min
                    )
                else:
                    accepted, lines = _asked(
                        connection, request, call_budget, record_path
                    )
            except catalog.UnknownFilterValue as error:
                raise _rejected(error) from error

            # Printed before it is written, and that order is the point. A
            # rejected plan is not printed at all -- the refusal above has
            # already raised -- but a plan that passed every rule is the
            # user's workout, and on the model path it cost a real run. A
            # database that cannot be written to is worth an error; it is not
            # worth throwing the workout away to report one.
            #
            # Folded to ASCII for the reason `trainer log` folds what it
            # prints: every block carries a reason the model wrote, and this
            # console runs at a code page that cannot encode what a model
            # reaches for. A valid plan from `gpt-oss:20b` was lost to a
            # non-breaking hyphen in exactly this echo.
            for line in lines:
                click.echo(_ascii(line))

            # Only the hand-written path writes here. A plan the graph made
            # was written by the node after the resume (ADR-0005), and writing
            # it again would make one workout two -- `record_prescribed` has no
            # upsert, deliberately. `--from` asks no model and has no graph to
            # resume, so the command is still the writer for it.
            if parsed is not None:
                _recorded(connection, accepted, today)


def _adaptable(connection: sqlite3.Connection) -> mesocycles.Today | None:
    """Today's slot of the mesocycle, or `None` when there is none to adapt and one is planned from nothing."""
    try:
        return mesocycles.today(connection)
    except mesocycles.MesocycleError:
        return None


def _rotation(where: state.Rotation, groups: tuple[str, ...]) -> str:
    """Where the groups came from, said out loud.

    Printed only when they were derived: told *rotation: workout 3 of 4* about
    a workout they named themselves, the reader learns nothing and cannot tell
    the two cases apart.
    """
    return (
        f"rotation: workout {where.position} of {where.cycle_length}, "
        f"cycle {where.cycle} ({where.performed} performed) -- "
        f"{', '.join(groups)}"
    )


def _served(connection: sqlite3.Connection, today: str) -> list[str]:
    """Today's workout off the mesocycle, prescribed once, and how it reads."""
    found, workout_id = mesocycles.record_served(connection, today)
    return [
        f"mesocycle: workout {found.slot} of {found.slots}, "
        f"cycle {found.cycle} of {found.cycles}",
        *plan.render(
            connection,
            plan.from_prescribed(found.blocks),
            [prescribed.block for prescribed in found.blocks],
            config.load().duration_cap_min,
            loads=True,
        ),
        "",
        f"prescribed as workout {workout_id}",
    ]


def _only_with_a_model(
    context: click.Context, path: str, *options: tuple[str, str]
) -> None:
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
                f"{option} has no meaning with {path}: that path asks no model, "
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
    violations = plan.validate(connection, blocks, request, parsed)
    if violations:
        raise plan.PlanRejected(plan.refusal(violations))
    return parsed, plan.render(connection, parsed, blocks, budget)


def _asked(
    connection: sqlite3.Connection,
    request: plan.Request,
    call_budget: int,
    record_path: Path | None,
) -> tuple[plan.WorkoutPlan, list[str]]:
    """One run of the planner graph, with the record written whichever way it goes.

    Written *before* a refusal is raised, on purpose: the record is what you
    open to find out why the model emitted what it did, and a run refused on
    its last attempt is exactly the case you want it for. Written *after* the
    resume when there is one, so that the file holds the whole run -- the same
    thing `trainer runs show` reads back off the last checkpoint, which it
    could not be if the two stopped at different points. In a `finally`, so
    that a resume that falls over still leaves the record of what came before
    it.

    **Invoked, then resumed** (ADR-0005). The graph stops at the plan and the
    workout is written by the node after the resume, so this command resumes
    immediately: it has no buttons, and printing a plan has always meant
    keeping it. That is why it needs a checkpointer with no bot in sight.

    A thread of its own per run, because a thread is a conversation: reusing
    one would plan today's workout against what was said the last time the
    command was run.
    """
    emitted, written = _ran(request, call_budget, record_path)
    assert isinstance(emitted, plan.WorkoutPlan)
    blocks = plan.to_blocks(emitted)
    return emitted, [
        *plan.render(connection, emitted, blocks, request.budget_min),
        "",
        *run_record.summary(written),
    ]


def _asked_mesocycle(
    connection: sqlite3.Connection,
    request: plan.MesocycleRequest,
    call_budget: int,
    record_path: Path | None,
) -> list[str]:
    """One run of the planner graph for a mesocycle, accepted, and how it reads."""
    emitted, written = _ran(request, call_budget, record_path)
    assert isinstance(emitted, plan.Mesocycle)
    lines = [f"mesocycle: {emitted.cycles} cycles -- {emitted.why}"]
    for slot, (workout, asked) in enumerate(
        zip(emitted.workouts, request.slots, strict=True), start=1
    ):
        lines.extend(
            [
                "",
                f"workout {slot} of {len(request.slots)} -- {', '.join(asked.groups)}",
                *plan.render(connection, workout, plan.to_blocks(workout), asked.budget_min),
            ]
        )
    return [
        *lines,
        "",
        "kept; nothing is prescribed until a workout is served",
        "",
        *run_record.summary(written),
    ]


def _ran(
    request: plan.Request | plan.MesocycleRequest,
    call_budget: int,
    record_path: Path | None,
) -> tuple[plan.WorkoutPlan | plan.Mesocycle, dict[str, Any]]:
    """The planner graph run once and resumed as accepted, and the run's record."""
    on = models.planner()
    models.ready(on)
    with checkpoints.saver() as saver:
        archive = run_record.archive()
        graph = planner.build(
            on, budget=call_budget, checkpointer=saver, archive=archive
        )
        thread: RunnableConfig = {"configurable": {"thread_id": f"plan:{uuid4()}"}}
        try:
            final = graph.invoke(planner.starting(request), thread)
            refused = final["violations"]
            emitted = final["plan"]
            if not refused:
                final = graph.invoke(Command(resume=planner.accepted()), thread)
        except Exception:
            run_record.failed(graph, thread, call_budget, archive)
            raise
        finally:
            if record_path is not None:
                _copied(graph, thread, archive, record_path)
        if refused:
            raise click.ClickException(plan.refusal(refused))
        assert emitted is not None, "a run with no violations emitted a plan"
        return emitted, run_record.of(final, call_budget)


def _copied(
    graph: run_record.Graph, thread: RunnableConfig, archive: Path, where: Path
) -> None:
    """The run's own document, put where `--record` asked for it.

    Copied out of the archive rather than derived a second time, so the two
    files are the same bytes: a record written twice is two answers to one
    question, and the second one drifts.
    """
    try:
        values = graph.get_state(thread).values
    except Exception:
        # This runs in a `finally`, and a checkpointer that cannot be read is
        # already the reason the run is ending: raised from here it would
        # replace the exception that says so with one about a record.
        return
    held = run_record.path_of(
        archive, str(values.get("negotiation", "")), str(values.get("run", ""))
    )
    if held.exists():
        where.write_text(held.read_text(encoding="utf-8"), encoding="utf-8")


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
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A performed workout written by hand, in the shape the agent emits. "
    "No model is asked, and nothing is read from what you say.",
)
@click.option(
    "--say",
    "said",
    metavar="TEXT",
    help="What you did, in your own words. Prompted for when it is not given.",
)
@click.option(
    "--call-budget",
    "call_budget",
    metavar="N",
    type=click.IntRange(min=1),
    default=tools.CALL_BUDGET,
    show_default=True,
    help="Tool calls the model may make before it is asked to emit anyway.",
)
@click.option(
    "--record",
    "record_path",
    metavar="FILE",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the run record here: the calls, the questions, the document.",
)
@click.pass_context
def log_command(
    context: click.Context,
    source: Path | None,
    said: str | None,
    call_budget: int,
    record_path: Path | None,
) -> None:
    """Report a workout you performed, and print what was understood.

    Say what you did in your own words and a model reads it against what was
    prescribed, asking you about anything the sentence does not settle. With
    `--from FILE` no model is involved and a document written by hand goes
    through the same validator, the same writer and the same renderer.

    What you do not mention was done as prescribed -- that is adherence, and
    every value it fills in is printed marked `(assumed)`. Nothing here is
    refused for being a bad workout: a report is a **fact**, and an exercise
    you were told not to do is written, flagged, and kept.

    Nothing is written until the whole report has been understood, so
    interrupting a question leaves the database exactly as it was.
    """
    if source is not None:
        _only_with_a_model(
            context,
            "--from",
            ("--say", "said"),
            ("--call-budget", "call_budget"),
            ("--record", "record_path"),
        )
    elif record_path is not None:
        # Before the model is called rather than after, for the reason
        # `trainer plan` checks it there: a path that cannot be written is
        # worth finding out about while the run is still free.
        _writable(record_path)

    today = date.today().isoformat()
    with _opened() as connection:
        _require_enrichment(connection)
        with reported():
            if source is not None:
                final = _by_hand(connection, source, today)
                trailer: list[str] = []
            else:
                final, trailer = _read(connection, said, today, call_budget, record_path)

            # Printed before it is written, for the reason `trainer plan`
            # gives: a database that cannot be written to is worth an error,
            # and it is not worth throwing away what the user reported in
            # order to report one.
            document = final["document"]
            blocks = log.to_performed(connection, document)
            # The flags are read off `blocks` rather than off the document,
            # because `blocks` is what gets written: adherence fills in what
            # the report did not mention, and an exercise filled in that way is
            # as much a performed exercise as one the user named.
            flagged = log.flags(connection, document, blocks, today)
            for line in log.render(connection, document, blocks, flagged):
                click.echo(_ascii(line))
            for line in trailer:
                click.echo(_ascii(line))

            logger.performed(connection, final, blocks)


def _by_hand(
    connection: sqlite3.Connection, source: Path, today: str
) -> dict[str, Any]:
    """A document written by hand, in the shape a run of the logger would have left.

    The same validator and the same writer, reached without a model. The
    author's own proposal stands unasked: confirming the line you just typed
    is noise, and the confirmation exists because a *model* read an exclusion
    out of a passing remark.
    """
    performed = log.parse(source.read_text(encoding="utf-8"))
    log.validate(connection, performed, today)
    return {"document": performed, "today": today, "confirmed": True}


def _read(
    connection: sqlite3.Connection,
    said: str | None,
    today: str,
    call_budget: int,
    record_path: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    """One run of the logger graph: what it understood, and how it went.

    Which workout is open is resolved here and put in the brief. Which workout
    the report is *about* is not: a user who trained something else entirely
    says so in the sentence, and the sentence is the model's to read.

    **The provider is checked before the report is asked for.** No
    credentials, a model the provider does not serve, a server that is not
    running: all knowable before anything is typed, and prompting first means
    the user writes out their whole workout and then loses it to an error that
    was already true.

    The record is written whichever way the run goes, and *before* a refusal
    is raised: it is what you open to find out why the model emitted what it
    did, and a refusal is exactly the case you want it for.
    """
    on = models.logger()
    models.ready(on)
    if not said:
        said = str(click.prompt("What did you do", type=str))
    open_workout = workouts.awaiting(connection)
    archive = run_record.archive()
    with checkpoints.saver() as saver:
        graph = logger.build(
            on, budget=call_budget, checkpointer=saver, archive=archive
        )
        thread: RunnableConfig = {"configurable": {"thread_id": f"log:{uuid4()}"}}
        given: Any = logger.starting(
            said,
            today,
            awaiting=None if open_workout is None else open_workout.id,
            prescribed_on=None if open_workout is None else open_workout.prescribed_on,
        )
        try:
            while True:
                final = graph.invoke(given, thread)
                waiting = final.get("__interrupt__")
                if not waiting:
                    break
                given = Command(resume=_answered(waiting[0].value))
        except Exception:
            run_record.failed(graph, thread, call_budget, archive)
            raise
        finally:
            if record_path is not None:
                _copied(graph, thread, archive, record_path)

    if final["refused"] is not None:
        raise click.ClickException(final["refused"])
    return final, ["", *run_record.summary(run_record.of(final, call_budget))]


def _answered(question: Mapping[str, Any]) -> str | bool:
    """One question from the graph, put to whoever is at the terminal.

    Open or closed is the graph's to say, not this door's: the same payload
    reaches the chat, where the closed one is two buttons and the open one is
    a message to reply to.
    """
    if question.get("kind") == logger.EXCLUSION:
        return _confirmed(question)
    return _ask(str(question.get("ask", "")))


TYPOGRAPHY = {
    "\u2014": "--",
    "\u2013": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u00a0": " ",
}
"""The characters a model reaches for, and what they become on the way out."""


def _ascii(text: str) -> str:
    """Text somebody else wrote, in the only alphabet the console can print.

    CLAUDE.md's standing rule -- *anything the CLI prints is ASCII* -- was
    written about this project's own output, where it is kept by writing `--`.
    `trainer log` is the first command that prints prose **this project did not
    write**: the report in the user's own words, and a model's clarifying
    question. This console runs at code page 437, and a run of it put
    `finch\u00e9` and an em dash on screen as replacement characters.

    Accents are dropped rather than transliterated, so `perch\u00e9` prints as
    `perche` -- which is how the user types it anyway, and is in every case
    better than `perch?`. **Presentation only**: `report` is stored verbatim,
    because it is what a hypothesis is formed from and a
    paraphrase is the system's reading of the user rather than the user.
    """
    import unicodedata

    folded = "".join(TYPOGRAPHY.get(character, character) for character in text)
    stripped = unicodedata.normalize("NFKD", folded)
    return "".join(
        character
        for character in stripped
        if character.isascii() and not unicodedata.combining(character)
    )


def _ask(question: str) -> str:
    """One clarifying question, at the terminal.

    `click.prompt` already asks again on an empty line. The loop is for a line
    of **spaces**, which it does not count as empty: that reaches the model as
    a turn saying nothing, and it fills the field in anyway -- which is the
    whole thing the question exists to prevent. Nothing here spins, because a
    closed stdin aborts the command rather than answering it.
    """
    while True:
        answer = str(click.prompt(f"? {_ascii(question)}", type=str)).strip()
        if answer:
            return answer


def _confirmed(question: Mapping[str, Any]) -> bool:
    """Whether the exclusion the model proposed is actually written.

    Asked only on the model path. A document given with `--from` carries the
    author's own proposal, and asking somebody to confirm the line they just
    typed is noise; a model proposing one has read it out of a passing remark,
    and an exclusion on `shoulder` takes 251 of the catalog's 582 exercises
    out of what may ever be prescribed.

    Declining writes the workout and no exclusion. The report keeps the user's
    words either way, so the remark that prompted it is still on the row.
    """
    click.echo(_ascii(str(question.get("ask", ""))))
    return bool(
        click.confirm(
            _ascii(
                f"Stop prescribing {question['granularity']} "
                f"'{question['value']}' until {question['retest_date']}?"
            ),
            default=False,
        )
    )


@main.command("state")
@click.option(
    "--cycles",
    "cycles",
    metavar="N",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="How many cycles back to count. A cycle is one rotation through the "
    "workouts you declared -- never a week.",
)
def state_command(cycles: int) -> None:
    """What has been trained, and what has not.

    Where the rotation is, what became of the workouts in the window, the
    volume accumulated on both axes, and the difference between what was
    planned and what was done. Read-only: nothing here closes an unreported
    workout or writes a number down.

    Every figure is recomputed from the performed workouts on each run. Change
    `cycle_length` in `training.toml` and the windows move on the next
    invocation -- there is no stored aggregate that could disagree with the
    file.
    """
    today = date.today().isoformat()
    with _opened() as connection:
        # Half the answer is the pattern axis, and an unenriched catalog
        # carries no patterns at all -- so the table would print as *nothing
        # performed* for a body that had trained. A state, named, with the
        # command that fixes it.
        _require_enrichment(connection)
        with reported():
            where = state.rotation(connection)
            covered = state.window(connection, cycles)
            adherence = state.adherence_history(connection, cycles)
            shortfalls = state.volume_deficit(connection, cycles)
            waiting = state.unreported(connection, today)
            trends = _trends(connection, shortfalls, cycles)

    click.echo(
        f"rotation: workout {where.position} of {where.cycle_length}, "
        f"cycle {where.cycle} -- {where.performed} workout(s) performed"
    )
    reach = f"from {covered.start}" if covered.start else "all of it"
    click.echo(f"window: {cycles} cycle(s), {covered.workouts} workouts, {reach}")

    click.echo("")
    if adherence.value is None:
        click.echo("adherence: nothing performed and nothing waiting in this window")
    else:
        click.echo(
            f"adherence: {adherence.value.performed} performed, "
            f"{adherence.value.unreported} unreported, "
            f"{adherence.value.unplanned} nobody planned"
        )

    for axis in state.AXES:
        _print_axis(axis, shortfalls, trends)

    # Not narrowed to the window, and the heading says so. The count in the
    # adherence line above is windowed -- it is about the workouts of those
    # cycles -- while a prescription nobody ever reported is worth naming
    # however long ago it was written, and the two numbers printed under one
    # word would otherwise contradict each other on the same screen.
    click.echo("")
    if not waiting:
        click.echo("unreported, whenever prescribed: none")
        return
    click.echo("unreported, whenever prescribed:")
    for found in waiting:
        click.echo(
            f"  workout {found.workout_id}, prescribed "
            f"{found.prescribed_on} ({found.days_ago} days ago)"
        )


def _trends(
    connection: sqlite3.Connection, shortfalls: tuple[state.Deficit, ...], cycles: int
) -> dict[tuple[str, str], str | None]:
    """The load trend for each key something was actually performed on.

    Not asked for the rest: a key with nothing performed has no loads to have
    a direction, and the question would come back unknown for a reason that is
    already visible in the row beside it.
    """
    return {
        (short.axis, short.key): _trend_of(connection, short, cycles)
        for short in shortfalls
        if short.performed > 0
    }


def _trend_of(
    connection: sqlite3.Connection, short: state.Deficit, cycles: int
) -> str | None:
    answer = state.volume_history(connection, short.axis, short.key, cycles)
    return None if answer.value is None else answer.value.load_trend


def _print_axis(
    axis: str,
    shortfalls: tuple[state.Deficit, ...],
    trends: dict[tuple[str, str], str | None],
) -> None:
    """One axis's table, largest deficit first.

    Both axes are printed even when one of them says nothing, because an axis
    that disappeared when it was empty would read as an axis nobody counts --
    and the whole argument for having two is that neither catches the other's
    failure (ADR-0001).
    """
    rows = [short for short in shortfalls if short.axis == axis]
    click.echo("")
    click.echo(f"volume per {axis}, in rounds performed:")
    if not rows:
        click.echo("  nothing planned and nothing performed in this window")
        return

    width = max(len(short.key) for short in rows)
    click.echo(f"  {'':{width}}  done  planned  deficit  loads")
    for short in rows:
        trend = trends.get((axis, short.key)) or "-"
        click.echo(
            f"  {short.key:{width}}  {short.performed:>4}  {short.planned:>7}  "
            f"{short.deficit:>7}  {trend}"
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
