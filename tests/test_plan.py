"""The plan as a document: the shape it arrives in, the three rules, the print.

No model anywhere in this file, which is the point of the ticket it covers:
the door the agent will come out through is built and exercised before there
is an agent to come out of it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from conftest import enrich, make_exercise
from trainer import plan as plans
from trainer.engine import admissible, catalog, database, migrations
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
    *items: dict[str, Any], rounds: int = 3, rest: int = 90, reason: str = "because"
) -> dict[str, Any]:
    return {"items": list(items), "rounds": rounds, "rest": rest, "reason": reason}


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

    plans.validate(connection, plans.to_blocks(parsed), BARBELL_45)


def test_an_id_outside_the_set_names_the_equipment(
    connection: sqlite3.Connection,
) -> None:
    parsed = plans.parse(document(block({"exercise_id": "Dumbbell_Bench_Press", "prescription": {"unit": "reps", "amount": 8}})))

    with pytest.raises(plans.PlanRejected) as rejected:
        plans.validate(connection, plans.to_blocks(parsed), BARBELL_45)

    assert "Dumbbell_Bench_Press" in str(rejected.value)
    assert "dumbbell" in str(rejected.value)


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

    with pytest.raises(plans.PlanRejected, match="excluded"):
        plans.validate(connection, plans.to_blocks(parsed), request)


def test_an_id_outside_the_set_names_the_setup_cost(
    connection: sqlite3.Connection,
) -> None:
    """Two minutes available, a bar that takes three to load."""
    parsed = plans.parse(document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}})))

    with pytest.raises(plans.PlanRejected, match="set up"):
        plans.validate(
            connection,
            plans.to_blocks(parsed),
            plans.Request(equipment=("barbell",), budget_min=2),
        )


def test_an_id_the_catalog_does_not_have_is_named_as_an_id(
    connection: sqlite3.Connection,
) -> None:
    parsed = plans.parse(document(block({"exercise_id": "Barbell_Sqvat", "prescription": {"unit": "reps", "amount": 8}})))

    with pytest.raises(plans.PlanRejected, match="Barbell_Sqvat"):
        plans.validate(connection, plans.to_blocks(parsed), BARBELL_45)


def test_a_row_enrichment_does_not_cover_is_rejected_as_that_state(
    connection: sqlite3.Connection,
) -> None:
    """A stretching row is out of the set and will never be in it, and saying
    *needs no equipment* about it would send the reader looking for a fix."""
    parsed = plans.parse(document(block({"exercise_id": "Ankle_Circles", "prescription": {"unit": "seconds", "amount": 30}})))

    with pytest.raises(plans.PlanRejected, match="stretching"):
        plans.validate(
            connection,
            plans.to_blocks(parsed),
            plans.Request(equipment=("barbell", "body only"), budget_min=45),
        )


def test_a_plan_over_the_budget_reports_both_numbers_and_nothing_is_cut(
    connection: sqlite3.Connection,
) -> None:
    parsed = plans.parse(
        document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 10}}, rounds=20, rest=180))
    )
    blocks = plans.to_blocks(parsed)

    with pytest.raises(plans.PlanRejected) as rejected:
        plans.validate(connection, blocks, BARBELL_45)

    assert "45" in str(rejected.value)
    assert "over" in str(rejected.value)
    assert len(blocks[0].items) == 1 and blocks[0].rounds == 20


def test_an_exercise_written_twice_is_refused(connection: sqlite3.Connection) -> None:
    parsed = plans.parse(
        document(
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 5}}),
            block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 12}}),
        )
    )

    with pytest.raises(plans.PlanRejected, match="more than once"):
        plans.validate(connection, plans.to_blocks(parsed), BARBELL_45)


def test_an_unenriched_catalog_is_a_state_not_an_empty_set(database_file: Path) -> None:
    """Validated against an empty admissible set, a good plan is rejected id
    by id -- which reads as four bad choices rather than one missing step."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)

        parsed = plans.parse(document(block({"exercise_id": "Barbell_Squat", "prescription": {"unit": "reps", "amount": 8}})))

        with pytest.raises(admissible.AdmissibleError, match="trainer enrich derive"):
            plans.validate(opened, plans.to_blocks(parsed), BARBELL_45)


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

    with pytest.raises(plans.PlanRejected) as rejected:
        plans.validate(
            connection,
            plans.to_blocks(parsed),
            plans.Request(equipment=("dumbbell",), budget_min=45, groups=("legs",)),
        )

    assert "chest" in str(rejected.value)
    assert "legs" in str(rejected.value)
