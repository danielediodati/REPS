"""The entrance: the node that talks, reaching the planner and the logger as tools (ADR-0006)."""

from __future__ import annotations

import operator
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from trainer import plan as plans
from trainer import tools
from trainer.coach import conclusions, models
from trainer.coach import record as records
from trainer.coach.calls import answered
from trainer.engine import catalog, mesocycles
from trainer.engine.exclusions import ExclusionError


def todays_workout() -> str:
    """Send the user today's workout, read off the mesocycle they accepted.

    Call this when they ask what to train, ask for today's workout, or say
    they are about to train. Which workout is due and what is in it are read
    for you, so this takes no arguments and you supply none of it.

    What comes back says whether there is a workout to send. When there is,
    it goes into the chat right after your message: say nothing about what is
    in it. When there is not, offer to plan a mesocycle.

    The body is never run. The graph answers this call by reading the mesocycle.
    """
    raise AssertionError("the graph answers todays_workout; nothing calls it")


def plan_mesocycle() -> str:
    """Plan a mesocycle and offer it to the user: a workout for each slot of
    their cycle, repeated for several cycles.

    Call this when they ask for a new mesocycle or programme, or say yes to
    your offer of one. What it is planned against is derived from what they
    declared, so this takes no arguments.

    Planning takes minutes. The call comes back at once and the mesocycle
    arrives in the chat by itself: your turn is to tell them you are on it,
    not to describe a mesocycle you have not seen.

    The body is never run. The graph answers this call by starting the planner
    behind the conversation.
    """
    raise AssertionError("the graph answers plan_mesocycle; nothing calls it")


def adapt_this_workout(said: str) -> str:
    """Plan this workout again from their mesocycle, for this workout only.

    Call this when what they want is this workout changed and the mesocycle
    left as it is: a different time, other equipment, an exercise out or in,
    another of the cycle's workouts, anything about today. `said` is what they
    asked for, in their own words: the planner reads it, and decides the rest.

    The adapted workout arrives in the chat by itself in a few minutes: tell
    them you are on it.

    The body is never run. The graph answers this call by starting the planner
    behind the conversation.
    """
    raise AssertionError("the graph answers adapt_this_workout; nothing calls it")


def change_mesocycle(said: str) -> str:
    """Rewrite their mesocycle for the cycles left, keeping the count already done.

    Call this when they want the mesocycle itself changed from now on: an
    exercise gone for good, a different emphasis, a different number of
    cycles. `said` is what they want changed, in their own words.

    The new mesocycle arrives in the chat by itself in a few minutes: tell
    them you are on it. When it does not start, what comes back says why.

    The body is never run. The graph answers this call by starting the planner
    behind the conversation.
    """
    raise AssertionError("the graph answers change_mesocycle; nothing calls it")


def change_declaration(said: str) -> str:
    """Change what they declared, from now on: equipment bought or gone, the
    minutes a workout lasts, their goal, their rotation.

    Call this when what changes is not today's workout or this mesocycle's
    exercises but what they have, how long they train, or what for, as in «ho
    preso una panca piana», «da adesso mi alleno un'ora», «passo alla
    forza». `said` is what they told you, in their own words.

    The interview that writes it down asks its own questions, and its first
    follows your message: tell them you are updating it.

    The body is never run. The graph answers this call by starting the interview
    behind the conversation.
    """
    raise AssertionError("the graph answers change_declaration; nothing calls it")


def log_workout() -> str:
    """Record the workout the user has just described, in their own words.

    Call this when they are reporting training that has already happened --
    what they did, how it went, what hurt. What they wrote reaches the logger
    exactly as they typed it, so this takes no arguments: never retell it,
    never translate it, never tidy it up.

    The body is never run. The graph answers this call by starting the logger
    behind the conversation.
    """
    raise AssertionError("the graph answers log_workout; nothing calls it")


def set_up() -> str:
    """Start the interview that sets up their training: their goal, their rotation, their time, their equipment.

    Call this when they ask to set up their training, or to start it again
    from the beginning. The interview asks its own questions, so this takes
    no arguments.

    The body is never run. The graph answers this call by starting the interview
    behind the conversation.
    """
    raise AssertionError("the graph answers set_up; nothing calls it")


TODAYS_WORKOUT = todays_workout.__name__
PLAN_MESOCYCLE = plan_mesocycle.__name__
ADAPT_THIS_WORKOUT = adapt_this_workout.__name__
CHANGE_MESOCYCLE = change_mesocycle.__name__
CHANGE_DECLARATION = change_declaration.__name__
LOG_WORKOUT = log_workout.__name__
SET_UP = set_up.__name__

HANDOFFS = (
    todays_workout,
    plan_mesocycle,
    adapt_this_workout,
    change_mesocycle,
    change_declaration,
    log_workout,
    set_up,
)
"""What the entrance hands on, on the same surface as the reads (ADR-0006, item 2)."""

CARRIED = (PLAN_MESOCYCLE, ADAPT_THIS_WORKOUT, CHANGE_MESOCYCLE, CHANGE_DECLARATION, LOG_WORKOUT, SET_UP)
"""The handoffs a subgraph carries on; the run of any other ends with the entrance's turn."""

CHECKED = (ADAPT_THIS_WORKOUT, CHANGE_MESOCYCLE)
"""The handoffs whose request is assembled before they start, so a misread goes back to the model."""

PLANS = (PLAN_MESOCYCLE, *CHECKED)
"""The handoffs that open a planner run: one called while a plan is written replaces it."""

WRITES = (LOG_WORKOUT, SET_UP, CHANGE_DECLARATION)
"""The handoffs that write what the planner reads: one called while a plan is written waits for it."""

SERVING = (
    "Today's workout is read off their mesocycle and goes into the chat right "
    "after your message. Tell them here it is, and say nothing about what is in it."
)

NO_MESOCYCLE = (
    "There is no workout to read: no mesocycle has been accepted, or the last "
    "one has run all its cycles. Tell them so and offer to plan one. Call "
    "`plan_mesocycle` only once they say yes."
)

WAITING_MESOCYCLE = (
    "Their mesocycle has run all its cycles, and the next one was prepared "
    "without them asking: it is in the chat, or arriving shortly. Tell them "
    "so, and that they accept it or turn it down there. Do not offer to plan "
    "another."
)

PREPARED = "prepared"
"""The handoff a turn takes instead when the next mesocycle is already waiting: it is offered again."""

UNREADABLE = (
    "Today's workout cannot be read: something on the machine needs fixing, "
    "and the next message says so. Tell them only that you could not read it."
)

MISREAD = (
    "That was not started: {error}. Call it again with that put right, or "
    "ask them what they meant."
)

STARTED = {
    PLAN_MESOCYCLE: (
        "The planner has started on a mesocycle. Tell the user you are putting "
        "it together and that it will arrive shortly. You have not seen it, so "
        "say nothing about what is in it."
    ),
    ADAPT_THIS_WORKOUT: (
        "The planner has started adapting this workout; the mesocycle stays "
        "as it is. Tell them you are on it and that it will arrive shortly. You "
        "have not seen it, so say nothing about what is in it."
    ),
    CHANGE_MESOCYCLE: (
        "The planner has started rewriting the mesocycle for the cycles left. "
        "Tell them you are on it and that it will arrive shortly. You have not "
        "seen it, so say nothing about what is in it."
    ),
    LOG_WORKOUT: (
        "The logger has started reading what they wrote. Tell them you are "
        "writing it down. You have not read it back yet, so do not repeat any "
        "of it to them as fact."
    ),
    SET_UP: (
        "The interview that sets up their training has started, and its first "
        "question follows your message. Tell them you will ask a few things to "
        "set it up. Ask nothing yourself."
    ),
    CHANGE_DECLARATION: (
        "The interview that updates what they declared has started, and what it "
        "says follows your message. Tell them you are updating it. Ask nothing "
        "yourself."
    ),
}
"""What a handoff call is answered with: not words for the user, but what the
model is told so it can find its own."""

MID_PLAN = """

Right now the planner is still writing what they asked for before. If this
message corrects that ask, or asks for something else to be planned, call the
handoff for the ask as it now stands, whole: the plan being written is dropped
for it. If it is a question, answer it; the plan carries on. If they are
reporting training or changing what they declared, call that handoff: it is
done once the plan arrives."""
"""What the prompt adds while a plan is being written on the thread."""

REPLACING = "The plan that was being written is dropped for this one. "
"""What a planning handoff's answer opens with while a plan is being written."""

AFTER_THE_PLAN = (
    "That waits for the plan being written, and is done as soon as it arrives. "
    "Tell them so."
)

ONE_AT_A_TIME = (
    "That one was not started: one thing at a time, and the first call of this "
    "turn is what is running. Say only what that one is doing."
)

SPENT = (
    "You have no tool calls left. Answer with what you know, and say you do "
    "not know the rest rather than filling it in."
)
"""What a read past the budget is answered with, the way the logger answers a
question past its own (`logger.SPENT_ASKING`)."""

TOOLS = (
    "pattern_history",
    "last_performed_load",
    "adherence_history",
    "volume_deficit",
    "unreported_workouts",
    "prescribed_workout",
    "due_workout",
    "search_exercises",
    "compare_variants",
)
"""The engine's reads, so a question about training is answered here.

Named rather than derived by subtraction, for the reason `planner.TOOLS` is.
`admissible_set`, `remaining_budget` and `allocate` are left out: they are the
arithmetic a plan is chosen with, and the entrance does not plan -- it hands
that to `plan_mesocycle` and never judges the answer (ADR-0006, item 4).
"""

KEEPS = ("id", "name", "equipment", "primary_muscles")
"""What talking about an exercise needs. `name` above all: the entrance answers
in prose, and an id read out loud is not an answer."""

TALKING = """\
You are the entrance to a training system, and the only part of it the user
talks to. You answer in Italian, in one or two sentences, the way a coach
texting back would -- never a list, never a form, never a wall of text.

Behind you is a deterministic engine over an exercise catalog and the training
state. It answers questions and never decides how to train, and nothing it
offers you writes anything down.

What a turn asks of you:

- They want something to train, now or today, as it is: call
  `todays_workout`. When they name something it should hold or not hold --
  an exercise, the time, the equipment -- read `due_workout` first: if
  today's workout is already what they ask, serve it; if not, it is this
  workout changed, below.
- They ask for a new mesocycle, or say yes when you offered one: call
  `plan_mesocycle`.
- They are telling you about training they have already done: call
  `log_workout`.
- They want to set up their training, or start it again from the beginning:
  call `set_up`.
- They ask something the tools above can answer -- how much of a muscle group
  this cycle, what they lifted last time, whether a workout is still
  unreported: call the tool and answer from what came back.
- Anything else -- hello, a question about how this works, a remark -- is
  yours to answer directly.

When they want something changed, the question is how long for:

- **This workout only** -- another time, other equipment, an exercise out or
  in, another of the cycle's workouts, as in «oggi ho solo mezz'ora», «in
  hotel ho solo un elastico», «oggi niente petto»: call `adapt_this_workout`
  with their words. The planner decides what the workout is.
- **The mesocycle, from now on** -- an exercise gone for good, a different
  emphasis, as in «d'ora in poi niente stacchi» or «i dip non li
  voglio più vedere»: call `change_mesocycle`.
- **What they declared, for good** -- equipment bought or gone, the minutes
  from now on, a new goal, as in «ho preso una panca piana» or «da adesso mi
  alleno un'ora»: call `change_declaration`.
- **When you cannot tell** whether they mean this workout or from now on, as
  in «niente panca» or «ho solo 30 minuti», ask them which, in one sentence,
  and call nothing. Their answer, next turn, is what you act on.
- **A dislike with nothing asked**, as in «detesto il rematore», changes nothing
  yet: remember it, and you may ask whether they want it out.
- **An ache or a pain**, as in «il ginocchio mi tira sugli squat», starts nothing: ask
  them about it, in one question -- where, and doing what.

Remembering, when `remember` is offered:

- Something lasting they tell you about themselves -- what they like, what
  they cannot stand, what they own, what their body does -- is worth
  keeping: «la cyclette mi annoia», «ho comprato i manubri». Call `remember`
  beside whatever else the turn needs.
- What is true only today is not: «oggi sono distrutto», «oggi la cyclette
  mi ha annoiato». No rule tells the two apart; you do.
- `quote` is their sentence exactly as they typed it; anything else is
  refused. Never remember what you inferred, only what they said.

What you may never do:

- **State a training fact no tool gave you.** Not a load, not a number of
  sets, not how much of a muscle group they have done, not what they trained
  last. If no tool answered it, say you do not know and offer to look.
- **Decide which workout is due.** That is the rotation, read off what has been
  performed, and `todays_workout` reads it for you. When they ask for another
  of the cycle's, `adapt_this_workout` takes it.
- **Judge whether a plan fits.** That is the validator's, and it has already
  refused plans you would have accepted.
- Invent an exercise, an id or a date.

One call per turn is enough. When you have what you need, answer.
"""

RELAYING = """\
Something has just happened, and you are the one who tells the user about it.
Say it to them in Italian, in one or two sentences, in your own words. Say
nothing this does not say -- above all no numbers and no exercise names.

{situation}"""
"""How a thing that happened is put to the model.

The words here are instructions and never what the user reads: what reaches
the chat is the model's own sentence, which is the whole of ADR-0006. A branch
whose words are written in advance is the router this replaced.
"""

HELLO = (
    "The user has just opened the chat, or sent /start. Introduce yourself as "
    "their trainer in one line and tell them they can write to you whenever "
    "they like, in their own words."
)

QUEUED = (
    "They have written again while you are still working on what they asked "
    "for before. Tell them you are still on the previous one and will come to "
    "this straight after."
)

PRESCRIBED = (
    "They accepted the workout you offered, and it is now written down as "
    "today's. Tell them it is theirs and wish them a good session."
)

SUPERSEDED = (
    "They tapped a button on a plan the conversation has already moved past, "
    "so there was nothing to answer. Tell them that plan is no longer the one "
    "in hand and that writing to you again gets them another."
)

NO_PLAN = (
    "You could not reach a plan that fits their constraints: every attempt "
    "was refused by the rules. Tell them so plainly, without blaming "
    "anything, and invite them to write again."
)

KEPT = (
    "They accepted the mesocycle you offered, and it is kept. Tell them it is "
    "theirs, and that asking what to train gets them today's workout from it."
)

LOGGED = (
    "The workout they reported has been written down. Tell them it is "
    "recorded."
)

NEXT_MESOCYCLE = (
    "That workout was the last of their mesocycle's cycles, and you have "
    "planned the next one without being asked: it follows this message. Tell "
    "them so, and in one sentence what the new one is about and why, from its "
    "direction below. Say nothing else about what is in it.\n"
    "Theme: {theme}\n"
    "What changes: {changes}\n"
    "Why: {why}"
)

ONBOARDED = (
    "The interview is over and what they told you is written down. You are "
    "planning their first mesocycle now, and it follows shortly. Tell them so, "
    "and say nothing about what is in it."
)

DECLARED = (
    "What they told you has changed is written down, and no mesocycle is "
    "running: the next one is planned from it. Tell them so."
)

NOT_LOGGED = (
    "What they reported could not be turned into a workout the engine will "
    "accept, so nothing was written. Tell them it did not go through and ask "
    "them to tell you again in their own words."
)

SITUATIONS = (
    HELLO,
    QUEUED,
    PRESCRIBED,
    KEPT,
    SUPERSEDED,
    NO_PLAN,
    LOGGED,
    NOT_LOGGED,
    NEXT_MESOCYCLE,
    ONBOARDED,
    DECLARED,
)
"""Everything the machine can ask the entrance to say.

Enumerated so a test can put each of them to a stand-in: every one of them was
a fixed Italian line before this, and the thing that must not come back is a
situation nobody can say.
"""


class EntranceState(TypedDict, total=False):
    said: Annotated[list[str], operator.add]
    """What the user has written on this thread, in the order they wrote it."""

    messages: Annotated[list[AnyMessage], add_messages]
    """The conversation, kept across runs.

    Unlike either subgraph's, which is a working history one run long and is
    cleared when the next starts. This is the conversation itself: the entrance
    is the only node that remembers the turn before.
    """

    negotiation: str
    run: str
    follows: str | None
    began: str
    ended: str
    ending: str

    spent: int
    budget: int
    timings: list[tuple[str, str, str, float, str, str]]

    relaying: str
    """The situation this turn was opened to say, and empty when the user spoke."""

    handoff: str
    """Which subgraph this turn reached for, and empty when it answered itself."""

    asked: dict[str, Any]
    """The arguments the handoff was called with: what an adaptation or a change was asked."""

    answer: str
    """What goes into the chat. The model's sentence, never a constant."""


def heard(text: str) -> EntranceState:
    """The input that starts a turn: what the user wrote, onto the thread's own history."""
    return _beginning() | {"said": [text], "messages": [HumanMessage(text)]}


def relayed(situation: str) -> EntranceState:
    """The input that starts a turn the machine opened: one thing that happened, to be said."""
    return _beginning() | {"relaying": situation}


def _beginning() -> EntranceState:
    """A run of the entrance, with what the run before it left cleared.

    `messages` and `said` are what it leaves alone: one is the conversation and
    the other is what the user has written on this thread, and both outlive
    every run on it (ADR-0006).
    """
    return {
        **records.identity(records.negotiation_id(), None),  # type: ignore[typeddict-item]
        "spent": 0,
        "timings": [],
        "relaying": "",
        "handoff": "",
        "asked": {},
        "answer": "",
    }


def carried(final: Mapping[str, Any]) -> dict[str, Any]:
    """What the entrance hands the subgraph it opened: the run it began, and its seconds.

    One run and not two. The user asked once, so what they asked is one run
    (ADR-0007), and the entrance is its first node -- which is what makes the
    run document name the entrance's model on the entrance's node and the
    subgraph's on the rest.
    """
    return {
        "negotiation": str(final.get("negotiation", "")),
        "run": str(final.get("run", "")),
        "follows": final.get("follows"),
        "began": str(final.get("began", "")),
        "ended": "",
        "ending": "",
        "timings": list(final.get("timings", ())),
    }


Entrance = CompiledStateGraph[EntranceState, None, EntranceState, EntranceState]
"""The compiled graph, as `build` returns it."""


def build(
    on: models.Chat,
    budget: int = tools.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
    today: Callable[[], str] | None = None,
    checking: Callable[[str, Mapping[str, Any]], str | None] | None = None,
    prepared: Callable[[str], bool] | None = None,
    store: BaseStore | None = None,
    planning: Callable[[str], bool] | None = None,
) -> Entrance:
    """The compiled entrance graph, talking on `on`; `today` answers `todays_workout`.

    `checking` says why a `CHECKED` handoff cannot start, or `None` when it can.
    `prepared` says whether the next mesocycle is waiting, or being prepared, on a thread.
    `planning` says whether a plan the user asked for is being written on a thread.
    `store` is where `remember` keeps a conclusion; without one it is not offered.

    **Nothing here writes, and nothing here plans.** The reads answer questions
    about what has been trained; everything else is handed to a subgraph, which
    the caller runs once this turn has been answered (ADR-0006, item 6).
    """
    model = on.model
    offered = tools.registered("entrance", TOOLS)
    reads = [{"type": "function", "function": tools.schema(tool)} for tool in offered]
    if store is not None:
        reads.append({"type": "function", "function": tools.schema(conclusions.remember)})
    timed = records.timing(on)
    looked_up = today if today is not None else reading_today
    checked = checking if checking is not None else startable
    free = [
        {"type": "function", "function": tools.schema(tool)}
        for tool in HANDOFFS
        if tool.__name__ not in CHECKED
    ]
    bounded = [
        {"type": "function", "function": tools.schema(tool)}
        for tool in HANDOFFS
        if tool.__name__ in CHECKED
    ]

    def on_thread(asks: Callable[[str], bool] | None) -> bool:
        thread = get_config().get("configurable", {}).get("thread_id")
        return asks is not None and thread is not None and asks(str(thread))

    def talk(state: EntranceState) -> dict[str, Any]:
        """One turn of the conversation, with the tools bound only while they are still useful.

        The system prompt is prepended rather than stored, because this history
        is never cleared: kept in it, the words the entrance works to would be
        whatever they were on the day the thread started.
        """
        born = records.born(state)
        situation = state.get("relaying", "")
        asked = (
            [HumanMessage(RELAYING.format(situation=situation), name="machine")]
            if situation
            else []
        )
        definitions: list[dict[str, Any]] = []
        if not situation and not state.get("handoff"):
            # A turn that has already reached for a subgraph, and a turn opened
            # to say one thing, both have nothing left to do but speak. Bound
            # anyway, a model that calls a tool there is a second handoff on a
            # turn that has one, or a tool call answering nobody.
            # A checked handoff can be refused and called again, so it is
            # bounded like a read; the others always start.
            within = state.get("spent", 0) < budget
            definitions = [*(reads + bounded if within else []), *free]
        bound = model.bind_tools(definitions) if definitions else model
        prompt = TALKING + (MID_PLAN if not situation and on_thread(planning) else "")
        reply = bound.invoke([SystemMessage(prompt), *state.get("messages", []), *asked])
        return born | {"budget": budget, "messages": [*asked, reply]}

    def read(state: EntranceState) -> dict[str, Any]:
        """The turn's reads, run -- unless the budget they were taken off the
        table for has already gone.

        The bound is kept here as well as in `talk`, because the two are not
        the same guarantee: `talk` stops *offering* the reads and this stops
        *running* them. A model that calls a tool it was not offered would
        otherwise spend the surface past its budget, one turn at a time, and
        the only thing to end the run would be LangGraph's recursion limit.
        """
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        spent = state.get("spent", 0)
        if spent >= budget:
            return {
                "messages": [
                    ToolMessage(SPENT, tool_call_id=answered(call), name=call["name"])
                    for call in reply.tool_calls
                ]
            }
        answers = [answering(call, state) for call in reply.tool_calls]
        return {"messages": answers, "spent": spent + len(answers)}

    def answering(call: ToolCall, state: EntranceState) -> ToolMessage:
        """A call that is not a handoff: a conclusion to keep, or an engine read."""
        if call["name"] != conclusions.REMEMBER or store is None:
            return _answer(call, offered)
        said, refused = conclusions.kept(
            store,
            conclusions.whose(),
            call["args"],
            state.get("said", []),
            date.today().isoformat(),
        )
        return ToolMessage(
            said,
            tool_call_id=answered(call),
            name=call["name"],
            status="error" if refused else "success",
        )

    def hand_off(state: EntranceState) -> dict[str, Any]:
        """The turn that reached for a subgraph: which one, and every call in it answered.

        Every call, because a turn carrying a read beside the handoff still has
        to come back whole -- a tool call left without its answer is a history
        the next turn is refused on.
        """
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        taken = ""
        asked: dict[str, Any] = {}
        answers: list[AnyMessage] = []
        spent = 0

        def waiting() -> bool:
            return on_thread(prepared)

        mid_plan = on_thread(planning)

        def started(name: str) -> str:
            if not mid_plan:
                return STARTED[name]
            if name in WRITES:
                return AFTER_THE_PLAN
            return REPLACING + STARTED[name]

        for call in reply.tool_calls:
            name = call["name"]
            if name not in HANDED:
                spent += 1
                answers.append(answering(call, state))
                continue
            if taken:
                said = ONE_AT_A_TIME
            elif name == TODAYS_WORKOUT:
                said, taken = looked_up(), name
                if said == NO_MESOCYCLE and waiting():
                    said, taken = WAITING_MESOCYCLE, PREPARED
            elif name == PLAN_MESOCYCLE and waiting():
                said, taken = WAITING_MESOCYCLE, PREPARED
            elif name not in CHECKED:
                said, taken = started(name), name
            elif state.get("spent", 0) + spent >= budget:
                said = SPENT
            else:
                refused = checked(name, call["args"])
                if refused is None:
                    said, taken, asked = started(name), name, dict(call["args"])
                elif refused == NO_MESOCYCLE and waiting():
                    said, taken = WAITING_MESOCYCLE, PREPARED
                else:
                    said, spent = refused, spent + 1
            answers.append(ToolMessage(said, tool_call_id=answered(call), name=name))
        return {
            "messages": answers,
            "handoff": taken,
            "asked": asked,
            "spent": state.get("spent", 0) + spent,
        }

    def answer(state: EntranceState) -> dict[str, Any]:
        """What the chat is told, and the run closed unless a subgraph is carrying it on."""
        reply = state["messages"][-1]
        said = reply.text.strip() if isinstance(reply, AIMessage) else ""
        decided: dict[str, Any] = {"answer": said}
        if state.get("handoff") not in CARRIED:
            decided.update(
                records.closing({**state, **decided}, records.DONE, budget, archive)
            )
        return decided

    def after_talk(state: EntranceState) -> Literal["reads", "handoff", "answer"]:
        reply = state["messages"][-1]
        if state.get("handoff") or not isinstance(reply, AIMessage):
            return "answer"
        called = {call["name"] for call in reply.tool_calls}
        if called & HANDED:
            return "handoff"
        return "reads" if called else "answer"

    graph = StateGraph(EntranceState)
    graph.add_node("entrance", timed("entrance", talk))
    graph.add_node("reads", timed("reads", read))
    graph.add_node("handoff", timed("handoff", hand_off))
    graph.add_node("answer", timed("answer", answer))
    graph.add_edge(START, "entrance")
    graph.add_conditional_edges("entrance", after_talk)
    graph.add_edge("reads", "entrance")
    graph.add_edge("handoff", "entrance")
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer)


HANDED = {handoff.__name__ for handoff in HANDOFFS}


def reading_today() -> str:
    """Whether there is a workout to serve today, as the entrance is told it."""
    try:
        with tools.reported(), tools.opened() as connection:
            try:
                mesocycles.today(connection)
            except mesocycles.MesocycleError:
                return NO_MESOCYCLE
    except tools.ToolFailure:
        return UNREADABLE
    return SERVING


MISREADS = (
    ExclusionError,
    plans.PlanRejected,
    TypeError,
    ValueError,
)
"""What a request refuses because the model misread the user, beside the unknown value `startable` names first."""


def startable(handoff: str, asked: Mapping[str, Any]) -> str | None:
    """Why this adaptation or change cannot start, as the entrance is told it, or `None`."""
    try:
        with tools.reported(), tools.opened() as connection:
            try:
                requested(connection, handoff, asked)
            except mesocycles.MesocycleError:
                return NO_MESOCYCLE
            except catalog.UnknownFilterValue as error:
                return MISREAD.format(
                    error=f"{error}; the catalog has {', '.join(error.valid)}"
                )
            except MISREADS as error:
                return MISREAD.format(error=error)
    except tools.ToolFailure:
        return UNREADABLE
    return None


def requested(
    connection: sqlite3.Connection, handoff: str, asked: Mapping[str, Any]
) -> plans.Request | plans.MesocycleRequest:
    """The request an adaptation or a change hands the planner, off the arguments it was called with."""
    today = date.today().isoformat()
    said = str(asked.get("said", ""))
    if handoff == CHANGE_MESOCYCLE:
        return plans.change_requested(connection, today, said=said)
    return plans.adaptation_requested(connection, today, said=said)


def _answer(
    call: ToolCall, offered: Sequence[Callable[..., Any]]
) -> ToolMessage:
    """One engine read, run and handed back."""
    call_id = answered(call)
    result = tools.execute(
        tools.Call(id=call_id, name=call["name"], arguments=call["args"]),
        offered,
        KEEPS,
    )
    return ToolMessage(
        result.content,
        tool_call_id=call_id,
        name=call["name"],
        status="error" if result.failed else "success",
    )


def studio() -> Entrance:
    """The entrance on the model `ENTRANCE_MODEL` names, as `langgraph dev` serves it."""
    return build(models.entrance(), archive=records.archive())
