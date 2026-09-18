"""The logger graph: read one report over the tools, ask what it cannot know, emit the document."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
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
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from trainer import log as logs
from trainer import tools
from trainer.coach import models
from trainer.coach import record as records
from trainer.coach.calls import answered
from trainer.engine import exclusions, workouts

logger = logging.getLogger(__name__)

ASK_BUDGET = 3
"""Clarifying questions one report may cost the user.

The person has just trained, and a report that needs a fourth question is a
report the agent has failed to read rather than an ambiguous one. Like the
call budget it is a bound and not a target: running out stops the asking and
the document is emitted with what is known.
"""

CLARIFY = "clarify"
"""An open question: the answer is prose, and the user writes it."""

EXCLUSION = "exclusion"
"""A closed question: the exclusion the report proposes stands, or it does not."""

SPENT_ASKING = (
    "You have no questions left. Emit the document with what you know, and "
    "leave out anything the report does not determine."
)
"""What a question past the budget is answered with.

The budget is kept by taking `ask_user` off the table on the next turn; this
is for the turn that spends it -- one turn can carry more calls than the
budget has left, and those are already in flight when it is counted.
"""

TOOLS = (
    "prescribed_workout",
    "unreported_workouts",
    "last_performed_load",
    "pattern_history",
    "search_exercises",
    "compare_variants",
)
"""Six tools, all reads, and no writer among them.

Named rather than derived by subtraction: `allocate` and `remaining_budget`
are arithmetic for a plan that has not happened, `admissible_set` is the space
a plan is chosen inside, `adherence_history` and `volume_deficit` are what the
*planner* wants to know about what was trained. None of them is a question
about the sentence in front of this agent, and a surface holding tools nobody
needs is context paid for on every turn.
"""

KEEPS = ("id", "name", "equipment", "mechanic", "primary_muscles")
"""What reading a report needs. `name` is here and not on the planner's list
(`coach.planner.KEEPS`), because a report says *"the bench"* and a plan is
written in ids."""


def ask_user(question: str) -> str:
    """Ask the user one thing the report does not determine, and wait for their answer.

    Use this when the report leaves a value open -- a bare number that is
    effort or is discomfort, a set count that could be rounds or reps. Ask one
    thing, in one sentence, and never for an rpe they did not offer. Their
    answer comes back as the result of this call and you carry on from there.

    The body is never run. The graph answers this call by putting the question
    to whoever wrote the report and handing back what they said -- which is
    what makes it an `interrupt()` that can wait days rather than a marked
    line in prose the loop had to recognise (ADR-0004).
    """
    raise AssertionError("the graph answers ask_user; nothing calls it")


LOGGING = f"""\
You read one report of one workout that has already happened, and turn it
into the document the engine writes down.

{tools.INSTRUCTIONS}
How you read it:

- Call `prescribed_workout` for the workout the brief names, first. It is what
  the report is a deviation from, and it is the closed set of exercises the
  user is talking about.
- Resolve every exercise they name inside that set, by its name. Only when
  nothing in it can be what they meant -- which is what a substitution looks
  like -- call `search_exercises`, and take the id from what comes back.
  **Never write an id you remember.** An id that does not exist is refused; an
  id that exists and is the wrong exercise files the training under something
  they did not do, and nothing anywhere says so.
- Emit only what deviated. Everything you leave out is filled in from the
  prescription and marked as assumed, which is the whole point of logging by
  deviation -- a workout that went as prescribed is a document with no blocks
  in it at all.
- *Sets*, and Italian *serie*, are **rounds** -- how many times the block was
  performed. They are never the `amount`, which is the reps or the seconds of
  one round. *"Solo 3 serie"* is `rounds: 3` with the prescribed reps
  untouched, not three reps.
- `report` is the user's own words, verbatim and complete, in the language
  they wrote them. Not a summary and not a translation.
- Provenance is `reported` for a value they gave and `asked` for one that came
  back from a question you asked. Never `assumed`: that is the engine's, and
  a document claiming it would be claiming the prescription said something.
- **A value nobody gave is left out, not filled in.** Leaving it out is what
  the prescription is for; writing it marks it `reported`, which is the state
  saying the user said it. That is the one mistake here nothing downstream can
  catch.
- A number marked `assumed` has to be the prescribed one. Where the plan is
  silent -- a substituted exercise, a block nobody prescribed -- `assumed` is
  the honest label for a value the user did not give; where the plan says 10
  and the document says 8, it is refused.
- `rpe` is recorded only if they say how hard it felt. Never ask for it and
  never infer it from how the report reads.
- `load_kg` is null unless they gave a load, and `load_kg_source` is null
  with it: the two are written together or both left empty, and a provenance
  describing nothing is not a provenance. Zero is not *"no load"* either --
  it is a claim that the bar was empty.

Asking:

- When the report does not determine a value, call `ask_user` instead of
  filling it in. A bare number is the case this exists for: *"4 out of 10"* is
  effort, or it is discomfort, and nothing in the sentence says which.
- One question per call, and at most {ASK_BUDGET} in all. Somebody has just
  trained and is answering them on a phone.
- When you have nothing left to ask, do not call it. You will then be asked
  for the document.
- Write the question, and the `why` of any exclusion you propose, in plain
  ASCII -- `perche`, not `perché`, and `--` rather than a dash. They are
  printed to a Windows console that has no other alphabet. This applies to
  what **you** write and never to `report`, which is the user's own words and
  is copied exactly as they typed them.

Pain, and the one thing you may propose:

- Pain is prose. There is no scale, no threshold, and nothing accumulates.
- If what they said means a movement should stop being prescribed for a while,
  propose an exclusion: a `value` naming a movement pattern (`vertical push`)
  or a loaded joint (`shoulder`) -- never an exercise id, and never something
  they merely dislike -- a `retest_date` after today, and a `why` saying what
  you are reading. Do not label which of the two it is; the engine decides
  that against the catalog.
- It is a proposal. The user is shown it and confirms it before anything is
  written, because an exclusion on `shoulder` takes 251 of 582 exercises out
  of what may ever be prescribed. Propose one when the report is about pain,
  not when it is about effort.

You have a budget of tool calls. When it runs out you will be asked for the
document with whatever you know at that point.
"""

EMIT_LOG = "Emit the performed workout now, in the required shape."


def brief(
    said: str,
    today: str,
    awaiting: int | None = None,
    prescribed_on: str | None = None,
) -> str:
    """The report, and what it is probably about, for the model to read.

    `awaiting` is the workout still to do -- resolved by the caller, because
    which prescribed workout is open is a fact and not a judgement. Which
    workout the report is *about* stays the model's call: a user who trained
    something else entirely says so in the sentence, and that sentence is the
    only place the answer is.
    """
    lines = [f"Today is {today}."]
    if awaiting is None:
        lines.append(
            "No prescribed workout is waiting for a report. Unless the user "
            "names one, this is training nobody planned: emit `workout_id` "
            "as null. `unreported_workouts` lists the ones a later workout "
            "overtook."
        )
    else:
        lines.append(
            f"Workout {awaiting}, prescribed on {prescribed_on}, is waiting "
            f"for a report, and this is almost certainly it. Call "
            f"`prescribed_workout({awaiting})` to see what it asked for. If "
            f"what they describe is plainly not that workout, emit "
            f"`workout_id` as null instead."
        )
    lines.append("The user said, in their own words:")
    lines.append(said)
    return "\n".join(lines)


class LoggerState(TypedDict, total=False):
    report: str
    """The user's own words, as they wrote them."""

    today: str
    awaiting: int | None
    prescribed_on: str | None

    negotiation: str
    run: str
    follows: str | None
    began: str
    ended: str
    ending: str

    messages: Annotated[list[AnyMessage], add_messages]
    spent: int
    budget: int
    asked: int
    """Clarifying questions this run has spent, bounded by `ASK_BUDGET`."""

    questions: list[tuple[str, str]]
    """What it asked and what it was told, in order. A field and not a reading
    of the prose: the log eval scores *did it ask* on it."""

    document: logs.PerformedWorkout | None
    refused: str | None
    """What `log.validate` said about the document, or nothing when it passed.

    An outcome of the run and not an exception: a report is a fact and is
    never refused for what the user did, and every refusal here is about the
    document -- a typo, a provenance that cannot be true, an exclusion naming
    nothing.
    """

    confirmed: bool
    """Whether the exclusion the document proposes is the user's. False until
    they say so, and nothing writes one before that (ADR-0004)."""

    timings: list[tuple[str, str, str, float]]


def starting(
    report: str,
    today: str,
    awaiting: int | None = None,
    prescribed_on: str | None = None,
) -> LoggerState:
    """The input that starts a run of the logger: one report, read once."""
    return {
        "report": report,
        "today": today,
        "awaiting": awaiting,
        "prescribed_on": prescribed_on,
        **records.identity(records.negotiation_id(), None),  # type: ignore[typeddict-item]
        # Cast because the annotation on `messages` is the list `add_messages`
        # reduces to, and a removal is an instruction to that reducer rather
        # than a message the state ever holds.
        "messages": [cast(AnyMessage, RemoveMessage(REMOVE_ALL_MESSAGES))],
        "spent": 0,
        "asked": 0,
        "questions": [],
        "document": None,
        "refused": None,
        "confirmed": False,
        "timings": [],
    }


Logger = CompiledStateGraph[LoggerState, None, LoggerState, LoggerState]
"""The compiled graph, as `build` returns it."""


def build(
    on: models.Chat,
    budget: int = tools.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
) -> Logger:
    """The compiled logger graph, running on `on`.

    **Nothing here writes.** The six tools are reads and the document goes
    back to the caller; `workouts.record_performed` is reached through
    `performed` below, from the door that asked. That is what makes an
    interrupted run leave nothing behind -- and it is what lets the log eval
    put thirty reports through this graph without leaving thirty performed
    workouts in the state the measurement is taken from.
    """
    model = on.model
    offered = tools.registered("logger", TOOLS)
    reads = [{"type": "function", "function": tools.schema(tool)} for tool in offered]
    asking = {"type": "function", "function": tools.schema(ask_user)}
    timed = records.timing(on)

    def closed(
        state: LoggerState | dict[str, Any], ending: str, **also: Any
    ) -> dict[str, Any]:
        """This run is over, written where both graphs write theirs."""
        return records.closing(state, ending, budget, archive, **also)

    def turn(state: LoggerState) -> dict[str, Any]:
        born = records.born(state)
        opening: list[AnyMessage] = []
        if not state.get("messages"):
            opening = [
                SystemMessage(LOGGING),
                HumanMessage(
                    brief(
                        state["report"],
                        state["today"],
                        state.get("awaiting"),
                        state.get("prescribed_on"),
                    )
                ),
            ]
        # The question budget is kept by taking `ask_user` off the table, which
        # is the only bound a model cannot talk its way past. Answered with a
        # sentence and left on it, a model that keeps asking loops between this
        # node and the tools without ever spending a call, and LangGraph's
        # recursion limit ends the run instead of the budget.
        #
        # The reads are guarded the same way for symmetry; in practice
        # `after_tools` sends a spent run to `emit` before this is read again.
        definitions = list(reads) if state.get("spent", 0) < budget else []
        if state.get("asked", 0) < ASK_BUDGET:
            definitions.append(asking)
        bound = model.bind_tools(definitions) if definitions else model
        reply = bound.invoke([*state.get("messages", []), *opening])
        return born | {"budget": budget, "messages": [*opening, reply]}

    def _asked(state: LoggerState, already: int, question: str) -> tuple[str, str]:
        """One question put to the user, or the sentence that says there are none left."""
        if state.get("asked", 0) + already >= ASK_BUDGET:
            return question, SPENT_ASKING
        answer = interrupt({"kind": CLARIFY, "ask": question})
        return question, str(answer)

    def run_tools(state: LoggerState) -> dict[str, Any]:
        """The turn's calls, answered -- including the one that is a question.

        `ask_user` stops the graph here rather than in a node of its own,
        because a turn can carry it alongside a read and LangGraph gives a
        node one input. Resuming replays this node from the top, so the reads
        beside it run a second time; every tool on this surface is a read, and
        the count of what was spent is taken from the state the node was given
        rather than added to as it goes.
        """
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        answers: list[AnyMessage] = []
        asked: list[tuple[str, str]] = []
        spent = 0
        for call in reply.tool_calls:
            call_id = answered(call)
            if call["name"] == ask_user.__name__:
                said = _asked(state, len(asked), str(call["args"].get("question", "")))
                asked.append(said)
                answers.append(
                    ToolMessage(said[1], tool_call_id=call_id, name=call["name"])
                )
                continue
            spent += 1
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
        return {
            "messages": answers,
            "spent": state.get("spent", 0) + spent,
            "asked": state.get("asked", 0) + len(asked),
            "questions": [*state.get("questions", []), *asked],
        }

    def emit(state: LoggerState) -> dict[str, Any]:
        asked = HumanMessage(EMIT_LOG)
        schema = tools.strict_schema(logs.PerformedWorkout)
        structured = model.with_structured_output(
            schema, method="json_schema", include_raw=True
        )
        emitted = structured.invoke([*state["messages"], asked])
        assert isinstance(emitted, dict)
        return {"messages": [asked, emitted["raw"]]}

    def validate(state: LoggerState) -> dict[str, Any]:
        document = state["messages"][-1]
        assert isinstance(document, AIMessage)
        try:
            performed = logs.parse(document.text)
        except logs.LogError as error:
            return {"document": None} | closed(
                {**state, "document": None, "refused": str(error)},
                records.REFUSED,
                refused=str(error),
            )
        refused: str | None = None
        try:
            with tools.opened() as connection:
                logs.validate(connection, performed, state["today"])
        except logs.LogRejected as error:
            refused = str(error)
        decided: dict[str, Any] = {"document": performed, "refused": refused}
        if refused is not None or performed.proposed_exclusion is None:
            decided.update(closed({**state, **decided}, _ending(refused)))
        return decided

    def confirm(state: LoggerState) -> dict[str, Any]:
        """The exclusion the document proposes, put to the user before anything writes it.

        A closed question, because the answer is yes or no. Nothing before the
        `interrupt` touches anything outside the state: a resumed node runs
        again from the top.
        """
        performed = state["document"]
        assert performed is not None and performed.proposed_exclusion is not None
        proposal = performed.proposed_exclusion
        with tools.opened() as connection:
            # Classified here so that the question says what is actually being
            # stopped: `shoulder` is a joint and `vertical push` a pattern, and
            # the two take very different amounts of the catalog away. The
            # catalog decides which, and only this side has it.
            classified = exclusions.classify(connection, proposal.value)
        answer = interrupt(
            {
                "kind": EXCLUSION,
                "ask": proposal.why,
                "granularity": classified.granularity,
                "value": classified.value,
                "retest_date": proposal.retest_date,
            }
        )
        confirmed = bool(answer)
        return {"confirmed": confirmed} | closed(
            {**state, "confirmed": confirmed}, records.DONE
        )

    def after_logger(state: LoggerState) -> Literal["tools", "emit"]:
        reply = state["messages"][-1]
        if isinstance(reply, AIMessage) and reply.tool_calls:
            return "tools"
        return "emit"

    def after_tools(state: LoggerState) -> Literal["logger", "emit"]:
        return "emit" if state.get("spent", 0) >= budget else "logger"

    def after_validate(state: LoggerState) -> Literal["confirm", "done"]:
        performed = state.get("document")
        if state.get("refused") is not None or performed is None:
            return "done"
        return "confirm" if performed.proposed_exclusion is not None else "done"

    graph = StateGraph(LoggerState)
    graph.add_node("logger", timed("logger", turn))
    graph.add_node("tools", timed("tools", run_tools))
    graph.add_node("emit", timed("emit", emit))
    graph.add_node("validate", timed("validate", validate))
    graph.add_node("confirm", timed("confirm", confirm))
    graph.add_edge(START, "logger")
    graph.add_conditional_edges("logger", after_logger)
    graph.add_conditional_edges("tools", after_tools)
    graph.add_edge("emit", "validate")
    graph.add_conditional_edges(
        "validate", after_validate, {"confirm": "confirm", "done": END}
    )
    graph.add_edge("confirm", END)
    return graph.compile(checkpointer=checkpointer)


def _ending(refused: str | None) -> str:
    """How a run of the logger finished: the document stood, or it was refused."""
    return records.REFUSED if refused is not None else records.DONE


def performed(
    connection: sqlite3.Connection,
    final: Mapping[str, Any],
    blocks: tuple[workouts.PerformedBlock, ...],
) -> int:
    """The run's document, written down, and the exclusion only if it was confirmed.

    The one writer, reached by whichever door asked. The graph does not call
    it -- see `build` -- so a run that was interrupted, or measured, leaves
    nothing behind.

    `blocks` is handed in rather than resolved here, because the caller has
    already resolved them: what is printed before the write and what is
    written are the same blocks, and resolving them twice is two answers to
    what adherence filled in.
    """
    document = final["document"]
    assert document is not None, "nothing is written without a document"
    exclusion, retest_date = (
        logs.proposed(connection, document) if final.get("confirmed") else (None, None)
    )
    return workouts.record_performed(
        connection,
        blocks,
        on=str(final["today"]),
        report=document.report,
        workout_id=document.workout_id,
        exclusion=exclusion,
        retest_date=retest_date,
    )


def studio() -> Logger:
    """The logger graph on the provider `LLM_BACKEND` names, as `langgraph dev` serves it."""
    return build(models.chat(), archive=records.archive())
