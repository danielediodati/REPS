"""The measurement session 5 is judged on: thirty reports, scored by code.

`trainer eval --suite log` runs the hand-written set in
`docs/logging/eval-set.md` against the real logger graph. Two halves, and the
second is the one that matters:

- **The reports the sentence determines** are scored by equality on the
  document the agent emitted -- the exercise ids, the rounds, the loads, the
  provenance on every number -- and on the volume that document produces on
  both axes.
- **The reports it cannot answer** are scored on one bit: did it ask. A value
  written where the row declares one unknowable is **false confidence**, and
  it is weighted double, because a system that knows it does not know is the
  thing being measured.

**No model judges another model's output anywhere in this file**, which is
`evaluation.py`'s standing rule and does not bend for a labelled set. Every
check below reads a `Read` -- the document, and the clarifying questions the
run recorded -- and answers yes or no.

**The volume is the engine's own.** A scored document is resolved by
`log.to_performed` -- adherence and all -- and costed by `workouts.volume`,
which is migration 0007's arithmetic asked of a workout that was never
written. Nothing here counts rounds itself: *a round counts whole to the
pattern and to each primary muscle* is a rule that lives in a migration, and
this project has been wrong once already by keeping a second copy of something
the data already answers.

**Nothing here writes anywhere but into its own fixture.** That fixture is a
throwaway copy of the project database holding the four prescriptions and the
one load-history row the set declares, and building it is the only thing in
this module that calls a writer at all: scoring a run writes nothing, and the
logger graph never writes -- `logger.performed` does, from the door that
asked, and no door asks here. Thirty rows against the real state would leave
thirty performed workouts in the state the measurement is taken from -- which
is the mistake issue 1 moved plan persistence into the CLI to avoid.

**The fixture is a file, and `TRAINER_DB` points at it while the suite runs.**
That is not a detail. Every tool on the surface opens its own connection --
`tools.opened()`, by design, because the same definitions serve `trainer mcp`
to a client that has no connection to hand -- so the database the *agent*
reads is the one the environment names, and not the connection this module
holds. Handed a fixture nothing pointed at, the agent's first call comes back
*there is no workout 1*, it emits `workout_id: null`, and thirty rows fail
against a measurement that never showed the model what it was measuring. That
is what `prepared` is for, and it is why it and not `fixture` is what a caller
should reach for.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from trainer import evaluation, log, log_set, tools
from trainer.coach import checkpoints, logger, models
from trainer.coach import record as run_record
from trainer.engine import database, workouts

DOCUMENT = "document"
"""A column of the matrix: the emitted document against the one the row
expects, field by field."""

VOLUME = "volume"
"""A column of the matrix: what that document adds to each of the two axes,
which is the fact the rest of the engine reads and the reason a wrong id or a
wrong round count matters at all."""

ASKED = "asked"
"""A column of the matrix, for the must-ask half only: the run's `questions`
are not empty. A question is a tool call the graph answered with an
`interrupt()`, so this is a field and not a reading of the model's prose."""

CONFIDENT = "false confidence"
"""A column of the matrix: it did not ask, **and** it wrote something anyway.
The failure the twelve exist to catch, and the one weighted double."""

UNANSWERED = "non lo so"
"""What the scripted answerer says to every clarifying question.

**The same answer to all of them, on purpose.** The set records no answers:
each must-ask row states what the report leaves open and nothing more, so an
answer written here would be a fact nobody wrote down -- and it would change
the document the row is then scored on. Saying *I don't know* gives the model
nothing to fill a field from, which leaves the two halves measuring what they
were written to measure: whether the sentence was enough, and whether the
agent knew when it was not.

Italian, like the reports, because it is the same person answering.
"""

_HISTORY_ON = 14
"""Days before `today` the load-history workout is performed on. Far enough
back that it is not the workout a report would be about, and it is performed
*before* every prescription so that none of the four counts as unreported --
`workouts.awaiting` subtracts those, and a fixture where nothing is open would
brief every row with *no workout is waiting for a report*."""


@dataclass(frozen=True)
class Fixture:
    """The database the set is run against, and where its workouts landed.

    A copy, thrown away with the directory it was made in. `prescribed` maps the set's
    own names to the ids they were written under, because an expected document
    names `workout_id: 1` and *which row that is* is a fact about this
    fixture -- not something the runner should be trusting to insertion order
    twice.
    """

    connection: sqlite3.Connection
    path: Path
    """Where it lives. `TRAINER_DB` is pointed at this while the suite runs,
    because that is the database the agent's own tools open."""

    today: str
    prescribed: dict[str, int]
    prescribed_on: dict[str, str]

    def awaiting(self, row: log_set.Row) -> tuple[int | None, str | None]:
        """What the brief tells this row is waiting for a report.

        The prescription the row names, resolved to its id. A row that names
        none -- training nobody planned -- is briefed with whatever
        `workouts.awaiting` answers, which is what `trainer log` would put in
        front of a person who trained something else that day. That is the
        harder and the truthful brief: the row is testing that the agent reads
        *"oggi a casa"* as not being the open workout, and a brief saying
        nothing is open would not ask the question at all.
        """
        if row.prescription is not None:
            return (
                self.prescribed[row.prescription],
                self.prescribed_on[row.prescription],
            )
        open_workout = workouts.awaiting(self.connection)
        if open_workout is None:
            return None, None
        return open_workout.id, open_workout.prescribed_on


@contextmanager
def prepared(
    source: sqlite3.Connection, holds: log_set.LogSet
) -> Iterator[Fixture]:
    """The fixture, and the environment the agent's tools will read it through.

    **Both, together, or the measurement is of nothing.** The tools resolve
    their own connection from `TRAINER_DB` (`tools.opened`), so a fixture the
    environment does not name is a fixture the model cannot see. Pointed at
    here rather than by the caller because forgetting it does not fail loudly:
    it fails as thirty wrong documents.

    The variable is put back afterwards and the copy is deleted with the
    directory it was made in, so a run leaves nothing behind but its records.
    """
    directory = Path(tempfile.mkdtemp(prefix="reps-log-eval-"))
    previous = os.environ.get(database.DATABASE_ENV_VAR)
    try:
        where = fixture(source, holds, directory / "eval.sqlite")
        os.environ[database.DATABASE_ENV_VAR] = str(where.path)
        try:
            yield where
        finally:
            where.connection.close()
    finally:
        if previous is None:
            os.environ.pop(database.DATABASE_ENV_VAR, None)
        else:
            os.environ[database.DATABASE_ENV_VAR] = previous
        shutil.rmtree(directory, ignore_errors=True)


def fixture(
    source: sqlite3.Connection, holds: log_set.LogSet, path: Path
) -> Fixture:
    """The set's own database: this catalog, its four prescriptions, one load.

    A copy, so the project database is read once and never written -- and so
    the workouts the set needs can be the *only* workouts in it, which is what
    makes `workout_id: 1` mean P1 for everybody who runs this.

    A file rather than an in-memory database, because the agent's tools open
    the path `TRAINER_DB` names and an in-memory copy has no path to name.
    `prepared` is what points the environment at it.
    """
    connection = database.connect(path)
    try:
        prescribed, prescribed_on = _built(connection, source, holds)
    except BaseException:
        # Closed before it is thrown away, because on Windows an open SQLite
        # file cannot be deleted: `prepared` removes the directory with
        # `ignore_errors`, and a connection left open here would leave a copy
        # of the whole database in the temp directory on every failure.
        connection.close()
        raise
    return Fixture(
        connection=connection,
        path=path,
        today=holds.today,
        prescribed=prescribed,
        prescribed_on=prescribed_on,
    )


def _built(
    connection: sqlite3.Connection,
    source: sqlite3.Connection,
    holds: log_set.LogSet,
) -> tuple[dict[str, int], dict[str, str]]:
    """The copy, emptied of the user's state and filled with the set's.

    The two mappings are the fixture's own facts: which id each prescription
    was written under, and the day it was prescribed on.
    """
    source.backup(connection)
    connection.execute("PRAGMA foreign_keys = ON")

    # Whatever the real state holds is not this measurement's. An exclusion
    # left standing would take exercises out of what `search_exercises`
    # answers with, and a workout left in would take an id the set expects.
    connection.execute("DELETE FROM workouts")
    connection.execute("DELETE FROM exclusions")
    # **And the counter with them.** `workouts.id` is AUTOINCREMENT, so the
    # ids it hands out go on climbing past every row that was ever deleted:
    # against a database somebody has actually logged workouts in, the first
    # prescription written here would be workout 12 and every expected
    # document in the set -- each naming `workout_id: 1` -- would fail a
    # correct agent. Emptying the table is not emptying the sequence.
    connection.execute("DELETE FROM sqlite_sequence WHERE name = 'workouts'")

    # In the set's own order, so the ids come out in it: an expected document
    # naming `workout_id: 1` means the first prescription in the file, and the
    # set says so where it says what the runner has to set up. Dated backwards
    # from yesterday for the same reason -- the last one prescribed is the one
    # `workouts.awaiting` offers, and the set's rows are written against it.
    prescribed: dict[str, int] = {}
    prescribed_on: dict[str, str] = {}
    for index, prescription in enumerate(holds.prescriptions):
        on = _days_before(holds.today, len(holds.prescriptions) - index)
        prescribed[prescription.name] = workouts.record_prescribed(
            connection, prescription.blocks, on=on
        )
        prescribed_on[prescription.name] = on

    _history(connection, holds)
    return prescribed, prescribed_on


def _history(connection: sqlite3.Connection, holds: log_set.LogSet) -> None:
    """The one performed workout behind the set: a load, and a day it was on.

    `state.last_performed_load` has nothing to answer with otherwise, and the
    row that reports a jump is measuring a flag that cannot fire -- the set
    says so itself, in the section on what the runner has to set up.
    """
    workouts.record_performed(
        connection,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id=holds.history_exercise,
                        unit="reps",
                        amount=5,
                        amount_source="reported",
                        load_kg=holds.history_load_kg,
                        load_kg_source="reported",
                    ),
                ),
                rounds=3,
                rounds_source="reported",
                rest=180,
                rest_source="reported",
            ),
        ),
        on=_days_before(holds.today, _HISTORY_ON),
        report="the load history the log set is measured against",
    )


def _days_before(today: str, days: int) -> str:
    return (date.fromisoformat(today) - timedelta(days=days)).isoformat()


# -- what the set says it produces, before anything reaches a provider --------


def missing(connection: sqlite3.Connection, holds: log_set.LogSet) -> tuple[str, ...]:
    """Ids the set needs and this catalog does not have, before anything else.

    Checked against the database the fixture is copied *from*, and before it
    is built: writing a prescription for an exercise the catalog lost is a
    foreign key violation, and a traceback is a worse answer than a sentence
    naming the id.
    """
    unknown = log_set.unknown_exercises(connection, holds)
    if not unknown:
        return ()
    # CLAUDE.md's standing rule: a missing precondition is a state, not a
    # typo. Against a database with no catalog every id in the file is
    # missing, and *no such exercise* would be thirty lies.
    held = connection.execute("SELECT COUNT(*) AS n FROM exercises").fetchone()
    if not held["n"]:
        return ("the catalog is empty; run `trainer db import` first",)
    return tuple(
        f"the set names {exercise_id}, which this catalog does not have"
        for exercise_id in unknown
    )


def verify(where: Fixture, holds: log_set.LogSet) -> tuple[str, ...]:
    """Everything about the set that can be wrong without a model, checked.

    Thirty agent runs are minutes and money, and every one of them measures
    nothing if a row's expected document reports against the wrong workout or
    its volume figures are not the ones that document produces. Both are
    decidable here, for free.

    **The volumes are recomputed, not trusted.** Each expected document is
    resolved the way `trainer log` resolves one -- adherence filling in
    whatever the report left out -- and costed by the engine. A figure the
    author computed by hand and got wrong would otherwise fail a correct
    agent, three runs at a time, and read as a fault in the model.
    """
    problems = []
    for row in holds.unambiguous:
        assert row.expects is not None  # `unambiguous` is what says so
        expected_id = (
            None if row.prescription is None else where.prescribed[row.prescription]
        )
        if row.expects.workout_id != expected_id:
            # The row names a prescription in its heading and a `workout_id`
            # in its document, and the two have to be the same workout. They
            # are written in different places by hand, so nothing but this
            # says when one of them moved.
            problems.append(
                f"{row.name} is about {row.prescription or 'no prescribed workout'}, "
                f"which is workout {expected_id} here, and its expected document "
                f"reports against {row.expects.workout_id}"
            )
        try:
            pattern, muscle = _produced(where, row.expects)
        except _UNWRITABLE as error:
            problems.append(
                f"{row.name}: its expected document cannot be costed: {error}"
            )
            continue
        if pattern != row.pattern_volume:
            problems.append(
                f"{row.name} says it produces {_counts(row.pattern_volume)} on the "
                f"pattern axis; its own expected document produces {_counts(pattern)}"
            )
        if muscle != row.muscle_volume:
            problems.append(
                f"{row.name} says it produces {_counts(row.muscle_volume)} on the "
                f"muscle axis; its own expected document produces {_counts(muscle)}"
            )
    return tuple(problems)


def _counts(counts: dict[str, int] | None) -> str:
    if not counts:
        return "nothing"
    return ", ".join(f"{name} {rounds}" for name, rounds in sorted(counts.items()))


_UNWRITABLE = (
    log.LogError, log.LogRejected, workouts.WorkoutError, ValueError, sqlite3.Error
)
"""What a document nobody could cost comes back as.

An exercise id nothing in the catalog answers to is the reachable one --
`log.validate` has already refused the document for it, and the volume check
has to survive the same document rather than take the whole command down with
it.
"""


def _produced(
    where: Fixture, document: log.PerformedWorkout
) -> tuple[dict[str, int], dict[str, int]]:
    """The two axes this document moves, once adherence has filled it in.

    `to_performed` first, and that is the whole reason the figures are not
    read off the document: what a report leaves out was performed as
    prescribed, and it counts. Then `workouts.volume`, which is the engine's
    own arithmetic -- nothing here decides what a round is worth.
    """
    return workouts.volume(
        where.connection, log.to_performed(where.connection, document)
    )


@dataclass(frozen=True)
class Read:
    """One run of the logger graph, as this suite scores it.

    `evaluation.Ran` is the same idea for the planner: what the run produced,
    and what it cost. Neither suite reads the other's, and `evaluation.Costed`
    is the little both of them answer to.
    """

    record: Mapping[str, Any]
    document: log.PerformedWorkout
    questions: tuple[tuple[str, str], ...]
    refused: str | None
    seconds: float

    @property
    def written(self) -> str:
        """The run as it is written down -- ADR-0007's document, unchanged."""
        return run_record.document(self.record)

    @property
    def calls(self) -> list[Any]:
        return list(self.record["calls"])

    @property
    def input_tokens(self) -> int:
        return int(self.record["tokens"]["input"])

    @property
    def output_tokens(self) -> int:
        return int(self.record["tokens"]["output"])

    @property
    def dollars(self) -> float | None:
        dollars = self.record.get("dollars")
        return None if dollars is None else float(dollars)


# -- scoring one run ----------------------------------------------------------


def score(
    where: Fixture, row: log_set.Row, record: Read
) -> tuple[tuple[tuple[str, str], ...], int]:
    """What this run got wrong, and what the metric charges for it.

    All of it, never the first thing to fail: a run that emitted the wrong
    document *and* the wrong volume is a different thing from one that got the
    ids right and the rounds wrong, and stopping early would print them the
    same.
    """
    if row.must_ask:
        return _asked(row, record)
    return _wrote(where, row, record), 1


def _asked(
    row: log_set.Row, record: Read
) -> tuple[tuple[tuple[str, str], ...], int]:
    """One bit, and the weight that comes with getting it wrong.

    Held is `questions` not being empty. What it went on to emit afterwards is
    not scored -- the row has no answer to score against, which is the whole
    reason it is in this half.
    """
    if record.questions:
        return (), 1

    failures: tuple[tuple[str, str], ...] = (
        (ASKED, f"it asked nothing, and {row.unknowable}"),
    )
    wrote = _filled(record.document)
    if not wrote:
        # It asked nothing and claimed nothing: the deviation the report
        # states is simply missing from the document, which is wrong -- and
        # wrong once, because it did not put a number on what it could not
        # know. A document of nothing but `assumed` values is this case: it
        # says *as prescribed*, which is what adherence would have said.
        return failures, 1
    return (
        *failures,
        (CONFIDENT, f"it wrote {wrote}, and the row expects a question"),
    ), 2


_CLAIMED = ("reported", "asked")
"""The two provenances that are the model saying *this is what happened*.

`assumed` is the engine's, and it means *as prescribed*: a document whose
every value carries it claims nothing the prescription did not already say.
"""


def _filled(document: log.PerformedWorkout) -> str:
    """What the document claims **of its own**, in one clause, or nothing.

    Read off the provenance and never off the block count, and that is the
    difference between charging double and charging once. A block whose rounds
    and amounts are all `assumed` says *it went as prescribed* -- which is
    what `to_performed` fills in from an empty document anyway, so writing it
    out and leaving it out are the same document. Charging one of them twice
    and the other once would be weighting the shape of the emission rather
    than the confidence in it.

    `rpe` counts as a claim with no provenance of its own: it is recorded only
    when volunteered, so a number in that field is one the model heard or one
    it made up.
    """
    said = []
    for block in document.blocks:
        for item in block.items:
            if item.amount_source in _CLAIMED:
                said.append(f"{item.exercise_id} {item.amount} {item.unit}")
            if item.load_kg_source in _CLAIMED:
                said.append(f"{item.exercise_id} at {item.load_kg} kg")
        named = ", ".join(item.exercise_id for item in block.items)
        if block.rounds_source in _CLAIMED:
            said.append(f"{block.rounds} rounds of {named}")
        if block.rest_source in _CLAIMED:
            said.append(f"{block.rest} seconds rest after {named}")
        if block.rpe is not None:
            said.append(f"an rpe of {block.rpe}")
    if document.proposed_exclusion is not None:
        said.append(f"an exclusion on {document.proposed_exclusion.value}")
    return "; ".join(said)


def _wrote(
    where: Fixture, row: log_set.Row, record: Read
) -> tuple[tuple[str, str], ...]:
    """The unambiguous half: the document, and the volume it produces."""
    assert row.expects is not None  # `must_ask` is what says so

    failures = []
    if record.refused is not None:
        failures.append((evaluation.VALIDATOR, record.refused))
    difference = _difference(where, row.expects, record.document)
    if difference is not None:
        failures.append((DOCUMENT, difference))

    try:
        pattern, muscle = _produced(where, record.document)
    except _UNWRITABLE as error:
        failures.append((VOLUME, f"what it emitted cannot be costed: {error}"))
        return tuple(failures)
    if pattern != row.pattern_volume:
        failures.append((
            VOLUME,
            f"pattern axis {_counts(pattern)}, "
            f"expected {_counts(row.pattern_volume)}",
        ))
    if muscle != row.muscle_volume:
        failures.append((
            VOLUME,
            f"muscle axis {_counts(muscle)}, "
            f"expected {_counts(row.muscle_volume)}",
        ))
    return tuple(failures)


def _difference(
    where: Fixture, expected: log.PerformedWorkout, got: log.PerformedWorkout
) -> str | None:
    """Field by field on the workout that would be written, every difference rather than the first.

    Compared after `to_performed`, so the form of the emission is not scored:
    an untouched block written out with nothing said in it resolves to what
    leaving it out resolves to. What is scored is every number and where it
    came from -- a `reported` on a number nobody said is still a difference.

    Blocks are matched by the exercises in them, not by position: the order
    of a resolved workout is adherence's, reported blocks first.

    **Two fields are not compared by equality**, because the set says they are
    not: `proposed_exclusion.retest_date` is checked only for being after
    today -- which day to try a movement again is a judgement the document
    does not constrain -- and `why` is free prose.
    """
    said = []
    if got.workout_id != expected.workout_id:
        said.append(
            f"workout_id {got.workout_id}, expected {expected.workout_id}"
        )
    if got.report != expected.report:
        said.append(f"report is not the user's own words: {got.report!r}")
    try:
        wanted = _by_exercises(log.to_performed(where.connection, expected))
    except _UNWRITABLE as error:
        # `verify` refuses such a set before a pass starts; this is for a
        # caller that scores without it.
        said.append(f"the expected document cannot be resolved: {error}")
        return "; ".join(said)
    try:
        have = _by_exercises(log.to_performed(where.connection, got))
    except _UNWRITABLE as error:
        said.append(f"it cannot be resolved: {error}")
    else:
        for named in wanted.keys() - have.keys():
            said.append(f"block {named} is not in it")
        for named in have.keys() - wanted.keys():
            said.append(f"block {named} is in it and was not expected")
        for named in sorted(wanted.keys() & have.keys()):
            said.extend(
                f"block {named}: {why}" for why in _block(wanted[named], have[named])
            )
    said.extend(
        _exclusion(expected.proposed_exclusion, got.proposed_exclusion, where.today)
    )
    return "; ".join(said) or None


def _by_exercises(
    blocks: tuple[workouts.PerformedBlock, ...],
) -> dict[str, workouts.PerformedBlock]:
    """Each resolved block under the exercises in it, as a reader names it."""
    return {
        " + ".join(sorted(item.exercise_id for item in block.items)): block
        for block in blocks
    }


def _block(
    wanted: workouts.PerformedBlock, have: workouts.PerformedBlock
) -> list[str]:
    """One block against another. Its exercises are compared as a set.

    Order inside a block carries nothing -- a superset's two exercises are
    performed together, and the order they are written in is not a claim the
    document makes.
    """
    said = []
    for field, mine, theirs in (
        ("rounds", wanted.rounds, have.rounds),
        ("rounds_source", wanted.rounds_source, have.rounds_source),
        ("rest", wanted.rest, have.rest),
        ("rest_source", wanted.rest_source, have.rest_source),
        ("rpe", wanted.rpe, have.rpe),
    ):
        if mine != theirs:
            said.append(f"{field} {theirs!r}, expected {mine!r}")

    mine_items = {item.exercise_id: item for item in wanted.items}
    their_items = {item.exercise_id: item for item in have.items}
    for exercise_id in sorted(mine_items):
        said.extend(
            f"{exercise_id} {why}"
            for why in _item(mine_items[exercise_id], their_items[exercise_id])
        )
    return said


def _item(
    wanted: workouts.PerformedItem, have: workouts.PerformedItem
) -> list[str]:
    return [
        f"{field} {theirs!r}, expected {mine!r}"
        for field, mine, theirs in (
            ("unit", wanted.unit, have.unit),
            ("amount", wanted.amount, have.amount),
            ("amount_source", wanted.amount_source, have.amount_source),
            ("load_kg", wanted.load_kg, have.load_kg),
            ("load_kg_source", wanted.load_kg_source, have.load_kg_source),
        )
        if mine != theirs
    ]


def _exclusion(
    wanted: log.ProposedExclusion | None,
    have: log.ProposedExclusion | None,
    today: str,
) -> list[str]:
    if wanted is None and have is None:
        return []
    if wanted is None:
        assert have is not None
        return [f"it proposes an exclusion on {have.value}, and the row expects none"]
    if have is None:
        return [f"it proposes no exclusion, and the row expects one on {wanted.value}"]

    said = []
    if have.value != wanted.value:
        said.append(f"exclusion on {have.value}, expected {wanted.value}")
    if have.retest_date <= today:
        said.append(
            f"the exclusion is re-tested on {have.retest_date}, "
            f"which is not after {today}"
        )
    return said


# -- running them -------------------------------------------------------------


def run(
    where: Fixture,
    chosen: Sequence[log_set.Row],
    *,
    on: models.Chat,
    repetitions: int = evaluation.REPETITIONS,
    records: Path | None = None,
    budget: int = tools.CALL_BUDGET,
) -> evaluation.Report:
    """Every row, every repetition, against the logger graph.

    `repetitions` is `evaluation.REPETITIONS` for the reason the six
    situations run three times: a model is a distribution, and one green run
    measures nothing for a labelled row either.

    **A checkpointer in memory, and no archive.** The graph needs somewhere to
    hold a run that is waiting on a question; these threads are of no interest
    once the run is scored, and a pass is a measurement rather than thirty
    evenings somebody had.
    """
    into = records if records is not None else evaluation.records_path()
    graph = logger.build(
        on, budget=budget, checkpointer=InMemorySaver(serde=checkpoints.Declared())
    )
    return evaluation.measured(
        [row.name for row in chosen],
        repetitions,
        lambda at, attempt: _once(where, chosen[at], attempt, graph, into, budget),
    )


def _once(
    where: Fixture,
    row: log_set.Row,
    attempt: int,
    graph: logger.Logger,
    records: Path,
    budget: int,
) -> evaluation.Outcome:
    awaiting, prescribed_on = where.awaiting(row)
    try:
        read = _invoked(graph, where, row, awaiting, prescribed_on, budget)
    except Exception as error:
        if (quota := models.spent(error)) is not None:
            raise quota from error
        # Every way a provider can fail in the middle of a pass: no
        # credentials, a request it refused, a rate limit, a server that went
        # away. Caught broadly for the reason the plan suite catches broadly
        # -- the run lands in the *not run* column and counts against the
        # metric there, and a pass that lost its other twenty-nine rows to one
        # transport error would measure nothing.
        return evaluation.Outcome(row.name, attempt, error=str(error))

    written = evaluation.write(records, f"{row.name}-{attempt}", read.written)
    failures, weight = score(where, row, read)
    return evaluation.Outcome(row.name, attempt, failures, read, written, weight=weight)


def _invoked(
    graph: logger.Logger,
    where: Fixture,
    row: log_set.Row,
    awaiting: int | None,
    prescribed_on: str | None,
    budget: int,
) -> Read:
    """One run of the graph, answered the way the set answers, and timed.

    The clock is read around the whole invocation rather than summed from the
    record's per-node seconds: what a person waits for is the run, and the
    gaps between nodes are part of that wait.

    Every question is answered `UNANSWERED` and every proposed exclusion is
    declined: the run must reach its document, and the set records no answers
    to give it.
    """
    started = time.monotonic()
    thread: RunnableConfig = {"configurable": {"thread_id": f"log:{uuid4()}"}}
    given: Any = logger.starting(row.report, where.today, awaiting, prescribed_on)
    while True:
        final = graph.invoke(given, thread)
        waiting = final.get("__interrupt__")
        if not waiting:
            break
        question = waiting[0].value
        given = Command(
            resume=False if question.get("kind") == logger.EXCLUSION else UNANSWERED
        )
    document = final["document"]
    if document is None:
        # Nothing that parses as a document at all. The row is scored on what
        # was emitted, and there is nothing to score -- so it is reported the
        # way an unreachable provider is, under its own name.
        raise LogEvaluationError(final["refused"] or "it emitted no document")
    return Read(
        record=run_record.of(final, budget),
        document=document,
        questions=tuple(final.get("questions", ())),
        refused=final["refused"],
        seconds=time.monotonic() - started,
    )


def barred(report: evaluation.Report, holds: log_set.LogSet) -> evaluation.Report:
    """The pass measured against the two bars the set declares, one per half."""
    return replace(
        report,
        halves=(
            evaluation.Half(
                "unambiguous",
                frozenset(row.name for row in holds.unambiguous),
                holds.bar_unambiguous,
            ),
            evaluation.Half(
                "must ask",
                frozenset(row.name for row in holds.must_ask),
                holds.bar_must_ask,
            ),
        ),
    )


class LogEvaluationError(RuntimeError):
    """A run that produced nothing to score. Not a failed invariant: a run that did not happen."""


# -- the matrix ---------------------------------------------------------------


def render(
    report: evaluation.Report, chosen: Sequence[log_set.Row]
) -> list[str]:
    """Two matrices, the number, and what it cost. ASCII.

    Two rather than one because the halves are scored on different things, and
    a single table would need four columns that are blank for half its rows --
    which reads as *this was not checked* rather than *this does not apply*.
    """
    determined = [row for row in chosen if not row.must_ask]
    open_ended = [row for row in chosen if row.must_ask]

    lines: list[str] = []
    if determined:
        lines.append(f"{len(determined)} the report determines")
        lines.extend(
            evaluation.matrix(
                report,
                [row.name for row in determined],
                [DOCUMENT, VOLUME, evaluation.VALIDATOR, evaluation.NOT_RUN],
            )
        )
        lines.append("")
    if open_ended:
        lines.append(f"{len(open_ended)} that must make it ask")
        lines.extend(
            evaluation.matrix(
                report,
                [row.name for row in open_ended],
                [ASKED, CONFIDENT, evaluation.NOT_RUN],
            )
        )
        lines.append("")

    lines.extend(
        evaluation.failures(report, {row.name: row.describes for row in chosen})
    )
    lines.append("")
    lines.extend(_notes(report, chosen))
    lines.extend(evaluation.totals(report, "held the outcome its row declared"))
    return lines


def _notes(
    report: evaluation.Report, chosen: Sequence[log_set.Row]
) -> list[str]:
    """Two facts that are not failures, and are worth the line they take.

    **Questions asked where the report determined the answer.** They are not
    scored -- the row is scored on the document -- but an agent that asks
    about everything would hold all twelve of the must-ask half for the wrong
    reason, and this is the number that says whether that is what happened.

    **Rows the author marked `?`.** The set says where it doubts itself; a
    failing row that carries the marker is a row to go and re-read before it
    is a bug in the agent.
    """
    determined = {row.name for row in chosen if not row.must_ask}
    asked = sum(
        1
        for outcome in report.outcomes
        if outcome.case in determined
        and isinstance(outcome.record, Read)
        and outcome.record.questions
    )
    ran = sum(1 for outcome in report.outcomes if outcome.case in determined)

    lines = []
    if asked:
        lines.append(
            f"{asked} of {ran} runs of a report that determines its answer "
            f"asked a question anyway; not scored, and not free either"
        )
    doubted = [row.name for row in chosen if row.uncertain]
    if doubted:
        lines.append(
            f"marked `?` in the set, and doubted by its author: "
            f"{', '.join(doubted)}"
        )
    if lines:
        lines.append("")
    return lines
