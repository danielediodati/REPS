"""The plan as a document: the shape it arrives in, the three rules, the print.

No model anywhere in this file, which is the point of the ticket it covers:
the door the agent will come out through is built and exercised before there
is an agent to come out of it.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from conftest import enrich, make_exercise
from trainer import plan as plans
from trainer.engine import (
    admissible,
    catalog,
    config,
    constraints,
    database,
    duration,
    mesocycles,
    migrations,
    workouts,
)
from trainer.engine.exclusions import Exclusion

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Dumbbell_Bench_Press",
        name="Dumbbell Bench Press",
        equipment="dumbbell",
        primary_muscles=("chest",),
    ),
    make_exercise(
        id="Standing_Military_Press", name="Standing Military Press", equipment="barbell"
    ),
    make_exercise(
        id="Plank", name="Plank", equipment="body only", primary_muscles=("abdominals",)
    ),
    make_exercise(id="Ankle_Circles", name="Ankle Circles", category="stretching"),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Dumbbell_Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 1),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Plank": ("isolation", "shoulder", "no", "low", 0),
}


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


def document(*blocks: dict[str, Any]) -> str:
    return json.dumps({"blocks": list(blocks)})


def block(
    *items: dict[str, Any], rounds: int = 10, rest: int = 210, reason: str = "because"
) -> dict[str, Any]:
    return {"items": list(items), "rounds": rounds, "rest": rest, "reason": reason}


def acknowledging(despite: list[dict[str, Any]], *blocks: dict[str, Any]) -> str:
    return json.dumps({"blocks": list(blocks), "despite": despite})


BARBELL_45 = plans.Request(equipment=("barbell",), budget_min=45)


# -- the shape ----------------------------------------------------------------


def test_a_plan_arrives_whole() -> None:
    parsed = plans.parse(
        document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}, reason="heaviest first"))
    )

    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].items[0].exercise_id == "Barbell_Squat"
    assert parsed.blocks[0].items[0].prescription.amount == 8
    assert parsed.blocks[0].reason == "heaviest first"


def test_timed_work_is_a_prescription_too() -> None:
    """*Three rounds of ten reps of plank* means nothing."""
    parsed = plans.parse(document(block({"exercise_id": "Plank", "prescription": {"unit": "seconds", "amount": 45}})))

    assert parsed.blocks[0].items[0].prescription.unit == "seconds"
    assert parsed.blocks[0].items[0].prescription.amount == 45


def test_a_superset_survives_as_one_block() -> None:
    """Two exercises in one block are not two adjacent blocks; ADR-0002 is
    the whole of why the wire shape is nested rather than flat."""
    parsed = plans.parse(
        document(
            block(
                {"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}},
                {"exercise_id": "Standing_Military_Press", "prescription": {"unit": "reps", "amount": 8}},
            )
        )
    )

    (costed,) = plans.to_blocks(parsed)
    assert len(costed.items) == 2


def test_something_that_is_not_json_says_so() -> None:
    with pytest.raises(plans.PlanError, match="not JSON"):
        plans.parse("blocks: one squat, please")


def test_a_missing_field_is_named() -> None:
    with pytest.raises(plans.PlanError, match="reason"):
        plans.parse(
            json.dumps(
                {
                    "blocks": [
                        {
                            "items": [{"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}],
                            "rounds": 3,
                            "rest": 90,
                        }
                    ]
                }
            )
        )


def test_a_block_with_an_empty_reason_is_refused() -> None:
    """The agent gives its reasons, and an empty string is not one."""
    with pytest.raises(plans.PlanError, match="reason"):
        plans.parse(document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}, reason="")))


def test_an_unrecognised_field_is_refused_rather_than_ignored() -> None:
    """A misspelled field that is quietly dropped is a prescription the author
    believes they wrote."""
    with pytest.raises(plans.PlanError) as raised:
        plans.parse(document(block({"exercise_id": "Barbell_Squat", "repts": 8})))

    assert "repts" in str(raised.value)


def test_a_plan_with_no_blocks_is_refused() -> None:
    with pytest.raises(plans.PlanError):
        plans.parse(json.dumps({"blocks": []}))


def test_reps_and_seconds_together_cannot_be_written_at_all() -> None:
    """The shape carries an amount and its unit, so *both at once* is not a
    plan the validator refuses -- it is not a plan that can be written. That is
    the point: a rule no schema can state is a rule whoever writes against the
    schema is being asked to guess, and a model asked to guess eventually
    guesses wrong."""
    with pytest.raises(plans.PlanError, match="prescription"):
        plans.parse(document(block({"exercise_id": "Plank", "reps": 8, "seconds": 30})))


def test_an_amount_of_zero_is_refused_by_the_block_itself() -> None:
    """`BlockItem.__post_init__` is the one definition of what a block holds,
    and this module restates none of it. The position is added because that
    message is about an item and the author is looking at a file."""
    parsed = plans.parse(
        document(
            block({"exercise_id": "Plank", "prescription": {"unit": "seconds", "amount": 45}}),
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 0}}),
        )
    )

    with pytest.raises(plans.PlanError, match="block 2"):
        plans.to_blocks(parsed)


# -- the validator ------------------------------------------------------------


def test_a_plan_inside_every_rule_passes(connection: sqlite3.Connection) -> None:
    parsed = plans.parse(document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}})))

    assert plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed) == ()


def test_an_id_outside_the_set_names_the_equipment(
    connection: sqlite3.Connection,
) -> None:
    parsed = plans.parse(document(block({"exercise_id": "Dumbbell_Bench_Press", "prescription": {"unit": "reps", "amount": 8}})))

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert refused.rule == plans.ADMISSIBLE
    assert "Dumbbell_Bench_Press" in refused.says
    assert "dumbbell" in refused.says


def test_an_id_outside_the_set_names_the_exclusion(
    connection: sqlite3.Connection,
) -> None:
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        exclusions=(Exclusion("pattern", "vertical push"),),
    )
    parsed = plans.parse(
        document(block({"exercise_id": "Standing_Military_Press", "prescription": {"unit": "reps", "amount": 8}}))
    )

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), request, parsed)

    assert "excluded" in refused.says


def test_an_id_outside_the_set_names_the_setup_cost(
    connection: sqlite3.Connection,
) -> None:
    """Two minutes available, a bar that takes three to load."""
    parsed = plans.parse(document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}})))

    (refused,) = plans.validate(
        connection,
        plans.to_blocks(parsed),
        plans.Request(equipment=("barbell",), budget_min=2),
        parsed,
    )

    assert "set up" in refused.says


def test_an_id_the_catalog_does_not_have_is_named_as_an_id(
    connection: sqlite3.Connection,
) -> None:
    parsed = plans.parse(document(block({"exercise_id": "Barbell_Sqvat", "prescription": {"unit": "reps", "amount": 8}})))

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert "Barbell_Sqvat" in refused.says


def test_a_row_enrichment_does_not_cover_is_rejected_as_that_state(
    connection: sqlite3.Connection,
) -> None:
    """A stretching row is out of the set and will never be in it, and saying
    *needs no equipment* about it would send the reader looking for a fix."""
    parsed = plans.parse(document(block({"exercise_id": "Ankle_Circles", "prescription": {"unit": "seconds", "amount": 30}})))

    (refused,) = plans.validate(
        connection,
        plans.to_blocks(parsed),
        plans.Request(equipment=("barbell", "body only"), budget_min=45),
        parsed,
    )

    assert "stretching" in refused.says


def test_a_plan_over_the_budget_reports_both_numbers_and_nothing_is_cut(
    connection: sqlite3.Connection,
) -> None:
    parsed = plans.parse(
        document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 10}}, rounds=20, rest=180))
    )
    blocks = plans.to_blocks(parsed)

    (refused,) = plans.validate(connection, blocks, BARBELL_45, parsed)

    assert refused.rule == plans.BUDGET
    assert "45" in refused.says
    assert "over" in refused.says
    assert len(blocks[0].items) == 1 and blocks[0].rounds == 20


def lasting(connection: sqlite3.Connection, minutes: int) -> plans.WorkoutPlan:
    """A one-block squat plan that the engine costs at exactly `minutes`."""
    setup = _PATTERNS["Barbell_Squat"][4] * duration.SECONDS_PER_MINUTE
    work = 10 * duration.SECONDS_PER_REP
    for rounds in range(1, 20):
        rest = (minutes * duration.SECONDS_PER_MINUTE - setup) // rounds - work
        parsed = plans.parse(
            document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 10}}, rounds=rounds, rest=max(rest, 0)))
        )
        if duration.plan_duration(connection, plans.to_blocks(parsed)) == minutes:
            return parsed
    raise AssertionError(f"no squat plan lasts {minutes} min")


@pytest.mark.parametrize("minutes", [40, 45, 48, 50])
def test_a_plan_within_five_minutes_of_the_request_is_accepted(
    connection: sqlite3.Connection, minutes: int
) -> None:
    parsed = lasting(connection, minutes)

    assert plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed) == ()


@pytest.mark.parametrize("minutes", [51, 53])
def test_a_plan_over_the_tolerance_is_refused(
    connection: sqlite3.Connection, minutes: int
) -> None:
    parsed = lasting(connection, minutes)

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert refused.rule == plans.BUDGET
    assert f"{minutes - 50} min over" in refused.says


@pytest.mark.parametrize("minutes", [25, 39])
def test_a_plan_under_the_floor_is_refused_saying_how_far_under(
    connection: sqlite3.Connection, minutes: int
) -> None:
    """*You asked for 45 minutes and this gives you 25* is a different mistake from running over."""
    parsed = lasting(connection, minutes)

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert refused.rule == plans.BUDGET
    assert f"{minutes} min" in refused.says and "45" in refused.says
    assert f"{40 - minutes} min under" in refused.says
    assert "over" not in refused.says


def test_a_request_shorter_than_the_tolerance_has_no_floor(
    connection: sqlite3.Connection,
) -> None:
    parsed = lasting(connection, 4)
    short = plans.Request(equipment=("barbell",), budget_min=plans.TOLERANCE_MIN)

    assert plans.validate(connection, plans.to_blocks(parsed), short, parsed) == ()


def test_an_exercise_written_twice_is_refused(connection: sqlite3.Connection) -> None:
    parsed = plans.parse(
        document(
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 5}}),
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 12}}),
        )
    )

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert refused.rule == plans.DUPLICATES
    assert "more than once" in refused.says


def test_every_broken_rule_comes_back_at_once(connection: sqlite3.Connection) -> None:
    """Both rules, in the order the validator decided them."""
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        preferences=("Standing_Military_Press",),
    )
    parsed = plans.parse(
        document(
            block({"exercise_id": "Dumbbell_Bench_Press", "prescription": {"unit": "reps", "amount": 8}}),
            block({"exercise_id": "Standing_Military_Press", "prescription": {"unit": "reps", "amount": 8}}),
        )
    )

    violations = plans.validate(connection, plans.to_blocks(parsed), request, parsed)

    assert [violation.rule for violation in violations] == [
        plans.ADMISSIBLE,
        plans.PREFERENCES,
    ]
    assert "Dumbbell_Bench_Press" in violations[0].says
    assert "Standing_Military_Press" in violations[1].says


def test_a_duplicate_does_not_also_arrive_as_a_costing_error(
    connection: sqlite3.Connection,
) -> None:
    """The clock cannot be read on a plan that names one exercise twice: the
    cost of setting it up is charged once or twice and nothing says which. The
    rule that can be decided is the one reported."""
    parsed = plans.parse(
        document(
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 5}}),
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 12}}),
        )
    )

    violations = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert [violation.rule for violation in violations] == [plans.DUPLICATES]


def test_an_unenriched_catalog_is_a_state_not_an_empty_set(database_file: Path) -> None:
    """Validated against an empty admissible set, a good plan is rejected id
    by id -- which reads as four bad choices rather than one missing step."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)

        parsed = plans.parse(document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}})))

        with pytest.raises(admissible.AdmissibleError, match="trainer enrich derive"):
            plans.validate(opened, plans.to_blocks(parsed), BARBELL_45, parsed)


# -- the reason agrees with the set -------------------------------------------


@pytest.mark.parametrize(
    "request_",
    [
        plans.Request(equipment=("barbell",), budget_min=45),
        plans.Request(equipment=("barbell", "dumbbell"), budget_min=2),
        plans.Request(
            equipment=("barbell", "dumbbell", "body only"),
            budget_min=45,
            exclusions=(Exclusion("pattern", "squat"), Exclusion("joint", "shoulder")),
        ),
        plans.Request(
            equipment=("barbell", "dumbbell", "body only"),
            budget_min=45,
            groups=("legs", "core"),
        ),
    ],
    ids=["one equipment", "no time", "two exclusions", "a leg day"],
)
def test_a_reason_is_given_for_exactly_the_exercises_the_set_leaves_out(
    connection: sqlite3.Connection, request_: plans.Request
) -> None:
    """The property that keeps the explanation honest: `rejection` returns a
    sentence for every id outside the set and `None` for every id inside it.
    A condition added to the `WHERE` without a clause beside it fails here."""
    inside = {
        exercise.id
        for exercise in admissible.admissible_set(
            connection, request_.exclusions, request_.equipment, request_.budget_min
        )
    }

    for exercise_id in sorted(catalog.known_ids(connection)):
        why = admissible.rejection(
            connection,
            exercise_id,
            request_.exclusions,
            request_.equipment,
            request_.budget_min,
        )
        assert (why is None) == (exercise_id in inside), exercise_id


# -- the renderer -------------------------------------------------------------


def rendered(connection: sqlite3.Connection, text: str, budget: int = 45) -> str:
    parsed = plans.parse(text)
    return "\n".join(plans.render(connection, parsed, plans.to_blocks(parsed), budget))


def test_the_rendering_carries_the_whole_prescription(
    connection: sqlite3.Connection,
) -> None:
    out = rendered(
        connection,
        document(
            block(
                {"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}},
                rounds=4,
                rest=150,
                reason="the heaviest lift while fresh",
            )
        ),
    )

    assert "Barbell Squat" in out
    assert "4 rounds" in out
    assert "150s rest" in out
    assert "8 reps" in out
    assert "why: the heaviest lift while fresh" in out
    assert "of 45" in out


def test_an_adaptation_is_rendered_without_the_usual_minutes(
    connection: sqlite3.Connection,
) -> None:
    """Its time is the planner's, read off what the user said: the slot's
    usual minutes are context, and *31 min of 45* reads as a plan that ignored
    them."""
    text = document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}))
    parsed = plans.parse(text)
    adapting = plans.Adapting(
        mesocycle=1,
        served_after=0,
        slot=1,
        cycle=(parsed,),
        split=("legs",),
        still=(1,),
        usual_minutes=45,
        usual_equipment=("barbell",),
    )
    asked = dataclasses.replace(BARBELL_45, adapting=adapting)

    out = plans.render(connection, parsed, plans.to_blocks(parsed), asked.shown_minutes)

    assert BARBELL_45.shown_minutes == 45
    assert out[-1] == f"total {plans.shown(connection, parsed, plans.to_blocks(parsed), None).total_min} min"


def test_timed_work_is_printed_in_seconds(connection: sqlite3.Connection) -> None:
    out = rendered(connection, document(block({"exercise_id": "Plank", "prescription": {"unit": "seconds", "amount": 45}})))

    assert "45 seconds" in out


def test_the_rendering_is_ascii(connection: sqlite3.Connection) -> None:
    """An em dash reaches the Windows console as a replacement character."""
    out = rendered(
        connection, document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}))
    )

    assert out.isascii(), out


def test_the_block_costs_add_up_to_the_total(connection: sqlite3.Connection) -> None:
    """Exact seconds per block, whole minutes rounded up for the total: a
    reader who checks the arithmetic has to find it right."""
    out = rendered(
        connection,
        document(
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}, rounds=3, rest=120),
            block({"exercise_id": "Plank", "prescription": {"unit": "seconds", "amount": 45}}, rounds=3, rest=60),
        ),
    )

    per_block = [
        line.rsplit("-- ", 1)[1] for line in out.splitlines() if line.startswith("block ")
    ]
    seconds = sum(
        int(cost.split(":")[0]) * 60 + int(cost.split(":")[1]) for cost in per_block
    )
    total = int(out.rsplit("total ", 1)[1].split()[0])

    assert len(per_block) == 2
    assert total == -(-seconds // 60)


def test_the_renderer_names_an_unknown_id_rather_than_costing_it(
    connection: sqlite3.Connection,
) -> None:
    """Unreachable through `trainer plan`, which validates first. Called on
    its own, the alternative is a costing failure about a plan whose real
    problem is that it names an exercise nobody has."""
    parsed = plans.parse(document(block({"exercise_id": "Barbell_Sqvat", "prescription": {"unit": "reps", "amount": 8}})))

    with pytest.raises(plans.PlanError, match="Barbell_Sqvat"):
        plans.render(connection, parsed, plans.to_blocks(parsed), 45)


def test_the_renderer_refuses_two_representations_of_different_plans(
    connection: sqlite3.Connection,
) -> None:
    """`render` takes the shape and the costed blocks and trusts them to be
    parallel. Zipped loosely, a mismatched pair prints the shorter of the two
    -- a partial workout rendered as a whole one."""
    parsed = plans.parse(
        document(
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}),
            block({"exercise_id": "Plank", "prescription": {"unit": "seconds", "amount": 45}}),
        )
    )

    with pytest.raises(ValueError):
        plans.render(connection, parsed, plans.to_blocks(parsed)[:1], 45)


def test_an_exercise_for_another_day_is_rejected_naming_what_today_trains(
    connection: sqlite3.Connection,
) -> None:
    """A bench press on a leg day is not a bad choice, it is not today's
    workout, and the rejection has to say which of the two it is."""
    parsed = plans.parse(document(block({"exercise_id": "Dumbbell_Bench_Press", "prescription": {"unit": "reps", "amount": 8}})))

    (refused,) = plans.validate(
        connection,
        plans.to_blocks(parsed),
        plans.Request(equipment=("dumbbell",), budget_min=45, groups=("legs",)),
        parsed,
    )

    assert "chest" in refused.says
    assert "legs" in refused.says


# -- every group asked for is trained ----------------------------------------


SQUAT_ONLY = plans.parse(
    document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}}))
)


def test_a_group_asked_for_and_never_trained_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """The model is told, and gets an attempt to fix it: an eval-only check
    let a plan with no shoulders pass at the first attempt."""
    legs_and_core = plans.Request(
        equipment=("barbell", "body only"), budget_min=45, groups=("legs", "core")
    )

    rules = {
        violation.rule: violation.says
        for violation in plans.validate(
            connection, plans.to_blocks(SQUAT_ONLY), legs_and_core, SQUAT_ONLY
        )
    }

    assert plans.UNTRAINED in rules
    assert "core" in rules[plans.UNTRAINED]
    assert "legs" not in rules[plans.UNTRAINED]


def test_a_group_nothing_today_could_train_is_not_refused(
    connection: sqlite3.Connection,
) -> None:
    """With only a barbell, the dumbbell bench press is the catalog's one chest
    exercise and is out: planning no chest is the honest answer."""
    legs_and_chest = plans.Request(
        equipment=("barbell",), budget_min=45, groups=("legs", "chest")
    )

    assert plans.every_group_trained(connection, SQUAT_ONLY, legs_and_chest) is None


# -- the preferences, and the plan you turned down ----------------------------


LEG_DAY = plans.Request(
    equipment=("barbell",), budget_min=45, preferences=("Barbell_Squat",)
)


def prefers_not(text: str) -> plans.WorkoutPlan:
    return plans.parse(text)


def test_a_preference_prescribed_silently_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """TRAINER.md's fourth invariant is *nothing the user has refused; and if
    it proposes it again, it says so and asks*. Silence is the failure."""
    parsed = plans.parse(
        document(block({"exercise_id": "Barbell_Squat",
                        "prescription": {"unit": "reps", "amount": 8}}))
    )

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), LEG_DAY, parsed)

    assert refused.rule == plans.PREFERENCES
    assert "Barbell_Squat" in refused.says
    assert "rather not" in refused.says


def test_the_refusal_names_the_field_the_reason_goes_in(
    connection: sqlite3.Connection,
) -> None:
    """`PlanBlock.reason` and `Acknowledgement.why` are adjacent ideas under
    different names, and this refusal is what a model reads before trying
    again. It used to say *put the reason in the item's `despite`*, which
    invites the very field it then rejects.

    Measured on `gpt-oss:20b`: a run converged over two attempts, wrote
    `despite: [{exercise_id, reason}]` on the third, and was refused on shape
    with its attempts gone -- a whole run lost to a field name.
    """
    parsed = plans.parse(
        document(block({"exercise_id": "Barbell_Squat",
                        "prescription": {"unit": "reps", "amount": 8}}))
    )

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), LEG_DAY, parsed)

    assert '"why"' in refused.says, "it has to name the field that is accepted"
    assert "`reason`" in refused.says, "and the one that is not"


def test_a_preference_prescribed_with_a_reason_is_allowed(
    connection: sqlite3.Connection,
) -> None:
    """An agent that has read the history and thinks the user should revisit
    something is doing its job. One that slips it in is not."""
    parsed = plans.parse(
        acknowledging(
            [{"exercise_id": "Barbell_Squat",
              "why": "nothing else your equipment reaches loads the knee"}],
            block({"exercise_id": "Barbell_Squat",
                   "prescription": {"unit": "reps", "amount": 8}}),
        )
    )

    assert plans.validate(connection, plans.to_blocks(parsed), LEG_DAY, parsed) == ()


def test_an_empty_acknowledgement_does_not_count() -> None:
    """Whitespace is not saying so, and the shape refuses it before any rule
    has to."""
    with pytest.raises(plans.PlanError, match="why"):
        plans.parse(
            acknowledging(
                [{"exercise_id": "Barbell_Squat", "why": ""}],
                block({"exercise_id": "Barbell_Squat",
                       "prescription": {"unit": "reps", "amount": 8}}),
            )
        )


def test_a_preference_is_not_an_exclusion_and_stays_admissible(
    connection: sqlite3.Connection,
) -> None:
    """An exclusion is safety and the engine takes it out of the space. A
    preference is knowledge of the person, and the agent may still reach for
    it -- which is only possible if it is still there to reach for."""
    inside = {
        exercise.id
        for exercise in admissible.admissible_set(
            connection, LEG_DAY.exclusions, LEG_DAY.equipment, LEG_DAY.budget_min
        )
    }

    assert "Barbell_Squat" in inside


def test_the_acknowledgement_is_printed_where_it_will_be_read(
    connection: sqlite3.Connection,
) -> None:
    """On its own line and marked. Folded into the block's reason it becomes
    one clause among several, and the thing the user has to notice is the
    thing they were asked about."""
    out = rendered(
        connection,
        acknowledging(
            [{"exercise_id": "Barbell_Squat", "why": "nothing else loads the knee today"}],
            block({"exercise_id": "Barbell_Squat",
                   "prescription": {"unit": "reps", "amount": 8}}),
        ),
    )

    assert "! you said no to this: nothing else loads the knee today" in out
    assert out.isascii()


def test_the_plan_that_was_refused_is_not_an_answer(
    connection: sqlite3.Connection,
) -> None:
    """Asked again, it has to answer differently. Handing back the same
    document is the one response that is certainly not a second proposal."""
    text = document(block({"exercise_id": "Barbell_Squat",
                           "prescription": {"unit": "reps", "amount": 8}}))
    again = plans.parse(text)
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        refusals=plans.turned_down((), plans.parse(text), "non mi va"),
    )

    (refused,) = plans.validate(connection, plans.to_blocks(again), request, again)

    assert refused.rule == plans.REFUSED
    assert "already turned down" in refused.says


def test_the_first_plan_of_the_evening_is_still_refused_four_refusals_later(
    connection: sqlite3.Connection,
) -> None:
    """One step of memory is not memory (ADR-0007, item 5). The negotiation
    narrows the older refusals to their exercise ids, which is exactly what it
    takes to recognise the first plan coming back round."""
    text = document(block({"exercise_id": "Barbell_Squat",
                           "prescription": {"unit": "reps", "amount": 8}}))
    first = plans.parse(text)
    refusals = plans.turned_down((), first, "troppo lunga")
    for exercise, said in (
        ("Dumbbell_Bench_Press", "non mi va la panca"),
        ("Standing_Military_Press", "basta spalle"),
        ("Barbell_Deadlift", "no"),
    ):
        refusals = plans.turned_down(
            refusals,
            plans.parse(
                document(block({"exercise_id": exercise,
                                "prescription": {"unit": "reps", "amount": 8}}))
            ),
            said,
        )
    request = plans.Request(
        equipment=("barbell",), budget_min=45, refusals=refusals
    )
    again = plans.parse(text)

    violations = plans.validate(connection, plans.to_blocks(again), request, again)

    assert [violation.rule for violation in violations] == [plans.REFUSED]


def test_a_different_plan_after_a_refusal_passes(
    connection: sqlite3.Connection,
) -> None:
    """What makes the second one better is the agent's business; a rule about
    *how* different it must be would be this module deciding method."""
    refused = plans.parse(
        document(block({"exercise_id": "Barbell_Squat",
                        "prescription": {"unit": "reps", "amount": 8}}))
    )
    offered = plans.parse(
        document(block({"exercise_id": "Barbell_Squat",
                        "prescription": {"unit": "reps", "amount": 5}}, rounds=12))
    )
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        refusals=plans.turned_down((), refused, "non mi va"),
    )

    assert plans.validate(connection, plans.to_blocks(offered), request, offered) == ()


def test_an_acknowledgement_of_something_nobody_refused_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    """Strict structured output puts `despite` on every item, so a model that
    writes a sentence where `null` belongs invents a refusal the user never
    made -- and the renderer prints it back to them as their own words."""
    parsed = plans.parse(
        acknowledging(
            [{"exercise_id": "Barbell_Squat",
              "why": "you hate these but it is all that is left"}],
            block({"exercise_id": "Barbell_Squat",
                   "prescription": {"unit": "reps", "amount": 8}}),
        )
    )

    (refused,) = plans.validate(connection, plans.to_blocks(parsed), BARBELL_45, parsed)

    assert refused.rule == plans.PREFERENCES
    assert "did not" in refused.says

# -- the request, assembled once for every door -------------------------------
#
# `plan.requested` is what both the terminal and the chat call. What is checked
# here is that nothing derivable is asked for, and that a state the declaration
# cannot answer arrives as a state.

TODAY = "2026-09-16"

DECLARING_LEGS = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
split = [["legs"], ["shoulders"]]
equipment = ["barbell", "body only"]
goal = "strength"
"""


@pytest.fixture()
def declaring_legs(declared_training: Path) -> Path:
    """A declaration this catalog can train, so a derived request is answerable."""
    declared_training.write_text(DECLARING_LEGS, encoding="utf-8")
    return declared_training


def test_a_request_nobody_filled_in_is_derived_whole(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """*"What am I doing today?"* names nothing at all: the equipment comes off
    the declaration, the minutes off the cap, and the groups off the workout
    the rotation is at."""
    assembled = plans.requested(connection, TODAY)

    assert assembled.request.equipment == ("barbell", "body only")
    assert assembled.request.budget_min == 45
    assert assembled.request.groups == ("legs",)
    assert assembled.request.allocation == (("legs", 45),)
    assert assembled.request.goal == "strength"
    assert assembled.rotation is not None
    assert assembled.rotation.position == 1


def test_what_a_door_names_wins_over_what_was_declared(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """The declaration is what you own; today is where you are."""
    assembled = plans.requested(
        connection,
        TODAY,
        plans.Asked(equipment=("dumbbell",), minutes=30, groups=("chest",)),
    )

    assert assembled.request.equipment == ("dumbbell",)
    assert assembled.request.budget_min == 30
    assert assembled.request.groups == ("chest",)
    assert assembled.rotation is None, "a named group was derived from nothing"


def test_the_terminal_and_the_chat_assemble_the_same_request(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """The terminal passes what its flags collected and the chat passes an
    empty `Asked`. Given the same state, the two have to be one request --
    which is the whole reason this is a function and not code at each door."""
    from_the_chat = plans.requested(connection, TODAY)
    from_the_terminal = plans.requested(
        connection,
        TODAY,
        plans.Asked(equipment=(), minutes=None, workout=None, groups=(), avoid=()),
    )

    assert from_the_terminal == from_the_chat


def test_a_named_workout_takes_its_groups_off_the_split(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    assembled = plans.requested(connection, TODAY, plans.Asked(workout=2))

    assert assembled.request.groups == ("shoulders",)
    assert assembled.rotation is None


def test_a_named_workout_and_named_groups_ask_for_two_workouts(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    with pytest.raises(plans.PlanRejected, match="one or the other"):
        plans.requested(
            connection, TODAY, plans.Asked(workout=2, groups=("legs",))
        )


def test_a_time_over_the_declared_cap_is_refused_and_never_clamped(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    with pytest.raises(constraints.ConstraintError, match="over the 45"):
        plans.requested(connection, TODAY, plans.Asked(minutes=90))


def test_a_repeated_group_is_dropped_rather_than_halving_the_workout(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """Left in, the even division gives each copy half the time."""
    assembled = plans.requested(
        connection, TODAY, plans.Asked(groups=("legs", "legs"))
    )

    assert assembled.request.groups == ("legs",)
    assert assembled.request.allocation == (("legs", 45),)


def test_a_preference_that_names_no_exercise_is_refused(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """Silently unenforced is the worst outcome: the plan comes back with the
    thing in it, and the typo travels to the model as a rule."""
    with pytest.raises(plans.PlanRejected, match="no such exercise: 'Barbel_Squat'"):
        plans.requested(
            connection, TODAY, plans.Asked(avoid=("Barbel_Squat",))
        )


def test_equipment_the_catalog_does_not_have_is_refused_where_it_is_read(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """A typo in the declaration, caught while the request is assembled rather
    than from inside the graph run -- where a chat could only say *something
    went wrong*. The vocabulary comes off the imported rows, and the refusal
    carries it."""
    declared_training.write_text(
        DECLARING_LEGS.replace(
            'equipment = ["barbell", "body only"]', 'equipment = ["a trapeze"]'
        ),
        encoding="utf-8",
    )

    with pytest.raises(catalog.UnknownFilterValue) as raised:
        plans.requested(connection, TODAY)

    assert raised.value.field == "equipment"
    assert "barbell" in raised.value.valid


def test_equipment_named_today_is_checked_the_same_way(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    with pytest.raises(catalog.UnknownFilterValue, match="no such equipment"):
        plans.requested(
            connection, TODAY, plans.Asked(equipment=("dumbell",))
        )


def test_an_exclusion_is_classified_against_the_catalogs_vocabulary(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    assembled = plans.requested(connection, TODAY, plans.Asked(exclude=("squat",)))

    assert assembled.request.exclusions == (Exclusion("pattern", "squat"),)


def test_an_unenriched_catalog_is_that_state_and_not_a_typo(
    database_file: Path, declared_training: Path
) -> None:
    """Imported but not enriched. Every part of a request is classified
    against the enriched vocabulary sooner or later, so the honest answer is
    *nobody has enriched it yet* -- and it is given before a door promises a
    plan it cannot make."""
    declared_training.write_text(DECLARING_LEGS, encoding="utf-8")
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)

        with pytest.raises(admissible.AdmissibleError) as raised:
            plans.requested(opened, TODAY)

    assert "trainer enrich derive" in str(raised.value)


def test_with_no_declaration_a_door_that_names_everything_still_plans(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """Nothing is derived without declarations, and nothing has to be:
    a door naming the equipment, the time and the groups has said everything a
    plan needs."""
    declared_training.unlink()

    assembled = plans.requested(
        connection,
        TODAY,
        plans.Asked(equipment=("barbell",), minutes=45, groups=("legs",)),
    )

    assert assembled.request.budget_min == 45
    assert assembled.request.goal is None, "nothing declared it"
    assert assembled.rotation is None


def test_with_no_declaration_a_request_nobody_filled_in_is_that_state(
    connection: sqlite3.Connection, declared_training: Path
) -> None:
    """Reported as the state it is, naming the bot -- not as a complaint about
    a field nobody filled in."""
    declared_training.unlink()

    with pytest.raises(config.NoTrainingConfig) as raised:
        plans.requested(connection, TODAY)

    assert "bot" in str(raised.value)

def test_only_one_place_in_the_code_assembles_a_request() -> None:
    """`Request`'s docstring says it is assembled once, and `requested` is
    where. A second `Request(...)` at a door is how the two drift, and this is
    the check that would have caught it -- a convention would be forgotten in
    a month.

    `evaluation.py` is named as the exception rather than excluded quietly:
    its six adverse situations are hand-written requests on purpose, and a
    suite that derived them would measure the rotation instead of the planner.
    """
    source_root = Path(__file__).resolve().parents[1] / "src" / "trainer"
    allowed = {source_root / "plan.py", source_root / "evaluation.py"}

    building = {
        module
        for module in source_root.rglob("*.py")
        if "Request(" in module.read_text(encoding="utf-8")
    }

    assert building <= allowed, sorted(str(m) for m in building - allowed)



# -- a mesocycle: a workout for each slot, checked as that slot ---------------


def squat_day() -> dict[str, Any]:
    return {"blocks": [block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 5}})]}


def press_day() -> dict[str, Any]:
    return {
        "blocks": [
            block({"exercise_id": "Standing_Military_Press", "prescription": {"unit": "reps", "amount": 8}})
        ]
    }


def mesocycle(*workouts: dict[str, Any], cycles: int = 4, why: str = "four cycles to settle the loads") -> str:
    return json.dumps({"workouts": list(workouts), "cycles": cycles, "why": why})


def test_a_mesocycle_is_asked_as_one_request_per_slot(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    asked = plans.mesocycle_requested(connection, TODAY)

    assert [slot.groups for slot in asked.slots] == [("legs",), ("shoulders",)]
    assert {slot.budget_min for slot in asked.slots} == {45}
    assert {slot.goal for slot in asked.slots} == {"strength"}


def test_a_mesocycle_that_fits_every_slot_breaks_nothing(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    asked = plans.mesocycle_requested(connection, TODAY)
    parsed = plans.parse_mesocycle(mesocycle(squat_day(), press_day()))

    assert plans.validate_mesocycle(connection, parsed, asked) == ()


def test_a_workout_that_breaks_a_rule_is_named_by_its_slot(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """The press is admissible for shoulders and not for legs: the same
    workout is right in one slot and wrong in the other."""
    asked = plans.mesocycle_requested(connection, TODAY)
    parsed = plans.parse_mesocycle(mesocycle(press_day(), press_day()))

    violations = plans.validate_mesocycle(connection, parsed, asked)

    assert violations
    assert all(violation.says.startswith("workout 1: ") for violation in violations)


def test_a_mesocycle_is_one_workout_per_slot(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    asked = plans.mesocycle_requested(connection, TODAY)
    parsed = plans.parse_mesocycle(mesocycle(squat_day()))

    (violation,) = plans.validate_mesocycle(connection, parsed, asked)

    assert "1 workout" in violation.says and "2" in violation.says


@pytest.mark.parametrize(
    ("cycles", "why", "field"), [(0, "because", "cycles"), (4, "   ", "why")]
)
def test_a_mesocycle_says_how_long_and_why(cycles: int, why: str, field: str) -> None:
    with pytest.raises(plans.PlanError, match=field):
        plans.parse_mesocycle(mesocycle(squat_day(), cycles=cycles, why=why))


def test_a_mesocycle_already_turned_down_is_refused(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    parsed = plans.parse_mesocycle(mesocycle(squat_day(), press_day()))
    asked = plans.mesocycle_requested(connection, TODAY)
    asked = dataclasses.replace(
        asked, refusals=plans.mesocycle_turned_down(asked.refusals, parsed, "no")
    )

    (violation,) = plans.validate_mesocycle(connection, parsed, asked)

    assert violation.rule == plans.REFUSED


# -- an adaptation and a change: today's slot, or the mesocycle, asked again --


def kept(connection: sqlite3.Connection, cycles: int = 4) -> int:
    """The squat day and the press day, accepted."""
    parsed = plans.parse_mesocycle(mesocycle(squat_day(), press_day(), cycles=cycles))
    return mesocycles.record_mesocycle(
        connection,
        tuple(
            tuple(
                workouts.PrescribedBlock(block=costed, reason=shape.reason)
                for shape, costed in zip(workout.blocks, plans.to_blocks(workout), strict=True)
            )
            for workout in parsed.workouts
        ),
        cycles=parsed.cycles,
        why=parsed.why,
        on=TODAY,
    )


def test_an_adaptation_starts_from_todays_slot_and_binds_nothing_of_it(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    identifier = kept(connection)

    asked = plans.adaptation_requested(connection, TODAY, said="solo 30 minuti oggi")

    assert asked.groups == ()
    assert asked.equipment == tuple(catalog.values(connection, "equipment"))
    assert asked.adapting is not None
    assert asked.adapting.workout == plans.WorkoutPlan.model_validate(squat_day())
    assert (asked.adapting.mesocycle, asked.adapting.served_after) == (identifier, 0)
    assert (asked.adapting.said, asked.adapting.still) == ("solo 30 minuti oggi", (1, 2))


def test_an_adaptation_needs_a_mesocycle_to_adapt(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    with pytest.raises(mesocycles.MesocycleError, match="--mesocycle"):
        plans.adaptation_requested(connection, TODAY, plans.Asked(minutes=30))


def test_equipment_named_on_the_terminal_is_this_workouts_in_full(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    kept(connection)

    asked = plans.adaptation_requested(connection, TODAY, plans.Asked(equipment=("body only",)))

    assert asked.equipment == ("body only",)


def test_this_workouts_equipment_is_checked_against_the_catalog(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    kept(connection)

    with pytest.raises(catalog.UnknownFilterValue):
        plans.adaptation_requested(connection, TODAY, plans.Asked(equipment=("dumbells",)))


@pytest.mark.parametrize("asked", [plans.Asked(workout=2), plans.Asked(groups=("shoulders",))])
def test_an_adaptation_chooses_its_workout_itself(
    connection: sqlite3.Connection, declaring_legs: Path, asked: plans.Asked
) -> None:
    kept(connection)

    with pytest.raises(plans.PlanRejected, match="chooses"):
        plans.adaptation_requested(connection, TODAY, asked)


def test_a_workout_already_performed_this_cycle_is_not_one_to_count_as(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    kept(connection)
    found = mesocycles.today(connection)
    served = mesocycles.record_adapted(
        connection,
        mesocycles.active(connection).slots[1],  # type: ignore[union-attr]
        on=TODAY,
        mesocycle=found.mesocycle,
        served_after=found.performed,
        slot=2,
    )
    connection.execute("UPDATE workouts SET state = 'performed', performed_on = ? WHERE id = ?", (TODAY, served))

    asked = plans.adaptation_requested(connection, TODAY)

    assert asked.adapting is not None and asked.adapting.still == (1,)
    assert plans.COUNTS_AS in rules(connection, asked, adapted_document(counts_as=2))
    assert plans.COUNTS_AS not in rules(connection, asked, adapted_document(counts_as=1))


def test_an_exclusion_binds_an_adaptation_and_carries_its_retest(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    kept(connection)
    connection.execute(
        "INSERT INTO exclusions (granularity, value, retest_date) VALUES ('pattern', 'squat', '2099-03-01')"
    )

    asked = plans.adaptation_requested(connection, TODAY, said="oggi squat")

    assert asked.adapting is not None
    assert asked.adapting.retests == ("pattern squat until 2099-03-01",)
    assert plans.ADMISSIBLE in rules(connection, asked, adapted_document())


def test_an_adaptation_is_held_to_no_time(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    kept(connection)
    asked = plans.adaptation_requested(connection, TODAY, plans.Asked(minutes=10))

    assert plans.BUDGET not in rules(connection, asked, adapted_document(rounds=20))


def adapted_document(counts_as: int = 1, rounds: int = 3) -> str:
    plan = json.loads(
        document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 5}}, rounds=rounds))
    )
    return json.dumps({**plan, "counts_as": counts_as, "note": ""})


def rules(connection: sqlite3.Connection, request: plans.Request, text: str) -> list[str]:
    plan = plans.parse(text) if request.adapting is None else plans.parse_adapted(text)
    return [v.rule for v in plans.validate(connection, plans.to_blocks(plan), request, plan)]


def test_a_change_is_asked_with_the_mesocycle_it_rewrites(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    identifier = kept(connection, cycles=3)

    asked = plans.change_requested(connection, TODAY, said="basta squat")

    assert [slot.groups for slot in asked.slots] == [("legs",), ("shoulders",)]
    assert asked.changing is not None
    assert asked.changing.current == plans.parse_mesocycle(
        mesocycle(squat_day(), press_day(), cycles=3)
    )
    assert (asked.changing.mesocycle, asked.changing.accepted_after) == (identifier, 0)
    assert (asked.changing.cycle, asked.changing.said) == (1, "basta squat")


def test_a_change_needs_a_mesocycle_to_change(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    with pytest.raises(mesocycles.MesocycleError, match="--mesocycle"):
        plans.change_requested(connection, TODAY, said="basta squat")


def test_a_change_that_would_end_before_the_cycle_it_is_in_is_refused(
    connection: sqlite3.Connection, declaring_legs: Path
) -> None:
    """Its cycles count the ones done: fewer than the current one ends it on the spot."""
    kept(connection, cycles=3)
    asked = plans.change_requested(connection, TODAY, said="basta squat")
    assert asked.changing is not None
    asked = dataclasses.replace(asked, changing=dataclasses.replace(asked.changing, cycle=2))
    parsed = plans.parse_mesocycle(mesocycle(squat_day(), press_day(), cycles=1))

    (violation,) = plans.validate_mesocycle(connection, parsed, asked)

    assert violation.rule == plans.CYCLES
    assert "cycle 2" in violation.says
