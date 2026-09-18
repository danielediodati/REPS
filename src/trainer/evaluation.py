"""The measurement session 4 is judged on: six situations, six invariants, 100%.

`trainer eval` runs TRAINER.md's six hand-written, deliberately nasty
situations against the real agent and checks six properties over every run.
Not *good plan / bad plan* -- properties that must hold always, **decided by
code**. For a decidable constraint a validator always beats an agent judge:
it costs nothing, it is not persuadable, and it catches all of them rather
than most.

**No model judges another model's output anywhere in this file.** Every check
below reads the run record and the plan and answers yes or no.

**Not under `pytest`.** The suite takes sockets and credentials away from
every test on purpose, and this is the one thing in the project that needs
both. The *checks* are pure functions over a record and are covered there; the
*running* is this command's own, and `conftest.py` is left alone.

**Every run counts.** A model is a distribution and one green run is not a
measurement, so each situation runs a declared number of times. The bar stays
at 100% across all of them: anything below is a bug to go and read, not a
tuning knob.

**The runs are the planner graph's** (ADR-0004), one `invoke` each, and what a
run leaves behind is ticket 03's record: the attempts, the rule that refused
each of them, the calls, the tokens and what every node cost. The checks below
read that record and the plan the graph held; nothing here asks a model what it
did.

**The database is named in the environment.** Every tool on the surface opens
its own connection from `TRAINER_DB` (`tools.opened`), so the database the
*model* reads is the one the environment names and not the connection this
module holds. `pointed_at_the_database` is what makes those the same file, and
CLAUDE.md asks for it because a fixture nothing points at is invisible to the
agent.
"""

from __future__ import annotations

import dataclasses
import math
import os
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from trainer import tools
from trainer import plan as plans
from trainer.coach import models, planner
from trainer.coach import record as run_record
from trainer.engine import admissible, catalog, database, duration, home, muscle_groups

REPETITIONS = 3
"""How many times each situation runs, unless told otherwise.

Three because a model is a distribution: one run measures nothing, two cannot
tell a coin from a certainty, and every run past that costs a full agent loop
against a rate-limited tier. `--repetitions` raises it when the question is
worth the wait.
"""

VALIDATOR = "validator"
"""A column of the matrix, not an invariant: the door refused a plan for a
reason none of the six names. Not reachable today, and reported rather than
swallowed, because the validator and the invariants disagreeing is the
interesting thing."""

NOT_RUN = "not run"
"""A column of the matrix: runs that never reached the provider. They hold
nothing and they count against the metric, but they are not a failure of any
invariant either."""

RECORDS_ENV_VAR = "TRAINER_EVAL_RUNS"
"""Overrides where the records are written, the way `TRAINER_DB` does for the database."""

DEFAULT_RECORDS_NAME = "eval-runs"


def records_path() -> Path:
    """Where each run's record is written. A failure names the file, because
    *invariant 3 failed* is a fact and the record is the only thing that says
    why."""
    override = os.environ.get(RECORDS_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return home.inside(DEFAULT_RECORDS_NAME)

TURNED_DOWN_BECAUSE = "I don't feel like it"
"""What the user says when they turn down the first plan of the after-a-refusal situation."""


@dataclass(frozen=True)
class Situation:
    """One of TRAINER.md's adverse situations, as data.

    `describes` is the sentence from the document, kept beside the request so
    that reading this file tells you what the situation is *for* -- a request
    with six groups and thirty minutes does not announce itself as *the
    contradictory one*.
    """

    name: str
    describes: str
    request: plans.Request
    after_a_refusal: bool = False
    """Situation 5. The measured run is the second: the first exists only to
    have something to turn down, and its cost counts towards the pass."""


def situations(connection: sqlite3.Connection) -> tuple[Situation, ...]:
    """The six, built against this catalog.

    A seventh is a row here. The two that read the catalog do so rather than
    naming ids in the source: a hand-written list of sixty exercises is a
    vocabulary copy, and this project has been wrong that way once already.
    """
    everything = muscle_groups.groups()
    bodyweight = plans.Request(equipment=("body only",), budget_min=15)

    return (
        Situation(
            name="no-equipment",
            describes="15 minutes, no equipment",
            request=bodyweight,
        ),
        Situation(
            name="half-refused",
            describes="half the catalog out on stated preferences",
            request=plans.Request(
                equipment=("body only",),
                budget_min=30,
                groups=("core",),
                preferences=_half_of(connection, ("body only",), 30, ("core",)),
            ),
        ),
        Situation(
            name="contradictory",
            describes="30 minutes, but I want to train everything",
            request=plans.Request(
                equipment=("body only",), budget_min=30, groups=everything
            ),
        ),
        Situation(
            name="no-history",
            describes="the previous report ambiguous or missing",
            request=plans.Request(
                equipment=("body only",), budget_min=30, groups=("legs", "core")
            ),
        ),
        Situation(
            name="refused",
            describes="the user refuses the plan and it proposes again",
            request=plans.Request(
                equipment=("body only",), budget_min=30, groups=("legs", "core")
            ),
            after_a_refusal=True,
        ),
        Situation(
            name="preference-against-the-split",
            describes="a preference in conflict with what the workout must train",
            request=plans.Request(
                equipment=("body only",),
                budget_min=30,
                groups=("legs",),
                preferences=_half_of(connection, ("body only",), 30, ("legs",)),
            ),
        ),
    )


def _half_of(
    connection: sqlite3.Connection,
    equipment: tuple[str, ...],
    minutes: int,
    groups: tuple[str, ...],
) -> tuple[str, ...]:
    """Half the exercises this request leaves standing, by id.

    Read from the catalog rather than written out, so it stays half of
    whatever the catalog holds. Every other one, not the first half, because
    the set is ordered by name and taking a prefix would refuse whole families
    of movement while leaving others untouched -- a different situation from
    the one TRAINER.md describes.
    """
    standing = admissible.admissible_set(connection, [], equipment, minutes, groups)
    return tuple(exercise.id for exercise in standing[::2])


# -- one run of the graph -----------------------------------------------------


@dataclass(frozen=True)
class Ran:
    """One run of the planner graph: ticket 03's record, and what it cost.

    The record is what is written to disk **and** what every number the matrix
    reports is read off, so the file a failure names and the row above it
    cannot disagree.

    The plan and the request are kept as the objects the graph held rather
    than parsed back out of the record: the invariants validate them, and a
    round trip through JSON would be measuring the round trip.
    """

    record: Mapping[str, Any]
    request: plans.Request
    """What the graph planned against: the situation's request with today's
    standing exclusions and the declared cap folded in, which is the space the
    model was actually shown."""

    plan: plans.WorkoutPlan | None
    """`None` when nothing it emitted parses as a plan at all."""

    spent: int
    """What the run actually paid, which is not the budget: a turn's calls are
    answered as a batch, so the last one can carry the count past it."""

    seconds: float

    @property
    def document(self) -> str:
        """The record as it is written down -- ticket 03's, unchanged."""
        return run_record.document(self.record)

    @property
    def attempts(self) -> int:
        """Plans emitted, which is one more than the number of refusals it read."""
        return len(self.record["attempts"])

    @property
    def refused(self) -> tuple[tuple[str, str], ...]:
        """What refused the last attempt, by rule and by sentence, or nothing when it passed."""
        attempts = self.record["attempts"]
        if not attempts:
            return ()
        return tuple(
            (violation["rule"], violation["says"])
            for violation in attempts[-1]["violations"]
        )

    @property
    def calls(self) -> list[Any]:
        """Every tool call the run made, as the record holds them."""
        return list(self.record["calls"])

    @property
    def input_tokens(self) -> int:
        return int(self.record["tokens"]["input"])

    @property
    def output_tokens(self) -> int:
        return int(self.record["tokens"]["output"])


# -- the six invariants -------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    name: str
    holds: Callable[
        [sqlite3.Connection, Situation, Ran, tuple[plans.Violation, ...]],
        str | None,
    ]
    """`None` when it holds, and the sentence saying how it failed otherwise.

    The violations are handed in rather than asked for: they cost three
    queries and a costing pass, and every invariant that reads them would
    otherwise run that again.
    """


def _terminates(
    connection: sqlite3.Connection,
    situation: Situation,
    ran: Ran,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """A plan came out, inside the bounds the graph runs under.

    **A run that never returned is not measured here.** It has no record to
    read, so it arrives as `Outcome.error`, shows in the *not run* column and
    counts against the metric there. What this checks is a run that did
    return: that it emitted a plan with something in it, and that it stopped
    where it was built to stop.

    **The call budget is reported rather than checked**, and that moved here
    from the old loop deliberately. Tools stop being offered the moment the
    budget is crossed, but a turn's calls are answered as a whole batch, so a
    turn asking for seven at once ends at *16 of 12* -- observed on Groq in
    ticket 04. Overshooting is therefore not a fault to fail a run for; what
    it is, is a number worth seeing, and `numbers` prints what was actually
    spent beside every run.
    """
    if ran.plan is None:
        return "it emitted nothing that parses as a plan"
    if not ran.plan.blocks:
        return "it emitted a plan with no blocks in it"
    if ran.attempts > planner.ATTEMPTS:
        return (
            f"it emitted {ran.attempts} plans against a bound of "
            f"{planner.ATTEMPTS} attempts"
        )
    return None


def violations_of(
    connection: sqlite3.Connection, situation: Situation, ran: Ran
) -> tuple[plans.Violation, ...]:
    """Every rule this run's plan breaks, decided once for all the invariants that read one.

    The rules themselves, not a second reading of them: read twice, the day
    the two disagree the run is measured against whichever one is wrong.
    """
    if ran.plan is None:
        return (
            plans.Violation(plans.SHAPE, "it emitted nothing that parses as a plan"),
        )
    try:
        blocks = plans.to_blocks(ran.plan)
        return plans.validate(connection, blocks, situation.request, ran.plan)
    except (plans.PlanError, duration.DurationError) as error:
        return (plans.Violation(plans.SHAPE, f"it cannot be costed: {error}"),)


def _says(violations: tuple[plans.Violation, ...], *rules: str) -> str | None:
    """What the first of these rules that fired says, or `None` when none did."""
    for violation in violations:
        if violation.rule in rules:
            return violation.says
    return None


def _respects_the_time(
    connection: sqlite3.Connection,
    situation: Situation,
    ran: Ran,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """Estimated duration inside the declared budget. Never trimmed to fit.

    A plan the clock could not be read on at all fails here rather than
    passing: `validate` skips the budget when an exercise is written twice or
    an id is not in the catalog, and *no violation* would read as *it fits*.
    """
    return _says(violations, plans.BUDGET, plans.DUPLICATES, plans.ADMISSIBLE, plans.SHAPE)


def _respects_the_constraints(
    connection: sqlite3.Connection,
    situation: Situation,
    ran: Ran,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """Nothing outside the admissible set.

    The set is asked for against the request rather than read back off
    whatever the model was handed mid-loop, which would measure the loop's
    bookkeeping instead of the plan.
    """
    return _says(violations, plans.ADMISSIBLE)


def _respects_the_preferences(
    connection: sqlite3.Connection,
    situation: Situation,
    ran: Ran,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """Nothing the user refused -- and if it proposes one again, it says so.

    Both halves, because TRAINER.md states both. Proposing one with the reason
    attached is allowed and is the behaviour the invariant wants; proposing one
    in silence is the failure.
    """
    return _says(violations, plans.PREFERENCES)


def _todays_equipment_only(
    connection: sqlite3.Connection,
    situation: Situation,
    ran: Ran,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """Every exercise is one today's equipment reaches.

    Checked apart from the admissible set although the set already filters on
    it: this is its own invariant in TRAINER.md, and a fault in the filter
    would otherwise pass both.
    """
    allowed = set(situation.request.equipment)
    wrong = []
    for exercise_id in sorted(_prescribed(ran)):
        found = catalog.exercise(connection, exercise_id)
        if found is None:
            wrong.append(f"{exercise_id} (no such exercise)")
        elif found.equipment not in allowed:
            wrong.append(f"{exercise_id} needs {found.equipment}")
    if wrong:
        return "; ".join(wrong)
    return None


def _does_not_degenerate(
    connection: sqlite3.Connection,
    situation: Situation,
    ran: Ran,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """It uses the space it was given.

    **The definition, because this is the one invariant that is not already a
    sentence about the admissible set or the clock.** ADR-0001 settles it: the
    volume deficit is measured on two axes, and degeneration is what each axis
    is for.

    - **The muscle axis answers *am I touching this at all*.** Every group the
      workout was asked to train has at least one exercise whose *primary*
      muscles fall in it. A leg day of calf raises fails; the pattern axis
      alone would not catch it.
    - **The pattern axis answers *am I balanced*.** The plan uses more than one
      movement pattern. An arm workout made entirely of curls is the case
      ADR-0001 names, and it is invisible on the muscle axis because biceps,
      triceps and forearms are one bucket there.

    **Both halves are checked against what was actually available**, never
    against an absolute. If the admissible set offers nothing for a group, or
    holds only one movement pattern, then a plan that reflects that is not
    degenerate -- it is the only honest answer, and an invariant that failed it
    would be measuring the catalog rather than the agent. That escape clause is
    what makes 100% a bar the agent can clear.

    What is deliberately **not** here: a ratio of compound to isolation work.
    Against this catalog the arms group is 70 isolation exercises to 12
    compound, so any majority-compound rule fails a correct arm day -- and in a
    measurement whose bar is 100%, an invariant that can be wrong is worse than
    one that is weak.
    """
    request = situation.request
    prescribed = _prescribed(ran)

    available = admissible.admissible_set(
        connection,
        request.exclusions,
        request.equipment,
        request.budget_min,
        request.groups,
    )

    untouched = []
    for group in request.groups:
        muscles = set(admissible.muscles_of([group]))
        if not any(set(e.primary_muscles) & muscles for e in available):
            continue  # nothing today could have trained it
        trained = any(
            set(e.primary_muscles) & muscles
            for e in available
            if e.id in prescribed
        )
        if not trained:
            untouched.append(group)
    if untouched:
        return f"it trains nothing for {', '.join(untouched)}"

    offered = {
        row["movement_pattern"]
        for row in connection.execute(
            "SELECT DISTINCT movement_pattern FROM exercises WHERE id IN "
            f"({','.join('?' for _ in available)})",
            [exercise.id for exercise in available],
        )
    } if available else set()
    if len(offered) > 1:
        used = {
            row["movement_pattern"]
            for row in connection.execute(
                "SELECT DISTINCT movement_pattern FROM exercises WHERE id IN "
                f"({','.join('?' for _ in prescribed)})",
                sorted(prescribed),
            )
        } if prescribed else set()
        if len(used) < 2:
            only = ", ".join(sorted(str(pattern) for pattern in used)) or "nothing"
            return f"every exercise is {only}, out of {len(offered)} patterns available"
    return None


INVARIANTS = (
    Invariant("terminates", _terminates),
    Invariant("time", _respects_the_time),
    Invariant("constraints", _respects_the_constraints),
    Invariant("preferences", _respects_the_preferences),
    Invariant("equipment", _todays_equipment_only),
    Invariant("not degenerate", _does_not_degenerate),
)


def _prescribed(ran: Ran) -> set[str]:
    """Every exercise the plan names, and nothing at all when there is no plan to read."""
    if ran.plan is None:
        return set()
    return {item.exercise_id for block in ran.plan.blocks for item in block.items}


# -- running them -------------------------------------------------------------


class Costed(Protocol):
    """What the cost lines read off a run, whichever graph made it.

    A protocol and not either suite's class, because this module is what both
    report through: named as one of them, the other would be a union that
    grows with every graph.
    """

    @property
    def calls(self) -> list[Any]: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...


@dataclass(frozen=True)
class Outcome:
    """One run, and what held.

    `case` is what the run was of -- one of the six situations here, one of
    the thirty reports in `log_evaluation`. Both suites keep their outcomes in
    this shape because both are *a model run many times and checked by code*,
    and a second copy of the counting would be a second answer to *what
    percentage held*.
    """

    case: str
    attempt: int
    failures: tuple[tuple[str, str], ...] = ()
    record: Costed | None = None
    """One run of the planner graph here, one of the logger graph in
    `log_evaluation`. Both answer what this report reads of them -- the calls
    and the tokens -- and neither suite reads the other's."""

    written: Path | None = None
    error: str | None = None
    """The run never finished -- no credentials, the provider refusing, a rate
    limit. It holds no invariant, because a measurement that quietly skipped
    the runs it could not make would report on the easy ones. It is not a
    *failure* of any of them either, which is why the matrix gives it a column
    of its own rather than blanking the ones it says nothing about."""

    also: tuple[Costed, ...] = ()
    """Runs made to set this one up and not measured -- the plan that gets
    turned down, on the refusal situation. They hold no invariants and they
    are not counted towards the metric, but they were paid for, so they count
    towards the cost."""

    weight: int = 1
    """How much this run counts **against** the metric when it fails.

    One everywhere except the failure ROADMAP.md § Session 5 and TRAINER.md's
    golden-set rules single out: a report that could not be answered, answered
    confidently anyway. It is weighted double because it is the error the
    whole must-ask half exists to detect -- a system that knows it does not
    know is the thing being measured, and a wrong value written without
    hesitation costs more than a question left unasked. A run that held is
    never weighted: the weight is a cost, and nothing was paid.
    """

    @property
    def held(self) -> bool:
        return self.error is None and not self.failures

    @property
    def records(self) -> tuple[Costed, ...]:
        return (*self.also, *((self.record,) if self.record else ()))


@dataclass(frozen=True)
class Report:
    outcomes: tuple[Outcome, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def held(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.held)

    @property
    def against(self) -> int:
        """What the percentage is out of, once weights are counted.

        Runs, plus one more for every failure weighted double. `total` stays
        the number of runs, because *how many runs held* and *what the metric
        is out of* are two different facts and the report prints both. With
        every weight at one -- which is every run of the six situations --
        the two are the same number and the figure is unchanged.
        """
        return sum(
            outcome.weight if not outcome.held else 1 for outcome in self.outcomes
        )

    @property
    def percentage(self) -> float:
        return 100.0 * self.held / self.against if self.against else 0.0

    @property
    def passed(self) -> bool:
        """100%, and at least one run. An empty pass is not a pass."""
        return self.total > 0 and self.held == self.total

    @property
    def calls(self) -> int:
        return sum(len(r.calls) for o in self.outcomes for r in o.records)

    @property
    def input_tokens(self) -> int:
        """Every run that was paid for, measured or not.

        The refusal situation makes two: the plan that gets turned down and
        the one that answers it. Only the second is measured; both are on the
        bill, and this number is what a pass is budgeted against."""
        return sum(r.input_tokens for o in self.outcomes for r in o.records)

    @property
    def output_tokens(self) -> int:
        return sum(r.output_tokens for o in self.outcomes for r in o.records)


def check(
    connection: sqlite3.Connection, situation: Situation, ran: Ran
) -> tuple[tuple[str, str], ...]:
    """Every invariant against one run. All of them, not the first to fail.

    A run that breaks three properties is a different thing from one that
    breaks one, and stopping at the first would hide the difference behind an
    identical line in the matrix.
    """
    failures = []
    violations = violations_of(connection, situation, ran)
    for invariant in INVARIANTS:
        why = invariant.holds(connection, situation, ran, violations)
        if why is not None:
            failures.append((invariant.name, why))
    return tuple(failures)


@contextmanager
def pointed_at_the_database() -> Iterator[Path]:
    """`TRAINER_DB` naming the database this pass measures, for as long as it runs.

    The tools open their own connection from that variable, so the database
    the *model* reads is the one the environment names. Left to the default
    the two are the same file only because both fell back to the home, and a
    coincidence is not what CLAUDE.md's standing rule asks for -- a fixture
    nothing points at is invisible to the agent, and the pass measures a model
    answering *there is no such workout* thirty times.

    Put back afterwards, because a command that moved it would change where
    every later one in the same process reads.
    """
    path = database.database_path().resolve()
    previous = os.environ.get(database.DATABASE_ENV_VAR)
    os.environ[database.DATABASE_ENV_VAR] = str(path)
    try:
        yield path
    finally:
        if previous is None:
            os.environ.pop(database.DATABASE_ENV_VAR, None)
        else:
            os.environ[database.DATABASE_ENV_VAR] = previous


def run(
    connection: sqlite3.Connection,
    chosen: Sequence[Situation],
    *,
    on: models.Chat,
    repetitions: int = REPETITIONS,
    records: Path | None = None,
    budget: int = tools.CALL_BUDGET,
) -> Report:
    """Every situation, every repetition, against the planner graph.

    `on` is the model the graph runs on, handed in rather than built here:
    nothing in this module reaches a provider on its own, and the caller is
    what decides which one is being measured.

    The graph is compiled once. A run is one `invoke` of it and carries
    everything it knows in its own state, so a second compilation per run
    would buy nothing.

    **A checkpointer in memory, and no resume.** The graph stops at the plan
    and waits for somebody to accept it (ADR-0005), which needs somewhere to
    wait; nothing here answers, so no run reaches the node that writes. That is
    what keeps a measurement of eighteen runs from leaving eighteen phantom
    prescribed workouts in the state it is measuring. In memory because these
    threads are of no interest once the run is scored.

    **And no archive.** A pass is a measurement, not an evening: its runs in
    the home would be the history session 10 reads to ask how many plans an
    evening takes. The records this suite keeps are its own, under `records`.
    """
    where = records if records is not None else records_path()
    graph = planner.build(on, budget=budget, checkpointer=InMemorySaver())
    outcomes = []
    for situation in chosen:
        for attempt in range(1, repetitions + 1):
            outcomes.append(
                _once(connection, situation, attempt, graph, budget, where)
            )
    return Report(tuple(outcomes))


NOTHING_TO_REFUSE = (
    "the plan that was to be turned down did not parse, so there was nothing "
    "to refuse and the second run would not have been this situation"
)
"""Why the refusal situation can fail before it starts. See `_once`."""


def _once(
    connection: sqlite3.Connection,
    situation: Situation,
    attempt: int,
    graph: planner.Planner,
    budget: int,
    records: Path,
) -> Outcome:
    request = situation.request
    also: list[Ran] = []
    try:
        if situation.after_a_refusal:
            # Two turns, not a conversation. The first plan exists only to be
            # turned down, and what is measured is what comes back after --
            # but it was paid for, so it is kept and it counts towards cost.
            first = _invoked(graph, request, budget)
            also.append(first)
            write(records, f"{situation.name}-{attempt}-turned-down", first.document)
            if first.plan is None:
                # Nothing came back that could be turned down. With no
                # refusals to carry, `brief` says nothing about one at all --
                # not even the user's reason, which travels with the plan --
                # so the second run is an ordinary planning run. Measured as
                # situation 5 it would put a green row under a situation that
                # never happened, which at a bar of 100% is the one failure
                # this file exists to make impossible.
                return Outcome(
                    situation.name, attempt, error=NOTHING_TO_REFUSE, also=tuple(also)
                )
            request = dataclasses.replace(
                request,
                refusals=plans.turned_down((), first.plan, TURNED_DOWN_BECAUSE),
            )
        ran = _invoked(graph, request, budget)
    except Exception as error:
        # Every way a provider can fail in the middle of a pass: no
        # credentials, a request it refused, a rate limit, a server that went
        # away. Caught broadly on purpose -- the run lands in the *not run*
        # column and counts against the metric there, and a pass that lost its
        # other seventeen runs to one transport error would measure nothing.
        return Outcome(situation.name, attempt, error=str(error), also=tuple(also))

    written = write(records, f"{situation.name}-{attempt}", ran.document)

    # Checked against the request the graph actually planned against, not the
    # one the situation declared: `constraining_today` folds the standing
    # exclusions and the declared cap into it on the first turn, and measuring
    # the other one would measure a space the model was never shown.
    failures = check(
        connection, dataclasses.replace(situation, request=ran.request), ran
    )
    if ran.refused and not failures:
        # The validator refused a plan every invariant says is fine. The two
        # disagreeing is the interesting thing, so it is recorded rather than
        # swallowed -- under its own name, and `VALIDATOR` is a column of the
        # matrix so it cannot be a failure nothing shows.
        failures = tuple((VALIDATOR, f"{rule}: {says}") for rule, says in ran.refused)
    return Outcome(situation.name, attempt, failures, ran, written, also=tuple(also))


def _invoked(graph: planner.Planner, request: plans.Request, budget: int) -> Ran:
    """One run of the graph, and the wall time somebody waited for it.

    The clock is read around the whole invocation rather than summed from the
    record's per-node seconds: what a person waits for is the run, and the
    gaps between nodes are part of that wait.
    """
    started = time.monotonic()
    thread: RunnableConfig = {"configurable": {"thread_id": f"eval:{uuid4()}"}}
    final = graph.invoke(planner.starting(request), thread)
    return Ran(
        record=run_record.of(final, budget),
        request=final["request"],
        plan=final["plan"],
        spent=final.get("spent", 0),
        seconds=time.monotonic() - started,
    )


def write(records: Path, name: str, document: str) -> Path:
    """One record to disk. The directory is made here rather than when the run
    starts, so a pass that never reaches a provider leaves nothing behind --
    the suite invokes this command to check it stops at the credentials state,
    and an empty `eval-runs/` in the repo after every `pytest` is litter."""
    records.mkdir(parents=True, exist_ok=True)
    written = records / f"{name}.json"
    written.write_text(document, encoding="utf-8")
    return written


# -- the matrix ---------------------------------------------------------------


def render(report: Report, chosen: Sequence[Situation]) -> list[str]:
    """The situation-by-invariant matrix, the number, and what it cost. ASCII.

    One column per invariant, plus `validator` -- a refusal no invariant names
    -- plus `not run`. The last is its own column rather than a dash across
    the row: a rate limit on the second of three repetitions says nothing
    about the two that did run, and blanking their verdicts would hide real
    failures behind an unrelated transport error.
    """
    columns = [invariant.name for invariant in INVARIANTS] + [VALIDATOR, NOT_RUN]
    cases = [situation.name for situation in chosen]
    return [
        *matrix(report, cases, columns),
        "",
        "what the planner spent getting there:",
        *numbers(report, cases),
        "",
        *failures(report),
        "",
        *totals(report, "held every invariant"),
    ]


PLANNER_COLUMNS = ("attempts", "seconds", "tool calls", "refused by")
"""What the graph itself costs, which the invariants say nothing about.

*It held every invariant* and *it held them on the third attempt, after two
refusals, in four minutes* are different answers to whether this model can
plan on this laptop, and only the second one decides whether the session was
built on the right model.
"""


def numbers(report: Report, cases: Sequence[str]) -> list[str]:
    """One row per situation: what each run took, and the rule that refused it.

    **Every run's own figure, never an average.** A situation that reached a
    valid plan first time twice and on the third attempt once is a different
    fact from one that always needs two, and a mean prints them the same --
    the argument the matrix makes for `2 failed` over `failed`.

    The tool calls are what was actually **spent**, not the budget: a turn's
    calls are answered as a whole batch, so the last one can carry the count
    past the budget, and the number that means anything is the one that was
    paid for.

    `refused by` names the rules still standing after the last attempt. Empty
    is the normal answer, and a rule here with an `ok` row above it is the
    validator and the invariants disagreeing -- which `VALIDATOR` is a column
    for.
    """
    width = max((len(case) for case in cases), default=0) + 2
    widths = [max(12, len(name) + 2) for name in PLANNER_COLUMNS]

    lines = [
        "".ljust(width)
        + "  ".join(f"{name:^{size}}" for name, size in zip(PLANNER_COLUMNS, widths))
    ]
    for case in cases:
        ran = [
            outcome.record
            for outcome in report.outcomes
            if outcome.case == case and isinstance(outcome.record, Ran)
        ]
        cells = (
            ", ".join(str(one.attempts) for one in ran) or "-",
            ", ".join(f"{one.seconds:.0f}" for one in ran) or "-",
            ", ".join(str(one.spent) for one in ran) or "-",
            ", ".join(sorted({rule for one in ran for rule, _ in one.refused})) or "-",
        )
        lines.append(
            case.ljust(width)
            + "  ".join(f"{cell:^{size}}" for cell, size in zip(cells, widths))
        )
    return lines


def matrix(report: Report, cases: Sequence[str], columns: Sequence[str]) -> list[str]:
    """One row per case, one column per check, `N failed` in the cells.

    Shared with the log suite, which has different cases and different columns
    and the same question to answer: *of the runs of this case, how many broke
    this check*. The distribution is the point -- a cell saying `1 failed` out
    of three runs is a different fact from one saying `3 failed`, and a
    pass/fail cell would print them the same.
    """
    width = max((len(case) for case in cases), default=0) + 2
    # Each column as wide as it needs to be, and no narrower than the number
    # under it: `false confidence` is 16 characters, and a fixed 14 would put
    # every cell in its row half a column to the right of its heading.
    widths = {name: max(14, len(name) + 2) for name in columns}

    lines = ["".ljust(width) + "  ".join(f"{n:^{widths[n]}}" for n in columns)]
    for case in cases:
        runs = [outcome for outcome in report.outcomes if outcome.case == case]
        measured = [outcome for outcome in runs if outcome.error is None]
        cells = []
        for name in columns:
            if name == NOT_RUN:
                missed = sum(1 for outcome in runs if outcome.error is not None)
                said = str(missed) if missed else "-"
            elif not measured:
                said = "-"
            else:
                broke = sum(
                    1 for o in measured if any(n == name for n, _ in o.failures)
                )
                said = "ok" if not broke else f"{broke} failed"
            cells.append(f"{said:^{widths[name]}}")
        lines.append(case.ljust(width) + "  ".join(cells))
    return lines


def failures(report: Report, about: Mapping[str, str] | None = None) -> list[str]:
    """Every failure, one to a line, with the record that says why.

    `about` says what a case *is*, for a suite whose names do not: `U11` is a
    row number and `no-equipment` is a description, so the log suite passes
    its headings and the six situations do not need to.
    """
    said = about or {}
    lines = []
    for outcome in report.outcomes:
        named = outcome.case
        if outcome.case in said:
            named = f"{outcome.case} ({said[outcome.case]})"
        if outcome.error is not None:
            lines.append(f"{named} #{outcome.attempt}: {outcome.error}")
        for name, why in outcome.failures:
            where = outcome.written or "(not written)"
            lines.append(f"{named} #{outcome.attempt} {name}: {why}")
            lines.append(f"    {where}")
    return lines


def totals(report: Report, held: str) -> list[str]:
    """The number, what it cost, and the bar it is measured against.

    `held` is what holding meant -- every invariant, or the outcome the row
    declared. The bar is the same either way and it is not a knob: a labelled
    row is an expected outcome somebody wrote down before the run, so a row
    that fails is either the agent being wrong or the row being wrong, and
    both are things to go and read.
    """
    lines = []
    # Floored, never rounded. At 249 of 250 a rounded figure prints 100% on
    # the line above "the bar is 100%" and then exits non-zero -- the one
    # number this command exists to produce, contradicting itself.
    counted = (
        ""
        if report.against == report.total
        else f", out of {report.against} with false confidence counted double"
    )
    lines.append(
        f"{report.held} of {report.total} runs {held} "
        f"-- {math.floor(report.percentage)}%{counted}"
    )
    lines.append(
        f"cost: {report.calls} tool calls, {report.input_tokens} tokens in, "
        f"{report.output_tokens} out"
    )
    if not report.passed:
        lines.append("")
        lines.append("The bar is 100%. Anything below it is a bug, not a knob.")
    return lines
