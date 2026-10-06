"""The adaptation suite: messages through the entrance, and every adaptation planned and held by code."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from langgraph.store.memory import InMemoryStore

from trainer import adapt_set, eval_runner, history
from trainer import plan as plans
from trainer.coach import conclusions, entrance, models, onboarding, planner
from trainer.coach import record as run_record
from trainer.engine import (
    catalog,
    config,
    duration,
    exclusions,
    mesocycles,
    muscle_groups,
)

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
"""Appended to a case's name for its adapted plan, the half code holds against the set's bar."""

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


EMPTIED = (
    "served",
    "workout_exercises",
    "workout_blocks",
    "workouts",
    "mesocycle_exercises",
    "mesocycle_blocks",
    "mesocycles",
    "declarations",
    "exclusions",
)


class Adapt(eval_runner.Suite[adapt_set.Case, Fixture]):
    """Messages through the entrance against an active mesocycle, and every adaptation planned and held."""

    def __init__(self, holds: adapt_set.AdaptSet) -> None:
        super().__init__(holds.cases)
        self.holds = holds

    def problems(self, connection: sqlite3.Connection) -> Sequence[str]:
        return problems(connection, self.holds)

    @contextmanager
    def fixture(self, connection: sqlite3.Connection) -> Iterator[Fixture]:
        """A copy holding only the set's declaration and mesocycle."""
        with eval_runner.copied(connection, emptied=EMPTIED) as copy:
            declared = onboarding.settled(dict(self.holds.declared))
            config.record(copy.connection, declared, self.holds.today)
            mesocycles.record_mesocycle(
                copy.connection,
                tuple(history.prescribed(workout) for workout in self.holds.mesocycle.workouts),
                cycles=self.holds.mesocycle.cycles,
                why=self.holds.mesocycle.why,
                on=self.holds.today,
            )
            yield Fixture(copy.connection, copy.path, declared.duration_cap_min)

    def nodes(self, chosen: Sequence[adapt_set.Case]) -> Sequence[models.Node]:
        """The entrance, and the planner when a chosen case is planned."""
        return ("entrance", "planner") if any(case.planned for case in chosen) else ("entrance",)

    def runs(
        self, where: Fixture, chats: models.Roster, *, records: Path, budget: int
    ) -> eval_runner.Once[adapt_set.Case]:
        return lambda case, attempt: _adapted(where, case, attempt, chats, budget, records)

    def halves(self) -> tuple[eval_runner.Half, ...]:
        """On the adapted plans, and on where messages go."""
        holds = self.holds
        return (
            eval_runner.Half("held", frozenset(case.name + PLAN for case in holds.cases if case.planned), holds.bar_held),
            eval_runner.Half("routed", frozenset(case.name for case in holds.cases), holds.bar_routed),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[adapt_set.Case]) -> list[str]:
        return render(report, chosen)


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


def _adapted(
    where: Fixture,
    case: adapt_set.Case,
    attempt: int,
    chats: models.Roster,
    budget: int,
    records: Path,
) -> tuple[eval_runner.Outcome, ...]:
    """One message routed and scored; when it started an adaptation, the plan too."""
    with excluding(where, case) as retest:
        heard: dict[str, Any] = {}

        def route() -> eval_runner.Scored:
            talked, final = _routed(case, chats["entrance"], budget)
            heard.update(final)
            failures = routing(case, final)
            acted = bool(final.get("handoff"))
            weight = 2 if failures and case.goes == adapt_set.ASK and acted else 1
            return eval_runner.Scored(talked, failures, weight)

        routed = eval_runner.attempted(case.name, attempt, records, f"{case.name}-{attempt}", route)
        if routed.error is not None or not (
            case.planned and heard.get("handoff") == entrance.ADAPT_THIS_WORKOUT
        ):
            return (routed,)
        planned = eval_runner.attempted(
            case.name + PLAN,
            attempt,
            records,
            f"{case.name}-{attempt}-plan",
            lambda: _planned(where, case, dict(heard.get("asked", {})), chats["planner"], budget, retest),
            typed=True,
        )
        return (routed, planned)


def _routed(
    case: adapt_set.Case, on: models.Chat, budget: int
) -> tuple[eval_runner.Talked, Mapping[str, Any]]:
    """One message through the entrance, reading today's workout and checking requests off the fixture."""
    store = InMemoryStore()
    graph = entrance.build(on, budget=budget, checkpointer=eval_runner.checkpointer(), store=store)

    def heard() -> dict[str, Any]:
        final = dict(graph.invoke(entrance.heard(case.says), eval_runner.thread("adapt", remembers=True)))
        final["kept"] = [one.quote for one in conclusions.live(store, eval_runner.USER)]
        return final

    final, seconds = eval_runner.timed(heard)
    talked = eval_runner.Talked(
        record=run_record.of(final, budget),
        seconds=seconds,
        conversation=(("user", case.says), ("agent", str(final.get("answer", "")))),
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
    asked: Mapping[str, Any],
    on: models.Chat,
    budget: int,
    retest: str,
) -> eval_runner.Scored:
    """The adaptation the entrance started, planned, and held against the row."""
    request = entrance.requested(where.connection, entrance.ADAPT_THIS_WORKOUT, asked)
    assert isinstance(request, plans.Request)
    graph = planner.build(on, budget=budget, checkpointer=eval_runner.checkpointer())
    final, seconds = eval_runner.timed(
        lambda: graph.invoke(planner.starting(request), eval_runner.thread("adapt-plan"))
    )
    talked = eval_runner.Talked(
        record=run_record.of(final, budget),
        seconds=seconds,
        conversation=(("user", case.says),),
    )
    failures = held(
        where.connection,
        case,
        final.get("plan"),
        tuple(final.get("violations", ())),
        cap=where.cap,
        retest=retest,
    )
    return eval_runner.Scored(talked, failures)


def held(
    connection: sqlite3.Connection,
    case: adapt_set.Case,
    plan: plans.WorkoutPlan | None,
    violations: Sequence[plans.Violation],
    *,
    cap: int,
    retest: str,
) -> tuple[tuple[str, str], ...]:
    """Every check code holds on one adapted plan."""
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


def render(report: eval_runner.Report, chosen: Sequence[adapt_set.Case]) -> list[str]:
    """Where each message went, what each plan held, the failures, and $ and s per message. ASCII."""
    names = [case.name for case in chosen]
    lines = ["routing", *eval_runner.matrix(report, names, [ROUTED, eval_runner.NOT_RUN]), ""]
    planned = [case.name + PLAN for case in chosen if case.planned]
    if planned:
        lines += ["adapted plans", *eval_runner.matrix(report, planned, [*COLUMNS, eval_runner.NOT_RUN]), ""]
    about = {case.name: f"{case.says} -> {case.goes}" for case in chosen}
    about |= {case.name + PLAN: case.says for case in chosen}
    lines += [*eval_runner.failures(report, about), ""]
    lines += per_message(report, chosen)
    lines += eval_runner.totals(report, "held what their row declares")
    return lines


def per_message(report: eval_runner.Report, chosen: Sequence[adapt_set.Case]) -> list[str]:
    """Dollars and seconds each message took, its plan included, averaged over its runs."""
    lines = ["per message"]
    for case in chosen:
        runs: dict[int, list[eval_runner.Talked]] = {}
        for outcome in report.outcomes:
            if outcome.case in (case.name, case.name + PLAN) and isinstance(outcome.record, eval_runner.Talked):
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
