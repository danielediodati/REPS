"""The adaptation set's rows for this workout, as the requests `adapt_this_workout` assembles from them."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich, make_exercise
from trainer import adapt_evaluation, adapt_set, tools
from trainer import plan as plans
from trainer.coach import entrance, planner
from trainer.engine import catalog, database, duration, migrations

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(id="Romanian_Deadlift", name="Romanian Deadlift", primary_muscles=("hamstrings",)),
    make_exercise(
        id="Split_Squat_with_Dumbbells",
        name="Split Squat with Dumbbells",
        equipment="dumbbell",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(id="Plank", name="Plank", equipment="body only", primary_muscles=("abdominals",)),
    make_exercise(
        id="Kettlebell_Goblet_Squat",
        name="Kettlebell Goblet Squat",
        equipment="kettlebells",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Barbell_Bench_Press_-_Medium_Grip",
        name="Barbell Bench Press - Medium Grip",
        primary_muscles=("chest",),
    ),
    make_exercise(id="Pullups", name="Pullups", equipment="body only", primary_muscles=("lats",)),
    make_exercise(id="Bent_Over_Barbell_Row", name="Bent Over Barbell Row", primary_muscles=("middle back",)),
)

PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Romanian_Deadlift": ("hip hinge", "hip, lumbar spine", "yes", "medium", 2),
    "Split_Squat_with_Dumbbells": ("lunge", "hip, knee, ankle", "no", "medium", 1),
    "Plank": ("isolation", "shoulder", "no", "low", 0),
    "Kettlebell_Goblet_Squat": ("squat", "hip, knee, ankle", "no", "medium", 1),
    "Barbell_Bench_Press_-_Medium_Grip": ("horizontal push", "shoulder, elbow", "no", "medium", 2),
    "Pullups": ("vertical pull", "shoulder, elbow", "no", "medium", 0),
    "Bent_Over_Barbell_Row": ("horizontal pull", "shoulder, elbow, lumbar spine", "yes", "medium", 2),
}


def one(exercise_id: str) -> str:
    return (
        '{ rounds = 4, rest = 90, reason = "work", items = [{ exercise_id = "'
        + exercise_id
        + '", prescription = { unit = "reps", amount = 8 } }] }'
    )


SET = f"""\
today = "2026-10-01"

[bars]
routed = 80

[declared]
cycle_length = 3
duration_cap_min = 45
split = [["legs", "core"], ["chest", "shoulders", "arms"], ["back", "arms"]]
equipment = ["barbell", "dumbbell", "body only"]
goal = "hypertrophy"

[mesocycle]
cycles = 4
why = "four cycles to settle the loads"

[[mesocycle.slots]]
blocks = [{one("Barbell_Squat")}, {one("Plank")}]

[[mesocycle.slots]]
blocks = [{one("Barbell_Bench_Press_-_Medium_Grip")}]

[[mesocycle.slots]]
blocks = [{one("Bent_Over_Barbell_Row")}]

[[cases]]
name = "hinge-excluded"
says = "oggi stacchi rumeni"
goes = "adapt_this_workout"
excluded = ["hip hinge"]
without_pattern = ["hip hinge"]
told = true
"""


@pytest.fixture()
def holds() -> adapt_set.AdaptSet:
    return adapt_set.parse(SET)


@pytest.fixture()
def where(database_file: Path, holds: adapt_set.AdaptSet) -> Iterator[adapt_evaluation.Fixture]:
    with closing(database.connect(database_file)) as source:
        migrations.migrate(source, migrations.discover())
        catalog.import_exercises(source, CATALOG)
        enrich(source, PATTERNS)
        with adapt_evaluation.prepared(source, holds) as prepared:
            yield prepared


def asked(where: adapt_evaluation.Fixture, said: str) -> plans.Request:
    request = entrance.requested(where.connection, entrance.ADAPT_THIS_WORKOUT, {"said": said})
    assert isinstance(request, plans.Request)
    assert request.adapting is not None
    return request


def adapted(*exercise_ids: str, counts_as: int = 1, rounds: int = 4, note: str = "") -> plans.AdaptedPlan:
    return plans.parse_adapted(
        json.dumps(
            {
                "blocks": [
                    {
                        "rounds": rounds,
                        "rest": 90,
                        "reason": "work",
                        "items": [
                            {"exercise_id": one, "prescription": {"unit": "reps", "amount": 8}}
                        ],
                    }
                    for one in exercise_ids
                ],
                "despite": [],
                "counts_as": counts_as,
                "note": note,
            }
        )
    )


def violations(where: adapt_evaluation.Fixture, request: plans.Request, plan: plans.WorkoutPlan) -> list[str]:
    return [v.rule for v in plans.validate(where.connection, plans.to_blocks(plan), request, plan)]


def test_the_request_is_their_words_with_the_mesocycle_as_a_starting_point(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(where, "oggi niente squat, stacchi rumeni in superset con i bulgari")

    assert request.adapting is not None
    assert request.adapting.said == "oggi niente squat, stacchi rumeni in superset con i bulgari"
    assert (request.adapting.slot, request.adapting.still) == (1, (1, 2, 3))
    assert request.adapting.split == ("legs, core", "chest, shoulders, arms", "back, arms")
    assert len(request.adapting.cycle) == 3
    assert (request.adapting.usual_minutes, request.adapting.usual_equipment) == (
        45,
        ("barbell", "dumbbell", "body only"),
    )


def test_neither_the_groups_nor_the_declared_equipment_bind_it(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(where, "mi hanno prestato una kettlebell, usiamola oggi")

    assert request.groups == ()
    assert "kettlebells" in request.equipment
    assert violations(where, request, adapted("Kettlebell_Goblet_Squat")) == []


def test_2_no_legs_today_is_a_plan_of_another_workout_counted_as_it(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(where, "oggi niente gambe che stasera gioco a calcio")

    assert violations(where, request, adapted("Barbell_Bench_Press_-_Medium_Grip", counts_as=2)) == []


def test_core_but_no_legs_is_a_plan_the_slots_groups_never_described(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(where, "oggi faccio il core ma niente gambe")

    assert violations(where, request, adapted("Plank", counts_as=1)) == []


def test_5_more_time_than_the_usual_is_no_violation(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi ho tempo, metti un esercizio in più per gruppo")
    long = adapted("Barbell_Squat", "Romanian_Deadlift", "Split_Squat_with_Dumbbells", "Plank", rounds=12)

    assert duration.plan_duration(where.connection, plans.to_blocks(long)) > where.cap
    assert violations(where, request, long) == []


def test_it_counts_as_a_workout_still_to_do(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi niente gambe")

    assert violations(where, request, adapted("Plank", counts_as=4)) == [plans.COUNTS_AS]


def test_a_plain_workout_plan_does_not_say_what_it_counts_as(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi niente gambe")
    plan = plans.WorkoutPlan.model_validate(adapted("Plank").model_dump(exclude={"counts_as", "note"}))

    assert violations(where, request, plan) == [plans.COUNTS_AS]


def test_16_an_exclusion_still_binds_and_the_planner_is_told_its_retest(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet
) -> None:
    case = next(case for case in holds.cases if case.name == "hinge-excluded")
    with adapt_evaluation.excluding(where, case) as retest:
        request = asked(where, case.says)
        refused = violations(where, request, adapted("Romanian_Deadlift"))

    assert refused == [plans.ADMISSIBLE]
    assert request.adapting is not None
    assert request.adapting.retests == (f"pattern hip hinge until {retest}",)


def test_the_workout_due_today_is_read_with_its_exercises_by_name(where: adapt_evaluation.Fixture) -> None:
    """What the entrance reads to tell whether what they ask is already in it."""
    due = tools.due_workout()

    assert (due["workout"], due["of"], due["trains"]) == (1, 3, ["legs", "core"])
    named = {item["exercise_id"]: item["name"] for block in due["blocks"] for item in block["items"]}
    assert named == {"Barbell_Squat": "Barbell Squat", "Plank": "Plank"}


def test_the_entrance_reads_the_workout_due_and_the_planner_does_not() -> None:
    assert "due_workout" in entrance.TOOLS
    assert "due_workout" not in planner.TOOLS
