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
from trainer import plan as plans
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

VALIDATOR = "validator"
"""The rule a `log.validate` refusal is recorded under; `plans.SHAPE` is the other."""

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


def done_reading() -> str:
    """Say you have read what you need; the document is asked for next.

    The body is never run. A model that ends every turn on a tool call had
    only `ask_user` to end on, and put *"No question needed"* to the user.
    """
    raise AssertionError("the graph answers done_reading; nothing calls it")


LOGGING = f"""\
You read one report of one workout that has already happened, and turn it
into the document the engine writes down. The document says what the user
told you, and nothing else: the engine fills in the rest from what was
prescribed.

{tools.INSTRUCTIONS}
Reading the report:

- Call `prescribed_workout` for the workout the brief names, first. It is what
  the report is about and the closed set of exercises the user is talking about.
- Resolve every exercise they name inside that set, by its name. When nothing
  in it can be what they meant -- a substitution, something done on the end,
  a workout nobody planned -- call `search_exercises` and take the id from
  what comes back. **Never write an id you remember.**
- Write a block only for what the user talked about. A workout that went as
  prescribed is a document with no blocks.
- Inside a block you write, a number the user did not give: leave it null,
  with its source. The engine writes the prescribed one. A number they gave
  is `reported`; one that came back from a question you asked is `asked`.
- *Sets*, and Italian *serie*, are **rounds** -- how many times the block was
  performed -- never the `amount`, which is the reps or seconds of one round.
- `report` is the user's own words, verbatim and complete, in their language.
- `rpe` only if they say how hard it felt. Never ask for it.
- `load_kg` only if they gave a load, with its source; otherwise both null.

Asking:

- Ask only about something they *said*: a word that could mean two
  different things, or a number with nothing to attach to. Then call
  `ask_user` instead of choosing. One question per call,
  at most {ASK_BUDGET} in all: they have just trained and are answering on a
  phone.
- A number they did not mention is not a question: leave it null, and it is
  the prescribed one. Most reports need no question at all.
- Never ask to confirm an exclusion. Propose it in the document; the user is
  asked to confirm it after you emit.
- When you have what you need, call `done_reading`; you will be asked for
  the document.
- Write questions, and the `why` of an exclusion, in plain ASCII -- `perche`
  and `--`, never an accent or a dash. `report` is exempt: it is copied
  exactly as typed.

Pain:

- If what they said means a movement should stop being prescribed for a
  while, propose an exclusion: a movement pattern (`vertical push`) or a
  loaded joint (`shoulder`) -- never an exercise id -- with a `retest_date`
  after today and a `why`. It is a proposal the user confirms. Propose one for
  pain, not for effort or a dislike.

The validator checks the document. If it refuses one, you are told why and
may read, ask and emit again. You also have a budget of tool calls; when it
runs out you will be asked for the document with what you know.
"""

EMIT_LOG = "Emit the performed workout now, in the required shape."

ATTEMPTS = 3
"""Documents one run may emit before a refusal ends it."""

FEEDBACK = """The validator refused that document:
{why}
Read the report again with this in mind. Look up what you need, ask the user
if only they know it, then emit the document again."""
"""What a refusal is turned into, on its way back to the model."""


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
    attempts: int
    refusals: list[tuple[plans.Violation, ...]]
    """What each emitted document broke, in order, and nothing for one that stood: the record's `attempts`."""

    refused: str | None
    """What `log.validate` said about the document, or nothing when it passed.

    An outcome of the run and not an exception: a report is a fact and is
    never refused for what the user did, and every refusal here is about the
    document -- a typo, a provenance that cannot be true, an exclusion naming
    nothing.
    """

    finished: bool
    """The model called `done_reading` this turn: the document is next."""

    confirmed: bool
    """Whether the exclusion the document proposes is the user's. False until
    they say so, and nothing writes one before that (ADR-0004)."""

    timings: list[tuple[str, str, str, float, str, str]]


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
        "attempts": 0,
        "refusals": [],
        "refused": None,
        "finished": False,
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
    finishing = {"type": "function", "function": tools.schema(done_reading)}
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
        definitions.append(finishing)
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
        finished = False
        for call in reply.tool_calls:
            call_id = answered(call)
            if call["name"] == done_reading.__name__:
                finished = True
                answers.append(
                    ToolMessage(EMIT_LOG, tool_call_id=call_id, name=call["name"])
                )
                continue
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
            "finished": finished,
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
        attempts = state.get("attempts", 0) + 1
        performed: logs.PerformedWorkout | None = None
        violation: plans.Violation | None = None
        try:
            performed = logs.parse(document.text)
            with tools.opened() as connection:
                logs.validate(connection, performed, state["today"])
        except logs.LogError as error:
            violation = plans.Violation(plans.SHAPE, str(error))
        except logs.LogRejected as error:
            violation = plans.Violation(VALIDATOR, str(error))
        refused = None if violation is None else violation.says
        decided: dict[str, Any] = {
            "document": performed,
            "refused": refused,
            "attempts": attempts,
            "refusals": [
                *state.get("refusals", []),
                () if violation is None else (violation,),
            ],
        }
        if refused is not None and attempts < ATTEMPTS:
            decided["finished"] = False
            decided["messages"] = [
                HumanMessage(FEEDBACK.format(why=refused), name="validator")
            ]
        elif refused is not None or performed is None or performed.proposed_exclusion is None:
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
        if state.get("finished") or state.get("spent", 0) >= budget:
            return "emit"
        return "logger"

    def after_validate(state: LoggerState) -> Literal["logger", "confirm", "done"]:
        performed = state.get("document")
        if state.get("refused") is not None:
            return "logger" if state.get("attempts", 0) < ATTEMPTS else "done"
        if performed is None:
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
        "validate",
        after_validate,
        {"logger": "logger", "confirm": "confirm", "done": END},
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
    return build(models.logger(), archive=records.archive())
