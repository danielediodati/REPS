"""`plan_duration`: how long a plan actually takes.

A plan is a sequence of blocks, and a block is one or more exercises performed
for a number of rounds with the rest taken after each round -- so a superset is
costed as a superset and not as two exercises that happen to be adjacent. No
LLM and no network anywhere in this file: the formula is arithmetic over a
small, hand-built catalog, and every expectation below is written out in
seconds rather than checked against a second implementation of the same sum.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, duration, migrations
from trainer.engine.catalog import Exercise
from trainer.engine.duration import Block, BlockItem
from trainer.engine.enrichment import MOVEMENT_PATTERNS


def exercise(**overrides: object) -> Exercise:
    base: dict[str, object] = {
        "id": "Some_Exercise",
        "name": "Some Exercise",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("shoulders",),
        "secondary_muscles": (),
        "instructions": (),
        "images": (),
    }
    base.update(overrides)
    return Exercise(**base)  # type: ignore[arg-type]


CATALOG = (
    exercise(id="Standing_Military_Press", name="Standing Military Press"),
    exercise(id="Bent_Over_Barbell_Row", name="Bent Over Barbell Row"),
    exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        primary_muscles=("quadriceps",),
    ),
    exercise(
        id="Dumbbell_Bicep_Curl",
        name="Dumbbell Bicep Curl",
        equipment="dumbbell",
        primary_muscles=("biceps",),
    ),
    exercise(
        id="Farmers_Walk",
        name="Farmers Walk",
        equipment="dumbbell",
        primary_muscles=("forearms",),
    ),
    exercise(
        id="Spell_Caster",
        name="Spell Caster",
        equipment="dumbbell",
        primary_muscles=("abdominals",),
    ),
)

# id -> (movement_pattern, loaded_joints, axial, stability, setup_cost_min).
# `Spell_Caster` is absent on purpose: it is one of the rows the rules leave
# undecided, and it is what the unenriched error is tested against.
_PATTERNS = {
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Bent_Over_Barbell_Row": ("horizontal pull", "shoulder, elbow", "yes", "medium", 2),
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
    "Dumbbell_Bicep_Curl": ("isolation", "elbow", "no", "medium", 1),
    "Farmers_Walk": ("carry", "shoulder, wrist", "yes", "high", 2),
}


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        catalog.import_exercises(opened, CATALOG, allow_pruning=True)
        for exercise_id, (pattern, joints, axial, stability, setup) in _PATTERNS.items():
            opened.execute(
                "UPDATE exercises SET movement_pattern = ?, movement_pattern_source = 'rule', "
                "loaded_joints = ?, loaded_joints_source = 'rule', "
                "spinal_axial_load = ?, spinal_axial_load_source = 'rule', "
                "required_stability = ?, required_stability_source = 'rule', "
                "setup_cost_min = ?, setup_cost_min_source = 'rule' WHERE id = ?",
                (
                    pattern,
                    json.dumps([joint.strip() for joint in joints.split(",")]),
                    axial,
                    stability,
                    setup,
                    exercise_id,
                ),
            )
        yield opened


def straight(exercise_id: str, *, rounds: int, reps: int, rest: int) -> Block:
    """Straight sets: the block holding one exercise."""
    return Block(items=(BlockItem(exercise_id, reps=reps),), rounds=rounds, rest=rest)


# --- straight sets: the one-exercise block ------------------------------


def test_straight_sets_cost_setup_plus_rounds(connection: sqlite3.Connection) -> None:
    """5 rounds of 5 reps on the military press: 3 min setup, then each round
    is 15 s of work and the 180 s prescribed after it."""
    plan = [straight("Standing_Military_Press", rounds=5, reps=5, rest=180)]

    assert duration.plan_seconds(connection, plan) == 180 + 5 * (15 + 180)


def test_setup_is_spent_once_per_block_not_once_per_round(
    connection: sqlite3.Connection,
) -> None:
    plan = [straight("Standing_Military_Press", rounds=3, reps=5, rest=180)]

    seconds = duration.plan_seconds(connection, plan)

    assert seconds == 180 + 3 * (15 + 180)
    assert seconds != 3 * 180 + 3 * (15 + 180)


def test_an_exercise_with_no_setup_cost_adds_none(
    connection: sqlite3.Connection,
) -> None:
    plan = [straight("Bodyweight_Squat", rounds=3, reps=10, rest=120)]

    assert duration.plan_seconds(connection, plan) == 0 + 3 * (30 + 120)


# --- the shape that flat costing gets wrong -----------------------------


def test_a_superset_rests_once_per_round_not_once_per_exercise(
    connection: sqlite3.Connection,
) -> None:
    """The correctness fix this rework exists for.

    Press and row alternated for 3 rounds, resting 120 s after the pair: both
    bars are set up once, and the rest falls after the round rather than after
    each exercise.
    """
    superset = Block(
        items=(
            BlockItem("Standing_Military_Press", reps=10),
            BlockItem("Bent_Over_Barbell_Row", reps=10),
        ),
        rounds=3,
        rest=120,
    )

    assert duration.plan_seconds(connection, [superset]) == (3 + 2) * 60 + 3 * (
        30 + 30 + 120
    )


def test_the_superset_is_cheaper_than_the_same_work_as_two_blocks(
    connection: sqlite3.Connection,
) -> None:
    """Costed as two straight-set blocks -- which is what the flat model
    shipped at 9e21b10 did -- the same work comes out six minutes longer."""
    superset = Block(
        items=(
            BlockItem("Standing_Military_Press", reps=10),
            BlockItem("Bent_Over_Barbell_Row", reps=10),
        ),
        rounds=3,
        rest=120,
    )
    apart = [
        straight("Standing_Military_Press", rounds=3, reps=10, rest=120),
        straight("Bent_Over_Barbell_Row", rounds=3, reps=10, rest=120),
    ]

    assert duration.plan_seconds(connection, [superset]) == 840
    assert duration.plan_seconds(connection, apart) == 1200
    assert duration.plan_duration(connection, [superset]) == 14
    assert duration.plan_duration(connection, apart) == 20


def test_a_circuit_is_the_same_rule_with_more_exercises(
    connection: sqlite3.Connection,
) -> None:
    circuit = Block(
        items=(
            BlockItem("Bodyweight_Squat", reps=15),
            BlockItem("Dumbbell_Bicep_Curl", reps=12),
            BlockItem("Standing_Military_Press", reps=10),
        ),
        rounds=4,
        rest=60,
    )

    assert duration.plan_seconds(connection, [circuit]) == (0 + 1 + 3) * 60 + 4 * (
        45 + 36 + 30 + 60
    )


def test_straight_sets_and_a_superset_take_the_same_code_path(
    connection: sqlite3.Connection,
) -> None:
    """A one-item block is not a special case: dropping the second exercise
    from a superset turns it into straight sets and only removes that
    exercise's own setup and work."""
    press = BlockItem("Standing_Military_Press", reps=10)
    row = BlockItem("Bent_Over_Barbell_Row", reps=10)

    pair = duration.plan_seconds(
        connection, [Block(items=(press, row), rounds=3, rest=120)]
    )
    alone = duration.plan_seconds(
        connection, [Block(items=(press,), rounds=3, rest=120)]
    )

    assert pair - alone == 2 * 60 + 3 * 30


# --- timed work ----------------------------------------------------------


def test_timed_work_contributes_its_declared_seconds(
    connection: sqlite3.Connection,
) -> None:
    plan = [
        Block(items=(BlockItem("Farmers_Walk", seconds=45),), rounds=3, rest=90),
    ]

    assert duration.plan_seconds(connection, plan) == 2 * 60 + 3 * (45 + 90)


def test_a_block_may_mix_reps_and_timed_work(connection: sqlite3.Connection) -> None:
    block = Block(
        items=(
            BlockItem("Bodyweight_Squat", reps=10),
            BlockItem("Farmers_Walk", seconds=30),
        ),
        rounds=3,
        rest=60,
    )

    assert duration.plan_seconds(connection, [block]) == (0 + 2) * 60 + 3 * (
        30 + 30 + 60
    )


# --- rest is prescribed, never chosen by the engine ----------------------


def test_the_prescribed_rest_is_what_gets_counted(
    connection: sqlite3.Connection,
) -> None:
    """Same exercise, same reps, two different prescriptions. If the engine
    were still deriving rest from the pattern these would be equal."""
    short = [straight("Standing_Military_Press", rounds=3, reps=5, rest=60)]
    long = [straight("Standing_Military_Press", rounds=3, reps=5, rest=180)]

    assert duration.plan_seconds(connection, short) == 180 + 3 * (15 + 60)
    assert duration.plan_seconds(connection, long) == 180 + 3 * (15 + 180)


def test_costing_never_consults_the_reference_bands(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bands are a reference for whoever plans. If any costing path still
    reached for them, this would raise instead of returning a number."""

    def refuse(*args: object, **kwargs: object) -> int:
        raise AssertionError("the costing path consulted the reference bands")

    class Forbidden(dict[str, int]):
        def __getitem__(self, key: str) -> int:
            raise AssertionError("the costing path read the reference bands")

    # Both the function and the table it reads. Patching only the function
    # would let `rest = block.rest or REST_SECONDS["hypertrophy"]` slip
    # through, and a defaulted rest is the one thing ADR-0001 forbids.
    monkeypatch.setattr(duration, "reference_rest", refuse)
    monkeypatch.setattr(duration, "REST_SECONDS", Forbidden())

    plan = [
        straight("Standing_Military_Press", rounds=3, reps=5, rest=45),
        Block(
            items=(
                BlockItem("Dumbbell_Bicep_Curl", reps=12),
                BlockItem("Farmers_Walk", seconds=30),
            ),
            rounds=2,
            rest=30,
        ),
    ]

    assert duration.plan_seconds(connection, plan) > 0


def test_a_block_may_prescribe_no_rest_at_all(connection: sqlite3.Connection) -> None:
    """Zero is a legitimate prescription, not a missing value."""
    plan = [straight("Dumbbell_Bicep_Curl", rounds=3, reps=12, rest=0)]

    assert duration.plan_seconds(connection, plan) == 60 + 3 * 36


# --- the reference bands, kept for a planner to consult ------------------


def test_the_reference_bands_hold_the_values_trainer_md_gives() -> None:
    assert duration.REST_SECONDS == {
        "strength": 180,
        "hypertrophy": 120,
        "isolation": 60,
    }


@pytest.mark.parametrize(
    ("reps", "rest"),
    [(1, 180), (5, 180), (6, 180), (7, 120), (8, 120), (20, 120)],
)
def test_six_is_the_strength_hypertrophy_boundary(reps: int, rest: int) -> None:
    assert duration.reference_rest("vertical push", reps) == rest


def test_isolation_has_one_reference_value_whatever_the_reps() -> None:
    assert duration.reference_rest("isolation", 5) == 60
    assert duration.reference_rest("isolation", 15) == 60


def test_every_pattern_has_a_reference_value() -> None:
    for pattern in MOVEMENT_PATTERNS:
        expected = 60 if pattern == "isolation" else 180
        assert duration.reference_rest(pattern, 5) == expected


def test_the_reference_refuses_a_pattern_the_catalog_cannot_hold() -> None:
    with pytest.raises(duration.DurationError):
        duration.reference_rest("interpretive dance", 5)


# --- whole plans ---------------------------------------------------------


def test_a_plan_sums_its_blocks(connection: sqlite3.Connection) -> None:
    plan = [
        straight("Standing_Military_Press", rounds=4, reps=5, rest=180),
        Block(
            items=(
                BlockItem("Bodyweight_Squat", reps=12),
                BlockItem("Dumbbell_Bicep_Curl", reps=12),
            ),
            rounds=3,
            rest=90,
        ),
    ]

    assert duration.plan_seconds(connection, plan) == (
        180 + 4 * (15 + 180) + (0 + 1) * 60 + 3 * (36 + 36 + 90)
    )


def test_an_empty_plan_takes_no_time(connection: sqlite3.Connection) -> None:
    assert duration.plan_seconds(connection, []) == 0
    assert duration.plan_duration(connection, []) == 0


def test_plan_duration_reports_whole_minutes(connection: sqlite3.Connection) -> None:
    plan = [straight("Bodyweight_Squat", rounds=4, reps=10, rest=120)]

    assert duration.plan_seconds(connection, plan) == 4 * (30 + 120)
    assert duration.plan_duration(connection, plan) == 10


def test_a_part_minute_rounds_up_rather_than_away(
    connection: sqlite3.Connection,
) -> None:
    """7.5 minutes is 8, not 7: a budget is spoken in whole minutes and the
    half that would be dropped is real time the workout still takes."""
    plan = [straight("Bodyweight_Squat", rounds=3, reps=10, rest=120)]

    assert duration.plan_seconds(connection, plan) == 450
    assert duration.plan_duration(connection, plan) == 8


def test_block_order_does_not_change_the_total(connection: sqlite3.Connection) -> None:
    first = straight("Standing_Military_Press", rounds=4, reps=5, rest=180)
    second = straight("Dumbbell_Bicep_Curl", rounds=2, reps=12, rest=60)

    assert duration.plan_seconds(connection, [first, second]) == duration.plan_seconds(
        connection, [second, first]
    )


# --- the states this refuses to guess at ---------------------------------


def test_an_unknown_exercise_id_is_named(connection: sqlite3.Connection) -> None:
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(connection, [straight("Nope", rounds=3, reps=5, rest=60)])

    assert "Nope" in str(raised.value)


def test_an_unenriched_exercise_is_a_state_not_a_default(
    connection: sqlite3.Connection,
) -> None:
    """No setup cost is invented for a row nobody enriched -- the error names
    the row and the command that fixes it."""
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(
            connection, [straight("Spell_Caster", rounds=3, reps=5, rest=60)]
        )

    assert "Spell_Caster" in str(raised.value)
    assert "enrich" in str(raised.value)


def test_a_plan_is_refused_whole(connection: sqlite3.Connection) -> None:
    """A partial total over the blocks that did resolve would be a number
    smaller than the truth, quietly."""
    with pytest.raises(duration.DurationError):
        duration.plan_seconds(
            connection,
            [
                straight("Bodyweight_Squat", rounds=3, reps=10, rest=120),
                straight("Nope", rounds=3, reps=5, rest=60),
            ],
        )


def test_a_plan_that_can_only_be_walked_once_is_still_counted(
    connection: sqlite3.Connection,
) -> None:
    """The plan is walked twice -- once to resolve ids, once to sum. A
    generator would be empty by the second pass and cost 0, silently, in the
    one direction this number must never err in.

    `Plan` is a `Sequence`, so the annotation forbids this and mypy stops it
    repo-wide; the ignore is the point of the test. The guard is for the
    caller that is not type-checked -- an MCP client decoding JSON.
    """
    block = straight("Standing_Military_Press", rounds=3, reps=5, rest=180)

    once_only = (entry for entry in [block])

    assert duration.plan_seconds(
        connection, once_only  # type: ignore[arg-type]
    ) == duration.plan_seconds(connection, [block])


# --- one line per exercise ------------------------------------------------


def test_an_exercise_cannot_appear_twice_in_one_block(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(
            connection,
            [
                Block(
                    items=(
                        BlockItem("Standing_Military_Press", reps=5),
                        BlockItem("Standing_Military_Press", reps=12),
                    ),
                    rounds=3,
                    rest=120,
                )
            ],
        )

    assert "Standing_Military_Press" in str(raised.value)


def test_an_exercise_cannot_appear_in_two_blocks(
    connection: sqlite3.Connection,
) -> None:
    """The rule spans the plan, not the block: two entries on the same bar
    leave `setup_cost_min` with no honest answer wherever they sit."""
    with pytest.raises(duration.DurationError) as raised:
        duration.plan_seconds(
            connection,
            [
                straight("Bodyweight_Squat", rounds=3, reps=5, rest=180),
                straight("Bodyweight_Squat", rounds=2, reps=12, rest=90),
            ],
        )

    assert "Bodyweight_Squat" in str(raised.value)


def test_the_uniqueness_rule_is_checkable_on_its_own(
    connection: sqlite3.Connection,
) -> None:
    """Whoever builds a plan can ask for the invariant without costing it."""
    fine = [
        straight("Standing_Military_Press", rounds=3, reps=5, rest=180),
        straight("Bodyweight_Squat", rounds=3, reps=10, rest=120),
    ]

    duration.check_plan(fine)

    with pytest.raises(duration.DurationError):
        duration.check_plan([*fine, straight("Bodyweight_Squat", rounds=1, reps=5, rest=60)])


# --- shapes that are not a plan -------------------------------------------


def test_a_block_item_is_prescribed_in_reps_or_in_seconds_never_both() -> None:
    with pytest.raises(ValueError):
        BlockItem("Bodyweight_Squat", reps=10, seconds=30)


def test_a_block_item_prescribed_in_neither_is_refused() -> None:
    with pytest.raises(ValueError):
        BlockItem("Bodyweight_Squat")


@pytest.mark.parametrize("reps", [0, -1])
def test_a_block_item_refuses_a_rep_count_below_one(reps: int) -> None:
    with pytest.raises(ValueError):
        BlockItem("Bodyweight_Squat", reps=reps)


@pytest.mark.parametrize("seconds", [0, -30])
def test_a_block_item_refuses_a_duration_below_one_second(seconds: int) -> None:
    with pytest.raises(ValueError):
        BlockItem("Farmers_Walk", seconds=seconds)


@pytest.mark.parametrize("rounds", [0, -1])
def test_a_block_refuses_a_round_count_below_one(rounds: int) -> None:
    """Zero rounds is not a block, it is a block that was removed, and a
    negative one would subtract time from the workout."""
    with pytest.raises(ValueError):
        Block(items=(BlockItem("Bodyweight_Squat", reps=10),), rounds=rounds, rest=60)


def test_a_block_refuses_a_negative_rest() -> None:
    with pytest.raises(ValueError):
        Block(items=(BlockItem("Bodyweight_Squat", reps=10),), rounds=3, rest=-60)


def test_a_block_holding_no_exercise_is_refused() -> None:
    with pytest.raises(ValueError):
        Block(items=(), rounds=3, rest=60)


def test_a_block_built_from_a_generator_is_still_counted(
    connection: sqlite3.Connection,
) -> None:
    """`items` is walked three times -- uniqueness, setup, the sum. A
    generator would be empty after the first and cost the block at its rest
    alone, silently, in the one direction this must never err in."""
    press = BlockItem("Standing_Military_Press", reps=10)
    row = BlockItem("Bent_Over_Barbell_Row", reps=10)

    from_generator = Block(
        items=(item for item in [press, row]),  # type: ignore[arg-type]
        rounds=3,
        rest=120,
    )
    from_tuple = Block(items=(press, row), rounds=3, rest=120)

    assert duration.plan_seconds(connection, [from_generator]) == duration.plan_seconds(
        connection, [from_tuple]
    )


def test_a_block_from_an_empty_generator_is_still_refused() -> None:
    """`not self.items` is true of an empty generator too, so the guard has
    to run after the items are materialised, not before."""
    nothing: list[BlockItem] = []

    with pytest.raises(ValueError):
        Block(items=(item for item in nothing), rounds=3, rest=60)  # type: ignore[arg-type]


def test_a_block_built_from_a_list_stays_hashable() -> None:
    """Frozen dataclasses are hashable; one holding a list is not, and the
    failure would surface far from here."""
    block = Block(
        items=[BlockItem("Bodyweight_Squat", reps=10)],  # type: ignore[arg-type]
        rounds=3,
        rest=60,
    )

    assert hash(block)
    assert block.items == (BlockItem("Bodyweight_Squat", reps=10),)
