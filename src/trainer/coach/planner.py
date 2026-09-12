"""The planner graph: plan over the tools, emit against today's schema, validate."""

from __future__ import annotations

import dataclasses
import operator
import sqlite3
import time
from datetime import date
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter

from trainer import agent, tools
from trainer import plan as plans
from trainer.coach import models
from trainer.coach.calls import answered
from trainer.engine import admissible, constraints

ATTEMPTS = 3
"""Plans one run may emit before a refusal ends it."""

FEEDBACK = """\
The validator refused that plan:
{violations}
Plan the workout again with this in mind."""


class Node(Protocol):
    """One step of the graph. The parameter is named, which is what LangGraph asks of a node."""

    def __call__(self, state: PlannerState) -> dict[str, Any]: ...


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
    violations: tuple[plans.Violation, ...]
    refusals: Annotated[list[tuple[plans.Violation, ...]], operator.add]
    timings: Annotated[list[tuple[str, float]], operator.add]
    plan: plans.WorkoutPlan | None


def build(
    model: BaseChatModel,
    budget: int = agent.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
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
            with tools.reported(), tools.opened() as connection:
                today = constraints.constraining_today(
                    connection,
                    date.today().isoformat(),
                    budget_min=request.budget_min,
                    groups=request.groups,
                    given=request.exclusions,
                )
            # Folded into the request once, here: the emit schema and the
            # validator both read the request, and applied on one side only
            # they would describe different spaces.
            request = dataclasses.replace(
                request,
                exclusions=today.exclusions,
                budget_min=today.budget_min,
                groups=today.groups,
            )
            opening = [SystemMessage(agent.PLANNING), HumanMessage(agent.brief(request))]
        bound = model.bind_tools(definitions) if state.get("spent", 0) < budget else model
        reply = bound.invoke([*state.get("messages", []), *opening])
        return {"request": request, "messages": [*opening, reply]}

    def run_tools(state: PlannerState) -> dict[str, Any]:
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        answers = []
        for call in reply.tool_calls:
            call_id = answered(call)
            result = agent.execute(
                agent.Call(id=call_id, name=call["name"], arguments=call["args"]),
                offered,
                agent.PLANNER.keeps,
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
                violations = plans.validate(
                    connection, plans.to_blocks(emitted), state["request"], emitted
                )
        except plans.PlanError as error:
            violations = (plans.Violation(plans.SHAPE, str(error)),)
        decided: dict[str, Any] = {
            "attempts": attempts,
            "violations": violations,
            "refusals": [violations],
            "plan": emitted,
        }
        if violations and attempts < ATTEMPTS:
            decided["messages"] = [
                HumanMessage(
                    FEEDBACK.format(violations=plans.refusal(violations)), name="validator"
                )
            ]
        return decided

    def after_planner(state: PlannerState) -> Literal["tools", "emit"]:
        reply = state["messages"][-1]
        if isinstance(reply, AIMessage) and reply.tool_calls:
            return "tools"
        return "emit"

    def after_tools(state: PlannerState) -> Literal["planner", "emit"]:
        return "emit" if state.get("spent", 0) >= budget else "planner"

    def after_validate(state: PlannerState) -> Literal["planner", "done"]:
        if not state["violations"] or state["attempts"] >= ATTEMPTS:
            return "done"
        return "planner"

    def timed(node: str, run: Node) -> Node:
        """Every node says what it cost: the minutes are the thing being measured."""

        def counted(state: PlannerState) -> dict[str, Any]:
            started = time.monotonic()
            return run(state) | {"timings": [(node, time.monotonic() - started)]}

        return counted

    graph = StateGraph(PlannerState)
    graph.add_node("planner", timed("planner", turn))
    graph.add_node("tools", timed("tools", run_tools))
    graph.add_node("emit", timed("emit", emit))
    graph.add_node("validate", timed("validate", validate))
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", after_planner)
    graph.add_conditional_edges("tools", after_tools)
    graph.add_edge("emit", "validate")
    graph.add_conditional_edges(
        "validate", after_validate, {"planner": "planner", "done": END}
    )
    return graph.compile(checkpointer=checkpointer)


def studio() -> CompiledStateGraph[PlannerState, None, PlannerState, PlannerState]:
    """The planner graph on the provider `LLM_BACKEND` names, as `langgraph dev` serves it."""
    return build(models.chat().model)
