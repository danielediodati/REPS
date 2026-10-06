"""The measurement session 4 is judged on: six situations, six invariants, 100%.

`trainer eval` runs TRAINER.md's six hand-written, deliberately nasty
situations against the real agent and checks six properties over every run.
Each situation asks for a mesocycle, and the invariants hold on every workout
in it (ticket 10.5).
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
module holds. `eval_runner.pointed_at` is what makes those the same file, and
CLAUDE.md asks for it because a fixture nothing points at is invisible to the
agent.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from trainer import eval_runner
from trainer import plan as plans
from trainer.coach import models, planner
from trainer.coach import record as run_record
from trainer.engine import (
    admissible,
    catalog,
    constraints,
    duration,
    muscle_groups,
)


TURNED_DOWN_BECAUSE = "I don't feel like it"
"""What the user says when they turn down the first mesocycle of the after-a-refusal situation."""


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
    slots: tuple[plans.Request, ...]
    """One request per workout of the cycle, as a door would send them."""

    after_a_refusal: bool = False
    """Situation 5. The measured run is the second: the first exists only to
    have something to turn down, and its cost counts towards the pass."""

    @property
    def request(self) -> plans.MesocycleRequest:
        """The mesocycle this situation asks for."""
        return plans.MesocycleRequest(slots=self.slots)


GOAL = "hypertrophy"
"""The goal every situation plans for; a door always sends the declared one."""


SPLIT = (("legs", "core"), ("chest", "back"))
"""The cycle every situation plans, unless it is about the groups: two workouts, lower and upper."""


def situations(connection: sqlite3.Connection) -> tuple[Situation, ...]:
    """The six, each a mesocycle over `SPLIT`, built against this catalog.

    A seventh is a row here. The two that read the catalog do so rather than
    naming ids in the source: a hand-written list of sixty exercises is a
    vocabulary copy, and this project has been wrong that way once already.
    """
    body = ("body only",)

    def split(minutes: int, preferences: tuple[str, ...] = ()) -> tuple[plans.Request, ...]:
        return tuple(
            plans.Request(
                equipment=body,
                budget_min=minutes,
                groups=groups,
                goal=GOAL,
                preferences=preferences,
            )
            for groups in SPLIT
        )

    everything = plans.Request(
        equipment=body, budget_min=30, groups=muscle_groups.groups(), goal=GOAL
    )
    return (
        Situation(
            name="no-equipment",
            describes="15 minutes, no equipment",
            slots=split(15),
        ),
        Situation(
            name="half-refused",
            describes="half the catalog out on stated preferences",
            slots=split(
                30,
                tuple(
                    exercise_id
                    for groups in SPLIT
                    for exercise_id in _half_of(connection, body, 30, groups)
                ),
            ),
        ),
        Situation(
            name="contradictory",
            describes="30 minutes, but I want to train everything",
            slots=(everything, everything),
        ),
        Situation(
            name="no-history",
            describes="the previous report ambiguous or missing",
            slots=split(30),
        ),
        Situation(
            name="refused",
            describes="the user refuses the mesocycle and it proposes again",
            slots=split(30),
            after_a_refusal=True,
        ),
        Situation(
            name="preference-against-the-split",
            describes="a preference in conflict with what the workout must train",
            slots=split(30, _half_of(connection, body, 30, ("legs",))),
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
class Ran(eval_runner.Recorded):
    """One run of the planner graph: ticket 03's record, and what it cost.

    The record is what is written to disk **and** what every number the matrix
    reports is read off, so the file a failure names and the row above it
    cannot disagree.

    The plan and the request are kept as the objects the graph held rather
    than parsed back out of the record: the invariants validate them, and a
    round trip through JSON would be measuring the round trip.
    """

    request: plans.MesocycleRequest
    """What the graph planned against: the situation's slots with today's
    standing exclusions and the declared cap folded in, which is the space the
    model was actually shown."""

    plan: plans.Mesocycle | None
    """`None` when nothing it emitted parses as a mesocycle at all."""

    spent: int
    """What the run actually paid, which is not the budget: a turn's calls are
    answered as a batch, so the last one can carry the count past it."""

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



# -- the six invariants -------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    name: str
    holds: Callable[
        [sqlite3.Connection, plans.Request, plans.WorkoutPlan, tuple[plans.Violation, ...]],
        str | None,
    ]
    """Checked on one workout against its slot: `None` when it holds, and the
    sentence saying how it failed otherwise.

    The violations are handed in rather than asked for: they cost three
    queries and a costing pass, and every invariant that reads them would
    otherwise run that again.
    """


TERMINATES = "terminates"
"""The one invariant about the run as a whole; the others hold on each workout."""


def _terminates(ran: Ran, slots: int) -> str | None:
    """A mesocycle came out, one workout per slot, inside the bounds the graph runs under.

    **A run that never returned is not measured here.** It has no record to
    read, so it arrives as `Outcome.error`, shows in the *not run* column and
    counts against the metric there. What this checks is a run that did
    return: that it emitted a mesocycle with something in every workout, and
    that it stopped where it was built to stop.

    **The call budget is reported rather than checked**, and that moved here
    from the old loop deliberately. Tools stop being offered the moment the
    budget is crossed, but a turn's calls are answered as a whole batch, so a
    turn asking for seven at once ends at *16 of 12* -- observed on Groq in
    ticket 04. Overshooting is therefore not a fault to fail a run for; what
    it is, is a number worth seeing, and `numbers` prints what was actually
    spent beside every run.
    """
    if ran.plan is None:
        return "it emitted nothing that parses as a mesocycle"
    given = len(ran.plan.workouts)
    if given != slots:
        return f"it emitted {given} workouts for {slots} slots"
    empty = [
        str(slot)
        for slot, workout in enumerate(ran.plan.workouts, start=1)
        if not workout.blocks
    ]
    if empty:
        return f"workout {', '.join(empty)}: a plan with no blocks in it"
    if ran.attempts > planner.ATTEMPTS:
        return (
            f"it emitted {ran.attempts} mesocycles against a bound of "
            f"{planner.ATTEMPTS} attempts"
        )
    return None


def violations_of(
    connection: sqlite3.Connection, asked: plans.Request, workout: plans.WorkoutPlan
) -> tuple[plans.Violation, ...]:
    """Every rule one workout breaks against its slot, decided once for all the invariants that read one.

    The rules themselves, not a second reading of them: read twice, the day
    the two disagree the run is measured against whichever one is wrong.
    """
    try:
        blocks = plans.to_blocks(workout)
        return plans.validate(connection, blocks, asked, workout)
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
    asked: plans.Request,
    workout: plans.WorkoutPlan,
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
    asked: plans.Request,
    workout: plans.WorkoutPlan,
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
    asked: plans.Request,
    workout: plans.WorkoutPlan,
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
    asked: plans.Request,
    workout: plans.WorkoutPlan,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """Every exercise is one today's equipment reaches.

    Checked apart from the admissible set although the set already filters on
    it: this is its own invariant in TRAINER.md, and a fault in the filter
    would otherwise pass both.
    """
    allowed = set(asked.equipment)
    wrong = []
    for exercise_id in sorted(_prescribed(workout)):
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
    asked: plans.Request,
    workout: plans.WorkoutPlan,
    violations: tuple[plans.Violation, ...],
) -> str | None:
    """It uses the space it was given, on ADR-0001's two axes, each judged against what was available.

    The muscle axis is the validator's own rule, called here rather than read
    off `violations`, which skip it when an exercise is written twice or is not
    admissible. The pattern axis is checked here only: a plan with more than
    one pattern on offer uses at least two.
    """
    untrained = plans.every_group_trained(connection, workout, asked)
    if untrained is not None:
        return untrained.says

    available = admissible.admissible_set(
        connection,
        asked.exclusions,
        asked.equipment,
        asked.budget_min,
        asked.groups,
    )
    offered = _patterns(connection, [exercise.id for exercise in available])
    if len(offered) > 1:
        used = _patterns(connection, sorted(_prescribed(workout)))
        if len(used) < 2:
            only = ", ".join(sorted(used)) or "nothing"
            return f"every exercise is {only}, out of {len(offered)} patterns available"
    return None


def _patterns(connection: sqlite3.Connection, ids: Sequence[str]) -> set[str]:
    """The distinct movement patterns of these exercises."""
    if not ids:
        return set()
    return {
        str(row["movement_pattern"])
        for row in connection.execute(
            "SELECT DISTINCT movement_pattern FROM exercises WHERE id IN "
            f"({','.join('?' for _ in ids)})",
            list(ids),
        )
    }


INVARIANTS = (
    Invariant("time", _respects_the_time),
    Invariant("constraints", _respects_the_constraints),
    Invariant("preferences", _respects_the_preferences),
    Invariant("equipment", _todays_equipment_only),
    Invariant("not degenerate", _does_not_degenerate),
)


def _prescribed(workout: plans.WorkoutPlan) -> set[str]:
    """Every exercise the workout names."""
    return {item.exercise_id for block in workout.blocks for item in block.items}



# -- running them -------------------------------------------------------------


def check(
    connection: sqlite3.Connection, situation: Situation, ran: Ran
) -> tuple[tuple[str, str], ...]:
    """Every invariant against one run. All of them, not the first to fail.

    A run that breaks three properties is a different thing from one that
    breaks one, and stopping at the first would hide the difference behind an
    identical line in the matrix.
    """
    ended = _terminates(ran, len(situation.slots))
    if ran.plan is None or len(ran.plan.workouts) != len(situation.slots):
        # Nothing to pair with the slots, so nothing else can be read.
        return ((TERMINATES, str(ended)),)
    failures = [] if ended is None else [(TERMINATES, ended)]
    for slot, (workout, asked) in enumerate(
        zip(ran.plan.workouts, situation.slots, strict=True), start=1
    ):
        violations = violations_of(connection, asked, workout)
        for invariant in INVARIANTS:
            why = invariant.holds(connection, asked, workout, violations)
            if why is not None:
                failures.append((invariant.name, f"workout {slot}: {why}"))
    return tuple(failures)


NOTHING_TO_REFUSE = (
    "the plan that was to be turned down did not parse, so there was nothing "
    "to refuse and the second run would not have been this situation"
)
"""Why the refusal situation can fail before it starts."""


class NothingToRefuse(Exception):
    """The plan that was to be turned down did not parse."""


class Plan(eval_runner.Suite[Situation, sqlite3.Connection]):
    """The six situations against the planner graph, on the project database.

    **A checkpointer in memory, and no resume.** The graph stops at the plan
    and waits for somebody to accept it (ADR-0005); nothing here answers, so
    no run reaches the node that writes, and a pass leaves no phantom
    prescribed workouts in the state it measures.
    """

    what = "situation"

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(situations(connection))

    @contextmanager
    def fixture(self, connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        with eval_runner.pointed_at():
            yield connection

    def nodes(self, chosen: Sequence[Situation]) -> Sequence[models.Node]:
        return ("planner",)

    def runs(
        self,
        where: sqlite3.Connection,
        chats: models.Roster,
        *,
        records: Path,
        budget: int,
    ) -> eval_runner.Once[Situation]:
        # Compiled once: a run carries everything it knows in its own state.
        graph = planner.build(chats["planner"], budget=budget, checkpointer=eval_runner.checkpointer())
        return lambda situation, attempt: (
            _planned(where, situation, attempt, graph, budget, records),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[Situation]) -> list[str]:
        return render(report, chosen)


def _planned(
    connection: sqlite3.Connection,
    situation: Situation,
    attempt: int,
    graph: planner.Planner,
    budget: int,
    records: Path,
) -> eval_runner.Outcome:
    """One situation planned and checked; on the refusal situation, the plan turned down first."""
    request = _today(connection, situation.request)
    also: list[Ran] = []

    def run() -> eval_runner.Scored:
        asked = request
        if situation.after_a_refusal:
            # Two turns, not a conversation: the first plan exists only to be
            # turned down, but it was paid for, so it counts towards cost.
            first = _invoked(graph, asked, budget)
            also.append(first)
            eval_runner.write(records, f"{situation.name}-{attempt}-turned-down", first.written)
            if first.plan is None:
                # With nothing to carry, the second run would be an ordinary
                # planning run, and a green row under a situation that never
                # happened.
                raise NothingToRefuse(NOTHING_TO_REFUSE)
            asked = dataclasses.replace(
                asked,
                refusals=plans.mesocycle_turned_down((), first.plan, TURNED_DOWN_BECAUSE),
            )
        ran = _invoked(graph, asked, budget)
        # Checked against the slots the graph planned against: `_today`
        # folded the standing exclusions and the declared cap into them.
        failures = check(connection, dataclasses.replace(situation, slots=ran.request.slots), ran)
        if ran.refused and not failures:
            # The validator refused a plan every invariant says is fine: the
            # two disagreeing is recorded under its own column.
            failures = tuple((eval_runner.VALIDATOR, f"{rule}: {says}") for rule, says in ran.refused)
        return eval_runner.Scored(ran, failures)

    outcome = eval_runner.attempted(situation.name, attempt, records, f"{situation.name}-{attempt}", run)
    return dataclasses.replace(outcome, also=tuple(also))


def _today(
    connection: sqlite3.Connection, request: plans.MesocycleRequest
) -> plans.MesocycleRequest:
    """Every slot with today's standing exclusions and the declared cap folded in, as a door's are."""
    today = date.today().isoformat()
    folded = []
    for asked in request.slots:
        found = constraints.constraining_today(
            connection,
            today,
            budget_min=asked.budget_min,
            groups=asked.groups,
            given=asked.exclusions,
        )
        folded.append(
            dataclasses.replace(
                asked,
                exclusions=found.exclusions,
                budget_min=found.budget_min,
                groups=found.groups,
            )
        )
    return dataclasses.replace(request, slots=tuple(folded))


def _invoked(
    graph: planner.Planner, request: plans.MesocycleRequest, budget: int
) -> Ran:
    """One run of the graph, timed around the whole invocation, which is what a person waits for."""
    final, seconds = eval_runner.timed(
        lambda: graph.invoke(planner.starting(request), eval_runner.thread("eval"))
    )
    return Ran(
        record=run_record.of(final, budget),
        seconds=seconds,
        request=final["request"],
        plan=final["plan"],
        spent=final.get("spent", 0),
    )



# -- the matrix ---------------------------------------------------------------


def render(report: eval_runner.Report, chosen: Sequence[Situation]) -> list[str]:
    """The situation-by-invariant matrix, the number, and what it cost. ASCII.

    One column per invariant, plus `validator` -- a refusal no invariant names
    -- plus `not run`. The last is its own column rather than a dash across
    the row: a rate limit on the second of three repetitions says nothing
    about the two that did run, and blanking their verdicts would hide real
    failures behind an unrelated transport error.
    """
    columns = [TERMINATES, *(invariant.name for invariant in INVARIANTS), eval_runner.VALIDATOR, eval_runner.NOT_RUN]
    cases = [situation.name for situation in chosen]
    return [
        *eval_runner.matrix(report, cases, columns),
        "",
        "what the planner spent getting there:",
        *numbers(report, cases),
        "",
        *eval_runner.failures(report),
        "",
        *eval_runner.totals(report, "held every invariant"),
    ]


PLANNER_COLUMNS = ("attempts", "seconds", "tool calls", "refused by")
"""What the graph itself costs, which the invariants say nothing about.

*It held every invariant* and *it held them on the third attempt, after two
refusals, in four minutes* are different answers to whether this model can
plan on this laptop, and only the second one decides whether the session was
built on the right model.
"""


def numbers(report: eval_runner.Report, cases: Sequence[str]) -> list[str]:
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

