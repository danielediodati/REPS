"""The supervisor's suite: histories staged, directed and planned by scripted models, held by code."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from conftest import enrich, make_exercise
from test_planner import Scripted
from trainer import evaluation, supervise_evaluation, supervise_set
from trainer import plan as plans
from trainer.coach import models, supervisor
from trainer.engine import catalog, database, mesocycles, methodology, migrations

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(id="Front_Barbell_Squat", name="Front Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(id="Romanian_Deadlift", name="Romanian Deadlift", primary_muscles=("hamstrings",)),
    make_exercise(id="Barbell_Bench_Press", name="Barbell Bench Press", primary_muscles=("chest",)),
)

PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Front_Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Romanian_Deadlift": ("hip hinge", "hip, lumbar spine", "yes", "medium", 2),
    "Barbell_Bench_Press": ("horizontal push", "shoulder, elbow", "yes", "medium", 2),
}

SET = """\
[bars]
held = 80
followed = 80

[declared]
cycle_length = 1
duration_cap_min = 15
split = [["legs"]]
equipment = ["barbell"]
goal = "hypertrophy"

[mesocycles.base]
cycles = 2
why = "a base"

[[mesocycles.base.slots]]
blocks = [
  { rounds = 3, rest = 120, reason = "squat", items = [{ exercise_id = "Barbell_Squat", prescription = { unit = "reps", amount = 8 } }] },
  { rounds = 3, rest = 90, reason = "hinge", items = [{ exercise_id = "Romanian_Deadlift", prescription = { unit = "reps", amount = 10 } }] },
]

[[cases]]
name = "loved"
history = [
  { mesocycle = "base" },
  { mesocycle = "base", direction = { theme = "settle", changes = "rest down", why = "time", varies = ["rest"] } },
]
said = [{ conclusion = "loves the Romanian deadlift", quote = "adoro lo stacco rumeno" }]
keeps = ["Romanian_Deadlift"]
rotates = true
"""

DIRECTION = supervisor.Direction(
    theme="new squat", changes="the squat goes to a front squat", why="two alike", varies=["exercises"]
)


@pytest.fixture()
def source(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


@pytest.fixture()
def holds() -> supervise_set.SuperviseSet:
    return supervise_set.parse(SET)


@pytest.fixture()
def where(source: sqlite3.Connection) -> Iterator[supervise_evaluation.Fixture]:
    with supervise_evaluation.prepared(source) as prepared:
        yield prepared


def mesocycle_of(*blocks: tuple[str, int, int]) -> plans.Mesocycle:
    """One slot, a block per (exercise, reps, rest)."""
    return plans.Mesocycle.model_validate(
        {
            "cycles": 3,
            "why": "next",
            "workouts": [
                {
                    "blocks": [
                        {
                            "items": [{"exercise_id": one, "prescription": {"unit": "reps", "amount": reps}}],
                            "rounds": 3,
                            "rest": rest,
                            "reason": "work",
                        }
                        for one, reps, rest in blocks
                    ]
                }
            ],
        }
    )


ENDED = mesocycle_of(("Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 90))
HYPERTROPHY = methodology.committed().bounds("hypertrophy")


def direction_of(*varies: str) -> mesocycles.Direction:
    return mesocycles.Direction(theme="t", changes="c", why="w", varies=varies)


def case_of(**holding: object) -> supervise_set.Case:
    return supervise_set.Case(name="c", history=(supervise_set.Past("base"),), **holding)  # type: ignore[arg-type]


def failed(case: supervise_set.Case, plan: plans.Mesocycle | None, *varies: str) -> list[str]:
    found = supervise_evaluation.held(case, ENDED, direction_of(*(varies or ("rest",))), plan, (), HYPERTROPHY)
    return [name for name, _ in found]


# -- what code holds ------------------------------------------------------------


def test_what_moved_is_read_off_the_exercises_and_each_blocks_reps_and_rest_by_position() -> None:
    moved = supervise_evaluation.moved

    assert moved(ENDED, ENDED) == ()
    assert moved(ENDED, mesocycle_of(("Front_Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 90))) == ("exercises",)
    assert moved(ENDED, mesocycle_of(("Barbell_Squat", 8, 120), ("Romanian_Deadlift", 12, 90))) == ("reps",)
    assert moved(ENDED, mesocycle_of(("Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 75))) == ("rest",)
    added = mesocycle_of(("Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 90), ("Front_Barbell_Squat", 15, 45))
    assert moved(ENDED, added) == ("exercises",), "a block added is not the old blocks' reps or rest changing"


def test_a_row_that_asks_for_change_fails_on_the_same_mesocycle() -> None:
    assert failed(case_of(changes=True), ENDED) == [supervise_evaluation.CHANGED]
    assert failed(case_of(changes=True), mesocycle_of(("Barbell_Squat", 8, 90), ("Romanian_Deadlift", 10, 90))) == []


def test_the_loved_exercise_is_kept_while_the_rest_rotates() -> None:
    loved = case_of(keeps=(("Romanian_Deadlift",),), rotates=True)

    assert failed(loved, mesocycle_of(("Front_Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 90))) == []
    assert failed(loved, mesocycle_of(("Front_Barbell_Squat", 8, 120))) == [supervise_evaluation.KEPT]
    assert failed(loved, ENDED) == [supervise_evaluation.ROTATED]


def test_an_exercise_they_turned_against_is_left_out() -> None:
    assert failed(case_of(without=("Barbell_Squat",)), ENDED) == [supervise_evaluation.LEFT_OUT]


def test_reps_and_rest_outside_the_goals_column_fail_ranges_naming_them() -> None:
    plan = mesocycle_of(("Barbell_Squat", 5, 120), ("Romanian_Deadlift", 10, 45))

    (found,) = supervise_evaluation.held(case_of(ranges=True), ENDED, direction_of("rest"), plan, (), HYPERTROPHY)

    assert found == (supervise_evaluation.RANGES, "reps 5 outside 6-30; rest 45s outside 60-180s")


def test_the_direction_must_name_what_the_row_says_it_varies() -> None:
    assert failed(case_of(varies=("rest",)), ENDED, "exercises") == [supervise_evaluation.VARIES]
    assert failed(case_of(varies=("rest",)), ENDED, "rest", "reps") == []


def test_rest_and_reps_must_move_the_way_the_row_says() -> None:
    shorter = mesocycle_of(("Barbell_Squat", 6, 90), ("Romanian_Deadlift", 8, 60))

    assert failed(case_of(rest="shorter", reps="fewer"), shorter) == []
    assert failed(case_of(rest="longer"), shorter) == [supervise_evaluation.TREND]
    assert failed(case_of(reps="more"), shorter) == [supervise_evaluation.TREND]


def test_no_plan_or_one_the_validator_refused_fails_planned() -> None:
    refused = (plans.Violation("budget", "too long"),)

    assert failed(case_of(changes=True), None) == [supervise_evaluation.PLANNED]
    found = supervise_evaluation.held(case_of(without=("Front_Barbell_Squat",)), ENDED, direction_of("rest"), ENDED, refused, HYPERTROPHY)
    assert [name for name, _ in found] == [supervise_evaluation.PLANNED]


def test_a_plan_follows_when_it_changed_everything_the_direction_varies() -> None:
    swapped = mesocycle_of(("Front_Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 90))
    followed = supervise_evaluation.followed

    assert followed(ENDED, direction_of("exercises"), swapped) == ()
    assert [name for name, _ in followed(ENDED, direction_of("exercises", "rest"), swapped)] == [
        supervise_evaluation.FOLLOWED
    ]
    assert followed(ENDED, direction_of("exercises"), None) != ()


# -- the fixture ----------------------------------------------------------------


def test_a_history_is_staged_in_the_copy_trainer_db_names_and_asks_for_the_next_mesocycle(
    where: supervise_evaluation.Fixture, holds: supervise_set.SuperviseSet
) -> None:
    (loved,) = holds.cases

    request = supervise_evaluation.staged(where, holds, loved, "2026-10-04")
    again = supervise_evaluation.staged(where, holds, loved, "2026-10-04")

    assert Path(os.environ[database.DATABASE_ENV_VAR]) == where.path
    past = mesocycles.history(where.connection)
    assert [(one.performed, one.workouts) for one in past] == [(2, 2), (2, 2)], "staged over, not on top"
    assert past[1].direction == mesocycles.Direction("settle", "rest down", "time", ("rest",))
    assert again.continuing is not None and again.continuing.mesocycle == past[1].id
    assert request.slots[0].goal == "hypertrophy"


def test_what_the_set_and_the_catalog_disagree_on_is_a_problem_before_any_run(
    source: sqlite3.Connection,
) -> None:
    broken = supervise_set.parse(
        SET.replace('keeps = ["Romanian_Deadlift"]', 'keeps = ["Bulgarian_Split_Squat"]\ngoal = "power"')
    )

    found = supervise_evaluation.problems(source, broken)

    assert any("Bulgarian_Split_Squat" in line for line in found)
    assert any("no goal called power" in line for line in found)
    assert supervise_evaluation.problems(source, supervise_set.parse(SET)) == ()


def test_a_mesocycle_the_validator_would_refuse_is_refused_before_any_run(
    where: supervise_evaluation.Fixture, holds: supervise_set.SuperviseSet
) -> None:
    """A history the planner could never have planned teaches it to copy something illegal."""
    short = supervise_set.parse(SET.replace("duration_cap_min = 15", "duration_cap_min = 45"))
    untrained = supervise_set.parse(SET.replace('split = [["legs"]]', 'split = [["legs", "chest"]]'))

    assert supervise_evaluation.refused(where, holds, "2026-10-04") == ()
    assert any("budget: workout 1" in line for line in supervise_evaluation.refused(where, short, "2026-10-04"))
    assert any("untrained: workout 1" in line for line in supervise_evaluation.refused(where, untrained, "2026-10-04"))


# -- a run ----------------------------------------------------------------------


def chat(model: Scripted) -> models.Chat:
    return models.Chat(model, "scripted", "a-stand-in")


def test_a_run_directs_from_what_they_said_plans_from_the_direction_and_holds_both(
    source: sqlite3.Connection,
    where: supervise_evaluation.Fixture,
    holds: supervise_set.SuperviseSet,
    tmp_path: Path,
) -> None:
    directs = Scripted(turns=[AIMessage(content="enough")], documents=[DIRECTION])
    next_one = mesocycle_of(("Front_Barbell_Squat", 8, 120), ("Romanian_Deadlift", 10, 90))
    plans_on = Scripted(turns=[AIMessage(content="ready")], documents=[next_one])

    report = supervise_evaluation.run(
        where,
        holds,
        holds.cases,
        supervises_on=chat(directs),
        plans_on=chat(plans_on),
        repetitions=1,
        records=tmp_path / "records",
    )

    briefed = "\n".join(message.text for message in directs.seen[0])
    assert "adoro lo stacco rumeno" in briefed, "the conclusion reached the supervisor"
    planned = "\n".join(message.text for message in plans_on.seen[0])
    assert DIRECTION.changes in planned, "the planner planned from the direction"
    by_case = {outcome.case: outcome for outcome in report.outcomes}
    assert by_case["loved"].held, by_case["loved"].failures
    assert by_case["loved" + supervise_evaluation.FOLLOWS].held
    assert sorted(path.name for path in (tmp_path / "records").iterdir()) == [
        "loved-1-direction.json",
        "loved-1-plan.json",
    ]

    barred = supervise_evaluation.barred(report, holds)
    lines = supervise_evaluation.render(barred, holds.cases)
    assert barred.passed
    assert "  held: 1 of 1 -- 100%, the bar is 80%" in lines
    assert "  followed: 1 of 1 -- 100%, the bar is 80%" in lines
    assert any("loved #1: new squat | varies exercises" in line for line in lines)
    assert source.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 0, "the source is never written"


def test_a_supervisor_that_falls_over_is_a_run_not_made_and_the_pass_goes_on(
    where: supervise_evaluation.Fixture, holds: supervise_set.SuperviseSet, tmp_path: Path
) -> None:
    broken = Scripted(turns=[AIMessage(content="enough")], raw=["not a direction"] * 3)

    report = supervise_evaluation.run(
        where,
        holds,
        holds.cases,
        supervises_on=chat(broken),
        plans_on=chat(Scripted()),
        repetitions=1,
        records=tmp_path / "records",
    )

    (outcome,) = report.outcomes
    assert outcome.case == "loved" and outcome.error is not None
    assert not supervise_evaluation.barred(report, holds).passed


def test_plans_that_did_not_follow_hold_the_pass_below_its_bar() -> None:
    report = evaluation.Report(
        (
            evaluation.Outcome("loved", 1),
            evaluation.Outcome("loved" + supervise_evaluation.FOLLOWS, 1, ((supervise_evaluation.FOLLOWED, "no"),)),
        )
    )

    assert not supervise_evaluation.barred(report, supervise_set.parse(SET)).passed
