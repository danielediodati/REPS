"""The planner graph: plan over the tools, emit against today's schema, validate."""

from __future__ import annotations

import dataclasses
import operator
import sqlite3
import time
from datetime import date
from typing import Annotated, Any, Literal, Protocol, TypedDict, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import TypeAdapter

from trainer import agent, tools
from trainer import plan as plans
from trainer.coach import models
from trainer.coach.calls import answered
from trainer.engine import admissible, constraints, workouts

ATTEMPTS = 3
"""Plans one run may emit before a refusal ends it."""

FEEDBACK = """\
The validator refused that plan:
{violations}
Plan the workout again with this in mind."""

TOOLS = (
    "admissible_set",
    "remaining_budget",
    "allocate",
    "pattern_history",
    "last_performed_load",
    "search_exercises",
    "adherence_history",
    "volume_deficit",
    "unreported_workouts",
    "compare_variants",
)
"""Everything on the shared surface except the one tool that reads a
prescription back.

`prescribed_workout` answers *what did workout 12 ask for*, and a planner has
no workout 12: it is writing one. What it wants to know about the past is
volume and adherence, and those it already has.

**Named, not derived by subtracting one name from `tools.TOOLS`.** Written that
way this was the one place a tool could arrive without anybody deciding it
should: rename the excluded tool and the planner silently gains it, with
`agent.registered`'s guard -- which only checks the names that are *asked* for
-- unable to say a word.
"""

KEEPS = ("id", "equipment", "primary_muscles")
"""What a plan is written from: the id it names, whether today's equipment reaches it, and the muscles its time is divided over."""

PLANNING = f"""\
You plan one strength workout, for one person, today.

{tools.INSTRUCTIONS}
The rules you are working inside, none of which you can talk your way around:

- Every exercise you prescribe must be in what `admissible_set` returns for
  today's request, written as the `id` that came back, character for
  character. Anything else is rejected by a deterministic check after you
  emit.
- The plan must fit the time declared. It is never trimmed to fit: a plan that
  runs over is rejected whole, so ask `remaining_budget` before you commit to
  a block rather than after.
- An exercise appears at most once in the whole plan. One line per exercise,
  with the rounds and reps it needs.
- Each exercise is prescribed in reps or in seconds: its `prescription` gives
  the `unit` and the `amount`. A plank is seconds; a push-up is reps.
- Rest is yours to prescribe and travels with the block. There are reference
  bands -- around 3 min for heavy low-rep work, 90-120 s for hypertrophy, 60 s
  for isolation -- and they are a reference, not a rule.
- Every block carries the reason it is there, in one short sentence. That is
  the part of the plan only you can supply.

A plan that breaks one of these is refused, and the refusal comes back to you
naming every rule it broke. You have {ATTEMPTS} attempts in all: read what it
says and emit a plan that answers it. Handing back the same plan spends an
attempt and changes nothing, and there is nobody to argue with -- the check is
code.

You have a budget of tool calls. When it runs out you will be asked for the
plan with whatever you know at that point, so spend the calls on what you
actually need and do not explore for its own sake.
"""

EMIT_PLAN = "Emit the plan now, in the required shape."


def brief(request: plans.Request) -> str:
    """Today's request, in words, for the model to plan against."""
    lines = [
        f"Equipment available today: {', '.join(request.equipment)}.",
        f"Time available: {request.budget_min} minutes.",
    ]
    if request.groups:
        lines.append(
            f"This workout trains: {', '.join(request.groups)}. Ask "
            "`admissible_set` for those groups; anything else is not today's "
            "workout. Each of them needs at least one exercise whose "
            "**primary** muscles are in it: working it as a secondary does "
            "not count, so a push-up is chest and not arms however hard the "
            "triceps work, and saying (chest/arms) in the reason does not "
            "make it one. Cover each of them once before you give any one of "
            "them a second block."
        )
    if request.allocation:
        divided = ", ".join(
            f"{group} {minutes} min" for group, minutes in request.allocation
        )
        lines.append(
            f"The time divides over them as {divided}. That is a starting "
            "point and not an instruction: `allocate` will divide it on any "
            "proportions you think are better."
        )
    if request.exclusions:
        lines.append(
            "Excluded, and already filtered out of the admissible set: "
            + ", ".join(f"{e.granularity} {e.value}" for e in request.exclusions)
            + "."
        )
    if request.preferences:
        lines.append(
            "The user has said they would rather not do: "
            + ", ".join(request.preferences)
            + ". These are preferences, not exclusions, so they are still in "
            "the admissible set. Leave them out, or propose one and add a row "
            "to the plan's `despite` for it: "
            '{"exercise_id": "...", "why": "..."}. The field is `why`; '
            "`reason` belongs to a block. Proposing one silently is rejected."
        )
    if request.refused is not None:
        lines.append(
            "You proposed this workout and the user turned it down:\n"
            + request.refused.model_dump_json(indent=1)
        )
        if request.because:
            lines.append(f"They said: {request.because}")
        lines.append(
            "Propose a different one. Do not argue it, do not hand back the "
            "same plan, and do not give up and offer something token: they "
            "still want to train today."
        )
    lines.append("Plan the workout.")
    return "\n".join(lines)


class Answer(TypedDict, total=False):
    """What resumes a thread waiting on a plan: kept, or turned down and why."""

    accepted: bool
    because: str
    minutes: int


def accepted() -> Answer:
    """The plan is the user's workout, and the run goes on to write it."""
    return {"accepted": True}


def refused(because: str = "", minutes: int | None = None) -> Answer:
    """The plan is turned down, with what the user said and any shorter time they asked for."""
    answer: Answer = {"accepted": False, "because": because}
    if minutes is not None:
        answer["minutes"] = minutes
    return answer


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
    said: Annotated[list[str], operator.add]
    """What the user has written on this thread, in the order they wrote it.

    Beside `messages` and not in it. `messages` is the planner's own working
    history and a fresh proposal clears it, so a sentence left there would be
    destroyed by the next refusal; and a turn appended to it before the run
    starts makes `turn` read a non-empty history and skip the brief entirely.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    spent: int
    attempts: int
    violations: tuple[plans.Violation, ...]
    refusals: Annotated[list[tuple[plans.Violation, ...]], operator.add]
    timings: Annotated[list[tuple[str, float]], operator.add]
    plan: plans.WorkoutPlan | None
    accepted: bool
    workout: int | None


def starting(request: plans.Request) -> PlannerState:
    """The input that starts a run, with whatever a previous one left cleared.

    One chat is one thread for as long as the chat lives (ADR-0004, item 6),
    so the second plan a thread is asked for starts on top of the first. Left
    there, the old messages make `turn` read a non-empty history and never
    write the brief -- the new request planned against the old one's words --
    and an old `workout` makes a refused run look like one that wrote a
    workout.
    """
    return {
        "request": request,
        "accepted": False,
        "workout": None,
        # Cast because the annotation on `messages` is the list `add_messages`
        # reduces to, and a removal is an instruction to that reducer rather
        # than a message the state ever holds.
        "messages": [cast(AnyMessage, RemoveMessage(REMOVE_ALL_MESSAGES))],
        "attempts": 0,
        "spent": 0,
        "violations": (),
        "plan": None,
    }


Planner = CompiledStateGraph[PlannerState, None, PlannerState, PlannerState]
"""The compiled graph, as `build` returns it."""


def build(
    model: BaseChatModel,
    budget: int = agent.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> Planner:
    """The compiled planner graph, running on `model`."""
    offered = agent.registered("planner", TOOLS)
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
            opening = [SystemMessage(PLANNING), HumanMessage(brief(request))]
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
                KEEPS,
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
        asked = HumanMessage(EMIT_PLAN)
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

    def propose(state: PlannerState) -> dict[str, Any]:
        """The plan, offered; the run stops here until somebody answers (ADR-0005).

        Nothing before the `interrupt` touches anything outside the state: a
        resumed node runs again from the top.
        """
        offered = state["plan"]
        assert offered is not None, "a plan is proposed only after it validated"
        answer: Answer = interrupt(offered.model_dump())
        if answer.get("accepted"):
            return {"accepted": True}
        request = state["request"]
        shorter = answer.get("minutes")
        # The turn that follows is a fresh proposal and not an argument with
        # the one before it, so the messages go and the brief is written again
        # -- this time carrying what the user said.
        again = dataclasses.replace(
            request,
            refused=offered,
            because=answer.get("because", ""),
            budget_min=shorter if shorter is not None else request.budget_min,
            # An allocation divides the minutes that were asked for, so a
            # shorter workout carries none: `turn` divides the new budget.
            allocation=() if shorter is not None else request.allocation,
        )
        # `dict(...)` because a node contributes a plain mapping, while
        # `starting` is typed as the state so it can also be a run's input.
        return dict(starting(again))

    def record(state: PlannerState) -> dict[str, Any]:
        """The accepted plan, written as the prescribed workout it now is."""
        accepted_plan = state["plan"]
        assert accepted_plan is not None, "nothing is written without a plan"
        with tools.reported(), tools.opened() as connection:
            written = workouts.record_prescribed(
                connection,
                tuple(
                    workouts.PrescribedBlock(block=costed, reason=shape.reason)
                    for shape, costed in zip(
                        accepted_plan.blocks, plans.to_blocks(accepted_plan), strict=True
                    )
                ),
                on=date.today().isoformat(),
            )
        return {"workout": written}

    def after_planner(state: PlannerState) -> Literal["tools", "emit"]:
        reply = state["messages"][-1]
        if isinstance(reply, AIMessage) and reply.tool_calls:
            return "tools"
        return "emit"

    def after_tools(state: PlannerState) -> Literal["planner", "emit"]:
        return "emit" if state.get("spent", 0) >= budget else "planner"

    def after_validate(state: PlannerState) -> Literal["planner", "propose", "done"]:
        if not state["violations"]:
            return "propose"
        # Nothing to offer: a run the validator refused to the end ends here,
        # which is also why `trainer eval` never reaches an interrupt.
        if state["attempts"] >= ATTEMPTS:
            return "done"
        return "planner"

    def after_propose(state: PlannerState) -> Literal["planner", "record"]:
        return "record" if state.get("accepted") else "planner"

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
    graph.add_node("propose", timed("propose", propose))
    graph.add_node("record", timed("record", record))
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", after_planner)
    graph.add_conditional_edges("tools", after_tools)
    graph.add_edge("emit", "validate")
    graph.add_conditional_edges(
        "validate",
        after_validate,
        {"planner": "planner", "propose": "propose", "done": END},
    )
    graph.add_conditional_edges(
        "propose", after_propose, {"planner": "planner", "record": "record"}
    )
    graph.add_edge("record", END)
    return graph.compile(checkpointer=checkpointer)


def studio() -> Planner:
    """The planner graph on the provider `LLM_BACKEND` names, as `langgraph dev` serves it."""
    return build(models.chat().model)
