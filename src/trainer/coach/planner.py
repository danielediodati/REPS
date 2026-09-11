"""The planner graph: plan over the tools, emit against today's schema, validate."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter

from trainer import agent, tools
from trainer import plan as plans
from trainer.coach import models
from trainer.engine import admissible

ATTEMPTS = 3
"""Plans one run may emit before a refusal ends it."""

REFUSED = """\
The validator refused that plan:
{violations}
Plan the workout again with this in mind."""


def _emit_schema(connection: sqlite3.Connection, request: plans.Request) -> dict[str, Any]:
    """`WorkoutPlan`'s strict schema, with every `exercise_id` held to today's admissible ids."""
    admissible_ids = [
        exercise.id
        for exercise in admissible.admissible_set(
            connection,
            request.exclusions,
            request.equipment,
            request.budget_min,
            request.groups,
        )
    ]
    schema = agent.strict_schema(plans.WorkoutPlan)

    def restrict(node: Any) -> None:
        if isinstance(node, dict):
            declared = node.get("properties", {})
            if "exercise_id" in declared:
                declared["exercise_id"]["enum"] = admissible_ids
            for value in node.values():
                restrict(value)
        elif isinstance(node, list):
            for item in node:
                restrict(item)

    restrict(schema)
    return schema


class PlannerState(TypedDict, total=False):
    request: plans.Request
    messages: Annotated[list[AnyMessage], add_messages]
    spent: int
    attempts: int
    violations: str | None
    plan: plans.WorkoutPlan | None


def build(
    model: BaseChatModel, budget: int = agent.CALL_BUDGET
) -> CompiledStateGraph[PlannerState, None, PlannerState, PlannerState]:
    """The compiled planner graph, running on `model`."""
    offered = agent.registered(agent.PLANNER)
    definitions = [
        {"type": "function", "function": agent.schema(tool)} for tool in offered
    ]

    def turn(state: PlannerState) -> dict[str, Any]:
        request = state["request"]
        if not isinstance(request, plans.Request):
            # Studio and the HTTP API send the request as JSON.
            request = TypeAdapter(plans.Request).validate_python(request)
        opening: list[AnyMessage] = []
        if not state.get("messages"):
            opening = [SystemMessage(agent.PLANNING), HumanMessage(agent.brief(request))]
        bound = model.bind_tools(definitions) if state.get("spent", 0) < budget else model
        reply = bound.invoke([*state.get("messages", []), *opening])
        return {"request": request, "messages": [*opening, reply]}

    def run_tools(state: PlannerState) -> dict[str, Any]:
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        answers = []
        for call in reply.tool_calls:
            call_id = call["id"] or call["name"]
            result = agent.execute(
                agent.Call(id=call_id, name=call["name"], arguments=call["args"]),
                offered,
                agent.PLANNER.hides,
            )
            answers.append(
                ToolMessage(
                    result.content,
                    tool_call_id=call_id,
                    name=call["name"],
                    status="error" if result.failed else "success",
                )
            )
        return {"messages": answers, "spent": state.get("spent", 0) + len(answers)}

    def emit(state: PlannerState) -> dict[str, Any]:
        asked = HumanMessage(agent.EMIT_PLAN)
        with tools.reported(), tools.opened() as connection:
            schema = _emit_schema(connection, state["request"])
        structured = model.with_structured_output(
            schema, method="json_schema", include_raw=True
        )
        emitted = structured.invoke([*state["messages"], asked])
        assert isinstance(emitted, dict)
        return {"messages": [asked, emitted["raw"]]}

    def validate(state: PlannerState) -> dict[str, Any]:
        document = state["messages"][-1]
        assert isinstance(document, AIMessage)
        attempts = state.get("attempts", 0) + 1
        emitted: plans.WorkoutPlan | None = None
        try:
            emitted = plans.parse(document.text)
            with tools.opened() as connection:
                plans.validate(connection, plans.to_blocks(emitted), state["request"], emitted)
        except (plans.PlanError, plans.PlanRejected) as error:
            refused: dict[str, Any] = {
                "attempts": attempts,
                "violations": str(error),
                "plan": emitted,
            }
            if attempts < ATTEMPTS:
                refused["messages"] = [
                    HumanMessage(REFUSED.format(violations=error), name="validator")
                ]
            return refused
        return {"attempts": attempts, "violations": None, "plan": emitted}

    def after_planner(state: PlannerState) -> Literal["tools", "emit"]:
        reply = state["messages"][-1]
        if isinstance(reply, AIMessage) and reply.tool_calls:
            return "tools"
        return "emit"

    def after_tools(state: PlannerState) -> Literal["planner", "emit"]:
        return "emit" if state.get("spent", 0) >= budget else "planner"

    def after_validate(state: PlannerState) -> Literal["planner", "done"]:
        if state["violations"] is None or state["attempts"] >= ATTEMPTS:
            return "done"
        return "planner"

    graph = StateGraph(PlannerState)
    graph.add_node("planner", turn)
    graph.add_node("tools", run_tools)
    graph.add_node("emit", emit)
    graph.add_node("validate", validate)
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", after_planner)
    graph.add_conditional_edges("tools", after_tools)
    graph.add_edge("emit", "validate")
    graph.add_conditional_edges(
        "validate", after_validate, {"planner": "planner", "done": END}
    )
    return graph.compile()


def studio() -> CompiledStateGraph[PlannerState, None, PlannerState, PlannerState]:
    """The planner graph on Ollama, as `langgraph dev` serves it."""
    return build(models.ollama())
