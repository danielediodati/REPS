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
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from trainer import agent
from trainer import plan as plans
from trainer.engine import admissible, catalog, duration, muscle_groups

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

RECORDS = Path("eval-runs")
"""Where each run's record is written. A failure names the file, because
*invariant 3 failed* is a fact and the record is the only thing that says
why."""


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


# -- the six invariants -------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    name: str
    holds: Callable[[sqlite3.Connection, Situation, agent.RunRecord], str | None]
    """`None` when it holds, and the sentence saying how it failed otherwise."""


def _terminates(
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
) -> str | None:
    """A plan, within the call budget -- and if the budget ran out, one anyway.

    **A run that never returned is not measured here.** It has no record to
    read, so it arrives as `Outcome.error`, shows in the *not run* column and
    counts against the metric there. What this checks is the loop's own
    bookkeeping on a run that did return: that it stopped asking for tools
    once the budget was gone, and that the plan it emitted has something in
    it.

    The budget is a point at which tools stop being offered rather than a
    number the loop lands on exactly -- a turn's calls are executed together,
    so the last one can carry the count past it. What would be a fault is
    overshooting *without* having crossed the line, which is a loop that kept
    going after it decided to stop.
    """
    if not record.plan.blocks:
        return "it emitted a plan with no blocks in it"
    if record.spent > record.budget and not record.emitted_on_exhaustion:
        return (
            f"it made {record.spent} calls against a budget of {record.budget} "
            "without the loop recording that the budget ran out"
        )
    return None


def _respects_the_time(
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
) -> str | None:
    """Estimated duration inside the declared budget. Never trimmed to fit."""
    try:
        blocks = plans.to_blocks(record.plan)
        spent = duration.plan_duration(connection, blocks)
    except (plans.PlanError, duration.DurationError) as error:
        return f"it cannot be costed: {error}"
    if spent > situation.request.budget_min:
        return f"it runs {spent} min against {situation.request.budget_min}"
    return None


def _respects_the_constraints(
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
) -> str | None:
    """Nothing outside the admissible set.

    The set is asked for again here rather than trusted from the run: the
    invariant is about the plan against the request, and reading it back off
    whatever the model was handed mid-loop would measure the loop's bookkeeping
    instead of the plan.
    """
    request = situation.request
    inside = {
        exercise.id
        for exercise in admissible.admissible_set(
            connection,
            request.exclusions,
            request.equipment,
            request.budget_min,
            request.groups,
        )
    }
    outside = sorted(_prescribed(record) - inside)
    if outside:
        return f"it prescribes {', '.join(outside)}, which is outside the set"
    return None


def _respects_the_preferences(
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
) -> str | None:
    """Nothing the user refused -- and if it proposes one again, it says so.

    Both halves, because TRAINER.md states both. Proposing one with the reason
    attached is allowed and is the behaviour the invariant wants; proposing one
    in silence is the failure.
    """
    refused = set(situation.request.preferences)
    spoken = {said.exercise_id for said in record.plan.despite}
    silent = sorted(
        item.exercise_id
        for block in record.plan.blocks
        for item in block.items
        if item.exercise_id in refused and item.exercise_id not in spoken
    )
    if silent:
        return f"it prescribes {', '.join(silent)} without saying why"
    return None


def _todays_equipment_only(
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
) -> str | None:
    """Every exercise is one today's equipment reaches.

    Checked apart from the admissible set although the set already filters on
    it: this is its own invariant in TRAINER.md, and a fault in the filter
    would otherwise pass both.
    """
    allowed = set(situation.request.equipment)
    wrong = []
    for exercise_id in sorted(_prescribed(record)):
        found = catalog.exercise(connection, exercise_id)
        if found is None:
            wrong.append(f"{exercise_id} (no such exercise)")
        elif found.equipment not in allowed:
            wrong.append(f"{exercise_id} needs {found.equipment}")
    if wrong:
        return "; ".join(wrong)
    return None


def _does_not_degenerate(
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
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
    prescribed = _prescribed(record)

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


def _prescribed(record: agent.RunRecord) -> set[str]:
    return {
        item.exercise_id for block in record.plan.blocks for item in block.items
    }


# -- running them -------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """One run, and what held."""

    situation: str
    attempt: int
    failures: tuple[tuple[str, str], ...] = ()
    record: agent.RunRecord | None = None
    written: Path | None = None
    error: str | None = None
    """The run never finished -- no credentials, the provider refusing, a rate
    limit. It holds no invariant, because a measurement that quietly skipped
    the runs it could not make would report on the easy ones. It is not a
    *failure* of any of them either, which is why the matrix gives it a column
    of its own rather than blanking the ones it says nothing about."""

    also: tuple[agent.RunRecord, ...] = ()
    """Runs made to set this one up and not measured -- the plan that gets
    turned down, on the refusal situation. They hold no invariants and they
    are not counted towards the metric, but they were paid for, so they count
    towards the cost."""

    @property
    def held(self) -> bool:
        return self.error is None and not self.failures

    @property
    def records(self) -> tuple[agent.RunRecord, ...]:
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
    def percentage(self) -> float:
        return 100.0 * self.held / self.total if self.total else 0.0

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
    connection: sqlite3.Connection, situation: Situation, record: agent.RunRecord
) -> tuple[tuple[str, str], ...]:
    """Every invariant against one run. All of them, not the first to fail.

    A run that breaks three properties is a different thing from one that
    breaks one, and stopping at the first would hide the difference behind an
    identical line in the matrix.
    """
    failures = []
    for invariant in INVARIANTS:
        why = invariant.holds(connection, situation, record)
        if why is not None:
            failures.append((invariant.name, why))
    return tuple(failures)


def run(
    connection: sqlite3.Connection,
    chosen: Sequence[Situation],
    *,
    build: Callable[[], agent.Model],
    repetitions: int = REPETITIONS,
    records: Path = RECORDS,
    budget: int = agent.CALL_BUDGET,
) -> Report:
    """Every situation, every repetition, against the real agent.

    `build` makes the model, once per run: the model is a parameter so that
    nothing here reaches a provider on its own, and so the caller decides which
    one is being measured.
    """
    outcomes = []
    for situation in chosen:
        for attempt in range(1, repetitions + 1):
            outcomes.append(
                _once(connection, situation, attempt, build, records, budget)
            )
    return Report(tuple(outcomes))


def _once(
    connection: sqlite3.Connection,
    situation: Situation,
    attempt: int,
    build: Callable[[], agent.Model],
    records: Path,
    budget: int,
) -> Outcome:
    request = situation.request
    also: list[agent.RunRecord] = []
    try:
        if situation.after_a_refusal:
            # Two turns, not a conversation. The first plan exists only to be
            # turned down, and what is measured is what comes back after --
            # but it was paid for, so it is kept and it counts towards cost.
            first = agent.plan_workout(
                connection, request, model=build(), budget=budget
            )
            also.append(first)
            _write(records, f"{situation.name}-{attempt}-turned-down", first)
            request = plans.Request(
                equipment=request.equipment,
                budget_min=request.budget_min,
                exclusions=request.exclusions,
                groups=request.groups,
                allocation=request.allocation,
                preferences=request.preferences,
                refused=first.plan,
                because="I don't feel like it",
            )
        record = agent.plan_workout(connection, request, model=build(), budget=budget)
    except agent.AgentError as error:
        return Outcome(situation.name, attempt, error=str(error), also=tuple(also))

    written = _write(records, f"{situation.name}-{attempt}", record)

    failures = check(connection, Situation(
        name=situation.name,
        describes=situation.describes,
        request=request,
        after_a_refusal=situation.after_a_refusal,
    ), record)
    if record.refused is not None and not failures:
        # The validator refused a plan every invariant says is fine. The two
        # disagreeing is the interesting thing, so it is recorded rather than
        # swallowed -- under its own name, and `VALIDATOR` is a column of the
        # matrix so it cannot be a failure nothing shows.
        failures = ((VALIDATOR, record.refused),)
    return Outcome(situation.name, attempt, failures, record, written, also=tuple(also))


def _write(records: Path, name: str, record: agent.RunRecord) -> Path:
    """One record to disk. The directory is made here rather than when the run
    starts, so a pass that never reaches a provider leaves nothing behind --
    the suite invokes this command to check it stops at the credentials state,
    and an empty `eval-runs/` in the repo after every `pytest` is litter."""
    records.mkdir(parents=True, exist_ok=True)
    written = records / f"{name}.json"
    written.write_text(record.model_dump_json(indent=1), encoding="utf-8")
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
    width = max((len(s.name) for s in chosen), default=0) + 2
    columns = [invariant.name for invariant in INVARIANTS] + [VALIDATOR, NOT_RUN]

    lines = [
        "".ljust(width) + "  ".join(f"{name:^14}" for name in columns),
    ]
    for situation in chosen:
        runs = [o for o in report.outcomes if o.situation == situation.name]
        measured = [o for o in runs if o.error is None]
        cells = []
        for name in columns:
            if name == NOT_RUN:
                missed = sum(1 for o in runs if o.error is not None)
                cells.append(f"{(str(missed) if missed else '-'):^14}")
                continue
            broke = sum(1 for o in measured if any(n == name for n, _ in o.failures))
            if not measured:
                cells.append(f"{'-':^14}")
            else:
                cells.append(f"{('ok' if not broke else f'{broke} failed'):^14}")
        lines.append(situation.name.ljust(width) + "  ".join(cells))

    lines.append("")
    for outcome in report.outcomes:
        if outcome.error is not None:
            lines.append(f"{outcome.situation} #{outcome.attempt}: {outcome.error}")
        for name, why in outcome.failures:
            where = outcome.written or "(not written)"
            lines.append(f"{outcome.situation} #{outcome.attempt} {name}: {why}")
            lines.append(f"    {where}")

    lines.append("")
    # Floored, never rounded. At 249 of 250 a rounded figure prints 100% on
    # the line above "the bar is 100%" and then exits non-zero -- the one
    # number this command exists to produce, contradicting itself.
    lines.append(
        f"{report.held} of {report.total} runs held every invariant "
        f"-- {math.floor(report.percentage)}%"
    )
    lines.append(
        f"cost: {report.calls} tool calls, {report.input_tokens} tokens in, "
        f"{report.output_tokens} out"
    )
    if not report.passed:
        lines.append("")
        lines.append("The bar is 100%. Anything below it is a bug, not a knob.")
    return lines
