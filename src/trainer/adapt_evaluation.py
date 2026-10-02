"""The adaptation suite: messages through the entrance, and every adaptation planned and held by code."""

from __future__ import annotations

import json
import math
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
from langgraph.store.memory import InMemoryStore

from trainer import adapt_set, evaluation, tools
from trainer import plan as plans
from trainer.coach import checkpoints, conclusions, entrance, models, onboarding, planner
from trainer.coach import record as run_record
from trainer.engine import (
    catalog,
    config,
    database,
    duration,
    exclusions,
    mesocycles,
    muscle_groups,
    workouts,
)
from trainer.onboarding_evaluation import Talked

ROUTED = "routed"
PLANNED = "planned"
ASKED_FOR = "asked for"
LEFT_OUT = "left out"
EQUIPMENT = "equipment"
MINUTES = "minutes"
WORKOUT = "workout"
LONGER = "longer"
TOLD = "told"
COLUMNS = (PLANNED, ASKED_FOR, LEFT_OUT, EQUIPMENT, MINUTES, WORKOUT, LONGER, TOLD)

PLAN = " plan"
"""Appended to a case's name for its adapted plan, the half code holds at 100%."""

USER = "eval"
RETEST = timedelta(weeks=6)
"""How far off a case's exclusion is re-tested: well past the run."""


def retested() -> str:
    """The re-test date a case's exclusion is written with, and a refusal must name."""
    return (date.today() + RETEST).isoformat()


@dataclass(frozen=True)
class Fixture:
    """The copy the suite runs against, with the set's declaration and mesocycle in force."""

    connection: sqlite3.Connection
    path: Path
    cap: int


@contextmanager
def prepared(source: sqlite3.Connection, holds: adapt_set.AdaptSet) -> Iterator[Fixture]:
    """A copy of `source` holding only the set's declaration and mesocycle, named in `TRAINER_DB` while it is open."""
    directory = Path(tempfile.mkdtemp(prefix="reps-adapt-eval-"))
    previous = os.environ.get(database.DATABASE_ENV_VAR)
    connection = database.connect(directory / "eval.sqlite")
    try:
        source.backup(connection)
        for table in (
            "served",
            "workout_exercises",
            "workout_blocks",
            "workouts",
            "mesocycle_exercises",
            "mesocycle_blocks",
            "mesocycles",
            "declarations",
            "exclusions",
        ):
            connection.execute(f"DELETE FROM {table}")
        declared = onboarding.settled(dict(holds.declared))
        config.record(connection, declared, holds.today)
        mesocycles.record_mesocycle(
            connection,
            tuple(
                tuple(
                    workouts.PrescribedBlock(block=costed, reason=shape.reason)
                    for shape, costed in zip(workout.blocks, plans.to_blocks(workout), strict=True)
                )
                for workout in holds.mesocycle.workouts
            ),
            cycles=holds.mesocycle.cycles,
            why=holds.mesocycle.why,
            on=holds.today,
        )
        os.environ[database.DATABASE_ENV_VAR] = str(directory / "eval.sqlite")
        yield Fixture(connection, directory / "eval.sqlite", declared.duration_cap_min)
    finally:
        connection.close()
        if previous is None:
            os.environ.pop(database.DATABASE_ENV_VAR, None)
        else:
            os.environ[database.DATABASE_ENV_VAR] = previous
        shutil.rmtree(directory, ignore_errors=True)


@contextmanager
def excluding(where: Fixture, case: adapt_set.Case) -> Iterator[str]:
    """The case's own exclusions in force while it runs, and gone after; yields their re-test date."""
    retest = retested()
    for value in case.excluded:
        exclusions.add(where.connection, exclusions.classify(where.connection, value), retest)
    try:
        yield retest
    finally:
        where.connection.execute("DELETE FROM exclusions")


def problems(connection: sqlite3.Connection, holds: adapt_set.AdaptSet) -> tuple[str, ...]:
    """What in the set disagrees with this catalog, before anything is paid for."""
    found: list[str] = []
    try:
        declared = onboarding.settled(dict(holds.declared))
    except config.ConfigError as error:
        found.append(f"[declared] is not a declaration: {error}")
        declared = None
    known_equipment = set(catalog.values(connection, "equipment"))
    known_patterns = set(catalog.values(connection, "movement_pattern"))
    groups = set(muscle_groups.groups())
    named = {
        item.exercise_id
        for workout in holds.mesocycle.workouts
        for block in workout.blocks
        for item in block.items
    }
    if declared is not None:
        found += [f"[declared]: no equipment called {one}" for one in declared.equipment if one not in known_equipment]
        if declared.cycle_length != len(holds.mesocycle.workouts):
            found.append(
                f"[mesocycle] has {len(holds.mesocycle.workouts)} slots for a cycle of {declared.cycle_length}"
            )
    for case in holds.cases:
        named |= {one for any_of in case.holds for one in any_of}
        found += [f"{case.name}: no equipment called {one}" for one in case.equipment if one not in known_equipment]
        found += [f"{case.name}: no pattern called {one}" for one in case.without_pattern if one not in known_patterns]
        found += [f"{case.name}: no group called {one}" for one in case.untrained if one not in groups]
        for value in case.excluded:
            try:
                exclusions.classify(connection, value)
            except exclusions.ExclusionError:
                found.append(f"{case.name}: {value!r} is not a pattern or a joint")
    found += [f"the catalog has no exercise {one}" for one in sorted(named) if catalog.exercise(connection, one) is None]
    return tuple(found)


def run(
    where: Fixture,
    chosen: Sequence[adapt_set.Case],
    *,
    front: models.Chat,
    plans_on: models.Chat | None,
    repetitions: int = evaluation.REPETITIONS,
    records: Path | None = None,
    budget: int = tools.CALL_BUDGET,
) -> evaluation.Report:
    """Every case, every repetition: the message on `front`, and an adaptation planned on `plans_on`."""
    into = records if records is not None else evaluation.records_path()
    planned: list[evaluation.Outcome] = []
    report = evaluation.measured(
        [case.name for case in chosen],
        repetitions,
        lambda at, attempt: _once(where, chosen[at], attempt, front, plans_on, budget, into, planned),
    )
    return replace(report, outcomes=(*report.outcomes, *planned))


def _once(
    where: Fixture,
    case: adapt_set.Case,
    attempt: int,
    front: models.Chat,
    plans_on: models.Chat | None,
    budget: int,
    records: Path,
    planned: list[evaluation.Outcome],
) -> evaluation.Outcome:
    """One message routed and scored; when it started an adaptation, the plan too, into `planned`."""
    with excluding(where, case) as retest:
        try:
            talked, final = _routed(case, front, budget)
        except Exception as error:
            if (quota := models.spent(error)) is not None:
                raise quota from error
            return evaluation.Outcome(case.name, attempt, error=str(error))
        written = evaluation.write(records, f"{case.name}-{attempt}", talked.written)
        failures = routing(case, final)
        acted = bool(final.get("handoff"))
        weight = 2 if failures and case.goes == adapt_set.ASK and acted else 1
        routed = evaluation.Outcome(case.name, attempt, failures, talked, written, weight=weight)
        if case.planned and final.get("handoff") == entrance.ADAPT_THIS_WORKOUT:
            assert plans_on is not None
            planned.append(
                _planned(where, case, attempt, dict(final.get("asked", {})), plans_on, budget, records, retest)
            )
    return routed


def _routed(
    case: adapt_set.Case, on: models.Chat, budget: int
) -> tuple[Talked, Mapping[str, Any]]:
    """One message through the entrance, reading today's workout and checking requests off the fixture."""
    started = time.monotonic()
    store = InMemoryStore()
    graph = entrance.build(
        on,
        budget=budget,
        checkpointer=InMemorySaver(serde=checkpoints.Declared()),
        store=store,
    )
    thread: RunnableConfig = {"configurable": {"thread_id": f"adapt:{uuid4()}", conclusions.USER: USER}}
    final = dict(graph.invoke(entrance.heard(case.says), thread))
    final["kept"] = [one.quote for one in conclusions.live(store, USER)]
    talked = Talked(
        record=run_record.of(final, budget),
        conversation=(("user", case.says), ("agent", str(final.get("answer", "")))),
        seconds=time.monotonic() - started,
    )
    return talked, final


def routing(case: adapt_set.Case, final: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Whether the message went where its row says, as one failure or none."""
    handoff = str(final.get("handoff", ""))
    answer = str(final.get("answer", ""))
    went = handoff or "nothing"
    if case.goes in adapt_set.HANDED:
        wrong = handoff != case.goes
    elif case.goes in adapt_set.ASKING:
        wrong = bool(handoff) or "?" not in answer
    else:
        wrong = bool(handoff) or not final.get("kept")
        went = f"{went}, {len(final.get('kept', ()))} kept"
    if not wrong:
        return ()
    return ((ROUTED, f"went to {went}: {answer!r}"),)


def _planned(
    where: Fixture,
    case: adapt_set.Case,
    attempt: int,
    asked: Mapping[str, Any],
    on: models.Chat,
    budget: int,
    records: Path,
    retest: str,
) -> evaluation.Outcome:
    """The adaptation the entrance started, planned, and held against the row."""
    name = case.name + PLAN
    started = time.monotonic()
    try:
        request = entrance.requested(where.connection, entrance.ADAPT_THIS_WORKOUT, asked)
        assert isinstance(request, plans.Request)
        graph = planner.build(on, budget=budget, checkpointer=InMemorySaver(serde=checkpoints.Declared()))
        thread: RunnableConfig = {"configurable": {"thread_id": f"adapt-plan:{uuid4()}"}}
        final = graph.invoke(planner.starting(request), thread)
    except Exception as error:
        if (quota := models.spent(error)) is not None:
            raise quota from error
        return evaluation.Outcome(name, attempt, error=f"{type(error).__name__}: {error}")
    talked = Talked(
        record=run_record.of(final, budget),
        conversation=(("user", case.says),),
        seconds=time.monotonic() - started,
    )
    written = evaluation.write(records, f"{case.name}-{attempt}-plan", talked.written)
    failures = held(
        where.connection,
        case,
        final.get("plan"),
        tuple(final.get("violations", ())),
        cap=where.cap,
        retest=retest,
    )
    return evaluation.Outcome(name, attempt, failures, talked, written)


def held(
    connection: sqlite3.Connection,
    case: adapt_set.Case,
    plan: plans.WorkoutPlan | None,
    violations: Sequence[plans.Violation],
    *,
    cap: int,
    retest: str,
) -> tuple[tuple[str, str], ...]:
    """Every check code holds at 100% on one adapted plan."""
    if plan is None:
        return ((PLANNED, "nothing it emitted parses as a workout"),)
    failures: list[tuple[str, str]] = []
    if violations:
        failures.append((PLANNED, "; ".join(f"{one.rule}: {one.says}" for one in violations)))
    ids = list(dict.fromkeys(plans.exercise_ids(plan)))
    rows = {
        str(row["id"]): row
        for row in connection.execute(
            "SELECT id, name, equipment, movement_pattern, primary_muscles FROM exercises "
            f"WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        )
    }
    missing = [" or ".join(any_of) for any_of in case.holds if not set(any_of) & set(ids)]
    if missing:
        failures.append((ASKED_FOR, f"missing {', '.join(missing)}"))
    named = [n.lower() for n in case.without_named]
    left = [
        one
        for one in ids
        if one in rows
        and (
            rows[one]["movement_pattern"] in case.without_pattern
            or any(n in str(rows[one]["name"]).lower() for n in named)
        )
    ]
    if left:
        failures.append((LEFT_OUT, f"still holds {', '.join(left)}"))
    if case.equipment:
        off = [f"{one} needs {rows[one]['equipment']}" for one in ids if one in rows and rows[one]["equipment"] not in case.equipment]
        if off:
            failures.append((EQUIPMENT, "; ".join(off)))
    if case.minutes is not None or case.longer:
        try:
            spent = duration.plan_duration(connection, plans.to_blocks(plan))
        except (plans.PlanError, duration.DurationError) as error:
            failures.append((MINUTES, f"it cannot be costed: {error}"))
        else:
            if case.minutes is not None and not plans.window(case.minutes)[0] <= spent <= plans.window(case.minutes)[1]:
                failures.append((MINUTES, f"runs {spent} min against {case.minutes} asked"))
            if case.longer and spent <= cap:
                failures.append((LONGER, f"runs {spent} min against a cap of {cap}"))
    if case.untrained:
        mapping = muscle_groups.committed()
        trained = [
            one
            for one in ids
            if one in rows
            and any(_group(mapping, muscle) in case.untrained for muscle in json.loads(rows[one]["primary_muscles"]))
        ]
        if trained:
            failures.append((WORKOUT, f"trains {', '.join(case.untrained)}: {', '.join(trained)}"))
    if case.told and (not isinstance(plan, plans.AdaptedPlan) or retest not in plan.note):
        failures.append((TOLD, f"the note does not name the re-test on {retest}"))
    return tuple(failures)


def _group(mapping: muscle_groups.MuscleGroups, muscle: str) -> str | None:
    try:
        return mapping.group_of(muscle)
    except KeyError:
        return None


def barred(report: evaluation.Report, holds: adapt_set.AdaptSet) -> evaluation.Report:
    """The pass against its bars: 100% on the adapted plans, the set's own on where messages go."""
    return replace(
        report,
        halves=(
            evaluation.Half("held", frozenset(case.name + PLAN for case in holds.cases if case.planned), 100),
            evaluation.Half("routed", frozenset(case.name for case in holds.cases), holds.bar_routed),
        ),
    )


def render(report: evaluation.Report, chosen: Sequence[adapt_set.Case]) -> list[str]:
    """Where each message went, what each plan held, the failures, and $ and s per message. ASCII."""
    names = [case.name for case in chosen]
    lines = ["routing", *evaluation.matrix(report, names, [ROUTED, evaluation.NOT_RUN]), ""]
    planned = [case.name + PLAN for case in chosen if case.planned]
    if planned:
        lines += ["adapted plans", *evaluation.matrix(report, planned, [*COLUMNS, evaluation.NOT_RUN]), ""]
    about = {case.name: f"{case.says} -> {case.goes}" for case in chosen}
    about |= {case.name + PLAN: case.says for case in chosen}
    lines += [*evaluation.failures(report, about), ""]
    lines += per_message(report, chosen)
    lines += evaluation.totals(report, "held what their row declares")
    return lines


def per_message(report: evaluation.Report, chosen: Sequence[adapt_set.Case]) -> list[str]:
    """Dollars and seconds each message took, its plan included, averaged over its runs."""
    lines = ["per message"]
    for case in chosen:
        runs: dict[int, list[Talked]] = {}
        for outcome in report.outcomes:
            if outcome.case in (case.name, case.name + PLAN) and isinstance(outcome.record, Talked):
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
