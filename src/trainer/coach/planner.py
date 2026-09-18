"""The planner graph: plan over the tools, emit against today's schema, validate."""

from __future__ import annotations

import dataclasses
import logging
import operator
import sqlite3
import time
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, TypedDict, cast
from uuid import uuid4

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

from trainer import tools
from trainer import plan as plans
from trainer.coach import models
from trainer.coach import record as records
from trainer.coach.calls import answered
from trainer.engine import admissible, constraints, workouts

logger = logging.getLogger(__name__)

ATTEMPTS = 3
"""Plans one run may emit before a refusal ends it."""

REJECTIONS = 2
"""Turns the provider may refuse before the run gives up on the model."""

REFUSED_TURN = """\
The provider would not accept that turn:
{why}
That is a statement about what you wrote, not about the tools. Write it
again, in strict JSON. Numbers are literals there: 0.49, never an expression
like 22/45, which JSON has no way to represent."""
"""What a provider's refusal is turned into, on its way back to the model.

Observed twice on Ollama in one evening, from different causes: a tool call
carrying `{"chest": 22/45}`, which JSON has no arithmetic for, and a tool call
truncated by a context too small to finish it. Both are the model getting it
wrong, which is the case `tools.execute` exists for -- but the provider
refuses them before any of our code sees a call, so the recovery it offers
never comes into play and a run of several minutes is simply lost.
"""

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
`tools.registered`'s guard -- which only checks the names that are *asked* for
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
    if request.refusals:
        lines.append(turned_down(request.refusals))
        lines.append(
            "Propose a different one. Do not argue it, do not hand back a "
            "plan they have already turned down, and do not give up and offer "
            "something token: they still want to train today."
        )
    lines.append("Plan the workout.")
    return "\n".join(lines)


def turned_down(refusals: Sequence[plans.Refusal]) -> str:
    """Every plan this negotiation has turned down, oldest first, as the model reads them.

    The newest one whole, because it is the one being answered and the model
    has to see what it is changing; the ones before it as the exercises they
    named, which is what a plan has to avoid repeating and is all the
    negotiation still keeps of them (ADR-0007, item 4).
    """
    lines = [
        f"You have proposed {len(refusals)} workout(s) already and the user "
        "turned each one down."
    ]
    for turned_down in refusals:
        if turned_down.plan is None:
            lines.append("Turned down: " + ", ".join(turned_down.exercise_ids) + ".")
        else:
            lines.append(
                "Turned down, in full:\n" + turned_down.plan.model_dump_json(indent=1)
            )
        if turned_down.because:
            lines.append(f"They said: {turned_down.because}")
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
    schema = tools.strict_schema(plans.WorkoutPlan)

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
    negotiation: str
    """The ask this run belongs to. One ask, N runs, at most one plan accepted."""

    run: str
    follows: str | None
    """The run this one was born from, when a refusal ended that one."""

    began: str
    ended: str
    ending: str
    """How this run finished, written the moment it happens and empty until then.

    A run still waiting on an answer has no ending, and neither has one that
    was cut: what the reader found is the reader's to derive (ADR-0007, item 7).
    """

    said: Annotated[list[str], operator.add]
    """What the user has written on this thread, in the order they wrote it.

    Beside `messages` and not in it. `messages` is the planner's own working
    history and a fresh proposal clears it, so a sentence left there would be
    destroyed by the next refusal; and a turn appended to it before the run
    starts makes `turn` read a non-empty history and skip the brief entirely.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    spent: int
    budget: int
    """Tool calls this run was given. In the state because the reader has no
    other way back to it: a run cut mid-flight is read off its checkpoint, and
    what bounded it was an argument to `build` that nobody kept."""

    attempts: int
    rejections: int
    """Turns the provider has refused *in a row*, reset by the first it accepts."""

    violations: tuple[plans.Violation, ...]
    refusals: list[tuple[plans.Violation, ...]]
    """What the validator refused, attempt by attempt, **in this run only**.

    Written whole rather than appended to, because a run's record is its own.
    Accumulated by a reducer -- which is what these were, and `_beginning` has
    no way to say *empty* to one -- the plan the user turned down at nine is
    an attempt of the run at ten.
    """

    timings: list[tuple[str, str, str, float]]
    """Node, model, provider and seconds, per node run, for this run only."""

    plan: plans.WorkoutPlan | None
    accepted: bool
    workout: int | None


def starting(request: plans.Request) -> PlannerState:
    """The input that starts a negotiation: its first run, following nothing."""
    return _beginning(request, negotiation=_negotiation_id(), follows=None)


def following(request: plans.Request, negotiation: str, follows: str) -> PlannerState:
    """The run a refusal gives birth to: the same ask, carrying which run it follows."""
    return _beginning(request, negotiation=negotiation, follows=follows)


def _negotiation_id() -> str:
    """A negotiation's name: when it was asked, and enough to tell two of them apart."""
    return f"{datetime.now().astimezone():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"


def identity(negotiation: str, follows: str | None) -> dict[str, Any]:
    """Who a run is: its name, the ask it belongs to, what it follows, and no ending yet."""
    return {
        "negotiation": negotiation,
        "run": uuid4().hex[:8],
        "follows": follows,
        "began": records.now(),
        "ended": "",
        "ending": "",
    }


def _beginning(
    request: plans.Request, *, negotiation: str, follows: str | None
) -> PlannerState:
    """The input that starts a run, with whatever a previous one left cleared.

    One chat is one thread for as long as the chat lives (ADR-0004, item 6),
    so the second plan a thread is asked for starts on top of the first. Left
    there, the old messages make `turn` read a non-empty history and never
    write the brief -- the new request planned against the old one's words --
    and an old `workout` makes a refused run look like one that wrote a
    workout.

    `said` is the one key it leaves alone (ADR-0006): it is what the user has
    written on this thread, and it outlives every run on it.
    """
    return {
        "request": request,
        **identity(negotiation, follows),  # type: ignore[typeddict-item]
        "accepted": False,
        "workout": None,
        # Cast because the annotation on `messages` is the list `add_messages`
        # reduces to, and a removal is an instruction to that reducer rather
        # than a message the state ever holds.
        "messages": [cast(AnyMessage, RemoveMessage(REMOVE_ALL_MESSAGES))],
        "attempts": 0,
        "rejections": 0,
        "spent": 0,
        "violations": (),
        "refusals": [],
        "timings": [],
        "plan": None,
    }


Planner = CompiledStateGraph[PlannerState, None, PlannerState, PlannerState]
"""The compiled graph, as `build` returns it."""


def build(
    on: models.Chat,
    budget: int = tools.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
) -> Planner:
    """The compiled planner graph, running on `on`.

    `archive` is where a run goes when it ends (ADR-0007, item 6), and a graph
    built without one keeps nothing: the eval suites run the same graph
    dozens of times to measure it, and their runs in the home would be the
    history session 10 is supposed to read.
    """
    model = on.model
    offered = tools.registered("planner", TOOLS)

    def closed(
        state: PlannerState | dict[str, Any], ending: str, **also: Any
    ) -> dict[str, Any]:
        """This run is over, written where both graphs write theirs."""
        return records.closing(state, ending, budget, archive, **also)

    definitions = [
        {"type": "function", "function": tools.schema(tool)} for tool in offered
    ]

    def turn(state: PlannerState) -> dict[str, Any]:
        request = state["request"]
        if not isinstance(request, plans.Request):
            # Studio and the HTTP API send the request as JSON.
            request = TypeAdapter(plans.Request).validate_python(request)
        # Those two doors start a thread with a request and nothing else, and
        # a run has to be a thing that can be read back whichever door opened
        # it. Only when there is no run yet: every later turn of this one
        # would otherwise give it a new name.
        born = {} if state.get("run") else identity(_negotiation_id(), None)
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
        try:
            reply = bound.invoke([*state.get("messages", []), *opening])
        except Exception as error:
            # Everything inside `invoke` belongs to the provider and its
            # transport, so what comes out of it is a statement about the
            # model or the link and never about this graph -- which is why it
            # is caught this broadly and bounded rather than named. Past the
            # bound it is raised: a model that cannot produce an acceptable
            # turn twice running is not going to on the third, and the bot
            # says so rather than spending more minutes finding out.
            #
            # Twice *running*, which is why the count resets below on the
            # first turn the provider accepts. Counted over the whole run
            # instead, three isolated hiccups spread across the validator's
            # own retries would end a run that was recovering from every one
            # of them.
            refused = state.get("rejections", 0) + 1
            if refused > REJECTIONS:
                raise
            logger.warning("the provider refused a turn (%d): %s", refused, error)
            return born | {
                "request": request,
                "budget": budget,
                "rejections": refused,
                "messages": [
                    *opening,
                    HumanMessage(REFUSED_TURN.format(why=error), name="provider"),
                ],
            }
        return born | {
            "request": request,
            "budget": budget,
            "rejections": 0,
            "messages": [*opening, reply],
        }

    def run_tools(state: PlannerState) -> dict[str, Any]:
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        answers = []
        for call in reply.tool_calls:
            call_id = answered(call)
            result = tools.execute(
                tools.Call(id=call_id, name=call["name"], arguments=call["args"]),
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
            "refusals": [*state.get("refusals", []), violations],
            "plan": emitted,
        }
        if violations and attempts < ATTEMPTS:
            decided["messages"] = [
                HumanMessage(
                    FEEDBACK.format(violations=plans.refusal(violations)), name="validator"
                )
            ]
        elif violations:
            decided.update(closed({**state, **decided}, records.REFUSED))
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
        because = answer.get("because", "")
        shorter = answer.get("minutes")
        # Turning a plan down ends the run that offered it (ADR-0007, item 2).
        # What it cost is written here and nowhere else: the state below is
        # the next run's, and everything this one spent is about to be cleared.
        closed(state, records.TURNED_DOWN, because=because)
        # The run that follows is a fresh proposal and not an argument with the
        # one before it, so the messages go and the brief is written again --
        # this time carrying every plan the negotiation has turned down.
        again = dataclasses.replace(
            request,
            refusals=plans.turned_down(request.refusals, offered, because),
            budget_min=shorter if shorter is not None else request.budget_min,
            # An allocation divides the minutes that were asked for, so a
            # shorter workout carries none: `turn` divides the new budget.
            allocation=() if shorter is not None else request.allocation,
        )
        # `dict(...)` because a node contributes a plain mapping, while
        # `following` is typed as the state so it can also be a run's input.
        return dict(
            following(again, state["negotiation"], follows=state["run"])
        )

    def prescribe(state: PlannerState) -> dict[str, Any]:
        """The accepted plan, written as the prescribed workout it now is, and the run closed."""
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
        return {"workout": written} | closed(
            {**state, "workout": written}, records.ACCEPTED
        )

    def after_planner(state: PlannerState) -> Literal["tools", "emit", "planner"]:
        reply = state["messages"][-1]
        if isinstance(reply, AIMessage) and reply.tool_calls:
            return "tools"
        # Not an AIMessage at all: `turn` caught a provider refusing the turn
        # and left what it said in its place. There is nothing to emit from,
        # and the model has been told what to write instead.
        if not isinstance(reply, AIMessage):
            return "planner"
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

    def after_propose(state: PlannerState) -> Literal["planner", "prescribe"]:
        return "prescribe" if state.get("accepted") else "planner"

    def timed(node: str, step: Node) -> Node:
        """Every node says who answered it and what it cost: the minutes are the thing being measured.

        A node that started a new run says so by handing back timings of its
        own, and keeps them: its seconds belong to neither run. On `propose`,
        the only node that does it, they are how long the user took to answer,
        which is not a cost of planning at all.
        """

        def counted(state: PlannerState) -> dict[str, Any]:
            started = time.monotonic()
            produced = step(state)
            if "timings" in produced:
                return produced
            spent = time.monotonic() - started
            return produced | {
                "timings": [
                    *state.get("timings", []),
                    (node, on.name, on.provider, spent),
                ]
            }

        return counted

    graph = StateGraph(PlannerState)
    graph.add_node("planner", timed("planner", turn))
    graph.add_node("tools", timed("tools", run_tools))
    graph.add_node("emit", timed("emit", emit))
    graph.add_node("validate", timed("validate", validate))
    graph.add_node("propose", timed("propose", propose))
    graph.add_node("prescribe", timed("prescribe", prescribe))
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
        "propose", after_propose, {"planner": "planner", "prescribe": "prescribe"}
    )
    graph.add_edge("prescribe", END)
    return graph.compile(checkpointer=checkpointer)


def studio() -> Planner:
    """The planner graph on the provider `LLM_BACKEND` names, as `langgraph dev` serves it.

    On the home's archive, like the two real doors and unlike the eval suites:
    a run driven from Studio is one run somebody had, against the real catalog
    and the real checkpointer, and it already writes a prescribed workout when
    a plan is accepted. Given an archive of its own it would be the one door
    whose runs `trainer runs` cannot read -- while debugging the graph, which
    is the only reason to be in Studio at all.
    """
    return build(models.chat(), archive=records.archive())
