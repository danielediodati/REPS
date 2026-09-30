"""The shared tool surface: the answers, and the states that are not answers.

`tests/test_mcp_server.py` checks that one door serves exactly what is defined
here. This file checks what the definitions actually do -- the new tool, the
shaping, and the three preconditions that have to arrive as states with the
command that fixes them rather than as a plausible-looking empty answer.
"""

from __future__ import annotations

import enum
import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from conftest import enrich, make_exercise
from trainer import plan, tools
from trainer.engine import (
    catalog,
    database,
    duration,
    exclusions,
    graph,
    migrations,
    workouts,
)
from trainer.coach import logger
from trainer.engine.exclusions import Exclusion

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Dumbbell_Squat",
        name="Dumbbell Squat",
        equipment="dumbbell",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Standing_Military_Press", name="Standing Military Press", equipment="barbell"
    ),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Dumbbell_Squat": ("squat", "hip, knee, ankle", "yes", "medium", 1),
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
}

GRAPH = """\
# A throwaway graph

## Variant groups

| representative | member | note |
|---|---|---|
| `Barbell_Squat` | `Dumbbell_Squat` | the same squat, held at the sides |

## Regression edges

| easier | harder | note |
|---|---|---|
| `Bodyweight_Squat` | `Barbell_Squat` | the same squat, no load yet |
"""


@pytest.fixture()

def stocked(database_file: Path) -> Iterator[sqlite3.Connection]:
    """A database the tools will find: `TRAINER_DB` points them at it."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        graph.apply(opened, *graph.parse(GRAPH))
        yield opened


# -- what constrains training today -------------------------------------------


def test_a_persisted_exclusion_is_applied_when_the_caller_names_none(
    stocked: sqlite3.Connection,
) -> None:
    """Only the CLI read the exclusions table. A door that does not would hand
    the agent exercises the validator then refuses."""
    exclusions.add(stocked, Exclusion("pattern", "squat"), "2099-01-01")
    stocked.commit()

    found = tools.admissible_set(["barbell", "dumbbell", "body only"], 45)

    assert [exercise["id"] for exercise in found] == ["Standing_Military_Press"]


def test_a_budget_over_the_declared_cap_is_refused_naming_the_cap(
    stocked: sqlite3.Connection,
) -> None:
    """The cap is the one number in `training.toml` that says a workout never
    runs longer than this. Answered instead, the agent plans against minutes
    the user does not have."""
    with pytest.raises(tools.ToolFailure, match="60"):
        tools.admissible_set(["barbell"], 90)


def test_the_tool_itself_answers_with_the_whole_record(
    stocked: sqlite3.Connection,
) -> None:
    """What a door hides is the door's business: `trainer mcp` is an inspector
    and pays none of it."""
    found = tools.admissible_set(["barbell"], 45)

    assert sorted(found[0]) == [
        "category",
        "equipment",
        "force",
        "id",
        "images",
        "instructions",
        "level",
        "mechanic",
        "name",
        "primary_muscles",
        "secondary_muscles",
    ]


# -- compare_variants, the tool this ticket adds ------------------------------


def test_compare_variants_answers_with_the_four_fields(
    stocked: sqlite3.Connection,
) -> None:
    """TRAINER.md names them beside the call: movement pattern, loaded joints,
    required stability, setup cost."""
    found = tools.compare_variants("Barbell_Squat", "Dumbbell_Squat")

    for side in (found["a"], found["b"]):
        assert side["movement_pattern"] == "squat"
        assert side["loaded_joints"] == ["hip", "knee", "ankle"]
        assert side["required_stability"] in ("high", "medium")
        assert isinstance(side["setup_cost_min"], int)
    assert found["a"]["required_stability"] != found["b"]["required_stability"]


def test_compare_variants_says_two_members_of_a_group_are_one_movement(
    stocked: sqlite3.Connection,
) -> None:
    found = tools.compare_variants("Dumbbell_Squat", "Barbell_Squat")

    assert found["same_movement"] is True
    assert found["easier"] is None


def test_compare_variants_names_the_easier_of_a_regression_pair(
    stocked: sqlite3.Connection,
) -> None:
    found = tools.compare_variants("Barbell_Squat", "Bodyweight_Squat")

    assert found["easier"] == "Bodyweight_Squat"
    assert found["same_movement"] is False


def test_compare_variants_says_so_when_the_graph_relates_nothing(
    stocked: sqlite3.Connection,
) -> None:
    """Not an empty answer, which reads as *these two have nothing in common*
    whether the graph says nothing or the ids were wrong."""
    found = tools.compare_variants("Barbell_Squat", "Standing_Military_Press")

    assert found["same_movement"] is False
    assert found["easier"] is None
    assert "neither" in found["summary"]
    assert found["a"]["movement_pattern"] != found["b"]["movement_pattern"]


def test_compare_variants_names_an_id_the_catalog_does_not_have(
    stocked: sqlite3.Connection,
) -> None:
    with pytest.raises(tools.ToolFailure, match="Barbell_Sqvat"):
        tools.compare_variants("Barbell_Squat", "Barbell_Sqvat")


def test_compare_variants_asks_the_same_question_of_an_id_and_itself(
    stocked: sqlite3.Connection,
) -> None:
    """Read off the edges alone this answers *the same movement* for a group
    member, whose two sides share a `variant_of`, and *neither* for the
    representative of that same group -- one question, two answers, decided by
    where in the graph the id happens to sit."""
    member = tools.compare_variants("Dumbbell_Squat", "Dumbbell_Squat")
    representative = tools.compare_variants("Barbell_Squat", "Barbell_Squat")

    assert member["same_movement"] is representative["same_movement"] is True
    assert member["summary"] == representative["summary"] == "the same exercise"


def test_compare_variants_refuses_a_catalog_the_graph_was_never_applied_to(
    database_file: Path,
) -> None:
    """`trainer enrich curated` is a command of its own. Without it every pair
    comes back *neither the same movement nor a regression of one another* --
    a decided no, indistinguishable from a real one, and the running example
    TRAINER.md is built on is the first casualty."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)

    with pytest.raises(tools.ToolFailure, match="trainer enrich curated"):
        tools.compare_variants("Barbell_Squat", "Dumbbell_Squat")


# -- the read tools this ticket adds ------------------------------------------


def performed(connection: sqlite3.Connection, on: str, exercise_id: str, rounds: int) -> None:
    """One performed workout, straight sets, written the way a report writes
    it. `tools` reopens the database on its own, so this commits."""
    workouts.record_performed(
        connection,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id=exercise_id,
                        unit="reps",
                        amount=8,
                        amount_source="reported",
                    ),
                ),
                rounds=rounds,
                rounds_source="reported",
                rest=90,
                rest_source="reported",
            ),
        ),
        on=on,
        report="done",
    )


def test_search_exercises_finds_what_a_phrase_names(
    stocked: sqlite3.Connection,
) -> None:
    found = tools.search_exercises("dumbbell squat")

    assert found["total"] == 1
    assert found["exercises"][0]["id"] == "Dumbbell_Squat"


def test_search_exercises_answers_nothing_rather_than_a_guess(
    stocked: sqlite3.Connection,
) -> None:
    """An id you did not ask for reads exactly like the one you did, and it is
    the id that gets prescribed."""
    found = tools.search_exercises("quidditch broomstick")

    assert found == {"total": 0, "exercises": []}


def test_search_exercises_says_how_many_there_were_before_the_limit(
    stocked: sqlite3.Connection,
) -> None:
    found = tools.search_exercises("squat", limit=1)

    assert len(found["exercises"]) == 1
    assert found["total"] == 3


def test_adherence_history_counts_what_became_of_the_workouts(
    stocked: sqlite3.Connection,
) -> None:
    performed(stocked, "2026-09-01", "Barbell_Squat", 3)

    answer = tools.adherence_history(cycles=1)

    assert answer["known"] is True
    assert answer["value"]["performed"] == 1
    assert answer["value"]["unplanned"] == 1


def test_adherence_history_against_nothing_is_an_answer_and_not_a_failure(
    stocked: sqlite3.Connection,
) -> None:
    answer = tools.adherence_history(cycles=1)

    assert answer["known"] is False
    assert answer["value"] is None


def test_volume_deficit_carries_both_axes_and_the_number_itself(
    stocked: sqlite3.Connection,
) -> None:
    performed(stocked, "2026-09-01", "Barbell_Squat", 4)

    found = tools.volume_deficit(cycles=1)

    by_axis = {(short["axis"], short["key"]): short for short in found}
    assert by_axis[("pattern", "squat")]["performed"] == 4
    assert by_axis[("pattern", "squat")]["deficit"] == -4
    assert by_axis[("muscle", "quadriceps")]["performed"] == 4


def test_unreported_workouts_states_the_fact_and_changes_nothing(
    stocked: sqlite3.Connection,
) -> None:
    identifier = workouts.record_prescribed(
        stocked,
        (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(duration.BlockItem(exercise_id="Barbell_Squat", reps=8),),
                    rounds=4,
                    rest=120,
                ),
                reason="because",
            ),
        ),
        on="2020-01-01",
    )
    performed(stocked, "2020-02-01", "Standing_Military_Press", 3)

    (waiting,) = tools.unreported_workouts()

    assert waiting["workout_id"] == identifier
    assert waiting["prescribed_on"] == "2020-01-01"
    assert waiting["days_ago"] > 0
    assert stocked.execute(
        "SELECT state FROM workouts WHERE id = ?", (identifier,)
    ).fetchone()["state"] == "prescribed"


def test_unreported_workouts_is_empty_when_nothing_is_waiting(
    stocked: sqlite3.Connection,
) -> None:
    assert tools.unreported_workouts() == []


def test_a_window_with_no_declared_rotation_is_the_configuration_s_own_state(
    stocked: sqlite3.Connection, declared_training: Path
) -> None:
    """A question about cycles cannot be answered without knowing how long one
    is, and the answer names the bot rather than a state the engine invented."""
    declared_training.unlink()

    with pytest.raises(tools.ToolFailure, match="nothing declared yet"):
        tools.pattern_history(pattern="squat", cycles=1)


# -- the preconditions, stated once and with the way out ----------------------


def test_a_missing_database_is_a_state_with_its_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`no such table: exercises` names neither the state nor the way out."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))

    with pytest.raises(tools.ToolFailure, match="trainer db init"):
        tools.admissible_set(equipment=["barbell"], budget_min=45)


def test_a_database_behind_this_checkout_is_a_state_with_its_remedy(
    stocked: sqlite3.Connection,
) -> None:
    stocked.execute(
        "DELETE FROM schema_migrations WHERE version = (SELECT MAX(version) "
        "FROM schema_migrations)"
    )

    with pytest.raises(tools.ToolFailure, match="trainer db init"):
        tools.admissible_set(equipment=["barbell"], budget_min=45)


def test_an_empty_catalog_is_a_state_with_its_remedy(database_file: Path) -> None:
    """A vocabulary read from an empty table is empty, so every correct value
    would come back rejected as a typo. CLAUDE.md's standing rule."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())

    with pytest.raises(tools.ToolFailure, match="trainer db import"):
        tools.compare_variants("Barbell_Squat", "Dumbbell_Squat")


def test_an_unenriched_catalog_is_a_state_with_its_remedy(database_file: Path) -> None:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)

    with pytest.raises(tools.ToolFailure, match="trainer enrich derive"):
        tools.admissible_set(equipment=["barbell"], budget_min=45)


def test_arithmetic_needs_no_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`allocate` opens no connection. A tool that opened one it does not read
    would make a missing database look like a failure of the arithmetic."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))

    assert tools.allocate(minutes=30, proportions={"legs": 1.0}) == {"legs": 30}


# -- the surface itself -------------------------------------------------------


def test_every_tool_is_documented_and_annotated() -> None:
    """The docstring is what a model reads to decide whether to call the tool,
    and the annotations are what both doors build a schema from."""
    for tool in tools.TOOLS:
        assert tool.__doc__, f"{tool.__name__} has no description"
        assert "return" in tool.__annotations__, f"{tool.__name__} has no return type"


def test_the_tool_with_nothing_to_wrap_is_not_here() -> None:
    """`active_conclusions` needs `conclusions`, which is session 8. A tool
    that exists and cannot work is worse than one that does not exist.

    `adherence_history` was named here too until session 5 gave it the rows it
    reads, and it is registered now."""
    named = {tool.__name__ for tool in tools.TOOLS}

    assert "active_conclusions" not in named
    assert "adherence_history" in named


def test_allocate_says_what_a_share_looks_like() -> None:
    """The unit, where the model reads it rather than where we know it.

    An observed run called `allocate` with `{"chest": 22/45, "arms": 23/45}`:
    the minutes the brief had just given it, over the budget. JSON has no
    arithmetic, so Ollama refused the call before it reached the tool and the
    whole run went with it -- a failure `tools.execute` could not turn into a
    result to recover from, because the provider rejected it first.

    The docstring is the schema's description, so this is what is actually
    sent. The same mistake with the same shape is `rest: 60000` on
    `PlanBlock`, and it is guarded the same way.
    """
    described = tools.schema(tools.allocate)["description"]

    assert "decimal" in described
    assert "0.49" in described, "a share with no example is a share the model guesses"
    assert "fraction" in described


# -- how a model calls them ---------------------------------------------------
#
# The definition each tool is offered as, the arguments it comes back with,
# and the answer trimmed to what the door asking reads. These lived in
# `test_agent.py` beside the loop that session 9 deleted; the derivation they
# are about moved here with the code.


def call(name: str, **arguments: Any) -> tools.Call:
    return tools.Call(id=f"call_{name}", name=name, arguments=arguments)


def executed(one: tools.Call, offered: Sequence[str] = logger.TOOLS) -> tools.Result:
    """One call against the surface a door offers, the way a graph runs it."""
    return tools.execute(one, tools.registered("test", offered), logger.KEEPS)


def a_plan() -> plan.WorkoutPlan:
    """A plan the project calls valid, for the schema the model is held to."""
    return plan.WorkoutPlan(
        blocks=[
            plan.PlanBlock(
                items=[
                    plan.PlanItem(
                        exercise_id="Barbell_Squat",
                        prescription=plan.Prescription(unit="reps", amount=8),
                    )
                ],
                rounds=3,
                rest=120,
                reason="because it is a squat and squats are good",
            )
        ]
    )


def test_every_tool_reaches_the_model_with_a_description_and_arguments() -> None:
    """A tool the model cannot fill the arguments in for is a tool it cannot
    call, and a tool with no description is one it cannot choose."""
    for tool in tools.registered("test", logger.TOOLS):
        offered = tools.schema(tool)
        assert offered["description"], f"{offered['name']} has no description"
        assert offered["parameters"]["type"] == "object"
        if offered["name"] == "unreported_workouts":
            # The one question with nothing to ask about: *today* is the
            # door's to supply, never the model's, because nothing in
            # `engine/` reads the clock.
            assert offered["parameters"]["properties"] == {}
            continue
        assert offered["parameters"]["properties"], f"{offered['name']} takes nothing"


def test_a_result_reaches_the_model_as_json(stocked: sqlite3.Connection) -> None:
    """The tool docstrings describe `known: false`; Python would hand back
    `'known': False`, and a model translating between two dialects mid-loop is
    one more thing that can go wrong for nothing."""
    result = executed(call("pattern_history", pattern="squat", cycles=3))

    assert result.failed is False
    assert json.loads(result.content)["known"] is False


class Grip(enum.Enum):
    OVERHAND = "overhand"
    UNDERHAND = "underhand"


def a_tool(grips: list[Grip]) -> str:
    """A tool with a parameter pydantic describes by reference."""
    return ", ".join(grip.value for grip in grips)


def test_a_definition_a_parameter_needs_is_hoisted_where_it_resolves() -> None:
    """A `$ref` resolves from the root of the schema document, and the root is
    `parameters`. Left inside the property, the definitions an enum or a
    model-typed parameter needs sit one level too deep and every reference to
    them dangles."""
    built = tools.schema(a_tool)["parameters"]

    assert "$defs" in built, "the definition was left inside the property"
    assert "$defs" not in built["properties"]["grips"]
    referenced = built["properties"]["grips"]["items"]["$ref"].removeprefix("#/$defs/")
    assert referenced in built["$defs"]


def test_strict_mode_requires_every_property_including_the_defaulted_ones() -> None:
    """Strict mode is constrained decoding, and it demands every property be
    listed in `required`. Pydantic leaves out the ones carrying a default,
    which is the plan's `despite`. That it must be present is exactly why it
    is a list and not a field on every item: the empty answer is `[]`, which a
    model writes without being talked into it."""
    built = tools.strict_schema(plan.WorkoutPlan)
    item = built["$defs"]["PlanItem"]

    assert set(item["required"]) == {"exercise_id", "prescription"}
    assert set(built["$defs"]["Prescription"]["required"]) == {"unit", "amount"}
    assert item["additionalProperties"] is False
    assert set(built["required"]) == {"blocks", "despite"}


def test_the_strict_shape_still_accepts_a_plan_the_project_calls_valid() -> None:
    """The transform above rewrites the schema the model is held to. If it
    drifted from what `WorkoutPlan` actually parses, every run would emit
    something the validator then refuses on shape."""
    import jsonschema

    emitted = json.loads(a_plan().model_dump_json())

    jsonschema.validate(emitted, tools.strict_schema(plan.WorkoutPlan))


def test_trimming_reaches_a_record_nested_under_a_key() -> None:
    """`compare_variants` already answers `{"a": {...}, "b": {...}}`. A tool
    that nests a list of exercises brings back the payload this exists to
    bound, with nothing failing to say so."""
    answer = {"variants": [{"id": "X", "instructions": ["long"], "level": "expert"}]}

    trimmed = tools._trimmed(answer, logger.KEEPS)

    assert trimmed == {"variants": [{"id": "X"}]}


def test_an_answer_envelope_is_not_cut_to_an_exercise_record() -> None:
    """`known: false` is the difference between *nobody has trained this* and a
    field that happens to be empty, and it is not a catalog field to drop."""
    answer = {"about": "squat", "known": False, "value": None}

    assert tools._trimmed(answer, logger.KEEPS) == answer
