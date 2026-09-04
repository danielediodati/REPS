"""`remaining_budget` and `allocate`: the arithmetic of the time available.

Both are arithmetic and nothing else. Neither decides how to train -- there is
no cut here, no fallback, and no proportion this module carries of its own
(ADR-0001). No LLM and no network: every expectation below is written out.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich, make_exercise
from trainer.engine import budget, catalog, database, duration, migrations, muscle_groups
from trainer.engine.duration import Block, BlockItem


CATALOG = (
    make_exercise(id="Standing_Military_Press", name="Standing Military Press"),
    make_exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        primary_muscles=("quadriceps",),
    ),
)

_PATTERNS = {
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
}


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(opened, CATALOG, allow_pruning=True)
        enrich(opened, _PATTERNS)
        yield opened


def straight(exercise_id: str, *, rounds: int, reps: int, rest: int) -> Block:
    return Block(items=(BlockItem(exercise_id, reps=reps),), rounds=rounds, rest=rest)


# --- remaining_budget ----------------------------------------------------


def test_an_empty_plan_leaves_the_whole_budget(connection: sqlite3.Connection) -> None:
    assert budget.remaining_budget(connection, [], 40) == 40


def test_what_is_left_is_the_budget_minus_the_plan(
    connection: sqlite3.Connection,
) -> None:
    """3 rounds of 10 on the squat costs 8 minutes: 450 s, rounded up."""
    plan = [straight("Bodyweight_Squat", rounds=3, reps=10, rest=120)]

    assert duration.plan_duration(connection, plan) == 8
    assert budget.remaining_budget(connection, plan, 40) == 32


def test_a_plan_that_exactly_fills_the_budget_leaves_nothing(
    connection: sqlite3.Connection,
) -> None:
    plan = [straight("Bodyweight_Squat", rounds=4, reps=10, rest=120)]

    assert duration.plan_duration(connection, plan) == 10
    assert budget.remaining_budget(connection, plan, 10) == 0


def test_a_plan_already_over_budget_reports_a_negative_number(
    connection: sqlite3.Connection,
) -> None:
    """Negative, not zero and not an error: *how far over* is what the caller
    has to act on, and clamping it at zero would hide the size of the miss."""
    plan = [straight("Bodyweight_Squat", rounds=4, reps=10, rest=120)]

    assert budget.remaining_budget(connection, plan, 6) == -4


def test_the_room_reported_is_never_more_than_the_room_there_is(
    connection: sqlite3.Connection,
) -> None:
    """`plan_duration` rounds up, so a plan of 7.5 real minutes is charged 8
    and the answer errs towards saying there is less room, never more."""
    plan = [straight("Bodyweight_Squat", rounds=3, reps=10, rest=120)]

    assert duration.plan_seconds(connection, plan) == 450
    assert budget.remaining_budget(connection, plan, 40) == 40 - 8


def test_remaining_budget_refuses_a_negative_budget(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(budget.BudgetError):
        budget.remaining_budget(connection, [], -10)


def test_an_unusable_plan_fails_as_itself(connection: sqlite3.Connection) -> None:
    """The plan's own errors travel: this does not swallow them into a budget
    that happens to look full."""
    with pytest.raises(duration.DurationError):
        budget.remaining_budget(connection, [straight("Nope", rounds=3, reps=5, rest=60)], 40)


# --- allocate ------------------------------------------------------------


def test_a_single_group_gets_the_whole_workout() -> None:
    assert budget.allocate(40, {"legs": 1.0}) == {"legs": 40}


def test_two_groups_split_on_the_proportions_given() -> None:
    assert budget.allocate(40, {"chest": 0.6, "arms": 0.4}) == {"chest": 24, "arms": 16}


def test_the_same_two_groups_split_differently_when_told_to() -> None:
    """The proportions are the caller's; this module carries none of its own."""
    assert budget.allocate(40, {"chest": 0.7, "arms": 0.3}) == {"chest": 28, "arms": 12}


def test_three_groups_divide_too() -> None:
    allocated = budget.allocate(60, {"legs": 0.5, "core": 0.25, "arms": 0.25})

    assert allocated == {"legs": 30, "core": 15, "arms": 15}


def test_the_allocated_minutes_always_sum_to_the_input() -> None:
    third = 1 / 3
    allocated = budget.allocate(40, {"legs": third, "back": third, "chest": third})

    assert sum(allocated.values()) == 40


def test_the_rounding_remainder_goes_to_the_group_that_lost_the_most() -> None:
    """11 minutes at 55/45 is 6.05 and 4.95. The minute left over belongs to
    the group rounding stripped almost a whole minute from, not to the larger
    proportion -- which would hand it to the group that was barely short."""
    assert budget.allocate(11, {"chest": 0.55, "arms": 0.45}) == {"chest": 6, "arms": 5}


def test_the_remainder_is_deterministic_when_the_shortfalls_tie() -> None:
    third = 1 / 3
    first = budget.allocate(40, {"legs": third, "back": third, "chest": third})
    second = budget.allocate(40, {"chest": third, "back": third, "legs": third})

    assert first == second


def test_proportions_that_do_not_sum_to_one_are_refused() -> None:
    """0.6 and 0.3 is ten percent of the workout gone. Normalising it would
    turn a caller's typo into a silently different plan."""
    with pytest.raises(budget.BudgetError) as raised:
        budget.allocate(40, {"chest": 0.6, "arms": 0.3})

    assert "10%" in str(raised.value)
    assert "unaccounted" in str(raised.value)


def test_proportions_that_sum_to_more_than_one_are_refused() -> None:
    with pytest.raises(budget.BudgetError) as raised:
        budget.allocate(40, {"chest": 0.6, "arms": 0.6})

    assert "over-committed" in str(raised.value)


def test_a_miss_smaller_than_a_percent_is_still_named() -> None:
    """`:.0%` would report this as *«0% of the workout unaccounted for»*,
    which reads like the check misfired and names nothing to go and fix."""
    with pytest.raises(budget.BudgetError) as raised:
        budget.allocate(40, {"chest": 0.5, "arms": 0.4999})

    message = str(raised.value)

    assert "0%" not in message.replace("0.01%", "")
    assert "0.01%" in message


@pytest.mark.parametrize("minutes", [40.0, 39.5])
def test_allocate_refuses_minutes_that_are_not_whole(minutes: float) -> None:
    """mypy stops a typed caller. Ticket 05's MCP wrapper is the untyped one,
    and a JSON number can arrive as 40.0 -- which without this reaches a list
    slice and comes back as a TypeError instead of a sentence."""
    with pytest.raises(budget.BudgetError) as raised:
        budget.allocate(minutes, {"chest": 0.6, "arms": 0.4})  # type: ignore[arg-type]

    assert "whole number" in str(raised.value)


def test_remaining_budget_refuses_a_budget_that_is_not_whole(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(budget.BudgetError):
        budget.remaining_budget(connection, [], 40.0)  # type: ignore[arg-type]


def test_a_boolean_is_not_a_number_of_minutes() -> None:
    """`True` is an `int` in Python, and `allocate(True, ...)` would quietly
    mean one minute."""
    with pytest.raises(budget.BudgetError):
        # No ignore needed, and that is the point: `bool` is a subclass of
        # `int`, so mypy waves this through and only the runtime check stops it.
        budget.allocate(True, {"legs": 1.0})


def test_computed_proportions_a_bit_short_of_one_are_still_accepted() -> None:
    """A caller who derives proportions from a ratio rather than typing them
    can land a few bits low: 1:6:15 normalised sums to 0.9999999999999999.
    That is correct by construction, and the check has to tell it apart from
    a caller who really did lose ten percent of the workout."""
    parts = {"core": 1, "chest": 6, "legs": 15}
    total = sum(parts.values())
    proportions = {group: part / total for group, part in parts.items()}

    assert math.fsum(proportions.values()) != 1.0

    assert sum(budget.allocate(44, proportions).values()) == 44


def test_no_groups_at_all_is_refused() -> None:
    with pytest.raises(budget.BudgetError):
        budget.allocate(40, {})


@pytest.mark.parametrize("proportion", [0.0, -0.2])
def test_a_group_with_nothing_to_do_is_refused(proportion: float) -> None:
    """A group allocated nothing is a group that is not being trained, and it
    belongs out of the mapping rather than in it at zero."""
    with pytest.raises(budget.BudgetError):
        budget.allocate(40, {"chest": 1.0 - proportion, "arms": proportion})


def test_allocate_refuses_negative_minutes() -> None:
    with pytest.raises(budget.BudgetError):
        budget.allocate(-40, {"legs": 1.0})


def test_a_group_can_come_out_at_zero_minutes() -> None:
    """Honest arithmetic, not an error: at 2% of ten minutes there is no
    minute to give, and the caller who chose the proportions can see it."""
    allocated = budget.allocate(10, {"chest": 0.98, "arms": 0.02})

    assert allocated == {"chest": 10, "arms": 0}
    assert sum(allocated.values()) == 10


def test_zero_minutes_allocates_nothing_to_everyone() -> None:
    assert budget.allocate(0, {"chest": 0.6, "arms": 0.4}) == {"chest": 0, "arms": 0}


# --- what this module deliberately does not do ---------------------------


def test_there_is_no_cut_in_here() -> None:
    """ADR-0001: a plan that does not fit is rejected, never trimmed. The
    absence is the guarantee, so it is asserted rather than assumed."""
    surface = {name for name in dir(budget) if not name.startswith("_")}

    assert not {name for name in surface if "cut" in name.lower()}
    assert not {name for name in surface if "trim" in name.lower()}


# -- the group names are vocabulary, not the caller's ------------------------


def test_allocate_refuses_a_group_that_is_not_one_of_the_six() -> None:
    """Ticket 02 shipped without this check and its review said why: the six
    did not exist anywhere a function could read them. They do now.

    Left unchecked, `allocate` returns minutes keyed by the typo and the caller
    who later reads `allocated["chest"]` gets a `KeyError` a long way from the
    mistake.
    """
    with pytest.raises(budget.BudgetError) as raised:
        budget.allocate(40, {"Chest": 0.6, "arms": 0.4})

    message = str(raised.value)
    assert "'Chest'" in message
    for group in muscle_groups.groups():
        assert group in message


def test_allocate_reads_the_six_from_the_mapping() -> None:
    """Every group the committed mapping names is accepted -- proof the check
    is reading the vocabulary rather than carrying a copy of it."""
    groups = muscle_groups.groups()
    share = 1 / len(groups)

    allocated = budget.allocate(60, {group: share for group in groups})

    assert sorted(allocated) == sorted(groups)
    assert sum(allocated.values()) == 60


def test_a_muscle_is_not_a_muscle_group() -> None:
    """`biceps` is one of the catalog's seventeen, not one of the six. Time is
    allocated on the coarse axis; volume is counted on the fine one."""
    with pytest.raises(budget.BudgetError, match="not a muscle group"):
        budget.allocate(30, {"biceps": 1.0})


def test_an_unreadable_mapping_still_fails_as_a_budget_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading the vocabulary must not widen this function's failure
    vocabulary. A caller wrapping the arithmetic in `except BudgetError` --
    ticket 05's MCP wrapper among them -- would otherwise be handed an
    uncaught `MuscleGroupError` the day the packaged mapping cannot be read.
    """

    def unreadable() -> tuple[str, ...]:
        raise muscle_groups.MuscleGroupError("no muscle group mapping at /nowhere")

    monkeypatch.setattr(muscle_groups, "groups", unreadable)

    with pytest.raises(budget.BudgetError, match="cannot be read"):
        budget.allocate(40, {"chest": 1.0})
