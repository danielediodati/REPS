"""The supervisor graph: when a mesocycle ends, read the history over tools and write the next one's direction (ADR-0014)."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field, ValidationError, field_validator

from trainer import plan as plans
from trainer import tools
from trainer.coach import conclusions, models
from trainer.coach import record as records
from trainer.coach.calls import answered
from trainer.coach.planner import REFUSED_TURN, REJECTIONS, remembered
from trainer.engine import mesocycles, methodology, variation, workouts

logger = logging.getLogger(__name__)

TOOLS = (
    "mesocycle_history",
    "mesocycle_held",
    "mesocycle_volume",
    "adherence_history",
    "pattern_history",
    "last_performed_load",
)
"""The history, as numbers and exercises. Named, so no tool that returns the
planner's reasons (`prescribed_workout`) or anybody's prose arrives unasked."""

KEEPS = ("id", "name")

SUPERVISING = f"""\
You are the coach between mesocycles. One has just ended, and before the next
is planned you write its direction: one theme for every workout in it, what
changes from the last (exercises, reps, rest, or more than one), and why.

You do not plan the workouts. A planner does, from your direction, inside an
engine that checks every choice; so name what changes and how far, not the
workouts themselves.

The history is behind your tools, and you start from the mesocycle that ended:
- `mesocycle_history` lists every mesocycle, with its count and the direction
  it was planned from; read your own past directions there, so the thread runs
  across mesocycles.
- `mesocycle_held` is what one of them prescribed, `mesocycle_volume` what it
  planned and what was done, per pattern and per muscle.
- `adherence_history`, `pattern_history` and `last_performed_load` read what
  has been trained across the windows you ask for.

Look at what you need and nothing more: you have a budget of tool calls, and
when it runs out you will be asked for the direction with what you know.

The direction stays inside the goal's column of these ranges, from the
planner's methodology:

{methodology.committed().ranges}
How to vary between mesocycles is below. It gives principles, never a
template: how much changes is yours to judge from the history.

{variation.committed().for_supervisor}"""

EMIT = "Write the direction now, in the required shape."


class Direction(BaseModel):
    """The direction as the model writes it."""

    theme: str = Field(description="One theme for every workout of the mesocycle.")
    changes: str = Field(
        description="What changes from the last mesocycle (exercises, reps, rest) and how far, and what is kept.",
    )
    why: str = Field(description="Why, from the history and what they said.")
    varies: list[Literal["exercises", "reps", "rest"]] = Field(
        description=(
            "Exactly the ones `changes` changes, of exercises, reps and rest; at least one. "
            "The planner is checked for changing each one named here."
        ),
    )

    @field_validator("varies")
    @classmethod
    def _some(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("names nothing that changes")
        return list(dict.fromkeys(value))

    @field_validator("theme", "changes", "why")
    @classmethod
    def _said(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("is empty")
        return value.strip()


def brief(
    ended: mesocycles.Mesocycle,
    goal: str | None,
    known: Sequence[conclusions.Conclusion] = (),
    split: Sequence[Sequence[str]] = (),
) -> str:
    """The mesocycle that ended, the goal and what they said: where the supervisor starts."""
    lines = [
        f"Mesocycle {ended.id} has ended: {len(ended.slots)} workouts a cycle, "
        f"{ended.cycles} cycles, accepted on {ended.accepted_on}. What it prescribed:",
        *(
            f"- workout {number}{_training(split, number)}: "
            + "; ".join(_block(prescribed) for prescribed in slot)
            for number, slot in enumerate(ended.slots, start=1)
        ),
    ]
    if ended.direction is None:
        lines.append("It had no direction: it was the first, or planned from nothing.")
    else:
        lines.append(
            f"It was planned from your direction: {ended.direction.theme}. "
            f"Changes ({', '.join(ended.direction.varies)}): {ended.direction.changes} "
            f"Why: {ended.direction.why}"
        )
    if goal is not None:
        lines.append(f"The goal is {goal}: the direction stays inside its column of the ranges.")
    if known:
        lines.append(remembered(known))
    lines.append("Write the next mesocycle's direction.")
    return "\n".join(lines)


def _training(split: Sequence[Sequence[str]], number: int) -> str:
    """The groups the split gives this workout, when it gives it any."""
    groups = split[number - 1] if number <= len(split) else ()
    return f", training {', '.join(groups)}" if groups else ""


def _block(prescribed: workouts.PrescribedBlock) -> str:
    """One block as numbers and exercises; its reason is the planner's and stays out."""
    block = prescribed.block
    items = " + ".join(
        f"{item.exercise_id} {item.reps} reps" if item.reps is not None else f"{item.exercise_id} {item.seconds} s"
        for item in block.items
    )
    return f"{block.rounds} x ({items}), rest {block.rest} s"


class SupervisorState(TypedDict, total=False):
    last: int
    """The mesocycle that ended."""

    goal: str | None
    split: tuple[tuple[str, ...], ...]
    """The groups each workout of the next mesocycle trains, in order."""

    negotiation: str
    run: str
    follows: str | None
    began: str
    ended: str
    ending: str
    messages: Annotated[list[AnyMessage], add_messages]
    spent: int
    budget: int
    rejections: int
    timings: list[tuple[str, str, str, float, str, str]]
    emitted: list[str]
    direction: mesocycles.Direction | None


def starting(
    last: int, goal: str | None, split: tuple[tuple[str, ...], ...] = ()
) -> SupervisorState:
    """The input that starts a run, with whatever the thread's last run left cleared."""
    return {
        "last": last,
        "goal": goal,
        "split": split,
        **records.identity(records.negotiation_id(), None),  # type: ignore[typeddict-item]
        "messages": [cast(AnyMessage, RemoveMessage(REMOVE_ALL_MESSAGES))],
        "spent": 0,
        "rejections": 0,
        "timings": [],
        "emitted": [],
        "direction": None,
    }


Supervisor = CompiledStateGraph[SupervisorState, None, SupervisorState, SupervisorState]


def build(
    on: models.Chat,
    budget: int = tools.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
    store: BaseStore | None = None,
) -> Supervisor:
    """The compiled supervisor graph on `on`; `store` holds the conclusions its brief carries."""
    model = on.model
    offered = tools.registered("supervisor", TOOLS)
    timed = records.timing(on)
    definitions = [{"type": "function", "function": tools.schema(tool)} for tool in offered]

    def turn(state: SupervisorState) -> dict[str, Any]:
        born = records.born(state)
        opening: list[AnyMessage] = []
        if not state.get("messages"):
            with tools.reported(), tools.opened() as connection:
                ended = mesocycles.active(connection)
                if ended is None or ended.id != state["last"]:
                    raise tools.ToolFailure(
                        f"mesocycle {state['last']} is not the one that just ended"
                    )
            known = [] if store is None else conclusions.live(store, conclusions.whose())
            opening = [
                SystemMessage(SUPERVISING),
                HumanMessage(brief(ended, state.get("goal"), known, state.get("split", ()))),
            ]
        bound = model.bind_tools(definitions) if state.get("spent", 0) < budget else model
        try:
            reply = bound.invoke([*state.get("messages", []), *opening])
        except Exception as error:
            if (quota := models.spent(error)) is not None:
                raise quota from error
            refused = state.get("rejections", 0) + 1
            if refused > REJECTIONS:
                raise
            logger.warning("the provider refused a turn (%d): %s", refused, error)
            return born | {
                "budget": budget,
                "rejections": refused,
                "messages": [*opening, HumanMessage(REFUSED_TURN.format(why=error), name="provider")],
            }
        return born | {"budget": budget, "rejections": 0, "messages": [*opening, reply]}

    def run_tools(state: SupervisorState) -> dict[str, Any]:
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        answers = []
        for call in reply.tool_calls:
            call_id = answered(call)
            result = tools.execute(
                tools.Call(id=call_id, name=call["name"], arguments=call["args"]), offered, KEEPS
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

    def emit(state: SupervisorState) -> dict[str, Any]:
        asked = HumanMessage(EMIT)
        structured = model.with_structured_output(
            tools.strict_schema(Direction), method="json_schema", include_raw=True, strict=True
        )
        emitted = structured.invoke([*state["messages"], asked])
        assert isinstance(emitted, dict)
        raw = emitted["raw"]
        written = [*state.get("emitted", []), raw.text]
        try:
            direction = Direction.model_validate_json(raw.text)
        except ValidationError as error:
            refused = state.get("rejections", 0) + 1
            if refused > REJECTIONS:
                raise models.ProviderFailed(
                    f"{on.name} emitted no usable direction {refused} times running: {error}",
                    emitted=written,
                ) from error
            logger.warning("the direction was not usable (%d): %s", refused, error)
            return {"rejections": refused, "emitted": written}
        kept = mesocycles.Direction(**direction.model_dump())
        decided = {"messages": [asked, raw], "rejections": 0, "emitted": written, "direction": kept}
        whole = {**state, **decided, "messages": [*state["messages"], asked, raw]}
        return decided | records.closing(whole, records.DONE, budget, archive)

    def after_turn(state: SupervisorState) -> Literal["tools", "emit", "supervisor"]:
        reply = state["messages"][-1]
        if isinstance(reply, AIMessage) and reply.tool_calls:
            return "tools"
        if not isinstance(reply, AIMessage):
            return "supervisor"
        return "emit"

    def after_tools(state: SupervisorState) -> Literal["supervisor", "emit"]:
        return "emit" if state.get("spent", 0) >= budget else "supervisor"

    def after_emit(state: SupervisorState) -> Literal["emit", "done"]:
        return "done" if state.get("direction") is not None else "emit"

    graph = StateGraph(SupervisorState)
    graph.add_node("supervisor", timed("supervisor", turn))
    graph.add_node("tools", timed("tools", run_tools))
    graph.add_node("emit", timed("emit", emit))
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", after_turn)
    graph.add_conditional_edges("tools", after_tools)
    graph.add_conditional_edges("emit", after_emit, {"emit": "emit", "done": END})
    return graph.compile(checkpointer=checkpointer)


def directed(
    graph: Supervisor,
    request: plans.MesocycleRequest,
    config: RunnableConfig,
    archive: Path | None = None,
) -> plans.MesocycleRequest:
    """The request with the next mesocycle's direction, when it follows one that ended; any other, as it was.

    Not on the first mesocycle and not on a change (ADR-0014 item 1). A run
    that falls over is written down as failed and raised.
    """
    continuing = request.continuing
    if continuing is None or request.changing is not None:
        return request
    goal = request.slots[0].goal if request.slots else None
    try:
        split = tuple(slot.groups for slot in request.slots)
        final = graph.invoke(starting(continuing.mesocycle, goal, split), config)
    except Exception:
        records.failed(graph, config, tools.CALL_BUDGET, archive)
        raise
    direction = final["direction"]
    assert direction is not None, "the graph ends only once a direction is written"
    return dataclasses.replace(
        request, continuing=dataclasses.replace(continuing, direction=direction)
    )


def studio() -> Supervisor:
    """The supervisor graph on the provider `LLM_BACKEND` names, as `langgraph dev` serves it."""
    return build(models.supervisor(), archive=records.archive())
