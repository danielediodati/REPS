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
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from conftest import enrich, make_exercise
from trainer import tools
from trainer import plan as plans
from trainer.coach import checkpoints, models, planner, record
from trainer.coach import logger as coach_logger
from trainer.engine import catalog, database, exclusions, mesocycles, migrations, workouts
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

PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Dumbbell_Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 1),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
}

BARBELL_45 = plans.Request(equipment=("barbell",), budget_min=45)

SCRIPTED = "scripted"
STAND_IN = "a-stand-in"


def graph_of(model: BaseChatModel, **built: Any) -> planner.Planner:
    """The planner graph on a scripted model, named the way a real one is.

    `build` takes the model with its name and its provider, because the record
    writes them per node, and every test here would otherwise repeat the same
    three-field wrapper around a stand-in.
    """
    return planner.build(models.Chat(model, SCRIPTED, STAND_IN), **built)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
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
    raw: list[str] = []
    """Emissions that are not documents at all -- prose where the plan belongs,
    which is what a local model does when constrained decoding is not holding
    it. Taken before `documents`."""

    schemas: list[dict[str, Any]] = []
    seen: list[list[BaseMessage]] = []
    bound: list[list[str]] = []
    """The tools it was offered, per turn, by name.

    A bound is only a bound if the model cannot reach past it, and both
    budgets are kept by taking a tool off the table. Nothing else here can see
    that happen: a stand-in answers from its script whatever it was offered.
    """

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
        self.bound.append(
            [str(one.get("function", {}).get("name", "")) for one in tools]  # type: ignore[union-attr]
        )
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
            written = (
                self.raw.pop(0)
                if self.raw
                else self.documents.pop(0).model_dump_json()
            )
            return {
                "raw": AIMessage(content=written),
                "parsed": None,
                "parsing_error": None,
            }

        return RunnableLambda(emitted)


def test_a_turn_with_no_tool_call_goes_to_emit(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[AIMessage(content="I have what I need.")],
        documents=[plan_of("Barbell_Squat")],
    )

    final = graph_of(model).invoke({"request": BARBELL_45})

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

    final = graph_of(model).invoke({"request": BARBELL_45})

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

    final = graph_of(model, budget=1).invoke({"request": BARBELL_45})

    assert len(model.seen) == 1
    assert final["spent"] == 1
    assert final["plan"] == plan_of("Barbell_Squat")


def test_a_run_that_spends_the_whole_default_budget_still_emits(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calling("allocate", minutes=45, proportions={"legs": 1.0})
            for _ in range(tools.CALL_BUDGET)
        ],
        documents=[plan_of("Barbell_Squat")],
    )

    final = graph_of(model).invoke({"request": BARBELL_45})

    assert final["spent"] == tools.CALL_BUDGET
    assert final["plan"] == plan_of("Barbell_Squat")


def test_a_run_that_spends_the_budget_and_every_attempt_still_ends(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calling("allocate", minutes=45, proportions={"legs": 1.0})
            for _ in range(tools.CALL_BUDGET)
        ],
        documents=[plan_of("Dumbbell_Bench_Press")] * planner.ATTEMPTS,
    )

    final = graph_of(model).invoke({"request": BARBELL_45})

    assert final["attempts"] == planner.ATTEMPTS
    assert final["violations"]


def test_a_refusal_goes_back_to_the_planner_with_the_validators_message(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Fixed.")],
        documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
    )

    final = graph_of(model).invoke({"request": BARBELL_45})

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

    final = graph_of(model).invoke({"request": request})

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

    final = graph_of(model).invoke({"request": BARBELL_45})

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

    final = graph_of(model).invoke({"request": BARBELL_45})
    written = record.of(final, tools.CALL_BUDGET)

    assert "model" not in written, "the model belongs to the node that answered"
    assert {node["model"] for node in written["nodes"]} == {STAND_IN}
    assert {node["provider"] for node in written["nodes"]} == {SCRIPTED}
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

    final = graph_of(model).invoke({"request": BARBELL_45})
    written = record.of(final, tools.CALL_BUDGET)

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
        graph = graph_of(model, checkpointer=saver)
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

    graph_of(model).invoke({"request": BARBELL_45})

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

    graph_of(model).invoke({"request": BARBELL_45})

    for enum in exercise_id_enums(model.schemas[0]):
        assert enum == ["Standing_Military_Press"]


def test_the_emit_schema_cannot_express_an_id_outside_todays_set(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(documents=[plan_of("Barbell_Squat")])

    graph_of(model).invoke({"request": BARBELL_45})

    schema = model.schemas[0]
    jsonschema.validate(plan_of("Barbell_Squat").model_dump(), schema)
    with pytest.raises(jsonschema.ValidationError, match="Dumbbell_Bench_Press"):
        jsonschema.validate(plan_of("Dumbbell_Bench_Press").model_dump(), schema)


def test_an_emission_that_is_not_a_plan_at_all_is_refused_and_recorded_as_none(
    connection: sqlite3.Connection,
) -> None:
    """Prose where the plan belongs. The run has no plan to record, and
    everything downstream has to read `plan: null` rather than an empty one --
    *nothing prescribed* would hold every invariant about what was
    prescribed."""
    model = Scripted(raw=["I would start with squats."] * planner.ATTEMPTS)

    final = graph_of(model).invoke({"request": BARBELL_45})

    assert final["plan"] is None
    assert [violation.rule for violation in final["violations"]] == [plans.SHAPE]
    assert record.of(final, tools.CALL_BUDGET)["plan"] is None


def test_a_plan_the_block_vocabulary_cannot_express_is_refused_on_shape(
    connection: sqlite3.Connection,
) -> None:
    """The emit schema does not carry the rule that a prescription is reps
    **or** seconds -- `BlockItem` is where that lives -- so it reaches the
    validator as a shape failure. From the run's point of view that is the
    same outcome as any other refusal: the plan did not get through."""
    uncostable = plans.WorkoutPlan(
        blocks=[
            plans.PlanBlock(
                items=[
                    plans.PlanItem(
                        exercise_id="Barbell_Squat",
                        prescription=plans.Prescription(unit="reps", amount=0),
                    )
                ],
                rounds=3,
                rest=120,
                reason="neither reps nor seconds",
            )
        ]
    )
    model = Scripted(documents=[uncostable] * planner.ATTEMPTS)

    final = graph_of(model).invoke({"request": BARBELL_45})

    assert [violation.rule for violation in final["violations"]] == [plans.SHAPE]
    assert final["plan"] == uncostable, "the plan is still recorded whole"


# -- the tools the planner offers ---------------------------------------------
#
# The planner's surface, its field allow-list, its prompt and its brief moved
# here from `agent.py` in ticket 05, with the Groq planner loop that used to
# hold them. What `tools.py` owns is the machinery they are read through
# -- `registered`, `schema` and `execute` -- which the logger shares.


def executed(one: tools.Call) -> tools.Result:
    """One call through the planner's surface, which is what decides both
    whether the tool exists and what its answer carries back."""
    return tools.execute(
        one, tools.registered("planner", planner.TOOLS), planner.KEEPS
    )


def calls(name: str, **arguments: Any) -> tools.Call:
    return tools.Call(id=f"toolu_{name}", name=name, arguments=arguments)


def test_the_tools_offered_are_the_shared_surface_and_nothing_else() -> None:
    """No second definition: the planner names tools out of `tools.TOOLS`, the
    same tuple `trainer mcp` registers."""
    offered = tools.registered("planner", planner.TOOLS)
    defined = [tool.__name__ for tool in tools.TOOLS]

    assert [tool.__name__ for tool in offered] == [
        name for name in defined if name in planner.TOOLS
    ]


def test_every_tool_reaches_the_model_with_a_description_and_arguments() -> None:
    """A tool the model cannot fill the arguments in for is a tool it cannot
    call, and a tool with no description is one it cannot choose."""
    for tool in tools.registered("planner", planner.TOOLS):
        offered = tools.schema(tool)
        assert offered["description"], f"{offered['name']} has no description"
        assert offered["parameters"]["type"] == "object"
        if offered["name"] == "unreported_workouts":
            # The one question with nothing to ask about: *today* is the
            # caller's to supply, never the model's, because nothing in
            # `engine/` reads the clock.
            assert offered["parameters"]["properties"] == {}
            continue
        assert offered["parameters"]["properties"], f"{offered['name']} takes nothing"


def test_an_argument_with_a_default_is_not_required() -> None:
    """`admissible_set`'s exclusions are optional, and a schema that demanded
    them would make the common call the harder one to write."""
    (admissible,) = [
        tools.schema(tool)
        for tool in tools.registered("planner", planner.TOOLS)
        if tool.__name__ == "admissible_set"
    ]

    assert set(admissible["parameters"]["required"]) == {"equipment", "budget_min"}


def test_the_two_agents_offer_different_sets_of_the_same_definitions() -> None:
    """One definition per tool, two agents onto it. A tool both can call is
    the **same function object** for each: a copy diverges at the first fix
    applied to one and not the other, and nothing would fail when it did."""
    offered = {t.__name__: t for t in tools.registered("planner", planner.TOOLS)}
    logger = {t.__name__: t for t in tools.registered("logger", coach_logger.TOOLS)}

    assert set(offered) != set(logger)
    assert "allocate" in offered and "allocate" not in logger
    assert "prescribed_workout" in logger and "prescribed_workout" not in offered
    for shared in set(offered) & set(logger):
        assert offered[shared] is logger[shared], shared


def test_every_tool_that_exists_reaches_at_least_one_agent() -> None:
    """A tool defined and offered to nobody is a tool that cannot be called.

    `registered` guards the names that are **asked** for; nothing guards the
    other direction, and a tool added to `tools.TOOLS` without a caller is
    exactly as invisible as one that was never written. `trainer mcp` would
    still serve it, which is what makes the gap survivable long enough to
    forget about.
    """
    reached = set(planner.TOOLS) | set(coach_logger.TOOLS)

    assert {tool.__name__ for tool in tools.TOOLS} == reached


def test_the_model_can_ask_for_only_the_groups_today_trains(
    connection: sqlite3.Connection,
) -> None:
    """The whole admissible space is several times any one workout, and it is
    re-read on every later turn."""
    whole = executed(calls("admissible_set", equipment=["barbell"], budget_min=45))
    narrowed = executed(
        calls(
            "admissible_set",
            equipment=["barbell"],
            budget_min=45,
            muscle_groups=["shoulders"],
        )
    )

    assert narrowed.failed is False
    assert len(narrowed.content) < len(whole.content)


# -- what the planner is handed back ------------------------------------------


def test_an_admissible_set_reaches_the_model_without_its_prose(
    connection: sqlite3.Connection,
) -> None:
    """One answer must not be larger than the whole output budget, and every
    result is re-sent on every later turn. What is left is what a plan is
    written from: the id it names, whether today's equipment reaches it, and
    the muscles its time is divided over."""
    result = executed(calls("admissible_set", equipment=["barbell"], budget_min=45))
    (first, *_) = json.loads(result.content)

    assert result.failed is False
    assert set(first) == {"id", "equipment", "primary_muscles"}


def test_the_model_is_not_shown_the_name_it_could_write_by_mistake(
    connection: sqlite3.Connection,
) -> None:
    """A plan is written in ids, and a model shown both fields copied the
    readable one into `exercise_id`. No rule recovers the id from the name --
    `Butt Lift (Bridge)` is `Butt_Lift_Bridge` -- so the field is removed
    rather than explained, which makes the mistake impossible instead of
    rare."""
    result = executed(calls("admissible_set", equipment=["barbell"], budget_min=45))

    assert "name" not in json.loads(result.content)[0]
    assert "Barbell Squat" not in result.content
    assert "Barbell_Squat" in result.content


def test_trimming_reaches_a_record_nested_under_a_key() -> None:
    """`compare_variants` already answers `{"a": {...}, "b": {...}}`. A tool
    that nests a list of exercises brings back the payload this exists to
    bound, with nothing failing to say so."""
    answer = {"variants": [{"id": "X", "instructions": ["long"], "level": "expert"}]}

    assert tools._trimmed(answer, planner.KEEPS) == {"variants": [{"id": "X"}]}


def test_the_planner_is_shown_no_name_even_beside_an_enrichment() -> None:
    """`compare_variants` answers with two enrichments, which are not catalog
    records -- but `name` is a catalog field, and writing it into `exercise_id`
    is the mistake this list exists to prevent. What is not a catalog field at
    all is nobody's to drop."""
    answer = {"a": {"exercise_id": "X", "name": "Barbell Squat", "movement_pattern": "squat"}}

    trimmed = tools._trimmed(answer, planner.KEEPS)

    assert trimmed == {"a": {"exercise_id": "X", "movement_pattern": "squat"}}


# -- what the model can get wrong ---------------------------------------------


def test_an_argument_of_the_wrong_shape_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    """Exclusions as a list of strings rather than of objects. It satisfies
    the signature, reaches the tool body and comes apart on a string -- a
    traceback, no record, and a paid-for run thrown away over something the
    model could have corrected next turn."""
    result = executed(
        calls(
            "admissible_set",
            equipment=["barbell"],
            budget_min=45,
            exclusions=["squat"],
        )
    )

    assert result.failed is True
    assert "do not fit" in result.content


def test_a_dict_where_a_list_belongs_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    result = executed(calls("allocate", minutes=45, proportions=["legs"]))

    assert result.failed is True


def test_an_argument_nobody_declared_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    result = executed(
        calls("allocate", minutes=45, proportions={"legs": 1.0}, why="because")
    )

    assert result.failed is True
    assert "why" in result.content


def test_a_tool_the_surface_does_not_have_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    """The model's mistake, not this project's, so it comes back as something
    it can recover from -- with the real names in it."""
    result = executed(calls("active_conclusions"))

    assert result.failed is True
    assert "admissible_set" in result.content


def test_the_planner_cannot_read_a_prescription_back(
    connection: sqlite3.Connection,
) -> None:
    """`prescribed_workout` answers *what did workout 12 ask for*, and a
    planner has no workout 12: it is writing one."""
    result = executed(calls("prescribed_workout", workout_id=1))

    assert result.failed is True
    assert "no tool called 'prescribed_workout'" in result.content


# -- the prompt and the brief -------------------------------------------------


def test_the_prompt_carries_the_rules_the_validator_will_apply() -> None:
    """A model that is not told the rules is one whose refusals are the
    prompt's fault rather than a finding."""
    for rule in ("admissible_set", "never trimmed to fit", "at most once", "reason"):
        assert rule.lower() in planner.PLANNING.lower(), rule


def test_the_brief_states_the_invariant_no_rule_will_refuse() -> None:
    """*Every requested group is trained* is TRAINER.md's invariant 6. It is
    checked by `trainer eval` and by nothing in `plan.validate`, so the graph
    never refuses a plan for it and the brief is the only place the model can
    learn it.

    Measured on `gpt-oss:20b`: a 30-minute *train everything* plan that spent
    two blocks on core, left arms untouched and claimed it anyway in the
    reason -- *(chest/arms)* on a push-up. A rule the model was never told is
    the prompt's fault rather than a finding.
    """
    written = planner.brief(
        plans.Request(equipment=("body only",), budget_min=30, groups=("legs", "core"))
    ).lower()

    assert "primary" in written
    assert "secondary" in written, "it has to say what does not count"
    assert "second block" in written


def test_a_request_that_names_no_group_is_asked_to_cover_nothing() -> None:
    """Which groups today trains is a fact about **this request**, which is
    why the rule lives in the brief and not in the prompt: with no groups
    named it has to disappear entirely.

    Stated for every run instead, it read as *cover them all*. Measured on
    `gpt-oss:20b`: a 15-minute `body only` request naming no groups sent the
    model asking `admissible_set` for chest, back, shoulders, arms, legs and
    core, and it came back 40, then 20, then 21 minutes against a budget of
    15 -- three attempts, all refused on time.
    """
    written = planner.brief(
        plans.Request(equipment=("body only",), budget_min=15)
    ).lower()

    assert "primary" not in written
    assert "second block" not in written
    assert "group" not in written, "it owes no coverage it was never asked for"


def test_the_prompt_says_that_a_refusal_comes_back_with_its_reasons() -> None:
    """It does now, which it did not while this prompt was shared with a loop
    that ended at the first refusal. A model that is not told it gets another
    attempt has no reason to spend one well."""
    said = planner.PLANNING.lower()

    assert "refusal comes back to you" in said
    assert str(planner.ATTEMPTS) in planner.PLANNING


def test_the_model_is_told_what_it_is_planning_against() -> None:
    request = plans.Request(equipment=("barbell", "dumbbell"), budget_min=30)

    written = planner.brief(request)

    assert "barbell, dumbbell" in written
    assert "30 minutes" in written


def test_the_brief_names_what_today_trains() -> None:
    request = plans.Request(
        equipment=("dumbbell",), budget_min=45, groups=("legs", "core")
    )

    written = planner.brief(request)

    assert "legs, core" in written
    assert "admissible_set" in written


def test_the_brief_offers_the_allocation_rather_than_imposing_it() -> None:
    """Minutes divided before the plan is built rather than cut after it
    (ADR-0001), and offered the way the rest bands are: the agent has
    `allocate` and may divide the time differently."""
    request = plans.Request(
        equipment=("dumbbell",),
        budget_min=40,
        groups=("legs", "core"),
        allocation=(("legs", 20), ("core", 20)),
    )

    written = planner.brief(request)

    assert "legs 20 min, core 20 min" in written
    assert "not an instruction" in written


def test_a_preference_reaches_the_model_as_data() -> None:
    """Invariant 4 is measured by code against the request, so a preference
    has to be a field on it and not a sentence somebody typed into a prompt."""
    request = plans.Request(
        equipment=("barbell",), budget_min=45, preferences=("Barbell_Squat",)
    )

    assert request.preferences == ("Barbell_Squat",)
    assert "Barbell_Squat" in planner.brief(request)
    assert "despite" in planner.brief(request)


def test_the_refused_plan_and_the_reason_reach_the_model() -> None:
    """Two turns, not a conversation: both are inputs to a fresh run."""
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        refusals=plans.turned_down(
            (), plan_of("Barbell_Squat"), "I do not feel like squatting"
        ),
    )

    written = planner.brief(request)

    assert "turned each one down" in written
    assert "Barbell_Squat" in written
    assert "I do not feel like squatting" in written
    assert "do not give up" in written


def test_the_brief_carries_every_refusal_of_the_negotiation() -> None:
    """The last one whole, the ones before it as the exercises they named
    (ADR-0007, item 4). One step of memory is not memory: with only the newest
    kept, the first plan of the evening can be offered again."""
    refusals: tuple[plans.Refusal, ...] = ()
    for said, offered in (
        ("troppo lunga", plan_of("Barbell_Squat")),
        ("non mi va la panca", plan_of("Dumbbell_Bench_Press")),
        ("basta spalle", plan_of("Standing_Military_Press")),
    ):
        refusals = plans.turned_down(refusals, offered, said)

    written = planner.brief(
        plans.Request(equipment=("barbell",), budget_min=45, refusals=refusals)
    )

    assert "You have proposed 3 workout(s)" in written
    assert "Turned down: Barbell_Squat." in written
    assert "Turned down: Dumbbell_Bench_Press." in written
    assert "Turned down, in full:" in written
    assert '"exercise_id": "Standing_Military_Press"' in written
    for said in ("troppo lunga", "non mi va la panca", "basta spalle"):
        assert said in written


def test_a_run_with_no_refusal_says_nothing_about_one() -> None:
    written = planner.brief(plans.Request(equipment=("barbell",), budget_min=45))

    assert "turned each one down" not in written
    assert "rather not" not in written


# -- the plan that waits to be accepted (ADR-0005) -----------------------------


def waiting(model: BaseChatModel) -> tuple[planner.Planner, RunnableConfig]:
    """A graph that can pause, and the thread it pauses on."""
    return graph_of(model, checkpointer=InMemorySaver()), {
        "configurable": {"thread_id": "one"}
    }


def prescribed(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in connection.execute("SELECT id, state FROM workouts")]


def test_a_valid_plan_stops_at_the_interrupt_with_nothing_written(
    connection: sqlite3.Connection,
) -> None:
    """The run is waiting, not finished, and the database has not been touched."""
    graph, thread = waiting(Scripted(documents=[plan_of("Barbell_Squat")]))

    final = graph.invoke({"request": BARBELL_45}, thread)

    assert final["plan"] == plan_of("Barbell_Squat")
    (waited,) = final["__interrupt__"]
    assert waited.value["blocks"][0]["items"][0]["exercise_id"] == "Barbell_Squat"
    assert graph.get_state(thread).next == ("propose",)
    assert prescribed(connection) == []


def test_accepting_the_plan_writes_exactly_one_prescribed_workout(
    connection: sqlite3.Connection,
) -> None:
    graph, thread = waiting(Scripted(documents=[plan_of("Barbell_Squat")]))
    graph.invoke({"request": BARBELL_45}, thread)

    final = graph.invoke(Command(resume=planner.accepted()), thread)

    assert prescribed(connection) == [(final["workout"], "prescribed")]
    written = workouts.prescribed(connection, final["workout"])
    assert [item.exercise_id for block in written for item in block.block.items] == [
        "Barbell_Squat"
    ]
    assert graph.get_state(thread).next == ()


def test_refusing_the_plan_writes_nothing_and_proposes_another(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread = waiting(model)
    graph.invoke({"request": BARBELL_45}, thread)

    final = graph.invoke(
        Command(resume=planner.refused("non mi va, sempre squat")), thread
    )

    assert final["plan"] == plan_of("Standing_Military_Press")
    assert graph.get_state(thread).next == ("propose",)
    assert prescribed(connection) == []


def test_what_the_user_said_reaches_the_planner(connection: sqlite3.Connection) -> None:
    """It is the one thing only they can supply, and no rule checks it."""
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread = waiting(model)
    graph.invoke({"request": BARBELL_45}, thread)

    graph.invoke(Command(resume=planner.refused("non mi va, sempre squat")), thread)

    planned = "\n".join(message.text for message in model.seen[-1])
    assert "non mi va, sempre squat" in planned
    assert "Barbell_Squat" in planned, "the plan they turned down goes with it"


def test_only_30_minutes_plans_again_against_the_shorter_budget(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Shorter.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread = waiting(model)
    graph.invoke({"request": BARBELL_45}, thread)

    final = graph.invoke(Command(resume=planner.refused("", minutes=30)), thread)

    assert final["request"].budget_min == 30
    assert final["request"].allocation == (), "divided for a budget nobody asked for"
    assert "30 minutes" in "\n".join(message.text for message in model.seen[-1])


def test_a_refused_plan_is_never_the_one_that_is_written(
    connection: sqlite3.Connection,
) -> None:
    """Refuse, then accept: exactly one workout, and it is the second plan."""
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread = waiting(model)
    graph.invoke({"request": BARBELL_45}, thread)
    graph.invoke(Command(resume=planner.refused("non mi va")), thread)

    final = graph.invoke(Command(resume=planner.accepted()), thread)

    assert prescribed(connection) == [(final["workout"], "prescribed")]
    written = workouts.prescribed(connection, final["workout"])
    assert [item.exercise_id for block in written for item in block.block.items] == [
        "Standing_Military_Press"
    ]


def test_what_the_user_said_turning_a_plan_down_is_in_no_table(
    connection: sqlite3.Connection,
) -> None:
    """A *"non mi va, sempre panca"* said on a bad Tuesday must not settle into
    a preference, an exclusion or a workout. Asserted over every value of every
    table, because the guarantee is about the database and not about the tables
    somebody remembered to check."""
    said = "non mi va, sempre panca e mi fa male la spalla"
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread = waiting(model)
    graph.invoke({"request": BARBELL_45}, thread)
    graph.invoke(Command(resume=planner.refused(said)), thread)
    graph.invoke(Command(resume=planner.accepted()), thread)

    tables = [
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    ]
    assert "workouts" in tables, "the tables were read from the database"
    for table in tables:
        for row in connection.execute(f"SELECT * FROM {table}"):
            for value in row:
                assert said not in str(value), table


def test_a_run_the_validator_refuses_to_the_end_never_offers_a_plan(
    connection: sqlite3.Connection,
) -> None:
    """There is nothing to accept, so the run ends instead of waiting."""
    graph, thread = waiting(Scripted(documents=[plan_of("Dumbbell_Bench_Press")] * 4))

    final = graph.invoke({"request": BARBELL_45}, thread)

    assert "__interrupt__" not in final
    assert graph.get_state(thread).next == ()
    assert prescribed(connection) == []


# -- what the provider refuses -------------------------------------------------


REFUSED_CALL = (
    "error parsing tool call: "
    "raw='{\"minutes\":45,\"proportions\":{\"chest\":22/45,\"arms\":23/45}}', "
    "err=invalid character '/' after object key:value pair"
)
"""Verbatim from a run on Ollama. The model divided the minutes the brief had
just given it, and JSON has no arithmetic."""


class Refusing(Scripted):
    """A provider that refuses turns: the first `times`, or the ones `at` names."""

    times: int = 1
    at: list[int] = []
    """Turn numbers to refuse, counted from zero. Takes the place of `times`,
    for the scattered refusals a run recovers from one at a time."""

    asked: int = 0
    refused: int = 0

    def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        turn = self.asked
        self.asked += 1
        if turn in self.at if self.at else self.refused < self.times:
            self.refused += 1
            raise RuntimeError(REFUSED_CALL)
        return super()._generate(messages, *args, **kwargs)


def test_a_turn_the_provider_refuses_goes_back_to_the_model(
    connection: sqlite3.Connection,
) -> None:
    """The case `tools.execute` was built for, arriving where it cannot help.

    A tool call with a fraction in it is the model getting it wrong, and every
    other way of getting it wrong comes back as a result it can recover from.
    This one the provider rejects before any call reaches us, so without this
    the whole run -- minutes of it on Ollama -- is thrown away over a slash.
    """
    model = Refusing(documents=[plan_of("Barbell_Squat")])
    graph = graph_of(model, checkpointer=InMemorySaver())

    final = graph.invoke({"request": BARBELL_45}, {"configurable": {"thread_id": "t"}})

    assert model.refused == 1
    assert final["rejections"] == 0, "cleared by the turn that landed"
    assert final["__interrupt__"], "the run reached a plan anyway"
    told = [m for m in final["messages"] if getattr(m, "name", None) == "provider"]
    assert len(told) == 1
    assert "22/45" in told[0].text, "the model is shown what it wrote"
    assert "strict JSON" in told[0].text


def test_a_provider_that_keeps_refusing_ends_the_run(
    connection: sqlite3.Connection,
) -> None:
    """Bounded, like the validator's attempts. A model that cannot produce an
    acceptable turn twice running will not on the third, and the minutes spent
    finding out are minutes the user is waiting."""
    model = Refusing(times=planner.REJECTIONS + 1, documents=[plan_of("Barbell_Squat")])
    graph = graph_of(model, checkpointer=InMemorySaver())

    with pytest.raises(RuntimeError, match="error parsing tool call"):
        graph.invoke({"request": BARBELL_45}, {"configurable": {"thread_id": "t"}})


def test_the_brief_is_written_once_across_a_refusal(
    connection: sqlite3.Connection,
) -> None:
    """The retry is the same turn attempted again, not a second conversation.

    `turn` writes the system prompt and the brief only when it finds no
    history, and the refused turn leaves one behind -- so a second copy here
    would mean the model planning against two briefs at once.
    """
    model = Refusing(documents=[plan_of("Barbell_Squat")])
    graph = graph_of(model, checkpointer=InMemorySaver())

    final = graph.invoke({"request": BARBELL_45}, {"configurable": {"thread_id": "t"}})

    assert sum("Plan the workout." in m.text for m in final["messages"]) == 1


def test_the_refusal_budget_is_consecutive_and_not_a_run_total(
    connection: sqlite3.Connection,
) -> None:
    """`REJECTIONS` bounds refusals *in a row*, which is what the comment on it
    says and what the failure it describes looks like.

    Counted over the whole run instead, this is what happens: the provider
    hiccups once, the turn is retried and succeeds, the validator refuses the
    plan for its own unrelated reasons and the graph loops back -- and three
    laps later the third isolated hiccup trips a budget meant for a model that
    cannot write a turn at all. Minutes of recovered work, thrown away because
    nothing ever reset the count.
    """
    model = Refusing(
        at=[0, 2, 4],
        turns=[AIMessage(content="Planned.")] * 3,
        documents=[
            plan_of("Dumbbell_Bench_Press"),  # refused: not today's equipment
            plan_of("Dumbbell_Bench_Press"),  # refused again
            plan_of("Barbell_Squat"),         # the one that stands
        ],
    )
    graph = graph_of(model, checkpointer=InMemorySaver())

    final = graph.invoke({"request": BARBELL_45}, {"configurable": {"thread_id": "t"}})

    assert model.refused == 3, "the provider refused three separate turns"
    assert final["attempts"] == 3, "and the validator refused two plans of its own"
    assert final["__interrupt__"], "the run still reached a plan"
    assert final["rejections"] == 0, "the count is cleared by a turn that lands"


# -- a mesocycle ---------------------------------------------------------------

LEGS_AND_SHOULDERS = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
split = [["legs"], ["shoulders"]]
equipment = ["barbell"]
"""


def mesocycle_of(*workouts: plans.WorkoutPlan, cycles: int = 4) -> plans.Mesocycle:
    return plans.Mesocycle(workouts=list(workouts), cycles=cycles, why="settle the loads")


@pytest.fixture()
def two_slots(connection: sqlite3.Connection, declared_training: Path) -> plans.MesocycleRequest:
    declared_training.write_text(LEGS_AND_SHOULDERS, encoding="utf-8")
    return plans.mesocycle_requested(connection, "2026-09-22")


def pausing(model: BaseChatModel) -> tuple[planner.Planner, RunnableConfig]:
    """A graph that pauses on the serializer the bot uses."""
    return graph_of(model, checkpointer=InMemorySaver(serde=checkpoints.Declared())), {
        "configurable": {"thread_id": "one"}
    }


def test_a_mesocycle_is_proposed_whole(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    offered = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))
    model = Scripted(raw=[offered.model_dump_json()])
    graph, thread = pausing(model)

    final = graph.invoke(planner.starting(two_slots), thread)

    (waited,) = final["__interrupt__"]
    assert [w["blocks"][0]["items"][0]["exercise_id"] for w in waited.value["workouts"]] == [
        "Barbell_Squat",
        "Standing_Military_Press",
    ]
    briefed = "\n".join(message.text for message in model.seen[0])
    assert "Workout 1" in briefed and "legs" in briefed
    assert "Workout 2" in briefed and "shoulders" in briefed


def test_a_mesocycle_wrong_in_one_slot_goes_back_naming_it(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    wrong = mesocycle_of(plan_of("Standing_Military_Press"), plan_of("Standing_Military_Press"))
    right = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))
    model = Scripted(
        turns=[AIMessage(content="planned"), AIMessage(content="again")],
        raw=[wrong.model_dump_json(), right.model_dump_json()],
    )
    graph, thread = pausing(model)

    final = graph.invoke(planner.starting(two_slots), thread)

    assert final["plan"] == right
    told = "\n".join(message.text for message in model.seen[-1])
    assert "workout 1: " in told


def test_an_accepted_mesocycle_is_kept_and_prescribes_nothing(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    offered = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"), cycles=3)
    graph, thread = pausing(Scripted(raw=[offered.model_dump_json()]))
    graph.invoke(planner.starting(two_slots), thread)

    final = graph.invoke(Command(resume=planner.accepted()), thread)

    kept = mesocycles.active(connection)
    assert kept is not None and final["mesocycle"] == kept.id
    assert kept.cycles == 3
    assert [s[0].block.items[0].exercise_id for s in kept.slots] == [
        "Barbell_Squat",
        "Standing_Military_Press",
    ]
    assert prescribed(connection) == []


def test_a_mesocycle_turned_down_is_answered_with_another(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    first = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))
    second = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"), cycles=2)
    model = Scripted(
        turns=[AIMessage(content="planned"), AIMessage(content="another")],
        raw=[first.model_dump_json(), second.model_dump_json()],
    )
    graph, thread = pausing(model)
    graph.invoke(planner.starting(two_slots), thread)

    final = graph.invoke(Command(resume=planner.refused("troppi cicli")), thread)

    assert final["plan"] == second
    briefed = "\n".join(message.text for message in model.seen[-1])
    assert "troppi cicli" in briefed


def test_the_run_record_names_the_mesocycle_it_kept(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    offered = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))
    graph, thread = pausing(Scripted(raw=[offered.model_dump_json()]))
    graph.invoke(planner.starting(two_slots), thread)

    final = graph.invoke(Command(resume=planner.accepted()), thread)

    written = record.of(final, tools.CALL_BUDGET)
    assert written["mesocycle"] == final["mesocycle"]
    assert f"  kept mesocycle {final['mesocycle']}" in record.summary(written)


def test_a_mesocycle_request_sent_as_json_is_read_as_one(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    """Studio and the HTTP API send the request as JSON; a mesocycle's must not
    be read as one workout's."""
    import dataclasses as dc

    offered = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))
    graph, thread = pausing(Scripted(raw=[offered.model_dump_json()]))

    final = graph.invoke({"request": dc.asdict(two_slots)}, thread)  # type: ignore[call-overload]

    assert final["plan"] == offered
