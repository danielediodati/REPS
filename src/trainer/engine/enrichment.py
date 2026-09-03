"""The deterministic pass: rules over the columns, nothing read, nothing called.

`docs/enrichment/definitions.md` is the one document that defines what these
twelve patterns, seven joints, three stability levels and the rest actually
mean -- this module only executes it. A judgement that is not in that
document is a judgement nobody outside this file can check, so a rule added
here without a matching definition is a bug in the process, not a shortcut.

Every function here is total once its inputs are known, or returns `None` to
say a row is outside what a rule can decide -- never a guess. `derive()` is
the only thing that combines them into a per-exercise result, and it decides
`movement_pattern` first: the other four fields are, deliberately, functions
of the pattern and the equipment rather than of the exercise, so none of them
can be decided for a row the pattern rule left null.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from trainer.engine import catalog
from trainer.engine.catalog import Exercise

MOVEMENT_PATTERNS = (
    "horizontal push",
    "vertical push",
    "horizontal pull",
    "vertical pull",
    "squat",
    "hip hinge",
    "single-leg",
    "core anti-extension",
    "core rotation",
    "core lateral flexion",
    "carry",
    "isolation",
)

LOADED_JOINTS = ("shoulder", "elbow", "wrist", "lumbar spine", "hip", "knee", "ankle")

STABILITY_LEVELS = ("high", "medium", "low")

AXIAL_LOAD_VALUES = ("yes", "no")


def _name_has(name: str, *words: str) -> bool:
    """Substring, not word-boundary: `"row"` matches inside `"narrow"`. Safe
    against every keyword list in this module checked against the real 584
    strength rows -- `test_the_rule_never_disagrees_with_the_hand_read_
    residue` would catch a false match landing on the wrong pattern -- but a
    keyword added later has to be checked against the catalog, not assumed
    safe by inspection."""
    lowered = name.lower()
    return any(word in lowered for word in words)


_UNILATERAL = (
    "lunge",
    "split squat",
    "bulgarian",
    "step-up",
    "step up",
    "single-leg",
    "single leg",
    "one-leg",
    "one leg",
    "pistol",
    "skater",
    "curtsy",
)

_CARRY = ("carry", "farmer", "waiter", "suitcase", "walk with", "yoke")

_HIP_HINGE = (
    "deadlift",
    "good morning",
    "hip thrust",
    "glute bridge",
    "romanian",
    "swing",
    "pull-through",
    "pull through",
)

_SQUAT = ("squat", "leg press", "hack", "sissy", "wall sit", "box squat")

_HIP_DRIVEN_PULL = ("clean", "snatch")
"""A kettlebell clean or snatch is driven by hip extension, not the arm --
residue.md decided the whole family (`Two-Arm_Kettlebell_Clean`,
`One-Arm_Kettlebell_Snatch`, `One-Arm_Kettlebell_Split_Snatch`,
`Double_Kettlebell_Snatch`) as `hip hinge` for exactly this reason, overruling
what B4's "the pattern the load ends in" would say on its own."""


def _quad_glute_pattern(name: str) -> str | None:
    """Quadriceps, glutes, adductors and abductors: squat, hinge or single-leg."""
    if _name_has(name, *_UNILATERAL):
        return "single-leg"
    if _name_has(name, *_HIP_HINGE):
        return "hip hinge"
    if _name_has(name, *_SQUAT, "step"):
        return "squat"
    return None


_HYPEREXTENSION = ("hyperextension", "glute ham raise", "ham raise", "back raise")


def _hamstring_pattern(name: str) -> str | None:
    if _name_has(name, *_UNILATERAL):
        return "single-leg"
    if _name_has(name, *_HIP_DRIVEN_PULL):
        # A clean or a snatch, kettlebell or barbell, is hip-extension driven
        # -- residue.md decided the whole family this way. Most of this
        # family carries `primary_muscles: ["hamstrings"]` rather than
        # `["shoulders"]`, which is why the check is duplicated here rather
        # than shared with `_shoulder_pattern` through a single dispatch.
        return "hip hinge"
    if _name_has(name, *_HIP_HINGE, *_HYPEREXTENSION):
        return "hip hinge"
    if _name_has(name, "squat", "leg press"):
        return "squat"
    return None


def _lower_back_pattern(name: str) -> str | None:
    """`lower back` is the deadlift/good-morning family in this catalog, not
    the abdominal branch -- `Barbell_Deadlift` and `Stiff_Leg_Barbell_Good_
    Morning` are both `primary_muscles: ["lower back"]`."""
    if _name_has(name, *_HIP_HINGE, *_HYPEREXTENSION):
        return "hip hinge"
    return None


def _abdominal_pattern(name: str) -> str | None:
    """B1, B2a, B2b and B3 from `docs/enrichment/residue.md`, as keywords.

    A rule can only catch what a name says outright: `Spell Caster` produces
    core rotation and nothing in its name says so, which is exactly why it
    stayed in the residue rather than being caught here.
    """
    if _name_has(name, "plank", "rollout", "ab wheel", "hollow", "dead bug", "fallout"):
        return "core anti-extension"
    if _name_has(name, "pallof", "anti-rotation", "chop", "landmine twist", "wood chop"):
        return "core rotation"
    if _name_has(name, "windmill", "get-up", "get up", "side bend", "side bridge"):
        return "core lateral flexion"
    if _name_has(
        name,
        "crunch",
        "sit-up",
        "situp",
        "leg raise",
        "knee raise",
        "twist",
        "russian",
        "v-up",
        "oblique",
        "hip raise",
        "flutter",
        "scissor",
        "toe touch",
        "jackknife",
        "hyperextension",
        "extension",
    ):
        return "isolation"
    return None


def _shoulder_pattern(name: str) -> str | None:
    if _name_has(name, *_HIP_DRIVEN_PULL):
        return "hip hinge"
    if _name_has(name, "thruster"):
        # B4: a thruster is a squat and an overhead press. The pattern the
        # load ends in is the press -- see docs/enrichment/residue.md § B4.
        return "vertical push"
    if _name_has(name, "press", "push press", "jerk", "handstand"):
        return "vertical push"
    if _name_has(name, "internal rotation", "external rotation"):
        return "isolation"
    if _name_has(name, "row", "face pull", "pull", "high pull", "shrug"):
        return "horizontal pull"
    if _name_has(name, "raise", "fly", "flye", "reverse"):
        return "isolation"
    return None


def _triceps_pattern(name: str) -> str | None:
    if _name_has(name, "dip", "press", "push-up", "pushup", "push up"):
        return "horizontal push"
    return "isolation"


def _lat_pattern(name: str) -> str | None:
    if _name_has(name, "muscle up", "muscle-up"):
        # B4: a muscle-up is a vertical pull and a dip. residue.md decided
        # vertical pull for the family, against the muscle evidence rather
        # than the naive terminal-pattern reading -- see § B4's finding.
        return "vertical pull"
    if _name_has(
        name,
        "pulldown",
        "pull-down",
        "pullup",
        "pull-up",
        "pull up",
        "chin",
        "chinup",
        "chin-up",
        "climb",
    ):
        return "vertical pull"
    if _name_has(name, "row", "pullover"):
        return "horizontal pull"
    if _name_has(name, *_HIP_HINGE):
        return "hip hinge"
    return None


def _middle_back_pattern(name: str) -> str | None:
    if _name_has(name, "row", "shrug", "face pull", "rear", "reverse fly", "high pull"):
        return "horizontal pull"
    if _name_has(name, "pulldown", "pull-up", "pullup", "pull up", "chin"):
        return "vertical pull"
    if _name_has(name, "deadlift", "clean", "snatch"):
        return "hip hinge"
    return None


def _chest_pattern(name: str) -> str | None:
    if _name_has(name, "dip"):
        return "vertical push"
    return "horizontal push"


_ISOLATION_MUSCLES = (
    "biceps",
    "forearms",
    "calves",
    "neck",
    "adductors",
    "abductors",
)
"""Muscle groups this catalog has no compound entry for: every row against
them is worked in isolation, so the muscle alone decides it."""

_PER_MUSCLE_RULE = {
    "quadriceps": _quad_glute_pattern,
    "glutes": _quad_glute_pattern,
    "adductors": _quad_glute_pattern,
    "abductors": _quad_glute_pattern,
    "hamstrings": _hamstring_pattern,
    "lower back": _lower_back_pattern,
    "abdominals": _abdominal_pattern,
    "chest": _chest_pattern,
    "shoulders": _shoulder_pattern,
    "triceps": _triceps_pattern,
    "lats": _lat_pattern,
    "middle back": _middle_back_pattern,
    "traps": _middle_back_pattern,
}
"""Dispatch by primary muscle. A muscle absent here (biceps, forearms,
calves, neck, adductors, abductors -- see `_ISOLATION_MUSCLES`) has no
compound movement in this catalog and is decided by `derive_movement_pattern`
before this table is even consulted."""


def derive_movement_pattern(exercise: Exercise) -> str | None:
    """The pattern a rule can read off `name`, `primary_muscles`, `force` and
    `mechanic` -- `None` when it cannot, which is most honestly decided by
    what the *name* fails to say, not by a missing branch here.

    Order matters. A loaded carry is named as one regardless of what its
    mechanic says, so that check runs first. `mechanic == 'isolation'`
    decides 244 of the 584 strength rows correctly by itself, but not all of
    them: `Advanced_Kettlebell_Windmill` is `mechanic: isolation` in the
    source and is plainly a compound trunk-stability movement -- its own
    name says `windmill`. `Plank` and `Suspended_Fallout` are the same
    mistake on the anti-extension side: both are `mechanic: isolation` and
    both hold a fixed position resisting lumbar extension, which this
    taxonomy does not call isolation either. Rather than special-case
    individual ids, all three of the trunk keyword groups in
    `_abdominal_pattern` (plank/rollout, chop/Pallof, windmill/get-up --
    B1's boundary against B2a/B2b/B3) are checked first for abdominal-muscle
    rows, because a name that says `core anti-extension`, `core rotation` or
    `core lateral flexion` outright overrides a mechanic label that was
    never going to be right for a pattern this project's own taxonomy does
    not consider isolation.

    Everything after that is dispatched by primary muscle, and it is not
    gated on `mechanic == 'compound'`: the catalog leaves `mechanic` null
    for some strength rows (`Reverse_Hyperextension`, `Side_Bridge`), and a
    name that says `hip hinge` or `core lateral flexion` outright is not
    made less true by a missing column -- see README's note on `force` and
    `mechanic` being incomplete on their own terms.
    """
    if _name_has(exercise.name, *_CARRY):
        return "carry"

    primary = exercise.primary_muscles[0] if exercise.primary_muscles else None

    if primary == "abdominals":
        off_sagittal = _abdominal_pattern(exercise.name)
        if off_sagittal in ("core anti-extension", "core rotation", "core lateral flexion"):
            return off_sagittal

    if exercise.mechanic == "isolation":
        return "isolation"

    if primary in _ISOLATION_MUSCLES:
        return "isolation"

    rule = _PER_MUSCLE_RULE.get(primary or "")
    if rule is None:
        return None
    return rule(exercise.name)


_JOINTS_BY_PATTERN: dict[str, tuple[str, ...]] = {
    "horizontal push": ("shoulder", "elbow"),
    "vertical push": ("shoulder", "elbow"),
    "horizontal pull": ("shoulder", "elbow"),
    "vertical pull": ("shoulder", "elbow"),
    "squat": ("hip", "knee", "ankle"),
    "hip hinge": ("hip", "lumbar spine"),
    "single-leg": ("hip", "knee", "ankle"),
    "core anti-extension": ("lumbar spine",),
    "core rotation": ("lumbar spine",),
    "core lateral flexion": ("lumbar spine",),
    "carry": ("shoulder", "wrist", "lumbar spine"),
}
"""What a pattern loads, independent of the exercise. `isolation` is not
here: an isolation movement's joint follows the muscle it isolates, decided
by `_JOINT_BY_ISOLATION_MUSCLE` instead of by the pattern."""

_JOINT_BY_ISOLATION_MUSCLE: dict[str, tuple[str, ...]] = {
    "chest": ("shoulder",),
    "shoulders": ("shoulder",),
    "triceps": ("elbow",),
    "biceps": ("elbow",),
    "forearms": ("wrist",),
    "lats": ("shoulder",),
    "middle back": ("shoulder",),
    "traps": ("shoulder",),
    "abdominals": ("lumbar spine",),
    "lower back": ("lumbar spine",),
    "quadriceps": ("knee",),
    "hamstrings": ("knee", "hip"),
    "glutes": ("hip",),
    "adductors": ("hip",),
    "abductors": ("hip",),
    "calves": ("ankle",),
    "neck": (),
}
"""Which joint an isolation movement crosses, by the muscle it isolates.
`neck` is deliberately empty: none of `LOADED_JOINTS` names it, and claiming
one of the seven would be a wrong answer dressed as a right one."""


def derive_loaded_joints(pattern: str, exercise: Exercise) -> tuple[str, ...]:
    """Total once `pattern` is known -- every compound pattern has a fixed
    answer, and an isolation movement's answer follows its primary muscle."""
    if pattern == "isolation":
        primary = exercise.primary_muscles[0] if exercise.primary_muscles else None
        return _JOINT_BY_ISOLATION_MUSCLE.get(primary or "", ())
    return _JOINTS_BY_PATTERN.get(pattern, ())


_STANDING_LOADED_PATTERNS = ("squat", "hip hinge", "single-leg", "carry")
_FREE_WEIGHT_EQUIPMENT = ("barbell", "dumbbell", "kettlebells", "other", "e-z curl bar")
_SUPPORTED_POSITION = ("seated", "lying")
"""`squat`, `hip hinge`, `single-leg` and `carry` are standing by what the
pattern itself means, in this catalog -- there is no seated deadlift. Only
`vertical push` is ambiguous: a standing barbell press and a seated one
share a pattern and equipment, and differ only in whether the bench takes
the load the spine would otherwise carry, which is exactly what these two
keywords catch: `Seated_Barbell_Military_Press`, `Seated_Dumbbell_Press`
and `Kettlebell_Seated_Press` all say so in their own name."""


def derive_spinal_axial_load(pattern: str, exercise: Exercise) -> str:
    """Yes when a real external load bears down through the spine while
    standing: a barbell squat or deadlift, a standing overhead press, a
    loaded carry. No otherwise -- lying, seated, machine-supported, cable
    or bodyweight work, and every isolation movement, none of which load
    the spine axially in this catalog's typical entries.

    A coarse rule and a stated one, not a claim of biomechanical precision:
    `docs/enrichment/definitions.md` carries the same boundary.
    """
    if pattern in _STANDING_LOADED_PATTERNS and exercise.equipment in _FREE_WEIGHT_EQUIPMENT:
        return "yes"
    if (
        pattern == "vertical push"
        and exercise.equipment in _FREE_WEIGHT_EQUIPMENT
        and not _name_has(exercise.name, *_SUPPORTED_POSITION)
    ):
        return "yes"
    return "no"


def derive_required_stability(pattern: str, exercise: Exercise) -> str:
    """High for anything unilateral or carried, low for anything a machine,
    a fixed cable path or a seat supports, medium for standing bilateral
    free weight work in between."""
    if pattern in ("single-leg", "carry"):
        return "high"
    if exercise.equipment == "machine":
        return "low"
    if (
        pattern in ("squat", "hip hinge", "vertical push")
        and exercise.equipment in _FREE_WEIGHT_EQUIPMENT
        and not _name_has(exercise.name, *_SUPPORTED_POSITION)
    ):
        return "medium"
    if exercise.equipment in ("cable",) or pattern in ("horizontal push", "horizontal pull"):
        return "low"
    if _name_has(exercise.name, *_SUPPORTED_POSITION):
        return "low"
    return "medium"


_SETUP_COST_MIN_BY_EQUIPMENT: dict[str | None, int] = {
    "body only": 0,
    "dumbbell": 1,
    "kettlebells": 1,
    "bands": 1,
    "machine": 1,
    "exercise ball": 1,
    "medicine ball": 1,
    "cable": 2,
    "e-z curl bar": 2,
    "other": 2,
    "barbell": 3,
    None: 1,
}
"""Minutes to load and set the equipment up, not to perform the set. A
barbell needs plates found and a rack adjusted; a machine is already loaded
by whoever used it last, or close to it; bodyweight needs nothing at all."""


def derive_setup_cost_min(equipment: str | None) -> int:
    return _SETUP_COST_MIN_BY_EQUIPMENT.get(equipment, 1)


@dataclass(frozen=True)
class Derived:
    """What a rule decided for one exercise. `None` fields were not decided,
    and are never written -- see `derive()`."""

    movement_pattern: str | None
    loaded_joints: tuple[str, ...] | None
    spinal_axial_load: str | None
    required_stability: str | None
    setup_cost_min: int | None


def derive(exercise: Exercise) -> Derived:
    """Decide everything a rule can for one exercise.

    `movement_pattern` first; the other four are functions of it and of
    `equipment`, so a row the pattern rule leaves null gets nothing else
    either -- there is no honest basis for them without it.
    """
    pattern = derive_movement_pattern(exercise)
    if pattern is None:
        return Derived(None, None, None, None, None)
    return Derived(
        movement_pattern=pattern,
        loaded_joints=derive_loaded_joints(pattern, exercise),
        spinal_axial_load=derive_spinal_axial_load(pattern, exercise),
        required_stability=derive_required_stability(pattern, exercise),
        setup_cost_min=derive_setup_cost_min(exercise.equipment),
    )


@dataclass(frozen=True)
class DeriveReport:
    """What one run of `trainer enrich derive` did.

    `decided` and `undecided` are the ids this run actually looked at and
    wrote or could not write -- not the cumulative state of the table, which
    `catalog.stats()`'s enrichment breakdown already reports. `skipped`
    counts rows the pass did not touch because `movement_pattern` is already
    `curated`: the guarantee that a rule never overwrites a curated value
    holds here before it ever reaches the trigger that also enforces it.
    """

    considered: int
    decided: tuple[str, ...]
    undecided: tuple[str, ...]
    skipped_curated: int

    @property
    def coverage(self) -> float:
        """Share of the rows this run considered that it decided a pattern
        for -- undefined, as 0.0, when nothing was considered."""
        return len(self.decided) / self.considered if self.considered else 0.0


def run(connection: sqlite3.Connection) -> DeriveReport:
    """Fill every field a rule can decide, across the strength rows.

    One transaction for the whole batch -- the same shape `import_exercises`
    already uses for the same reason: a failure partway through must leave
    the table exactly as it was, not half-derived, and there is nothing
    row-specific here that a lock held a little longer would put at risk.
    Idempotent by construction -- running it twice re-derives the same
    values for the same inputs and writes them again, which changes nothing
    on disk, and it never touches a row whose `movement_pattern_source` is
    already `curated`.
    """
    found = catalog.search(
        connection, filters={"category": catalog.STRENGTH_CATEGORY}, limit=None
    )
    curated = {
        str(row["id"])
        for row in connection.execute(
            "SELECT id FROM exercises WHERE movement_pattern_source = 'curated'"
        )
    }

    decided: list[str] = []
    undecided: list[str] = []
    skipped = 0

    connection.execute("BEGIN IMMEDIATE")
    try:
        for exercise in found.exercises:
            # Checked before deriving anything: a curated row already has an
            # answer, and belongs in neither `decided` nor `undecided` -- both
            # describe what the rule did, and a curated row is precisely the
            # one the rule never touches.
            if exercise.id in curated:
                skipped += 1
                continue

            result = derive(exercise)
            if result.movement_pattern is None:
                undecided.append(exercise.id)
                continue

            # The WHERE clause repeats the guarantee the `curated` check
            # above already gives: a rule must never overwrite a curated
            # value, and this must hold even if a caller changes the loop
            # above, not only while it reads as written today.
            cursor = connection.execute(
                """
                UPDATE exercises SET
                    movement_pattern = ?, movement_pattern_source = 'rule',
                    loaded_joints = ?, loaded_joints_source = 'rule',
                    spinal_axial_load = ?, spinal_axial_load_source = 'rule',
                    required_stability = ?, required_stability_source = 'rule',
                    setup_cost_min = ?, setup_cost_min_source = 'rule'
                WHERE id = ?
                  AND (movement_pattern_source IS NULL OR movement_pattern_source = 'rule')
                """,
                (
                    result.movement_pattern,
                    json.dumps(list(result.loaded_joints or ())),
                    result.spinal_axial_load,
                    result.required_stability,
                    result.setup_cost_min,
                    exercise.id,
                ),
            )
            if cursor.rowcount:
                decided.append(exercise.id)
            else:
                skipped += 1
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    connection.execute("COMMIT")

    return DeriveReport(
        considered=len(found.exercises),
        decided=tuple(decided),
        undecided=tuple(undecided),
        skipped_curated=skipped,
    )
