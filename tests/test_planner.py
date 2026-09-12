"""The planner graph, against a scripted chat model."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from conftest import enrich, make_exercise
from trainer import agent
from trainer import plan as plans
from trainer.coach import checkpoints, planner, record
from trainer.engine import catalog, database, exclusions, migrations
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
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Dumbbell_Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 1),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
}

BARBELL_45 = plans.Request(equipment=("barbell",), budget_min=45)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


def plan_of(
    *exercise_ids: str, rounds: int = 3, reason: str = "it trains what today asks for"
) -> plans.WorkoutPlan:
    return plans.WorkoutPlan(
        blocks=[
            plans.PlanBlock(
                items=[
                    plans.PlanItem(
                        exercise_id=exercise_id,
                        prescription=plans.Prescription(unit="reps", amount=8),
                    )
                ],
                rounds=rounds,
                rest=120,
                reason=reason,
            )
            for exercise_id in exercise_ids
        ]
    )


class Scripted(BaseChatModel):
    """A chat model whose turns and emitted plans were written in advance."""

    turns: list[AIMessage] = []
    documents: list[plans.WorkoutPlan] = []
    schemas: list[dict[str, Any]] = []
    seen: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        turn = self.turns.pop(0) if self.turns else AIMessage(content="")
        return ChatResult(generations=[ChatGeneration(message=turn)])

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self.bind(tools=tools, **kwargs)

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        assert isinstance(schema, dict)
        self.schemas.append(schema)

        def emitted(messages: Any) -> dict[str, Any]:
            raw = AIMessage(content=self.documents.pop(0).model_dump_json())
            return {"raw": raw, "parsed": None, "parsing_error": None}

        return RunnableLambda(emitted)


def test_a_turn_with_no_tool_call_goes_to_emit(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[AIMessage(content="I have what I need.")],
        documents=[plan_of("Barbell_Squat")],
    )

    final = planner.build(model).invoke({"request": BARBELL_45})

    assert final["plan"] == plan_of("Barbell_Squat")
    assert final["violations"] == ()
    assert final["attempts"] == 1


def calling(name: str, **arguments: Any) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": arguments, "id": f"call_{name}", "type": "tool_call"}],
    )


def test_a_tool_call_is_answered_before_the_planner_turns_again(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[calling("admissible_set", equipment=["barbell"], budget_min=45)],
        documents=[plan_of("Barbell_Squat")],
    )

    final = planner.build(model).invoke({"request": BARBELL_45})

    answered = model.seen[1][-1]
    assert isinstance(answered, ToolMessage)
    assert "Standing_Military_Press" in answered.text
    assert final["spent"] == 1


def test_a_spent_call_budget_goes_to_emit(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[
            calling("allocate", minutes=45, proportions={"legs": 1.0}),
            calling("allocate", minutes=45, proportions={"legs": 1.0}),
        ],
        documents=[plan_of("Barbell_Squat")],
    )

    final = planner.build(model, budget=1).invoke({"request": BARBELL_45})

    assert len(model.seen) == 1
    assert final["spent"] == 1
    assert final["plan"] == plan_of("Barbell_Squat")


def test_a_run_that_spends_the_whole_default_budget_still_emits(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calling("allocate", minutes=45, proportions={"legs": 1.0})
            for _ in range(agent.CALL_BUDGET)
        ],
        documents=[plan_of("Barbell_Squat")],
    )

    final = planner.build(model).invoke({"request": BARBELL_45})

    assert final["spent"] == agent.CALL_BUDGET
    assert final["plan"] == plan_of("Barbell_Squat")


def test_a_run_that_spends_the_budget_and_every_attempt_still_ends(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calling("allocate", minutes=45, proportions={"legs": 1.0})
            for _ in range(agent.CALL_BUDGET)
        ],
        documents=[plan_of("Dumbbell_Bench_Press")] * planner.ATTEMPTS,
    )

    final = planner.build(model).invoke({"request": BARBELL_45})

    assert final["attempts"] == planner.ATTEMPTS
    assert final["violations"]


def test_a_refusal_goes_back_to_the_planner_with_the_validators_message(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Fixed.")],
        documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
    )

    final = planner.build(model).invoke({"request": BARBELL_45})

    feedback = model.seen[1][-1]
    assert isinstance(feedback, HumanMessage)
    assert "Dumbbell_Bench_Press" in feedback.text
    assert final["attempts"] == 2
    assert final["violations"] == ()
    assert final["plan"] == plan_of("Barbell_Squat")


def test_a_plan_that_breaks_two_rules_gets_both_back_in_one_message(
    connection: sqlite3.Connection,
) -> None:
    """Both of them in one message, and the planner plans again from it."""
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        preferences=("Standing_Military_Press",),
    )
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Fixed.")],
        documents=[
            plan_of("Dumbbell_Bench_Press", "Standing_Military_Press"),
            plan_of("Barbell_Squat"),
        ],
    )

    final = planner.build(model).invoke({"request": request})

    fed_back = [
        message
        for message in model.seen[1]
        if isinstance(message, HumanMessage) and message.name == "validator"
    ]
    assert len(fed_back) == 1
    assert "Dumbbell_Bench_Press" in fed_back[0].text
    assert "Standing_Military_Press" in fed_back[0].text
    assert final["violations"] == ()


def test_the_third_refusal_ends_the_run_as_refused(connection: sqlite3.Connection) -> None:
    model = Scripted(documents=[plan_of("Dumbbell_Bench_Press")] * 4)

    final = planner.build(model).invoke({"request": BARBELL_45})

    assert final["attempts"] == 3
    assert [violation.rule for violation in final["violations"]] == [plans.ADMISSIBLE]
    assert "Dumbbell_Bench_Press" in plans.refusal(final["violations"])
    assert final["plan"] == plan_of("Dumbbell_Bench_Press")
    assert len(model.documents) == 1


def test_the_record_holds_every_attempt_and_what_each_node_cost(
    connection: sqlite3.Connection,
) -> None:
    """A run refused once and fixed on the second attempt: the record says
    which rule refused which attempt, and where the minutes went."""
    model = Scripted(
        turns=[
            calling("allocate", minutes=45, proportions={"legs": 1.0}),
            AIMessage(content="Fixed."),
        ],
        documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
    )

    final = planner.build(model).invoke({"request": BARBELL_45})
    written = record.of(final, model="a-stand-in", provider="scripted")

    assert written["provider"] == "scripted"
    assert written["model"] == "a-stand-in"
    assert written["outcome"] == "valid"
    assert [attempt["violations"] for attempt in written["attempts"]][0][0]["rule"] == (
        plans.ADMISSIBLE
    )
    assert written["attempts"][1]["violations"] == []
    assert [call["name"] for call in written["calls"]] == ["allocate"]
    assert {node["node"] for node in written["nodes"]} == {
        "planner",
        "tools",
        "emit",
        "validate",
    }
    assert all(node["seconds"] >= 0 for node in written["nodes"])
    assert written["plan"]["blocks"][0]["items"][0]["exercise_id"] == "Barbell_Squat"
    assert json.dumps(written)


def test_a_failed_call_the_model_gave_no_id_is_recorded_as_failed(
    connection: sqlite3.Connection,
) -> None:
    """A local model does not always send one. Looked up under a different
    fallback than it was filed under, every call reads as having worked."""
    model = Scripted(
        turns=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "allocate",
                        "args": {"minutes": 45, "proportions": {"legs": 0.5}},
                        "id": None,
                        "type": "tool_call",
                    }
                ],
            )
        ],
        documents=[plan_of("Barbell_Squat")],
    )

    final = planner.build(model).invoke({"request": BARBELL_45})
    written = record.of(final, model="a-stand-in", provider="scripted")

    assert written["calls"][0]["failed"] is True


def test_the_checkpointer_refuses_to_open_the_training_database(
    database_file: Path,
) -> None:
    """Each store has one owner (ADR-0004, item 5): the conversation is the
    graph's and the training facts are the engine's."""
    with pytest.raises(checkpoints.CheckpointError, match="trainer.sqlite"):
        with checkpoints.saver(database_file):
            pass


def test_a_finished_runs_state_is_read_back_by_its_thread_id(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A run nobody watched is still a run somebody can read back."""
    model = Scripted(documents=[plan_of("Barbell_Squat")])
    thread: RunnableConfig = {"configurable": {"thread_id": "one"}}

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = planner.build(model, checkpointer=saver)
        graph.invoke({"request": BARBELL_45}, thread)

        assert graph.get_state(thread).values["plan"] == plan_of("Barbell_Squat")


def exercise_id_enums(node: Any) -> list[list[str] | None]:
    """The `enum` of every `exercise_id` property anywhere in a schema."""
    found: list[list[str] | None] = []
    if isinstance(node, dict):
        declared = node.get("properties", {})
        if "exercise_id" in declared:
            found.append(declared["exercise_id"].get("enum"))
        for value in node.values():
            found += exercise_id_enums(value)
    elif isinstance(node, list):
        for item in node:
            found += exercise_id_enums(item)
    return found


def test_the_emit_schema_offers_exactly_todays_admissible_ids(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(documents=[plan_of("Barbell_Squat")])

    planner.build(model).invoke({"request": BARBELL_45})

    enums = exercise_id_enums(model.schemas[0])
    assert enums
    for enum in enums:
        assert enum is not None
        assert sorted(enum) == ["Barbell_Squat", "Standing_Military_Press"]


def test_the_emit_schema_leaves_out_what_a_persisted_exclusion_covers(
    connection: sqlite3.Connection,
) -> None:
    """The request names no exclusion: the graph reads the standing ones the
    same way the tools do, so no door can offer what the validator refuses."""
    exclusions.add(connection, Exclusion("pattern", "squat"), "2099-01-01")
    connection.commit()
    model = Scripted(documents=[plan_of("Standing_Military_Press")])

    planner.build(model).invoke({"request": BARBELL_45})

    for enum in exercise_id_enums(model.schemas[0]):
        assert enum == ["Standing_Military_Press"]


def test_the_emit_schema_cannot_express_an_id_outside_todays_set(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(documents=[plan_of("Barbell_Squat")])

    planner.build(model).invoke({"request": BARBELL_45})

    schema = model.schemas[0]
    jsonschema.validate(plan_of("Barbell_Squat").model_dump(), schema)
    with pytest.raises(jsonschema.ValidationError, match="Dumbbell_Bench_Press"):
        jsonschema.validate(plan_of("Dumbbell_Bench_Press").model_dump(), schema)
