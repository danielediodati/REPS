"""The adaptation set's rows for this workout, as the requests `adapt_this_workout` assembles from them."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from conftest import enrich, make_exercise
from trainer import adapt_evaluation, adapt_set
from trainer import plan as plans
from trainer.coach import entrance
from trainer.engine import catalog, database, migrations

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
goes = "refused"
excluded = ["hip hinge"]
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


def asked(where: adapt_evaluation.Fixture, said: str, **args: Any) -> plans.Request:
    request = entrance.requested(
        where.connection, entrance.ADAPT_THIS_WORKOUT, {"said": said, **args}
    )
    assert isinstance(request, plans.Request)
    assert request.adapting is not None
    return request


def test_0_a_superset_leaves_the_squat_out_and_asks_for_the_hinge_and_the_split_squat(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(
        where,
        "oggi niente squat, stacchi rumeni in superset con i bulgari",
        leave_out=["Barbell_Squat"],
        ask_for=["Romanian_Deadlift", "Split_Squat_with_Dumbbells"],
    )

    assert request.adapting is not None
    assert request.adapting.left_out == ("Barbell_Squat",)
    assert request.adapting.asked_for == ("Romanian_Deadlift", "Split_Squat_with_Dumbbells")
    assert "superset" in request.adapting.said
    assert (request.adapting.slot, request.groups) == (1, ("legs", "core"))


def test_0b_you_choose_leaves_the_squat_out_and_asks_for_nothing(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(where, "oggi niente squat, proponi tu", leave_out=["Barbell_Squat"])

    assert request.adapting is not None
    assert (request.adapting.left_out, request.adapting.asked_for) == (("Barbell_Squat",), ())


def test_1_thirty_minutes(where: adapt_evaluation.Fixture) -> None:
    assert asked(where, "oggi ho 30 minuti invece di 45", minutes=30).budget_min == 30


def test_2_not_legs_is_another_of_the_cycles_workouts(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi niente gambe che stasera gioco a calcio", workout=2)

    assert request.adapting is not None
    assert request.adapting.slot == 2
    assert request.groups == ("chest", "shoulders", "arms")


def test_3_a_borrowed_kettlebell_is_this_workouts_equipment_in_full(
    where: adapt_evaluation.Fixture,
) -> None:
    request = asked(
        where,
        "mi hanno prestato una kettlebell, usiamola oggi",
        equipment=["barbell", "dumbbell", "body only", "kettlebells"],
    )

    assert request.equipment == ("barbell", "dumbbell", "body only", "kettlebells")


def test_4_away_with_nothing_but_the_body(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "sono in trasferta, solo corpo libero", equipment=["body only"])

    assert request.equipment == ("body only",)


def test_5_more_time_than_the_cap(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi ho tempo, metti un esercizio in più per gruppo", minutes=60)

    assert request.budget_min == 60 > where.cap


def test_6_dumbbells_only(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi solo manubri, la palestra è piena", equipment=["dumbbell"])

    assert request.equipment == ("dumbbell",)


def test_7_twenty_minutes_and_no_equipment(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "20 minuti e niente attrezzi", minutes=20, equipment=["body only"])

    assert (request.budget_min, request.equipment) == (20, ("body only",))


def test_8_pull_ups_on_the_legs_day_are_refused_naming_the_workout(
    where: adapt_evaluation.Fixture,
) -> None:
    said = entrance.startable(
        entrance.ADAPT_THIS_WORKOUT, {"said": "oggi vorrei fare trazioni", "ask_for": ["Pullups"]}
    )

    assert said is not None and "legs, core" in said


def test_8_the_refusal_names_the_workouts_still_to_do_by_number(
    where: adapt_evaluation.Fixture,
) -> None:
    said = entrance.startable(
        entrance.ADAPT_THIS_WORKOUT, {"said": "oggi vorrei fare trazioni", "ask_for": ["Pullups"]}
    )

    assert said is not None
    assert "`workout`" in said and "3 (back, arms)" in said and "Call it again" in said


def test_8_pull_ups_on_the_back_workout_are_asked_for(where: adapt_evaluation.Fixture) -> None:
    request = asked(where, "oggi vorrei fare trazioni", ask_for=["Pullups"], workout=3)

    assert request.adapting is not None
    assert (request.adapting.slot, request.adapting.asked_for) == (3, ("Pullups",))


def test_14_no_bench_today_leaves_it_out(where: adapt_evaluation.Fixture) -> None:
    request = asked(
        where, "oggi non ho voglia di panca", leave_out=["Barbell_Bench_Press_-_Medium_Grip"]
    )

    assert request.adapting is not None
    assert request.adapting.left_out == ("Barbell_Bench_Press_-_Medium_Grip",)


def test_16_a_hinge_under_an_exclusion_is_refused_naming_its_retest(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet
) -> None:
    case = next(case for case in holds.cases if case.name == "hinge-excluded")
    with adapt_evaluation.excluding(where, case) as retest:
        said = entrance.startable(
            entrance.ADAPT_THIS_WORKOUT, {"said": case.says, "ask_for": ["Romanian_Deadlift"]}
        )

    assert said is not None and "hip hinge" in said and retest in said


def test_16_an_exclusion_is_relayed_and_not_called_again(
    where: adapt_evaluation.Fixture, holds: adapt_set.AdaptSet
) -> None:
    case = next(case for case in holds.cases if case.name == "hinge-excluded")
    with adapt_evaluation.excluding(where, case):
        said = entrance.startable(
            entrance.ADAPT_THIS_WORKOUT, {"said": case.says, "ask_for": ["Romanian_Deadlift"]}
        )

    assert said is not None
    assert "do not call it again" in said and "Call it again" not in said
