"""The supervisor's set: parsed from its TOML, and refused where the runner could not drive it."""

from __future__ import annotations

from pathlib import Path

import pytest

from trainer import supervise_set

SET = """\
[bars]
held = 80
followed = 80

[declared]
cycle_length = 1
duration_cap_min = 45
split = [["legs"]]
equipment = ["barbell"]
goal = "hypertrophy"

[mesocycles.base]
cycles = 2
why = "a base"

[[mesocycles.base.slots]]
blocks = [
  { rounds = 3, rest = 90, reason = "squat", items = [{ exercise_id = "Barbell_Squat", prescription = { unit = "reps", amount = 8 } }] },
]

[[cases]]
name = "loved"
goal = "strength"
history = [
  { mesocycle = "base" },
  { mesocycle = "base", direction = { theme = "t", changes = "c", why = "w", varies = ["rest"] } },
]
said = [{ conclusion = "loves the squat", quote = "adoro lo squat" }]
keeps = ["Barbell_Squat", ["Front_Barbell_Squat", "Goblet_Squat"]]
rotates = true
varies = ["reps"]
rest = "shorter"
"""


def test_the_committed_set_parses_with_its_bars_and_fifteen_to_twenty_histories() -> None:
    holds = supervise_set.load(Path("docs") / "supervising" / "eval-set.toml")

    assert (holds.bar_held, holds.bar_followed) == (80, 80)
    assert 15 <= len(holds.cases) <= 20


def test_a_case_carries_its_history_what_they_said_and_what_it_holds() -> None:
    (loved,) = supervise_set.parse(SET).cases

    assert [past.mesocycle for past in loved.history] == ["base", "base"]
    assert loved.history[0].direction is None
    assert loved.history[1].direction is not None and loved.history[1].direction.varies == ("rest",)
    assert loved.said == (supervise_set.Said("loves the squat", "adoro lo squat"),)
    assert loved.keeps == (("Barbell_Squat",), ("Front_Barbell_Squat", "Goblet_Squat"))
    assert (loved.goal, loved.rotates, loved.varies, loved.rest) == ("strength", True, ("reps",), "shorter")


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (("[bars]\nheld = 80\nfollowed = 80", "[bars]\nheld = 80"), "no \\[bars\\]"),
        (('{ mesocycle = "base" },', '{ mesocycle = "nowhere" },'), "no \\[mesocycles.nowhere\\]"),
        (('{ mesocycle = "base" },', '{ mesocycle = "base", direction = { theme = "t", changes = "c", why = "w", varies = ["rest"] } },'), "follows nothing"),
        (('varies = ["rest"] }', 'varies = [] }'), "a direction varies"),
        (('varies = ["reps"]', 'varies = ["load"]'), "load is not one of"),
        (('rest = "shorter"', 'rest = "less"'), "rest is shorter or longer"),
    ],
)
def test_a_set_the_runner_could_not_drive_is_refused_saying_where(change: tuple[str, str], says: str) -> None:
    with pytest.raises(supervise_set.SuperviseSetError, match=says):
        supervise_set.parse(SET.replace(*change))


def test_a_case_holding_nothing_is_refused() -> None:
    bare = SET.split("[[cases]]")[0] + '[[cases]]\nname = "bare"\nhistory = [{ mesocycle = "base" }]\n'

    with pytest.raises(supervise_set.SuperviseSetError, match="bare: holds nothing"):
        supervise_set.parse(bare)


def test_a_case_named_twice_is_refused() -> None:
    twice = SET + '[[cases]]\nname = "loved"\nhistory = [{ mesocycle = "base" }]\nchanges = true\n'

    with pytest.raises(supervise_set.SuperviseSetError, match="named twice: loved"):
        supervise_set.parse(twice)


def test_a_missing_set_names_where_it_was_looked_for(tmp_path: Path) -> None:
    with pytest.raises(supervise_set.SuperviseSetError, match="not at"):
        supervise_set.load(tmp_path / "nowhere.toml")
