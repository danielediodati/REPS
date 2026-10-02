"""The adaptation suite: messages routed by a scripted entrance, plans held by code."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from conftest import enrich, make_exercise
from test_planner import Scripted
from trainer import adapt_evaluation, adapt_set, evaluation
from trainer import plan as plans
from trainer.coach import conclusions, entrance, models, planner
from trainer.engine import catalog, database, exclusions, mesocycles, migrations

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(id="Romanian_Deadlift", name="Romanian Deadlift", primary_muscles=("hamstrings",)),
    make_exercise(
        id="Dumbbell_Bench_Press",
        name="Dumbbell Bench Press",
        equipment="dumbbell",
        primary_muscles=("chest",),
    ),
    make_exercise(id="Pushups", name="Pushups", equipment="body only", primary_muscles=("chest",)),
)

PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Romanian_Deadlift": ("hip hinge", "hip, lumbar spine", "yes", "medium", 2),
    "Dumbbell_Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 1),
    "Pushups": ("horizontal push", "shoulder, elbow", "no", "low", 0),
}

SET = """\
today = "2026-10-01"

[bars]
routed = 80

[declared]
cycle_length = 2
duration_cap_min = 45
split = [["legs"], ["chest"]]
equipment = ["barbell", "dumbbell"]
goal = "hypertrophy"

[mesocycle]
cycles = 3
why = "three to settle"

[[mesocycle.slots]]
blocks = [{ rounds = 4, rest = 120, reason = "squat", items = [{ exercise_id = "Barbell_Squat", prescription = { unit = "reps", amount = 8 } }] }]

[[mesocycle.slots]]
blocks = [{ rounds = 4, rest = 90, reason = "press", items = [{ exercise_id = "Dumbbell_Bench_Press", prescription = { unit = "reps", amount = 10 } }] }]

[[cases]]
name = "hinge"
says = "oggi stacchi rumeni"
goes = "adapt_this_workout"
holds = ["Romanian_Deadlift"]

[[cases]]
name = "bought"
says = "ho comprato un bilanciere"
goes = "change_declaration"

[[cases]]
name = "which"
says = "niente squat"
goes = "ask"

[[cases]]
name = "hate"
says = "odio la panca"
goes = "remember"

[[cases]]
name = "excluded"
says = "oggi stacchi rumeni"
goes = "adapt_this_workout"
excluded = ["hip hinge"]
without_pattern = ["hip hinge"]
told = true
"""


@pytest.fixture()
def source(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


@pytest.fixture()
def holds() -> adapt_set.AdaptSet:
    return adapt_set.parse(SET)


@pytest.fixture()
def where(
    source: sqlite3.Connection, holds: adapt_set.AdaptSet
) -> Iterator[adapt_evaluation.Fixture]:
    with adapt_evaluation.prepared(source, holds) as prepared:
        yield prepared


def says(line: str) -> AIMessage:
    return AIMessage(content=line)


def calls(*made: tuple[str, dict[str, Any]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{n}", "type": "tool_call"}
            for n, (name, args) in enumerate(made)
        ],
    )


def chat(model: Scripted) -> models.Chat:
    return models.Chat(model, "scripted", "a-stand-in")


def case_of(holds: adapt_set.AdaptSet, name: str) -> adapt_set.Case:
    return next(case for case in holds.cases if case.name == name)


def ran(
    where: adapt_evaluation.Fixture,
    case: adapt_set.Case,
    tmp_path: Path,
    *turns: AIMessage,
    emitted: tuple[plans.WorkoutPlan, ...] = (),
) -> evaluation.Report:
    plans_on = chat(Scripted(turns=[says("ho quello che serve")] * 3, documents=list(emitted)))
    return adapt_evaluation.run(
        where,
        [case],
        front=chat(Scripted(turns=list(turns))),
        plans_on=plans_on,
        repetitions=1,
        records=tmp_path / "records",
    )


def outcome_of(report: evaluation.Report, case: str) -> evaluation.Outcome:
    (outcome,) = [o for o in report.outcomes if o.case == case]
    assert outcome.error is None, outcome.error
    return outcome


def failed(report: evaluation.Report, case: str) -> list[str]:
    return [name for name, _ in outcome_of(report, case).failures]


def plan_of(*ids: str, note: str = "", rounds: int = 3) -> plans.AdaptedPlan:
    return plans.AdaptedPlan.model_validate(
        {
            "counts_as": 1,
            "note": note,
            "blocks": [
                {
                    "items": [{"exercise_id": one, "prescription": {"unit": "reps", "amount": 8}}],
                    "rounds": rounds,
                    "rest": 90,
                    "reason": "work",
                }
                for one in ids
            ]
        }
    )


def test_the_fixture_is_the_one_trainer_db_names_with_the_sets_mesocycle_at_its_first_slot(
    where: adapt_evaluation.Fixture,
) -> None:
    assert Path(os.environ[database.DATABASE_ENV_VAR]) == where.path
    today = mesocycles.today(where.connection)
    assert (today.slot, today.slots, today.cycles) == (1, 2, 3)
    assert where.cap == 45


def test_a_cases_exclusion_holds_while_it_runs_and_is_gone_after(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet
) -> None:
    with adapt_evaluation.excluding(where, case_of(holds, "excluded")):
        inside = exclusions.active(where.connection, "2026-10-01")
    assert inside == (exclusions.Exclusion("pattern", "hip hinge"),)
    assert exclusions.active(where.connection, "2026-10-01") == ()


def test_what_the_catalog_cannot_hold_is_a_problem_before_any_run(
    source: sqlite3.Connection,
) -> None:
    holds = adapt_set.parse(
        SET.replace('holds = ["Romanian_Deadlift"]', 'holds = ["Bulgarian_Split_Squat"]\nequipment = ["kettlebells"]')
    )

    found = adapt_evaluation.problems(source, holds)

    assert any("Bulgarian_Split_Squat" in line for line in found)
    assert any("kettlebells" in line for line in found)
    assert adapt_evaluation.problems(source, adapt_set.parse(SET)) == ()


def test_a_message_handed_where_its_row_says_holds_and_elsewhere_fails_routed(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet, tmp_path: Path
) -> None:
    bought = case_of(holds, "bought")

    right = ran(where, bought, tmp_path, calls((entrance.CHANGE_DECLARATION, {"said": bought.says})), says("Aggiorno."))
    wrong = ran(where, bought, tmp_path, calls((entrance.CHANGE_MESOCYCLE, {"said": bought.says})), says("Cambio."))

    assert failed(right, "bought") == []
    assert failed(wrong, "bought") == [adapt_evaluation.ROUTED]


def test_asking_holds_and_acting_where_the_row_asks_counts_double(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet, tmp_path: Path
) -> None:
    which = case_of(holds, "which")

    asked = ran(where, which, tmp_path, says("Solo oggi o da ora in poi?"))
    acted = ran(where, which, tmp_path, calls((entrance.ADAPT_THIS_WORKOUT, {"said": which.says})), says("Adatto."))
    silent = ran(where, which, tmp_path, says("Va bene."))

    assert failed(asked, "which") == []
    assert outcome_of(acted, "which").weight == 2
    assert failed(silent, "which") == [adapt_evaluation.ROUTED]
    assert outcome_of(silent, "which").weight == 1


def test_a_fact_kept_and_nothing_started_holds_a_remember_row(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet, tmp_path: Path
) -> None:
    hate = case_of(holds, "hate")

    kept = ran(
        where,
        hate,
        tmp_path,
        calls((conclusions.REMEMBER, {"conclusion": "non ama la panca", "quote": hate.says})),
        says("Me lo segno."),
    )
    forgot = ran(where, hate, tmp_path, says("Capito."))

    assert failed(kept, "hate") == []
    assert failed(forgot, "hate") == [adapt_evaluation.ROUTED]


def test_a_note_naming_the_retest_holds_a_told_row(where: adapt_evaluation.Fixture) -> None:
    told = adapt_set.Case(name="c", says="", goes=entrance.ADAPT_THIS_WORKOUT, told=True)

    assert held(where, told, plan_of("Pushups", note="esclusi fino al 2026-11-13")) == []
    assert held(where, told, plan_of("Pushups")) == [adapt_evaluation.TOLD]
    assert held(where, told, plan_of("Pushups", note="esclusi per ora")) == [adapt_evaluation.TOLD]


def test_an_adaptation_started_is_planned_and_held_against_its_row(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet, tmp_path: Path
) -> None:
    hinge = case_of(holds, "hinge")

    report = ran(
        where,
        hinge,
        tmp_path,
        calls((entrance.ADAPT_THIS_WORKOUT, {"said": hinge.says})),
        says("Ci lavoro."),
        emitted=(plan_of("Barbell_Squat"),) * planner.ATTEMPTS,
    )

    assert failed(report, "hinge") == []
    assert adapt_evaluation.ASKED_FOR in failed(report, "hinge plan")
    assert (tmp_path / "records" / "hinge-1-plan.json").is_file()


def test_a_message_that_never_started_an_adaptation_has_no_plan_to_hold(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet, tmp_path: Path
) -> None:
    report = ran(where, case_of(holds, "hinge"), tmp_path, says("Ciao!"))

    assert [o.case for o in report.outcomes] == ["hinge"]


def held(where: adapt_evaluation.Fixture, case: adapt_set.Case, plan: plans.WorkoutPlan) -> list[str]:
    return [
        name
        for name, _ in adapt_evaluation.held(
            where.connection, case, plan, (), cap=where.cap, retest="2026-11-13"
        )
    ]


def test_a_plan_is_held_on_what_it_holds_and_leaves_out(where: adapt_evaluation.Fixture) -> None:
    case = adapt_set.Case(
        name="c",
        says="",
        goes=entrance.ADAPT_THIS_WORKOUT,
        holds=("Romanian_Deadlift",),
        without_pattern=("squat",),
        without_named=("bench press",),
    )

    assert held(where, case, plan_of("Romanian_Deadlift", "Pushups")) == []
    assert held(where, case, plan_of("Barbell_Squat")) == [
        adapt_evaluation.ASKED_FOR,
        adapt_evaluation.LEFT_OUT,
    ]
    assert held(where, case, plan_of("Romanian_Deadlift", "Dumbbell_Bench_Press")) == [
        adapt_evaluation.LEFT_OUT
    ]


def test_a_plan_is_held_on_its_equipment_workout_and_minutes(where: adapt_evaluation.Fixture) -> None:
    bare = adapt_set.Case(name="c", says="", goes=entrance.ADAPT_THIS_WORKOUT, equipment=("body only",))
    no_legs = adapt_set.Case(name="c", says="", goes=entrance.ADAPT_THIS_WORKOUT, untrained=("legs",))
    one_minute = adapt_set.Case(name="c", says="", goes=entrance.ADAPT_THIS_WORKOUT, minutes=1)

    assert held(where, bare, plan_of("Pushups")) == []
    assert held(where, bare, plan_of("Dumbbell_Bench_Press")) == [adapt_evaluation.EQUIPMENT]
    assert held(where, no_legs, plan_of("Pushups")) == []
    assert held(where, no_legs, plan_of("Romanian_Deadlift")) == [adapt_evaluation.WORKOUT]
    assert held(where, one_minute, plan_of("Barbell_Squat", "Romanian_Deadlift")) == [
        adapt_evaluation.MINUTES
    ]


def test_longer_holds_a_plan_that_runs_past_the_cap(where: adapt_evaluation.Fixture) -> None:
    longer = adapt_set.Case(name="c", says="", goes=entrance.ADAPT_THIS_WORKOUT, longer=True)

    assert held(where, longer, plan_of("Pushups")) == [adapt_evaluation.LONGER]
    assert held(where, longer, plan_of("Pushups", "Barbell_Squat", rounds=20)) == []


def test_a_plan_the_validator_refused_or_that_never_parsed_fails_planned(
    where: adapt_evaluation.Fixture,
) -> None:
    case = adapt_set.Case(name="c", says="", goes=entrance.ADAPT_THIS_WORKOUT)
    refused = adapt_evaluation.held(
        where.connection,
        case,
        plan_of("Pushups"),
        (plans.Violation(plans.COUNTS_AS, "workout 9"),),
        cap=45,
        retest="2026-11-13",
    )
    nothing = adapt_evaluation.held(where.connection, case, None, (), cap=45, retest="2026-11-13")

    assert [name for name, _ in refused] == [adapt_evaluation.PLANNED]
    assert [name for name, _ in nothing] == [adapt_evaluation.PLANNED]


def test_the_plans_are_held_at_100_and_the_routes_at_the_sets_bar(holds: adapt_set.AdaptSet) -> None:
    def outcome(case: str, held: bool) -> evaluation.Outcome:
        return evaluation.Outcome(case, 1, () if held else (("x", "y"),))

    routes = [outcome(case.name, n != 0) for n, case in enumerate(holds.cases)]
    held_plan = evaluation.Report((*routes, outcome("hinge plan", True)))
    broken_plan = evaluation.Report((*routes, outcome("hinge plan", False)))

    assert adapt_evaluation.barred(held_plan, holds).passed
    assert not adapt_evaluation.barred(broken_plan, holds).passed


def test_the_rendered_pass_is_ascii_with_cost_per_message(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet, tmp_path: Path
) -> None:
    bought = case_of(holds, "bought")
    report = ran(where, bought, tmp_path, calls((entrance.CHANGE_DECLARATION, {"said": bought.says})), says("Aggiorno."))

    lines = adapt_evaluation.render(adapt_evaluation.barred(report, holds), [bought])

    assert all(line.isascii() for line in lines)
    assert any(line.startswith("  bought: $") for line in lines)


def test_a_planner_run_that_fails_on_an_empty_message_still_says_what_failed(
    where: adapt_evaluation.Fixture,
    holds: adapt_set.AdaptSet,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError()

    monkeypatch.setattr(planner, "build", broken)
    hinge = case_of(holds, "hinge")

    report = ran(where, hinge, tmp_path, calls((entrance.ADAPT_THIS_WORKOUT, {"said": hinge.says})), says("Ok."))

    (plan,) = [o for o in report.outcomes if o.case == "hinge plan"]
    assert plan.error == "AssertionError: "
