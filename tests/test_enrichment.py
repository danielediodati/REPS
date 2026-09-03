"""The deterministic pass: docs/enrichment/definitions.md, executed.

Two kinds of test here. Unit tests over synthetic exercises check one
boundary rule at a time, the same way docs/enrichment/definitions.md states
one at a time. Tests over the real vendored catalog check the number this
ticket exists to produce: coverage on the 584 strength rows, measured, not
assumed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, enrichment, migrations
from trainer.engine.catalog import Exercise


def exercise(**overrides: object) -> Exercise:
    base: dict[str, object] = {
        "id": "Bench_Press",
        "name": "Bench Press",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("chest",),
        "secondary_muscles": (),
        "instructions": (),
        "images": (),
    }
    base.update(overrides)
    return Exercise(**base)  # type: ignore[arg-type]


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        yield opened


def stock(connection: sqlite3.Connection, *exercises: Exercise) -> None:
    catalog.import_exercises(connection, exercises, allow_pruning=True)


# --- movement_pattern: one boundary rule at a time --------------------------


def test_a_carry_wins_regardless_of_mechanic() -> None:
    row = exercise(name="Farmer's Carry", mechanic="isolation", primary_muscles=("forearms",))
    assert enrichment.derive_movement_pattern(row) == "carry"


def test_isolation_mechanic_decides_by_itself() -> None:
    row = exercise(name="Concentration Curl", mechanic="isolation", primary_muscles=("biceps",))
    assert enrichment.derive_movement_pattern(row) == "isolation"


def test_a_muscle_with_no_compound_entry_is_always_isolation() -> None:
    """B2's exception aside, biceps/forearms/calves/neck/adductors/abductors
    have no compound movement in this catalog."""
    row = exercise(name="Whatever It Is Called", mechanic="compound", primary_muscles=("calves",))
    assert enrichment.derive_movement_pattern(row) == "isolation"


def test_b1_dynamic_spinal_flexion_is_isolation_not_a_core_pattern() -> None:
    row = exercise(name="Weighted Crunch", mechanic="compound", primary_muscles=("abdominals",))
    assert enrichment.derive_movement_pattern(row) == "isolation"


def test_b2a_trunk_rotation_is_core_rotation() -> None:
    row = exercise(name="Cable Chop", mechanic="compound", primary_muscles=("abdominals",))
    assert enrichment.derive_movement_pattern(row) == "core rotation"


def test_b2b_trunk_lean_is_core_lateral_flexion() -> None:
    row = exercise(name="Kettlebell Windmill", mechanic="compound", primary_muscles=("abdominals",))
    assert enrichment.derive_movement_pattern(row) == "core lateral flexion"


def test_b2_overrides_a_wrong_isolation_mechanic() -> None:
    """The source calls `Advanced Kettlebell Windmill` `mechanic: isolation`.
    It is a compound trunk-stability movement, and its own name says so."""
    row = exercise(
        name="Advanced Kettlebell Windmill",
        mechanic="isolation",
        primary_muscles=("abdominals",),
    )
    assert enrichment.derive_movement_pattern(row) == "core lateral flexion"


def test_b3_a_plank_with_moving_limbs_is_still_anti_extension() -> None:
    row = exercise(name="Ab Wheel Rollout", mechanic="compound", primary_muscles=("abdominals",))
    assert enrichment.derive_movement_pattern(row) == "core anti-extension"


def test_b3_overrides_a_wrong_isolation_mechanic_too() -> None:
    """`Plank` and `Suspended_Fallout` are both `mechanic: isolation` in the
    real catalog, and both hold a fixed position resisting lumbar extension
    -- the same mistake B2 caught on the rotation side, on the
    anti-extension side instead. Code-review found this one: the first fix
    only widened the override for `core rotation` and `core lateral
    flexion`, and silently kept mislabeling every plank as `isolation`."""
    for name in ("Plank", "Suspended Fallout"):
        row = exercise(name=name, mechanic="isolation", primary_muscles=("abdominals",))
        assert enrichment.derive_movement_pattern(row) == "core anti-extension", name


def test_the_real_plank_and_fallout_rows_are_core_anti_extension() -> None:
    strength = {e.id: e for e in strength_exercises()}
    for row_id in ("Plank", "Suspended_Fallout"):
        assert enrichment.derive_movement_pattern(strength[row_id]) == "core anti-extension"


def test_b4_a_kettlebell_clean_is_hip_hinge_not_a_press() -> None:
    row = exercise(name="Power Clean", mechanic="compound", primary_muscles=("hamstrings",))
    assert enrichment.derive_movement_pattern(row) == "hip hinge"


def test_b4_a_thruster_is_the_press_it_ends_in() -> None:
    row = exercise(name="Kettlebell Thruster", mechanic="compound", primary_muscles=("shoulders",))
    assert enrichment.derive_movement_pattern(row) == "vertical push"


def test_b4_a_muscle_up_is_the_pull_it_starts_from() -> None:
    row = exercise(name="Muscle Up", mechanic="compound", primary_muscles=("lats",))
    assert enrichment.derive_movement_pattern(row) == "vertical pull"


def test_b5_a_carry_requires_travelling() -> None:
    """`Sled Overhead Backward Walk` -- B5's own example of a real carry --
    has no keyword this rule recognises and stays in the residue, decided by
    hand instead: `walk` alone is not enough of a signal to be a rule, since
    most walking in this catalog is not carrying anything. `Yoke Walk` is
    unambiguous, and the rule catches it."""
    row = exercise(name="Yoke Walk", mechanic="compound", primary_muscles=("quadriceps",))
    assert enrichment.derive_movement_pattern(row) == "carry"


def test_b5_a_static_band_hold_is_not_a_carry() -> None:
    row = exercise(name="Monster Walk", mechanic="compound", primary_muscles=("abductors",))
    assert enrichment.derive_movement_pattern(row) != "carry"


def test_a_single_leg_movement_is_caught_before_hinge_or_squat() -> None:
    row = exercise(name="Bulgarian Split Squat", mechanic="compound", primary_muscles=("glutes",))
    assert enrichment.derive_movement_pattern(row) == "single-leg"


def test_a_hip_hinge() -> None:
    row = exercise(name="Barbell Deadlift", mechanic="compound", primary_muscles=("lower back",))
    assert enrichment.derive_movement_pattern(row) == "hip hinge"


def test_a_squat() -> None:
    row = exercise(name="Back Squat", mechanic="compound", primary_muscles=("quadriceps",))
    assert enrichment.derive_movement_pattern(row) == "squat"


def test_horizontal_push() -> None:
    row = exercise(name="Bench Press", mechanic="compound", primary_muscles=("chest",))
    assert enrichment.derive_movement_pattern(row) == "horizontal push"


def test_vertical_push_via_a_chest_dip() -> None:
    row = exercise(name="Chest Dip", mechanic="compound", primary_muscles=("chest",))
    assert enrichment.derive_movement_pattern(row) == "vertical push"


def test_vertical_pull() -> None:
    row = exercise(name="Wide-Grip Pull-Up", mechanic="compound", primary_muscles=("lats",))
    assert enrichment.derive_movement_pattern(row) == "vertical pull"


def test_horizontal_pull() -> None:
    row = exercise(name="Bent-Over Row", mechanic="compound", primary_muscles=("lats",))
    assert enrichment.derive_movement_pattern(row) == "horizontal pull"


def test_a_rule_that_cannot_decide_returns_none_not_a_guess() -> None:
    row = exercise(name="Spell Caster", mechanic="compound", primary_muscles=("abdominals",))
    assert enrichment.derive_movement_pattern(row) is None


def test_an_unmapped_primary_muscle_returns_none() -> None:
    row = exercise(name="Something Unclassifiable", mechanic="compound", primary_muscles=())
    assert enrichment.derive_movement_pattern(row) is None


# --- the other four fields: functions of pattern and equipment --------------


def test_loaded_joints_follow_the_pattern_for_compound_work() -> None:
    assert enrichment.derive_loaded_joints("squat", exercise()) == ("hip", "knee", "ankle")


def test_loaded_joints_follow_the_muscle_for_isolation() -> None:
    row = exercise(primary_muscles=("biceps",))
    assert enrichment.derive_loaded_joints("isolation", row) == ("elbow",)


def test_loaded_joints_for_neck_isolation_is_empty_not_a_guess() -> None:
    row = exercise(primary_muscles=("neck",))
    assert enrichment.derive_loaded_joints("isolation", row) == ()


def test_spinal_axial_load_yes_for_a_standing_barbell_hinge() -> None:
    row = exercise(equipment="barbell")
    assert enrichment.derive_spinal_axial_load("hip hinge", row) == "yes"


def test_spinal_axial_load_no_for_a_machine_squat() -> None:
    row = exercise(equipment="machine")
    assert enrichment.derive_spinal_axial_load("squat", row) == "no"


def test_spinal_axial_load_no_for_isolation() -> None:
    row = exercise(equipment="barbell")
    assert enrichment.derive_spinal_axial_load("isolation", row) == "no"


def test_spinal_axial_load_no_for_a_seated_press() -> None:
    """A seated barbell press does not load the spine axially: the bench
    back takes what the spine would otherwise carry standing."""
    row = exercise(name="Seated Barbell Military Press", equipment="barbell")
    assert enrichment.derive_spinal_axial_load("vertical push", row) == "no"


def test_spinal_axial_load_yes_for_a_standing_press() -> None:
    row = exercise(name="Standing Military Press", equipment="barbell")
    assert enrichment.derive_spinal_axial_load("vertical push", row) == "yes"


def test_required_stability_high_for_single_leg() -> None:
    row = exercise(equipment="dumbbell")
    assert enrichment.derive_required_stability("single-leg", row) == "high"


def test_required_stability_low_for_a_machine() -> None:
    row = exercise(equipment="machine")
    assert enrichment.derive_required_stability("horizontal push", row) == "low"


def test_required_stability_medium_for_a_standing_barbell_squat() -> None:
    row = exercise(equipment="barbell")
    assert enrichment.derive_required_stability("squat", row) == "medium"


def test_required_stability_low_for_a_seated_press() -> None:
    row = exercise(name="Seated Dumbbell Press", equipment="dumbbell")
    assert enrichment.derive_required_stability("vertical push", row) == "low"


def test_required_stability_medium_for_a_standing_press() -> None:
    row = exercise(name="Standing Military Press", equipment="barbell")
    assert enrichment.derive_required_stability("vertical push", row) == "medium"


def test_setup_cost_zero_for_bodyweight() -> None:
    assert enrichment.derive_setup_cost_min("body only") == 0


def test_setup_cost_highest_for_a_barbell() -> None:
    assert enrichment.derive_setup_cost_min("barbell") == 3


def test_derive_leaves_everything_null_when_the_pattern_is_undecided() -> None:
    row = exercise(name="Spell Caster", mechanic="compound", primary_muscles=("abdominals",))
    result = enrichment.derive(row)
    assert result == enrichment.Derived(None, None, None, None, None)


def test_derive_fills_all_five_once_the_pattern_is_known() -> None:
    row = exercise(name="Back Squat", mechanic="compound", primary_muscles=("quadriceps",))
    result = enrichment.derive(row)
    assert result.movement_pattern == "squat"
    assert result.loaded_joints == ("hip", "knee", "ankle")
    assert result.spinal_axial_load in enrichment.AXIAL_LOAD_VALUES
    assert result.required_stability in enrichment.STABILITY_LEVELS
    assert isinstance(result.setup_cost_min, int)


# --- the closed vocabularies, checked against the whole catalog -------------
#
# MOVEMENT_PATTERNS, LOADED_JOINTS, AXIAL_LOAD_VALUES and STABILITY_LEVELS
# restate, in code, the same twelve patterns / seven joints / two values /
# three levels docs/enrichment/definitions.md and the SQL CHECK constraints
# in migrations/0003_enrichment.sql already state. Three copies of one
# vocabulary is only safe if drift between them fails loudly -- these tests
# are that failure path, run against every strength row in the real catalog,
# not just the handful exercised above.


def test_every_decided_pattern_is_one_of_the_twelve() -> None:
    strength = strength_exercises()
    for one in strength:
        pattern = enrichment.derive_movement_pattern(one)
        if pattern is not None:
            assert pattern in enrichment.MOVEMENT_PATTERNS, one.id


def test_every_loaded_joint_is_one_of_the_seven() -> None:
    strength = strength_exercises()
    for one in strength:
        pattern = enrichment.derive_movement_pattern(one)
        if pattern is None:
            continue
        joints = enrichment.derive_loaded_joints(pattern, one)
        assert set(joints) <= set(enrichment.LOADED_JOINTS), one.id


def test_every_axial_load_value_is_yes_or_no() -> None:
    strength = strength_exercises()
    for one in strength:
        pattern = enrichment.derive_movement_pattern(one)
        if pattern is None:
            continue
        assert enrichment.derive_spinal_axial_load(pattern, one) in (
            enrichment.AXIAL_LOAD_VALUES
        ), one.id


def test_every_stability_value_is_one_of_the_three() -> None:
    strength = strength_exercises()
    for one in strength:
        pattern = enrichment.derive_movement_pattern(one)
        if pattern is None:
            continue
        assert enrichment.derive_required_stability(pattern, one) in (
            enrichment.STABILITY_LEVELS
        ), one.id


# --- the number this ticket exists to produce --------------------------------


def strength_exercises() -> tuple[Exercise, ...]:
    return tuple(e for e in catalog.load() if e.category == catalog.STRENGTH_CATEGORY)


def test_the_measured_floor_is_exceeded() -> None:
    """The floor ROADMAP.md and the ticket both name: 90%, measured before
    the pass was written. This pass has to clear it, not just approach it."""
    strength = strength_exercises()
    decided = sum(1 for e in strength if enrichment.derive_movement_pattern(e) is not None)

    assert decided / len(strength) > 0.90


THE_NAMED_GAPS = (
    "Barbell_Deadlift",
    "Weighted_Pull_Ups",
    "Pull_Through",
    "Stiff_Leg_Barbell_Good_Morning",
    "Kettlebell_Thruster",
    "Two-Arm_Kettlebell_Clean",
    "Muscle_Up",
)
"""ROADMAP.md § Session 2 names these seven as the gaps a real rule pass
should close, against the throwaway rule that measured the residue."""


@pytest.mark.parametrize("exercise_id", THE_NAMED_GAPS)
def test_the_named_gaps_are_closed(exercise_id: str) -> None:
    strength = {e.id: e for e in strength_exercises()}
    assert enrichment.derive_movement_pattern(strength[exercise_id]) is not None


def test_the_rule_never_disagrees_with_the_hand_read_residue() -> None:
    """Every row `docs/enrichment/residue.md` decided by hand that this rule
    also now decides has to land on the same pattern. A silent disagreement
    here is exactly what ticket 04's spot-check exists to catch -- catching
    it before that ticket exists is strictly better."""
    residue_path = Path(__file__).resolve().parents[1] / "docs" / "enrichment" / "residue.md"
    text = residue_path.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| (?:\*\*)?([a-z][a-z\- ]*?)(?:\*\*)? \|", text, re.MULTILINE)
    hand_decisions = {row_id: pattern.strip() for row_id, pattern in rows}

    strength = {e.id: e for e in strength_exercises()}
    mismatches = [
        (row_id, rule_pattern, hand_pattern)
        for row_id, hand_pattern in hand_decisions.items()
        if row_id in strength
        and (rule_pattern := enrichment.derive_movement_pattern(strength[row_id])) is not None
        and rule_pattern != hand_pattern
    ]
    assert mismatches == []


def test_undecided_rows_are_a_subset_of_the_hand_read_residue() -> None:
    """The rule invents no new residue: everything it cannot decide is
    already accounted for in the file ticket 04 will read from."""
    residue_path = Path(__file__).resolve().parents[1] / "docs" / "enrichment" / "residue.md"
    text = residue_path.read_text(encoding="utf-8")
    residue_ids = set(re.findall(r"^\| `([^`]+)` \|", text, re.MULTILINE))

    strength = strength_exercises()
    undecided = {e.id for e in strength if enrichment.derive_movement_pattern(e) is None}
    assert undecided <= residue_ids


# --- run(): the batch job ----------------------------------------------------


def test_run_reports_what_it_did(connection: sqlite3.Connection) -> None:
    stock(connection, *catalog.load())

    report = enrichment.run(connection)

    assert report.considered == 584
    assert len(report.decided) > 0.90 * report.considered
    assert report.coverage > 0.90
    assert len(report.decided) + len(report.undecided) == report.considered


def test_running_it_twice_changes_nothing(connection: sqlite3.Connection) -> None:
    stock(connection, *catalog.load())

    first = enrichment.run(connection)
    before = _all_enrichment_rows(connection)
    second = enrichment.run(connection)
    after = _all_enrichment_rows(connection)

    assert before == after
    assert second.decided == first.decided
    assert second.undecided == first.undecided
    assert second.skipped_curated == 0


def test_it_never_overwrites_a_curated_value(connection: sqlite3.Connection) -> None:
    stock(connection, *catalog.load())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'isolation', "
        "movement_pattern_source = 'curated' WHERE id = 'Barbell_Deadlift'"
        # the rule would say hip hinge -- a curator is allowed to disagree
    )

    report = enrichment.run(connection)

    row = connection.execute(
        "SELECT movement_pattern, movement_pattern_source FROM exercises "
        "WHERE id = 'Barbell_Deadlift'"
    ).fetchone()
    assert row["movement_pattern"] == "isolation"
    assert row["movement_pattern_source"] == "curated"
    assert "Barbell_Deadlift" not in report.decided
    assert "Barbell_Deadlift" not in report.undecided
    assert report.skipped_curated >= 1


def test_a_curated_row_the_rule_cannot_decide_is_not_reported_as_undecided(
    connection: sqlite3.Connection,
) -> None:
    """`Spell Caster` is outside what the rule can decide on its own. A
    curated value already sitting there is an answer, not a gap -- it must
    not appear on ticket 04's reading list."""
    stock(connection, *catalog.load())
    connection.execute(
        "UPDATE exercises SET movement_pattern = 'core rotation', "
        "movement_pattern_source = 'curated' WHERE id = 'Spell_Caster'"
    )

    report = enrichment.run(connection)

    assert "Spell_Caster" not in report.undecided
    assert "Spell_Caster" not in report.decided


def test_the_292_non_strength_rows_are_untouched(connection: sqlite3.Connection) -> None:
    stock(connection, *catalog.load())

    enrichment.run(connection)

    row = connection.execute(
        "SELECT COUNT(*) AS total FROM exercises "
        "WHERE category != 'strength' AND movement_pattern_source IS NOT NULL"
    ).fetchone()
    assert row["total"] == 0


def test_the_other_four_fields_are_only_set_where_the_pattern_is(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, *catalog.load())

    enrichment.run(connection)

    row = connection.execute(
        """
        SELECT COUNT(*) AS mismatched FROM exercises
        WHERE (movement_pattern_source IS NULL) != (loaded_joints_source IS NULL)
           OR (movement_pattern_source IS NULL) != (spinal_axial_load_source IS NULL)
           OR (movement_pattern_source IS NULL) != (required_stability_source IS NULL)
           OR (movement_pattern_source IS NULL) != (setup_cost_min_source IS NULL)
        """
    ).fetchone()
    assert row["mismatched"] == 0


def test_regression_of_and_variant_of_are_never_written_by_the_rule(
    connection: sqlite3.Connection,
) -> None:
    """docs/enrichment/definitions.md is explicit: recognising the same
    movement under different equipment needs reading, not columns."""
    stock(connection, *catalog.load())

    enrichment.run(connection)

    row = connection.execute(
        "SELECT COUNT(*) AS total FROM exercises "
        "WHERE regression_of_source IS NOT NULL OR variant_of_source IS NOT NULL"
    ).fetchone()
    assert row["total"] == 0


def test_a_written_row_is_readable_back_as_json(connection: sqlite3.Connection) -> None:
    stock(
        connection,
        exercise(
            id="Back_Squat", name="Back Squat", mechanic="compound", primary_muscles=("quadriceps",)
        ),
    )

    enrichment.run(connection)

    row = connection.execute(
        "SELECT loaded_joints FROM exercises WHERE id = 'Back_Squat'"
    ).fetchone()
    assert json.loads(row["loaded_joints"]) == ["hip", "knee", "ankle"]


def _all_enrichment_rows(connection: sqlite3.Connection) -> list[tuple[object, ...]]:
    rows = connection.execute(
        """
        SELECT id, movement_pattern, movement_pattern_source, loaded_joints,
               spinal_axial_load, required_stability, setup_cost_min
        FROM exercises ORDER BY id
        """
    ).fetchall()
    return [tuple(row) for row in rows]
