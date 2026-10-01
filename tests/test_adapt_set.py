"""The adaptation set: parsed from its TOML, and refused where the runner could not drive it."""

from __future__ import annotations

from pathlib import Path

import pytest

from trainer import adapt_set
from trainer.coach import entrance

SET = """\
today = "2026-10-01"

[bars]
routed = 80

[declared]
cycle_length = 1
duration_cap_min = 45
split = [["legs"]]
equipment = ["barbell"]
goal = "hypertrophy"

[mesocycle]
cycles = 2
why = "two to settle"

[[mesocycle.slots]]
blocks = [
  { rounds = 3, rest = 90, reason = "squat", items = [{ exercise_id = "Barbell_Squat", prescription = { unit = "reps", amount = 8 } }] },
]

[[cases]]
name = "short"
says = "oggi ho 30 minuti"
goes = "adapt_today"
minutes = 30
holds = ["Barbell_Squat"]

[[cases]]
name = "which"
says = "niente squat"
goes = "ask"
"""


def test_the_committed_set_parses_with_its_bar() -> None:
    holds = adapt_set.load(Path("docs") / "adapting" / "eval-set.toml")

    assert holds.bar_routed == 80
    assert {case.goes for case in holds.cases} >= {entrance.ADAPT_TODAY, adapt_set.ASK}


def test_a_case_carries_what_its_plan_must_hold() -> None:
    holds = adapt_set.parse(SET)

    short, which = holds.cases
    assert short.minutes == 30 and short.holds == ("Barbell_Squat",)
    assert short.planned and not which.planned
    assert holds.mesocycle.workouts[0].blocks[0].items[0].exercise_id == "Barbell_Squat"
    assert holds.declared["cycle_length"] == 1


def test_a_set_without_its_bar_is_refused() -> None:
    with pytest.raises(adapt_set.AdaptSetError, match="routed"):
        adapt_set.parse(SET.replace("routed = 80", ""))


def test_a_destination_nothing_answers_is_refused_naming_the_case() -> None:
    with pytest.raises(adapt_set.AdaptSetError, match="which: goes 'elsewhere'"):
        adapt_set.parse(SET.replace('goes = "ask"', 'goes = "elsewhere"'))


def test_a_plan_expected_where_nothing_is_planned_is_refused() -> None:
    with pytest.raises(adapt_set.AdaptSetError, match="which: only an adaptation is planned"):
        adapt_set.parse(SET.replace('goes = "ask"', 'goes = "ask"\nminutes = 20'))


def test_a_name_used_twice_is_refused() -> None:
    with pytest.raises(adapt_set.AdaptSetError, match="named twice: short"):
        adapt_set.parse(SET.replace('name = "which"', 'name = "short"'))


def test_a_mesocycle_that_is_not_one_is_refused() -> None:
    with pytest.raises(adapt_set.AdaptSetError, match="mesocycle"):
        adapt_set.parse(SET.replace('why = "two to settle"', ""))


def test_a_missing_set_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(adapt_set.AdaptSetError, match="not at"):
        adapt_set.load(tmp_path / "absent.toml")
