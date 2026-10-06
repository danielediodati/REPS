"""The supervisor's suite: each history directed and planned from, the direction and the plan held by code."""

from __future__ import annotations

import math
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from trainer import eval_runner, history, supervise_set
from trainer import plan as plans
from trainer.coach import conclusions, models, onboarding, planner, supervisor
from trainer.coach import record as run_record
from trainer.engine import catalog, config, mesocycles, methodology

PLANNED = "planned"
CHANGED = "changed"
KEPT = "kept"
ROTATED = "rotated"
LEFT_OUT = "left out"
RANGES = "ranges"
VARIES = "varies"
TREND = "trend"
COLUMNS = (PLANNED, CHANGED, KEPT, ROTATED, LEFT_OUT, RANGES, VARIES, TREND)
FOLLOWED = "followed"

FOLLOWS = " followed"
"""Appended to a case's name for whether the plan shows what its direction varies."""

REPS_MOVE = 1
REST_MOVE = 10
"""How far the mean reps per item, and the mean rest per block in seconds, must move for `rest` and `reps` to hold."""

TABLES = (
    "served",
    "workout_exercises",
    "workout_blocks",
    "workouts",
    "directions",
    "mesocycle_exercises",
    "mesocycle_blocks",
    "mesocycles",
    "declarations",
    "exclusions",
)


@dataclass(frozen=True)
class Fixture:
    """The copy the suite runs against, named in `TRAINER_DB` while it is open."""

    connection: sqlite3.Connection
    path: Path


class Supervise(eval_runner.Suite[supervise_set.Case, Fixture]):
    """Each history written into a copy of the catalog in turn, directed, and planned from."""

    what = "history"

    def __init__(self, holds: supervise_set.SuperviseSet) -> None:
        super().__init__(holds.cases)
        self.holds = holds

    def problems(self, connection: sqlite3.Connection) -> Sequence[str]:
        return problems(connection, self.holds)

    @contextmanager
    def fixture(self, connection: sqlite3.Connection) -> Iterator[Fixture]:
        """A copy of the database, its catalog kept."""
        with eval_runner.copied(connection) as copy:
            yield Fixture(copy.connection, copy.path)

    def checked(self, where: Fixture) -> Sequence[str]:
        return refused(where, self.holds, date.today().isoformat())

    def nodes(self, chosen: Sequence[supervise_set.Case]) -> Sequence[models.Node]:
        return ("supervisor", "planner")

    def runs(
        self, where: Fixture, chats: models.Roster, *, records: Path, budget: int
    ) -> eval_runner.Once[supervise_set.Case]:
        return lambda case, attempt: _supervised(where, self.holds, case, attempt, chats, budget, records)

    def halves(self) -> tuple[eval_runner.Half, ...]:
        """What each row holds, and how often the plan followed."""
        holds = self.holds
        return (
            eval_runner.Half("held", frozenset(case.name for case in holds.cases), holds.bar_held),
            eval_runner.Half("followed", frozenset(case.name + FOLLOWS for case in holds.cases), holds.bar_followed),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[supervise_set.Case]) -> list[str]:
        return render(report, chosen)


def declared(holds: supervise_set.SuperviseSet, case: supervise_set.Case) -> config.TrainingConfig:
    """The set's declaration, with the case's goal when it names one."""
    given = dict(holds.declared)
    if case.goal is not None:
        given["goal"] = case.goal
    return onboarding.settled(given)


def staged(
    where: Fixture, holds: supervise_set.SuperviseSet, case: supervise_set.Case, today: str
) -> plans.MesocycleRequest:
    """The case's history written over whatever the last case left, and the request for what follows it."""
    connection = where.connection
    for table in TABLES:
        connection.execute(f"DELETE FROM {table}")
    meant = [holds.mesocycles[past.mesocycle] for past in case.history]
    days = sum(len(one.workouts) * one.cycles + 1 for one in meant)
    on = date.fromisoformat(today) - timedelta(days=days + 1)
    config.record(connection, declared(holds, case), on.isoformat())
    for past, mesocycle in zip(case.history, meant, strict=True):
        on = history.performed_as_prescribed(connection, mesocycle, on + timedelta(days=1), direction=past.direction)
    return plans.next_requested(connection, today)


def remembering(case: supervise_set.Case) -> BaseStore:
    """A store holding what the case says they said, under the suite's user."""
    store = InMemoryStore()
    for said in case.said:
        store.put(
            conclusions.namespace(eval_runner.USER),
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{said.conclusion}\n{said.quote}")),
            {"conclusion": said.conclusion, "quote": said.quote, "state": conclusions.PROVISIONAL, "on": "2026-01-01"},
            index=False,
        )
    return store


def problems(connection: sqlite3.Connection, holds: supervise_set.SuperviseSet) -> tuple[str, ...]:
    """What in the set disagrees with this catalog and this methodology, before anything is paid for."""
    found: list[str] = []
    goals = methodology.goals()
    known_equipment = set(catalog.values(connection, "equipment"))
    try:
        base = onboarding.settled(dict(holds.declared))
    except config.ConfigError as error:
        return (f"[declared] is not a declaration: {error}",)
    found += [f"[declared]: no equipment called {one}" for one in base.equipment if one not in known_equipment]
    for name, mesocycle in holds.mesocycles.items():
        if len(mesocycle.workouts) != base.cycle_length:
            found.append(f"[mesocycles.{name}] has {len(mesocycle.workouts)} slots for a cycle of {base.cycle_length}")
    named = {one for mesocycle in holds.mesocycles.values() for one in _ids(mesocycle)}
    for case in holds.cases:
        if case.goal is not None and case.goal not in goals:
            found.append(f"{case.name}: no goal called {case.goal}; the methodology has {', '.join(goals)}")
        named |= {one for any_of in case.keeps for one in any_of} | set(case.without)
    found += [f"the catalog has no exercise {one}" for one in sorted(named) if catalog.exercise(connection, one) is None]
    return tuple(found)


def refused(where: Fixture, holds: supervise_set.SuperviseSet, today: str) -> tuple[str, ...]:
    """What the validator would refuse in the set's mesocycles, asked for as a door would ask under the set's declaration."""
    for table in TABLES:
        where.connection.execute(f"DELETE FROM {table}")
    asked = plans.mesocycle_requested(where.connection, today, declared=onboarding.settled(dict(holds.declared)))
    return tuple(
        f"[mesocycles.{name}] {one.rule}: {one.says}"
        for name, mesocycle in holds.mesocycles.items()
        for one in plans.validate_mesocycle(where.connection, mesocycle, asked)
    )


def _supervised(
    where: Fixture,
    holds: supervise_set.SuperviseSet,
    case: supervise_set.Case,
    attempt: int,
    chats: models.Roster,
    budget: int,
    records: Path,
) -> tuple[eval_runner.Outcome, ...]:
    """One history directed and planned from; then whether the plan followed the direction."""
    today = date.today().isoformat()
    request = staged(where, holds, case, today)
    assert request.continuing is not None
    store = remembering(case)
    directed: list[plans.MesocycleRequest] = []

    def direct() -> eval_runner.Scored:
        graph = supervisor.build(
            chats["supervisor"], budget=budget, checkpointer=eval_runner.checkpointer(), store=store
        )
        thread = eval_runner.thread("supervise", remembers=True)
        asked, seconds = eval_runner.timed(lambda: supervisor.directed(graph, request, thread))
        assert asked.continuing is not None and asked.continuing.direction is not None
        directed.append(asked)
        return eval_runner.Scored(
            eval_runner.Talked(
                record=run_record.of(graph.get_state(thread).values, budget),
                seconds=seconds,
                conversation=(("direction", _said(asked.continuing.direction)),),
            )
        )

    directing = eval_runner.attempted(
        case.name, attempt, records, f"{case.name}-{attempt}-direction", direct, typed=True
    )
    if directing.error is not None:
        return (directing,)
    (asked,) = directed
    assert asked.continuing is not None and asked.continuing.direction is not None
    ended, direction = asked.continuing.ended, asked.continuing.direction
    failures: list[tuple[str, str]] = []

    def plan() -> eval_runner.Scored:
        planning = planner.build(
            chats["planner"], budget=budget, checkpointer=eval_runner.checkpointer(), store=store
        )
        final, seconds = eval_runner.timed(
            lambda: planning.invoke(
                planner.starting(asked, unasked=True), eval_runner.thread("supervise-plan", remembers=True)
            )
        )
        planned = eval_runner.Talked(
            record=run_record.of(final, budget),
            seconds=seconds,
            conversation=(("direction", _said(direction)),),
        )
        made = final.get("plan")
        made = made if isinstance(made, plans.Mesocycle) else None
        bounds = methodology.committed().bounds(declared(holds, case).goal)
        failures.extend(held(case, ended, direction, made, tuple(final.get("violations", ())), bounds))
        return eval_runner.Scored(planned, followed(ended, direction, made))

    follows = eval_runner.attempted(
        case.name + FOLLOWS, attempt, records, f"{case.name}-{attempt}-plan", plan, typed=True
    )
    if follows.error is not None:
        return (eval_runner.Outcome(case.name, attempt, error=follows.error, record=directing.record), follows)
    return (eval_runner.Outcome(case.name, attempt, tuple(failures), directing.record, follows.written), follows)


def _said(direction: mesocycles.Direction) -> str:
    return (
        f"{direction.theme} | varies {', '.join(direction.varies)} | "
        f"{direction.changes} | why: {direction.why}"
    )


def _ids(mesocycle: plans.Mesocycle) -> set[str]:
    return {one for workout in mesocycle.workouts for one in plans.exercise_ids(workout)}


def _reps(mesocycle: plans.Mesocycle) -> list[int]:
    return [
        item.prescription.amount
        for workout in mesocycle.workouts
        for block in workout.blocks
        for item in block.items
        if item.prescription.unit == "reps"
    ]


def _rests(mesocycle: plans.Mesocycle) -> list[int]:
    return [block.rest for workout in mesocycle.workouts for block in workout.blocks]


def _moved(before: Sequence[int], after: Sequence[int]) -> Fraction:
    """How far the mean moved, exactly, so one rep fewer everywhere is a move of one; zero when either side is empty."""
    if not before or not after:
        return Fraction(0)
    return Fraction(sum(after), len(after)) - Fraction(sum(before), len(before))


def _scheme(mesocycle: plans.Mesocycle) -> list[list[tuple[tuple[int, ...], int]]]:
    """Each workout's blocks in order, as the rep counts of its items and its rest."""
    return [
        [
            (tuple(item.prescription.amount for item in block.items if item.prescription.unit == "reps"), block.rest)
            for block in workout.blocks
        ]
        for workout in mesocycle.workouts
    ]


def moved(ended: plans.Mesocycle, plan: plans.Mesocycle) -> tuple[str, ...]:
    """Which of `mesocycles.VARIES` the plan changed from the mesocycle that ended.

    Reps and rest are compared block by block, at the positions both have.
    """
    pairs = [
        pair
        for before, after in zip(_scheme(ended), _scheme(plan))
        for pair in zip(before, after)
    ]
    found = []
    if _ids(plan) != _ids(ended):
        found.append("exercises")
    if any(old[0] != new[0] for old, new in pairs):
        found.append("reps")
    if any(old[1] != new[1] for old, new in pairs):
        found.append("rest")
    return tuple(found)


def held(
    case: supervise_set.Case,
    ended: plans.Mesocycle,
    direction: mesocycles.Direction,
    plan: plans.Mesocycle | None,
    violations: Sequence[plans.Violation],
    bounds: methodology.Bounds,
) -> tuple[tuple[str, str], ...]:
    """Every check the case's row names, on its direction and the plan made from it."""
    failures: list[tuple[str, str]] = []
    unnamed = [one for one in case.varies if one not in direction.varies]
    if unnamed:
        failures.append((VARIES, f"the direction varies {', '.join(direction.varies)}, not {', '.join(unnamed)}"))
    if plan is None:
        return (*failures, (PLANNED, "nothing it emitted parses as a mesocycle"))
    if violations:
        failures.append((PLANNED, "; ".join(f"{one.rule}: {one.says}" for one in violations)))
    ids, before = _ids(plan), _ids(ended)
    if case.changes and not moved(ended, plan):
        failures.append((CHANGED, "the same exercises, reps and rest as the mesocycle that ended"))
    missing = [" or ".join(any_of) for any_of in case.keeps if not set(any_of) & ids]
    if missing:
        failures.append((KEPT, f"missing {', '.join(missing)}"))
    kept = {one for any_of in case.keeps for one in any_of}
    if case.rotates and before - kept and not (before - kept) - ids:
        failures.append((ROTATED, f"every other exercise is back: {', '.join(sorted(before - kept))}"))
    back = sorted(set(case.without) & ids)
    if back:
        failures.append((LEFT_OUT, f"still holds {', '.join(back)}"))
    if case.ranges:
        outside = _outside(plan, bounds)
        if outside:
            failures.append((RANGES, "; ".join(outside)))
    trend = _trend(case, ended, plan)
    if trend is not None:
        failures.append((TREND, trend))
    return tuple(failures)


def _outside(plan: plans.Mesocycle, bounds: methodology.Bounds) -> list[str]:
    """Each rep count and rest outside the goal's column, said once."""
    (low, high), (shortest, longest) = bounds.reps, bounds.rest
    reps = sorted({one for one in _reps(plan) if not low <= one <= high})
    rests = sorted({one for one in _rests(plan) if not shortest <= one <= longest})
    found = []
    if reps:
        found.append(f"reps {', '.join(map(str, reps))} outside {low}-{high}")
    if rests:
        found.append(f"rest {', '.join(f'{one}s' for one in rests)} outside {shortest}-{longest}s")
    return found


def _trend(case: supervise_set.Case, ended: plans.Mesocycle, plan: plans.Mesocycle) -> str | None:
    """Whether rest and reps moved the way the row says, by at least the move that counts."""
    rest, reps = _moved(_rests(ended), _rests(plan)), _moved(_reps(ended), _reps(plan))
    wrong = []
    if case.rest == supervise_set.SHORTER and rest > -REST_MOVE:
        wrong.append(f"mean rest moved {float(rest):+.1f}s, not shorter")
    if case.rest == supervise_set.LONGER and rest < REST_MOVE:
        wrong.append(f"mean rest moved {float(rest):+.1f}s, not longer")
    if case.reps == supervise_set.FEWER and reps > -REPS_MOVE:
        wrong.append(f"mean reps moved {float(reps):+.2f}, not fewer")
    if case.reps == supervise_set.MORE and reps < REPS_MOVE:
        wrong.append(f"mean reps moved {float(reps):+.2f}, not more")
    return "; ".join(wrong) or None


def followed(
    ended: plans.Mesocycle, direction: mesocycles.Direction, plan: plans.Mesocycle | None
) -> tuple[tuple[str, str], ...]:
    """Whether the plan changed each thing the direction says it varies, as one failure or none."""
    if plan is None:
        return ((FOLLOWED, "nothing it emitted parses as a mesocycle"),)
    changed = moved(ended, plan)
    missed = [one for one in direction.varies if one not in changed]
    if not missed:
        return ()
    return ((FOLLOWED, f"the direction varies {', '.join(missed)}; the plan changed {', '.join(changed) or 'nothing'}"),)


def render(report: eval_runner.Report, chosen: Sequence[supervise_set.Case]) -> list[str]:
    """What each row held, whether each plan followed, the failures, and $ and s per history. ASCII."""
    names = [case.name for case in chosen]
    lines = ["held", *eval_runner.matrix(report, names, [*COLUMNS, eval_runner.NOT_RUN]), ""]
    lines += [
        "followed",
        *eval_runner.matrix(report, [name + FOLLOWS for name in names], [FOLLOWED, eval_runner.NOT_RUN]),
        "",
    ]
    lines += [*eval_runner.failures(report), ""]
    lines += directions(report, chosen)
    lines += per_history(report, chosen)
    lines += eval_runner.totals(report, "held what their row declares")
    return lines


def directions(report: eval_runner.Report, chosen: Sequence[supervise_set.Case]) -> list[str]:
    """Each direction written, one line a run, so the theme can be read beside the numbers."""
    lines = ["directions"]
    for case in chosen:
        for outcome in report.outcomes:
            if outcome.case == case.name and isinstance(outcome.record, eval_runner.Talked):
                lines.append(f"  {case.name} #{outcome.attempt}: {outcome.record.conversation[0][1]}")
    return [*lines, ""]


def per_history(report: eval_runner.Report, chosen: Sequence[supervise_set.Case]) -> list[str]:
    """Dollars and seconds each history took, direction and plan, averaged over its runs."""
    lines = ["per history"]
    for case in chosen:
        runs: dict[int, list[eval_runner.Talked]] = {}
        for outcome in report.outcomes:
            if outcome.case in (case.name, case.name + FOLLOWS) and isinstance(outcome.record, eval_runner.Talked):
                runs.setdefault(outcome.attempt, []).append(outcome.record)
        if not runs:
            lines.append(f"  {case.name}: not run")
            continue
        seconds = [sum(one.seconds for one in made) for made in runs.values()]
        priced = [sum(one.dollars or 0.0 for one in made) for made in runs.values()]
        lines.append(
            f"  {case.name}: ${sum(priced) / len(priced):.4f}, "
            f"{math.floor(min(seconds))}-{math.ceil(max(seconds))}s over {len(runs)} runs"
        )
    return [*lines, ""]

