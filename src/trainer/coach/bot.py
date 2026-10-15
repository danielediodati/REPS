"""The Telegram bot: long-polls from the graph's process, and answers only the owner."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import threading
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from langgraph.types import Command

from trainer import log as logs
from trainer import plan as plans
from trainer import tools
from trainer.coach import (
    conclusions,
    entrance,
    language,
    logfile,
    models,
    onboarding,
    planner,
    progress,
)
from trainer.coach import negotiation as negotiations
from trainer.coach import logger as logger_graph
from trainer.coach import record as run_record
from trainer.coach import supervisor as supervisor_graph
from trainer.engine import config, mesocycles, workouts

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import Application, ContextTypes

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
OWNER_ENV = "TELEGRAM_OWNER_ID"

EXAMPLE = ".env.example"
"""Where both settings are documented, named by every state that misses one."""

logger = logging.getLogger(__name__)

class BotError(RuntimeError):
    """A Telegram setting the environment gets wrong, stated with its fix."""


@dataclass(frozen=True)
class Settings:
    """The two things the bot cannot start without."""

    token: str
    owner_id: int


def settings() -> Settings:
    """The bot's settings, from the environment.

    Never from the declarations, which hold what the user declares about
    their training (ADR-0013). A token is a credential and an owner id is
    about this installation, and neither is a training requirement.
    """
    return Settings(token=_required(TOKEN_ENV), owner_id=_owner())


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BotError(f"{name} is not set; put it in .env (copy {EXAMPLE})")
    return value


def _owner() -> int:
    """The owner's user id, refusing the handle somebody will reach for instead.

    A username is the name you know yourself by and the id is the number
    Telegram knows you by. Left to `int` this arrives as a ValueError about
    base 10, which names neither the variable nor where the number comes from.
    """
    declared = _required(OWNER_ENV)
    try:
        return int(declared)
    except ValueError:
        raise BotError(
            f"{OWNER_ENV} is {declared!r}, which is not a user id: it is the "
            f"number @userinfobot replies with, not a username. See {EXAMPLE}"
        ) from None


REFUSED_TOKEN = (
    f"the {TOKEN_ENV} in .env is not one Telegram knows; @BotFather issued it "
    "and can show it again (send it /mybots)"
)


def identified(declared: Settings) -> str:
    """The bot's @name, as Telegram answers for the token, or the state that stops it."""
    return asyncio.run(_identified(declared.token))


async def _identified(token: str) -> str:
    from telegram import Bot
    from telegram.error import InvalidToken, NetworkError, TelegramError

    try:
        # `async with`, because `shutdown` closes the client only after `initialize`.
        async with Bot(token) as telegram:
            me = await telegram.get_me()
    except InvalidToken:
        # `from None`: the library's own message quotes the token.
        raise BotError(REFUSED_TOKEN) from None
    except NetworkError as error:
        raise BotError(
            f"Telegram cannot be reached ({error}); check the connection and "
            "start the bot again"
        ) from None
    except TelegramError as error:
        raise BotError(
            f"Telegram would not answer for the bot ({error}); start it again later"
        ) from None
    return f"@{me.username}"


def thread_for(chat_id: int) -> str:
    """One chat is one thread (ADR-0004, item 6).

    Derived from the chat id rather than invented per run, which is what lets
    the conversation survive a restart: the checkpointer is on disk, and the
    next process computes the same thread id for the same chat.

    This one is the entrance's -- the conversation itself. The subgraphs it
    opens run on threads of their own, named off this one by `under`.
    """
    return f"chat:{chat_id}"


PLANNING = "plan"
LOGGING = "log"
ONBOARDING = "onboard"
SUPERVISING = "supervise"


def under(thread: str, graph: str) -> str:
    """One of a chat's subgraph threads, derived from the chat's own.

    Three graphs on one thread id would write three states into one
    checkpoint, and every one of them has a channel called `messages`: on the
    entrance it is the conversation and on either subgraph a working history
    one run long. Derived rather than minted, for the reason `thread_for` is:
    the next process computes the same names for the same chat, so a plan
    offered before a restart is still answerable after it.
    """
    return f"{thread}/{graph}"


KEPT = "ok"
TURNED_DOWN = "no"

CONFIRMED = "y"
DECLINED = "n"

BUTTONS = (KEPT, TURNED_DOWN)
"""The two answers a proposed plan takes; anything else is asked in words."""

CONFIRM = (CONFIRMED, DECLINED)
"""The two answers the exclusion the logger proposes takes.

A closed question, which is what the payload says it is: the terminal reads
the same two answers as a prompt (`cli._confirmed`), and here they are the
buttons that shape.
"""

ACTIONS = {*BUTTONS, *CONFIRM}
"""Every action a callback may carry, so one tap is recognised and no other is."""

def labelled(actions: Sequence[str], spoken: language.Language) -> list[tuple[str, str]]:
    """Each action with the label its button shows in `spoken`."""
    said = language.texts(spoken).buttons
    labels = {
        KEPT: said.kept,
        TURNED_DOWN: said.turned_down,
        CONFIRMED: said.confirmed,
        DECLINED: said.declined,
    }
    return [(action, labels[action]) for action in actions]


SEPARATOR = "|"


@dataclass(frozen=True)
class Tap:
    """One button pressed: which answer, on which thread, to which proposal."""

    action: str
    thread: str
    proposal: str


def carried(tap: Tap) -> str:
    """What a button carries back, inside Telegram's 64 bytes.

    The thread goes in it so a tap always finds its run, and the proposal is
    the id of the interrupt it answers -- which is what makes a tap on a plan
    the thread has moved past recognisable as one.
    """
    return SEPARATOR.join((tap.action, tap.thread, tap.proposal))


def tap_of(data: str) -> Tap | None:
    """The tap a callback carries, or nothing when it is not one of ours."""
    action, _, rest = data.partition(SEPARATOR)
    thread, _, proposal = rest.partition(SEPARATOR)
    if action not in ACTIONS or not thread or not proposal:
        logger.info("ignored a callback carrying %r", data)
        return None
    return Tap(action=action, thread=thread, proposal=proposal)


Say = Callable[[str], Awaitable[None]]
"""One line into the chat. The bot's side of a conversation, as a function, so
what decides can be driven by a test that collects the lines instead of sending
them."""

Offer = Callable[[str, Sequence[tuple[str, str]]], Awaitable[None]]
"""A plan with its buttons: the text, and (callback data, label) pairs.
Telegram's own objects are built in `_offering`, so what decides stays as
testable as the rest."""

Draft = Callable[[str], Awaitable[None]]
"""The run's progress, re-sent in place while it works.

Ephemeral, about thirty seconds, so what goes down it is the phase the run is
in, one line: a draft is not a transcript and nothing that has to survive the
run may go this way.
"""


@dataclass(frozen=True)
class Chat:
    """The three channels one conversation is answered on.

    One object rather than three parameters, because they belong to the same
    chat and are always passed together -- a queued turn carries them, and a
    queue drained down somebody else's channels answers the wrong
    conversation.

    `draft` is separate from `say` although both write to the same chat: a
    line said stays, and a draft is a thirty-second preview of a run that has
    not finished. Telling them apart is what stops progress from being what
    the chat is left holding.
    """

    say: Say
    offer: Offer
    draft: Draft
    language: language.Language = language.ITALIAN


Run = Callable[[str, str, Chat], Awaitable[None]]
"""The work one message causes, on one thread: `talking` below."""

Resume = Callable[[str, "Tap", Chat], Awaitable[None]]
"""The work one tap causes: it answers the interrupt a run is waiting on."""

Relay = Callable[[str, str, Chat], Awaitable[None]]
"""One thing that happened, said on this thread in the entrance's own words.

The machine names the situation; the sentence is the model's (ADR-0006). Its
own type because the turn-taking says three of them -- hello, *in coda*, and
whatever a run it is holding could not say for itself -- and none of those is
a run.
"""

@dataclass(frozen=True)
class Later:
    """Work a message decided on while the thread was busy, run once the turn in flight is done."""

    work: Callable[[Chat], Awaitable[None]]
    first: bool = False
    """Ahead of what is already queued: the run that replaces a stopped one."""


Turn = str | Tap | Later
"""One piece of work on a thread: something the user wrote, a button they tapped, or work already decided."""

Interject = Callable[[str, str, Chat], Awaitable[str | Later | None]]
"""A message arriving while the thread is busy, read now: answered (`None`), work for later, or the text to queue."""

Waiting = tuple[Turn, Chat]
"""A turn queued behind a run, with the chat it arrived on."""


@dataclass
class _Conversation:
    """One chat's turn-taking: whether a run is in flight, and what arrived during it."""

    busy: bool = False
    waiting: list[Waiting] = field(default_factory=list)


class Turns:
    """One run at a time per thread, for the owner and nobody else.

    The turn-taking and nothing else. It was `Coach` until ADR-0006, which
    needed the word for the node that does the coaching: what this holds is
    whether the thread is busy and what arrived while it was. A message that
    arrives meanwhile goes to `interject` first, which may answer it, stop the
    run in flight, or hand it back to be queued.
    """

    def __init__(
        self,
        owner_id: int,
        run: Run,
        resume: Resume | None = None,
        relay: Relay | None = None,
        interject: Interject | None = None,
    ) -> None:
        self._owner_id = owner_id
        self._run = run
        self._resume = resume
        self._relay = relay
        self._interject = interject
        self._threads: dict[str, _Conversation] = {}

    async def started(self, user_id: int, chat_id: int, chat: Chat) -> None:
        """Answer `/start`, if the owner sent it.

        Outside the queue, and on purpose: saying hello must not wait out the
        four minutes a plan takes. Two entrance turns never overlap even so --
        the graph is serialised per thread where it is invoked.
        """
        if not self._answers(user_id):
            return
        await self._relayed(thread_for(chat_id), chat, entrance.HELLO)

    async def arriving(
        self, user_id: int, chat_id: int, text: str, chat: Chat
    ) -> None:
        """One message, run now, or read while the run in flight goes on.

        Never a second run on the same thread: what `interject` hands back is
        queued behind the one in flight, or ahead of the queue when it replaces
        a run it stopped.
        """
        if not self._answers(user_id):
            return
        await self._turn(thread_for(chat_id), text, chat)

    async def tapped(
        self, user_id: int, chat_id: int, data: str, chat: Chat
    ) -> None:
        """One button, on the thread it names rather than on the chat it came from.

        A tap is work like any other -- a refusal plans the whole workout again
        -- so it goes through the same queue, and the thread it resumes is the
        one the button carried. The two are the same today, and a plan sent on
        to somebody else is what would make them differ.
        """
        if not self._answers(user_id):
            return
        tap = tap_of(data)
        if tap is None:
            return
        await self._turn(tap.thread, tap, chat)

    async def _turn(self, thread: str, turn: Turn, chat: Chat) -> None:
        conversation = self._threads.setdefault(thread, _Conversation())
        if conversation.busy and isinstance(turn, str) and self._interject is not None:
            decided = await self._interjected(thread, turn, chat)
            if decided is None:
                return
            if isinstance(decided, Later):
                if not conversation.busy:
                    # The run it was read against ended while it was read.
                    await self._turn(thread, decided, chat)
                elif decided.first:
                    conversation.waiting.insert(0, (decided, chat))
                else:
                    conversation.waiting.append((decided, chat))
                return
            if not conversation.busy:
                await self._turn(thread, decided, chat)
                return
        if conversation.busy:
            # Queued before the acknowledgement is attempted, not after: a chat
            # that cannot be written to must not also cost the message.
            conversation.waiting.append((turn, chat))
            await self._relayed(thread, chat, entrance.QUEUED)
            return

        conversation.busy = True
        try:
            queued: Waiting | None = (turn, chat)
            while queued is not None:
                await self._attempt(thread, *queued)
                queued = conversation.waiting.pop(0) if conversation.waiting else None
        finally:
            # A run that raised must not leave the thread busy, or every later
            # message is answered with *in coda* by a bot with nothing running.
            conversation.busy = False
            # The queue goes with it, and only ever abnormally: the loop above
            # ends when there is nothing left. Reaching here with something
            # still queued means the chat itself could not be written to, and a
            # message promised *subito dopo* that then runs after whatever the
            # user said next is answered against a context that is no longer
            # its own -- worse than one dropped with a line saying so.
            if conversation.waiting:
                logger.warning(
                    "dropped %d queued message(s) on %s",
                    len(conversation.waiting),
                    thread,
                )
                conversation.waiting.clear()

    async def _attempt(self, thread: str, turn: Turn, chat: Chat) -> None:
        """One run, with its failure said out loud instead of left as silence.

        Caught per message rather than around the queue: one run that fell over
        must not cancel the messages behind it, which were promised an answer.
        """
        try:
            if isinstance(turn, Tap):
                assert self._resume is not None, "a tap reached a coach with no graph"
                await self._resume(thread, turn, chat)
            elif isinstance(turn, Later):
                await turn.work(chat)
            else:
                await self._run(thread, turn, chat)
        except Exception:
            logger.exception("the run on %s failed", thread)
            await self._tell(thread, chat, _said(chat).failed)

    async def _interjected(self, thread: str, text: str, chat: Chat) -> str | Later | None:
        """The message read while the thread is busy, with its failure said instead of raised."""
        assert self._interject is not None
        try:
            return await self._interject(thread, text, chat)
        except Exception:
            logger.exception("the message mid-run on %s failed", thread)
            await self._tell(thread, chat, _said(chat).failed)
            return None

    async def _tell(self, thread: str, chat: Chat, line: str) -> None:
        """One line into the chat, whose failure is never the caller's problem.

        The first failure this met outside the tests was a timeout reaching
        Telegram from inside `say` itself. Telling the user *it went wrong*
        then goes down the channel that has just gone wrong, raises again, and
        leaves `arriving` -- taking the queue with it, which is the one thing
        catching per message exists to prevent. There is no answering a chat
        that cannot be written to; there is only staying alive for the next
        message, and leaving a line in the log for whoever reads it.
        """
        try:
            await chat.say(line)
        except Exception:
            logger.exception("could not write to %s", thread)

    async def _relayed(self, thread: str, chat: Chat, situation: str) -> None:
        """One thing that happened, said by the entrance, whose failure is nobody's problem.

        The rule `_tell` keeps, with one more way to go wrong in front of it:
        the sentence has to be generated before it can be sent, and a model
        that is not there must not take the update handler down with it. That
        is the case ADR-0006 item 5 leaves a constant for.
        """
        assert self._relay is not None, "a situation reached the turn-taking with no entrance"
        try:
            await self._relay(thread, situation, chat)
        except Exception:
            logger.exception("the entrance could not speak on %s", thread)
            await self._tell(thread, chat, _said(chat).failed)

    def _answers(self, user_id: int) -> bool:
        """Whether this is the owner, checked before anything looks at the message."""
        if user_id == self._owner_id:
            return True
        logger.info("ignored an update from user %s", user_id)
        return False


@dataclass(frozen=True)
class Graphs:
    """The three graphs one chat is answered by, and where their runs are kept.

    One object rather than three parameters and a path, because every door
    below reaches for more than one of them: the entrance decides, a subgraph
    does the work, and the entrance says what came of it.
    """

    entrance: entrance.Entrance
    planner: planner.Planner
    logger: logger_graph.Logger
    onboarding: onboarding.Onboarding
    supervisor: supervisor_graph.Supervisor
    archive: Path
    talking: dict[str, asyncio.Lock] = field(default_factory=dict)
    """One lock per thread, so two turns never invoke the entrance on it at once.

    The queue in `Turns` serialises the *work* a chat causes, and this is the
    half it cannot. A message arriving mid-run is answered by the entrance
    saying so, and that sentence is itself a turn on the thread the run in
    flight is already talking on -- two invocations, one checkpoint.
    """

    preparing: set[str] = field(default_factory=set)
    """The planner threads whose next mesocycle is being prepared right now."""

    stopping: dict[str, threading.Event] = field(default_factory=dict)
    """The planner threads with a run in flight, each with the flag that stops it."""

    background: set[asyncio.Task[None]] = field(default_factory=set)
    """The preparations in flight, held so the loop does not drop them."""

    negotiation: negotiations.Negotiation = field(init=False)
    """The plan proposals on the planner, which the bot renders and never reads off its state."""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "negotiation",
            negotiations.Negotiation(
                self.planner,
                self.archive,
                supervisor=self.supervisor,
                preparing=self.preparing,
                stopping=self.stopping,
            ),
        )


def talking(graphs: Graphs) -> Run:
    """One message, answered by the entrance, which may hand it on to a subgraph.

    The turn is answered as soon as the entrance has spoken and the subgraph
    runs behind it (ADR-0006, item 6): a plan is minutes, and a chat that says
    nothing for four of them is the silence this replaces.

    What the entrance may decide is in ADR-0006 item 4, and the two things it
    is not asked are here: which workout is due comes from the rotation, read
    off the performed workouts by `plan.requested`, and which prescribed
    workout a report is filed against is resolved by `workouts.awaiting`.
    """

    async def run(thread: str, text: str, chat: Chat) -> None:
        if await asyncio.to_thread(_interviewing, graphs, thread):
            # Whatever the interview is waiting on, a message answers it.
            await _interview(graphs, thread, Command(resume=text), chat)
            return
        if await asyncio.to_thread(_asking, graphs, thread) is not None:
            # The logger is holding a clarifying question, so this message is
            # the answer to it and not a new turn. That is the graph's own
            # state and not something the entrance is asked to work out.
            await _reporting(graphs, thread, Command(resume=text), chat)
            return
        if await asyncio.to_thread(_undeclared):
            # Nothing is declared, so nothing else can be answered yet: the
            # interview is the answer, whatever the message was (ADR-0013).
            await _onboarding(graphs, thread, text, None, chat)
            return
        final = await _entrance(graphs, thread, entrance.heard(text), chat.language)
        await _spoken(final, thread, chat)
        await _handed_on(graphs, thread, text, final, chat)

    return run


async def _handed_on(
    graphs: Graphs,
    thread: str,
    text: str,
    final: Mapping[str, Any],
    chat: Chat,
    following: bool = False,
) -> None:
    """The subgraph the entrance's turn reached for, run; `following` opens a plan after a stopped run."""
    handoff = str(final.get("handoff", ""))
    if handoff == entrance.TODAYS_WORKOUT:
        await _serving(thread, chat)
    elif handoff == entrance.PREPARED:
        await _reoffered(graphs, thread, chat)
    elif handoff in entrance.PLANS:
        await _planning(graphs, thread, final, chat, following)
    elif handoff == entrance.ACCEPT_PLAN:
        await _answered(graphs, thread, None, planner.accepted(), chat)
    elif handoff == entrance.TURN_DOWN_PLAN:
        said = str(dict(final.get("asked", {})).get("said", "")) or text
        await _answered(graphs, thread, None, planner.refused(said), chat)
    elif handoff == entrance.LOG_WORKOUT:
        await _logging(graphs, thread, text, final, chat)
    elif handoff == entrance.SET_UP:
        await _onboarding(graphs, thread, text, final, chat)
    elif handoff == entrance.CHANGE_DECLARATION:
        await _changing(graphs, thread, text, final, chat)


def interjecting(graphs: Graphs) -> Interject:
    """A message arriving while a plan is written, read by the entrance instead of queued.

    Anything else the thread is busy with -- a report, an interview, a tap --
    hands the text back to be queued, as does a message an interview or a
    logger question is waiting on.
    """

    async def interject(thread: str, text: str, chat: Chat) -> str | Later | None:
        on = _reading(under(thread, PLANNING))
        if (
            not graphs.negotiation.running(on)
            or graphs.negotiation.preparing(on)
            or await asyncio.to_thread(_interviewing, graphs, thread)
            or await asyncio.to_thread(_asking, graphs, thread) is not None
        ):
            return text
        final = await _entrance(graphs, thread, entrance.heard(text), chat.language)
        await _spoken(final, thread, chat)
        handoff = str(final.get("handoff", ""))
        if handoff in entrance.PLANS:
            graphs.negotiation.stop(on)
            return Later(
                lambda later: _handed_on(graphs, thread, text, final, later, following=True),
                first=True,
            )
        if handoff in entrance.WRITES:
            return Later(lambda later: _handed_on(graphs, thread, text, final, later))
        await _handed_on(graphs, thread, text, final, chat)
        return None

    return interject


def planning(preparing: set[str], stopping: Mapping[str, threading.Event]) -> Callable[[str], bool]:
    """Whether a plan the user asked for is being written on a chat thread."""

    def asked(thread: str) -> bool:
        on = under(thread, PLANNING)
        return on in stopping and on not in preparing

    return asked


def proposing(plans_on: planner.Planner, stopping: Mapping[str, threading.Event]) -> Callable[[str], str | None]:
    """The kind of plan waiting on the user's answer on a chat thread, or nothing."""
    talks = negotiations.Negotiation(plans_on)

    def waiting(thread: str) -> str | None:
        on = _reading(under(thread, PLANNING))
        if under(thread, PLANNING) in stopping:
            return None
        held = talks.pending(on)
        if held is None or negotiations.passed(held.request):
            return None
        if isinstance(held.request, plans.Request):
            return entrance.ADAPTATION
        return entrance.CHANGE if held.request.changing is not None else entrance.MESOCYCLE

    return waiting


def relaying(graphs: Graphs) -> Relay:
    """One thing that happened, put to the entrance for it to say in its own words."""

    async def relay(thread: str, situation: str, chat: Chat) -> None:
        await _relay(graphs, thread, situation, chat)

    return relay


async def _relay(graphs: Graphs, thread: str, situation: str, chat: Chat) -> None:
    final = await _entrance(graphs, thread, entrance.relayed(situation), chat.language)
    await _spoken(final, thread, chat)


async def _entrance(
    graphs: Graphs, thread: str, given: Any, spoken: language.Language
) -> dict[str, Any]:
    """One turn of the entrance, serialised per thread and with its ending written.

    A node cannot write after it has raised (ADR-0007, item 1), and the turn
    above this catches the exception to say the failed line -- so without this the
    entrance would be the one graph whose failures leave nothing behind.
    """
    on = _reading(thread, spoken)
    async with graphs.talking.setdefault(thread, asyncio.Lock()):
        try:
            return cast(
                dict[str, Any],
                await asyncio.to_thread(graphs.entrance.invoke, given, on),
            )
        except Exception:
            await asyncio.to_thread(
                run_record.failed,
                graphs.entrance,
                on,
                tools.CALL_BUDGET,
                graphs.archive,
            )
            raise


async def _spoken(final: Mapping[str, Any], thread: str, chat: Chat) -> None:
    """What the entrance said, into the chat.

    A turn that came back with no words is the model failing rather than
    choosing silence, and it is answered the way an absent one is: nothing
    raised leaves the machine, and the chat gets the constant ADR-0006 keeps
    for exactly this.
    """
    said = str(final.get("answer", "")).strip()
    if not said:
        logger.warning("the entrance answered %s with nothing", thread)
    await chat.say(said or _said(chat).failed)


async def _serving(thread: str, chat: Chat) -> None:
    """Today's workout off the mesocycle, prescribed once and sent, with no model call.

    The entrance has already read whether there is one and said so; with none
    to serve, what it said is the whole answer.
    """
    try:
        text = await asyncio.to_thread(_served, chat.language)
    except tools.ToolFailure as state:
        logger.warning("%s cannot serve today's workout: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    if text is None:
        logger.info("%s has no mesocycle to serve from", thread)
        return
    await chat.offer(text, ())


def _served(spoken: language.Language) -> str | None:
    """Today's workout prescribed and rendered, or `None` when no mesocycle serves one."""
    with tools.reported(), tools.opened() as connection:
        try:
            found, _ = mesocycles.record_served(connection, date.today().isoformat())
        except mesocycles.MesocycleError:
            return None
        cap = config.load(connection).duration_cap_min
    return served(found, cap, spoken)


async def _planning(
    graphs: Graphs,
    thread: str,
    final: Mapping[str, Any],
    chat: Chat,
    following: bool = False,
) -> None:
    """The planner, asked for a mesocycle, a change or an adaptation, behind the turn the entrance has already answered.

    A request opened here ends any plan the thread was still waiting on, and
    a tap on that one is answered as superseded. `following` opens it in the
    negotiation of the run it replaced, as the run after it: a run stopped
    mid-plan, or the plan the entrance was told is waiting.

    Assembling the request is a synchronous read of SQLite and of the
    declaration, and it is the half that can be refused -- so it happens
    before the draft opens. Promising minutes of work and then answering with
    a state is worse than answering with the state.
    """
    try:
        request = await asyncio.to_thread(
            _handed, str(final.get("handoff", "")), dict(final.get("asked", {}))
        )
    except tools.ToolFailure as state:
        # Logged here rather than left to the caller: `_attempt` catches what
        # escapes a run, and this is a state the run never reached. With the
        # traceback, which is not noise on a state: it says which of the
        # preconditions the run stopped on.
        logger.warning("%s cannot plan: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    carrying = entrance.carried(final)
    on = _reading(under(thread, PLANNING))
    if following or await asyncio.to_thread(graphs.negotiation.pending, on) is not None:
        carrying |= await asyncio.to_thread(graphs.negotiation.continuing, on)
    await _proposing(graphs, thread, request, chat, carrying)


async def _proposing(
    graphs: Graphs,
    thread: str,
    request: plans.Request | plans.MesocycleRequest,
    chat: Chat,
    carrying: Mapping[str, Any] | None = None,
) -> None:
    """A request opened on the negotiation, streamed, and what it leaves the chat holding."""
    on = _reading(under(thread, PLANNING), chat.language)
    settled = await _streaming(
        lambda posted: graphs.negotiation.open(on, request, carrying, posted),
        chat,
        progress.Progress(progress.PLAN, chat.language),
    )
    await told(graphs, settled, thread, chat)


async def _logging(
    graphs: Graphs, thread: str, text: str, final: Mapping[str, Any], chat: Chat
) -> None:
    """The logger, behind the turn the entrance has already answered.

    The report is `text` -- what the user typed, character for character. The
    entrance never retells it: a paraphrase is the system's reading of the
    user rather than the user.
    """
    try:
        open_workout = await asyncio.to_thread(_awaiting)
    except tools.ToolFailure as state:
        logger.warning("%s cannot read a report: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    given = dict(
        logger_graph.starting(
            text,
            date.today().isoformat(),
            awaiting=None if open_workout is None else open_workout.id,
            prescribed_on=None if open_workout is None else open_workout.prescribed_on,
        )
    ) | entrance.carried(final)
    await _reporting(graphs, thread, given, chat)


async def _reporting(graphs: Graphs, thread: str, given: Any, chat: Chat) -> None:
    """One run of the logger, streamed, and what it leaves the chat holding."""
    settled = await _ending(
        graphs.logger,
        given,
        under(thread, LOGGING),
        chat,
        graphs.archive,
        progress.Progress(progress.LOG, chat.language),
    )
    await reported(graphs, settled, thread, chat)


async def _onboarding(
    graphs: Graphs, thread: str, text: str, final: Mapping[str, Any] | None, chat: Chat
) -> None:
    """The interview, behind the turn the entrance has already answered; `final` is `None` when no entrance turn opened it."""
    try:
        words = await asyncio.to_thread(_vocabulary)
    except tools.ToolFailure as state:
        logger.warning("%s cannot set up: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    given = dict(onboarding.starting(text, date.today().isoformat(), words))
    if final is not None:
        given |= entrance.carried(final)
    await _interview(graphs, thread, given, chat)


def _undeclared() -> bool:
    """Whether nothing is declared yet, on a database that is otherwise ready."""
    try:
        with tools.opened() as connection:
            return config.declared(connection) is None
    except (tools.ToolFailure, config.ConfigError):
        # Not ready, or declared wrongly: the entrance's turn reports either.
        return False


async def _changing(
    graphs: Graphs, thread: str, text: str, final: Mapping[str, Any], chat: Chat
) -> None:
    """The interview on what changed, seeded from the declarations in force; with none, the whole interview (ADR-0012)."""
    try:
        before = await asyncio.to_thread(_declarations)
        if before is None:
            await _onboarding(graphs, thread, text, final, chat)
            return
        words = await asyncio.to_thread(_vocabulary)
    except tools.ToolFailure as state:
        logger.warning("%s cannot change a declaration: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    given = dict(
        onboarding.changing(text, date.today().isoformat(), words, before)
    ) | entrance.carried(final)
    await _interview(graphs, thread, given, chat)


def _declarations() -> dict[str, Any] | None:
    with tools.reported(), tools.opened() as connection:
        try:
            return onboarding.declarations(connection)
        except config.NoTrainingConfig:
            return None


def _vocabulary() -> dict[str, list[str]]:
    with tools.reported(), tools.opened() as connection:
        return onboarding.vocabulary(connection)


async def _interview(graphs: Graphs, thread: str, given: Any, chat: Chat) -> None:
    """One run of the interview, up to its next question or its end."""
    settled = await _ending(
        graphs.onboarding,
        given,
        under(thread, ONBOARDING),
        chat,
        graphs.archive,
        progress.Progress(progress.ONBOARD, chat.language),
    )
    await interviewed(graphs, settled, thread, chat)


async def interviewed(
    graphs: Graphs, final: Mapping[str, Any], thread: str, chat: Chat
) -> None:
    """The interview's next question, or its declarations written and a first mesocycle planned."""
    waiting = final.get("__interrupt__")
    if waiting:
        await _asked(waiting[0], thread, chat)
        return
    if final.get("changing"):
        await _changed(graphs, final, thread, chat)
        return
    try:
        await asyncio.to_thread(_onboarded, final)
        request = await asyncio.to_thread(_handed, entrance.PLAN_MESOCYCLE, {})
    except tools.ToolFailure as state:
        logger.warning("%s cannot finish setting up: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    await _relay(graphs, thread, entrance.ONBOARDED, chat)
    await _proposing(graphs, thread, request, chat)


async def _changed(
    graphs: Graphs, final: Mapping[str, Any], thread: str, chat: Chat
) -> None:
    """A change written, the model's reason for its path said, and the planner started when the path needs one."""
    chosen = str(final.get("chosen", ""))
    try:
        await asyncio.to_thread(_onboarded, final)
        request = None
        if chosen == onboarding.REWRITE:
            said = str((final.get("said") or [""])[0])
            request = await asyncio.to_thread(
                _handed, entrance.CHANGE_MESOCYCLE, {"said": said}
            )
        elif chosen == onboarding.NEW_NOW:
            request = await asyncio.to_thread(_handed, entrance.PLAN_MESOCYCLE, {})
    except (tools.ToolFailure, mesocycles.MesocycleError) as state:
        logger.warning("%s cannot finish a change: %s", thread, state, exc_info=True)
        await chat.say(_said(chat).blocked)
        return
    if not chosen:
        await _relay(graphs, thread, entrance.DECLARED, chat)
        return
    await chat.say(str(final.get("why", "")) or _said(chat).failed)
    if request is not None:
        await _proposing(graphs, thread, request, chat)


def _onboarded(final: Mapping[str, Any]) -> None:
    with tools.reported():
        onboarding.written(dict(final))


def _interviewing(graphs: Graphs, thread: str) -> bool:
    """Whether the interview is waiting on this chat: a question, or an exclusion to confirm."""
    held = graphs.onboarding.get_state(_reading(under(thread, ONBOARDING)))
    return bool(held.interrupts)


DRAFT_SECONDS = 20.0
"""How often the draft is re-sent when the run has produced nothing new.

Under Telegram's thirty, because a draft nobody refreshes disappears and a
planner turn on Ollama is minutes long: between two lines the screen would go
back to being empty, which is the state this ticket exists to end.
"""


async def streamed(
    graph: Any,
    given: Any,
    on: RunnableConfig,
    chat: Chat,
    lines: progress.Progress,
) -> dict[str, Any]:
    """One run of a graph, with its progress in the chat while it happens; its last `values`, as `invoke` returns them."""

    def run(posted: negotiations.Progress) -> dict[str, Any]:
        final: dict[str, Any] = {}
        for mode, chunk in graph.stream(given, on, stream_mode=["updates", "values"]):
            if mode == "values":
                final = chunk
            else:
                posted(chunk)
        return final

    return await _streaming(run, chat, lines)


@dataclass(frozen=True)
class _Finished[T]:
    result: T


async def _streaming[T](
    work: Callable[[negotiations.Progress], T],
    chat: Chat,
    lines: progress.Progress,
) -> T:
    """Synchronous work that streams updates, run off the loop with its progress in the chat.

    The stream is the point: the tools the planner calls and the violations it
    is sent back are the refusal loop of ADR-0004, and without them on screen
    that loop is a property of the code that nobody can see.

    **On a thread, and not `astream`.** The graph is checkpointed by
    `checkpoints.saver()`, a `SqliteSaver`, which has no async methods at all
    -- the first thing `astream` does is ask it for `aget_tuple`, and it
    refuses. The async saver is not a swap either: it has no *sync* methods,
    and `trainer plan` drives this same graph synchronously against the same
    file. One checkpointer serves both doors, so the door that is async is the
    one that adapts.

    `lines` is handed in because the two subgraphs share four node names and
    mean different things by three of them: a draft saying *scrivo il piano*
    while a report is being read is a lie about what the machine is doing.
    """
    loop = asyncio.get_running_loop()
    arriving: asyncio.Queue[Any] = asyncio.Queue()

    def pump() -> None:
        """The work, run off the loop, posting each update and then its result back to it.

        `call_soon_threadsafe` rather than touching the queue directly: this
        runs on a worker thread, and an asyncio queue is not safe to put to
        from one. What the work raises is posted like any other item, so it is
        raised again on the loop where the caller can see it, instead of dying
        inside a thread nobody is waiting on.
        """
        def posted(chunk: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(arriving.put_nowait, chunk)

        try:
            result = work(posted)
        except BaseException as error:  # noqa: BLE001 -- re-raised on the loop
            loop.call_soon_threadsafe(arriving.put_nowait, error)
        else:
            loop.call_soon_threadsafe(arriving.put_nowait, _Finished(result))

    async with drafting(chat.draft, lines) as update:
        pumping = asyncio.create_task(asyncio.to_thread(pump))
        try:
            while True:
                item = await arriving.get()
                if isinstance(item, _Finished):
                    return cast(T, item.result)
                if isinstance(item, BaseException):
                    raise item
                if lines.reading(item):
                    await update()
        finally:
            # The thread has already posted its last item by the time either
            # exit is reached, so this collects it rather than waiting on it.
            await pumping


@asynccontextmanager
async def drafting(
    draft: Draft, lines: progress.Progress
) -> AsyncIterator[Callable[[], Awaitable[None]]]:
    """The draft, for as long as the run lasts: sent on every new line, kept alive between them.

    Two reasons to write to it, and they are not the same reason. A line is
    new and the user should see it now, which is the run's own call; and
    nothing has been new for long enough that the preview is about to expire,
    which is the task's.

    One lock over both, so the two never overlap. Each sends the whole
    progress as it stands when its turn comes, and the draft the user is
    looking at is therefore never an older one that finished last.

    It opens on the working line rather than on nothing, because the first line the
    graph produces is a minute away and an empty draft asks the client to draw
    a placeholder it may not know. A send that fails is logged and nothing
    more: progress is not the answer, and a run must not be lost because the
    preview of it could not be delivered.
    """
    fresh = asyncio.Event()
    sending = asyncio.Lock()

    async def update() -> None:
        fresh.set()
        async with sending:
            try:
                await draft(lines.text() or language.texts(lines.language).chat.working)
            except Exception:
                logger.exception("could not update the draft")

    async def alive() -> None:
        while True:
            try:
                await asyncio.wait_for(fresh.wait(), DRAFT_SECONDS)
            except TimeoutError:
                await update()
            fresh.clear()

    await update()
    task = asyncio.create_task(alive())
    try:
        yield update
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _handed(handoff: str, asked: Mapping[str, Any]) -> plans.Request | plans.MesocycleRequest:
    """The planner's request for this handoff, off the functions `trainer plan` assembles it with."""
    with tools.reported(), tools.opened() as connection:
        if handoff == entrance.PLAN_MESOCYCLE:
            return plans.mesocycle_requested(connection, date.today().isoformat(), plans.Asked())
        return entrance.requested(connection, handoff, asked)


def _awaiting() -> workouts.Workout | None:
    """The prescribed workout a report would be filed against, off the same function `trainer log` uses."""
    with tools.reported(), tools.opened() as connection:
        return workouts.awaiting(connection)


def _asking(graphs: Graphs, thread: str) -> Any | None:
    """The clarifying question the logger is holding on this thread, or nothing.

    The exclusion is not one of these. It is a closed question with two
    buttons under it, so a message arriving while it waits is a new turn and
    not an answer -- which is what the payload's `kind` is for (ADR-0006, and
    the terminal reads the same field in `cli._answered`).
    """
    pending = graphs.logger.get_state(_reading(under(thread, LOGGING))).interrupts
    if not pending:
        return None
    asked = pending[0].value
    if isinstance(asked, Mapping) and asked.get("kind") == logger_graph.CLARIFY:
        return pending[0]
    return None


def answering(graphs: Graphs) -> Resume:
    """The tap, answered: the thread resumes and the run goes on from there (ADR-0005).

    Which graph is resumed is read off the action, because a button carries 64
    bytes and the two sets of actions are disjoint. The write is the graph's
    for a plan and `_written`'s for a report, and neither is this function's:
    what happens here is a resume and a stream.
    """

    async def resume(thread: str, tap: Tap, chat: Chat) -> None:
        if tap.action in CONFIRM:
            await _confirming(graphs, thread, tap, chat)
            return
        await _answered(graphs, thread, tap.proposal, _answer(tap, chat.language), chat)

    return resume


async def _answered(
    graphs: Graphs, thread: str, proposal: str | None, answer: planner.Answer, chat: Chat
) -> None:
    """The plan waiting answered, by a tap on `proposal` or in words (`None`: whichever is waiting)."""
    on = _reading(under(thread, PLANNING), chat.language)
    held = await asyncio.to_thread(graphs.negotiation.pending, on)
    if (
        held is None
        or (proposal is not None and held.id != proposal)
        or await asyncio.to_thread(graphs.negotiation.lapse, on)
    ):
        # Checked before the draft opens, so a stale answer draws no
        # *Ci penso* for a plan nobody is working on.
        await told(graphs, negotiations.Superseded(), thread, chat)
        return
    # Streamed like any other run: a refusal plans the whole workout
    # again, which is the same minutes of silence a question costs.
    settled = await _streaming(
        lambda posted: graphs.negotiation.answer(on, held.id, answer, posted),
        chat,
        progress.Progress(progress.PLAN, chat.language),
    )
    await told(graphs, settled, thread, chat)


async def _confirming(graphs: Graphs, thread: str, tap: Tap, chat: Chat) -> None:
    """The exclusion, confirmed or declined, and the run carried on from there."""
    held = graphs.onboarding.get_state(_reading(under(thread, ONBOARDING))).interrupts
    if held and held[0].id == tap.proposal:
        await _interview(graphs, thread, Command(resume=tap.action == CONFIRMED), chat)
        return
    pending = graphs.logger.get_state(_reading(under(thread, LOGGING))).interrupts
    if not pending or pending[0].id != tap.proposal:
        await _relay(graphs, thread, entrance.SUPERSEDED, chat)
        return
    await _reporting(
        graphs, thread, Command(resume=tap.action == CONFIRMED), chat
    )


async def _ending(
    graph: Any,
    given: Any,
    thread: str,
    chat: Chat,
    archive: Path,
    lines: progress.Progress,
) -> dict[str, Any]:
    """One run, streamed, and its ending written even when it is the graph falling over.

    A node cannot write after it has raised (ADR-0007, item 1), and the
    turn-taking above this catches the exception to say the failed line -- so the run
    would otherwise be the one kind that leaves nothing behind, which is the
    kind you most want to read.
    """
    try:
        return await streamed(graph, given, _reading(thread, chat.language), chat, lines)
    except Exception:
        await asyncio.to_thread(
            run_record.failed, graph, _reading(thread), tools.CALL_BUDGET, archive
        )
        raise


def _answer(tap: Tap, spoken: language.Language) -> planner.Answer:
    """The button, as the planner reads it: kept, or turned down in words.

    A button is not a sentence, and the planner is told *why* rather than
    which button was pressed -- the same field the user's own words reach it
    through when they turn a plan down by writing instead of tapping.
    """
    if tap.action == KEPT:
        return planner.accepted()
    return planner.refused(language.texts(spoken).chat.turned_down)


async def told(
    graphs: Graphs,
    settled: negotiations.Outcome | Mapping[str, Any],
    thread: str,
    chat: Chat,
) -> None:
    """What the chat is left holding when a negotiation step stops: a plan, the workout, or neither.

    A mapping is a planner run's final state, read as the outcome it is.
    """
    if isinstance(settled, Mapping):
        settled = negotiations.outcome(settled)
    match settled:
        case negotiations.Proposed(plan=proposed, request=request, id=answerable):
            if isinstance(proposed, plans.Mesocycle):
                assert isinstance(request, plans.MesocycleRequest)
                text = mesocycle_proposal(proposed, request, chat.language)
            else:
                assert isinstance(request, plans.Request)
                text = proposal(proposed, request.shown_minutes, chat.language)
            await chat.offer(
                text,
                [
                    (carried(Tap(action, thread, answerable)), label)
                    for action, label in labelled(BUTTONS, chat.language)
                ],
            )
        case negotiations.Accepted(workout=written) if written is not None:
            await _relay(graphs, thread, entrance.PRESCRIBED, chat)
        case negotiations.Accepted():
            await _relay(graphs, thread, entrance.KEPT, chat)
        case negotiations.Superseded():
            # The thread has moved on, or this plan was already answered, and
            # silence would read as a bot that is down.
            await _relay(graphs, thread, entrance.SUPERSEDED, chat)
        case negotiations.Refused():
            # No plan to offer, and saying nothing would leave the user
            # waiting on a run that ended.
            await _relay(graphs, thread, entrance.NO_PLAN, chat)
        case negotiations.Stopped():
            # The entrance said so when it stopped it, and its replacement is
            # next in the queue.
            pass


async def reported(
    graphs: Graphs, final: Mapping[str, Any], thread: str, chat: Chat
) -> None:
    """What the chat is left holding when a run of the logger stops.

    The write happens here and never in the graph (`logger.build`), so a run
    stopped on a question leaves the training tables exactly as they were.
    """
    waiting = final.get("__interrupt__")
    if waiting:
        await _asked(waiting[0], thread, chat)
        return
    if final.get("refused") is not None:
        await _relay(graphs, thread, entrance.NOT_LOGGED, chat)
        return
    await asyncio.to_thread(_written, final)
    # The adaptation of the workout just reported has nothing left to adapt.
    await asyncio.to_thread(graphs.negotiation.lapse, _reading(under(thread, PLANNING)))
    await _relay(graphs, thread, entrance.LOGGED, chat)
    await _preparing(graphs, thread, chat)


def prepared(plans_on: planner.Planner, preparing: set[str]) -> Callable[[str], bool]:
    """Whether a chat thread's next mesocycle is being prepared, or waits unanswered."""
    talks = negotiations.Negotiation(plans_on, preparing=preparing)

    def waiting(thread: str) -> bool:
        on = _reading(under(thread, PLANNING))
        if talks.preparing(on):
            return True
        held = talks.pending(on)
        return held is not None and held.unasked

    return waiting


_next = negotiations.next_request


async def _preparing(graphs: Graphs, thread: str, chat: Chat) -> None:
    """The next mesocycle, prepared in the background when the last cycle has just ended (ADR-0008 item 5).

    A task and not a turn: the queue in `Turns` is released once the report is
    answered, so a message arriving while the planner works is answered.
    """
    task = asyncio.create_task(_prepare(graphs, thread, chat))
    graphs.background.add(task)
    task.add_done_callback(graphs.background.discard)


async def _prepare(graphs: Graphs, thread: str, chat: Chat) -> None:
    """One negotiation nobody asked for, on the thread a requested one uses, and its offer."""
    try:
        settled = await asyncio.to_thread(
            graphs.negotiation.prepare,
            _reading(under(thread, PLANNING), chat.language),
            _reading(under(thread, SUPERVISING), chat.language),
        )
    except tools.ToolFailure as state:
        logger.warning("%s cannot prepare the next mesocycle: %s", thread, state, exc_info=True)
        return
    except Exception:
        logger.exception("preparing the next mesocycle on %s failed", thread)
        with contextlib.suppress(Exception):
            await chat.say(_said(chat).failed)
        return
    if settled is None:
        return
    if isinstance(settled, negotiations.Proposed):
        assert isinstance(settled.request, plans.MesocycleRequest)
        await _relay(graphs, thread, _following(settled.request), chat)
    await told(graphs, settled, thread, chat)


def _following(request: plans.MesocycleRequest) -> str:
    """The situation that announces a prepared mesocycle, with the direction it was planned from."""
    assert request.continuing is not None and request.continuing.direction is not None, (
        "a prepared mesocycle is always directed first"
    )
    return entrance.NEXT_MESOCYCLE.format(**asdict(request.continuing.direction))


async def _reoffered(graphs: Graphs, thread: str, chat: Chat) -> None:
    """The prepared mesocycle offered again, with the buttons of the one already waiting.

    While it is still being prepared there is nothing to offer yet: it arrives
    by itself, which is what the entrance has already said.
    """
    on = _reading(under(thread, PLANNING))
    if graphs.negotiation.preparing(on):
        return
    held = await asyncio.to_thread(graphs.negotiation.pending, on)
    if held is not None:
        await told(graphs, held, thread, chat)


async def _asked(waiting: Any, thread: str, chat: Chat) -> None:
    """The question the run stopped on, put to the chat the way its kind asks for.

    Open or closed is the graph's to say and not this door's -- the same
    payload reaches the terminal, where the closed one is a yes/no prompt.
    Here it is two buttons, and the open one is a message to reply to.
    """
    question = waiting.value
    if question.get("kind") == logger_graph.EXCLUSION:
        await chat.offer(
            exclusion(question, chat.language),
            [
                (carried(Tap(action, thread, waiting.id)), label)
                for action, label in labelled(CONFIRM, chat.language)
            ],
        )
        return
    await chat.say(str(question.get("ask", "")))


def exclusion(question: Mapping[str, Any], spoken: language.Language) -> str:
    """The proposed exclusion, as the chat asks about it.

    Escaped and with no markup of its own. Everything in it was written by a
    model or read out of the catalog, and MarkdownV2 makes a dot and a hyphen
    syntax -- an unescaped one loses the question, not the formatting.
    """
    from telegram.helpers import escape_markdown

    return escape_markdown(
        language.texts(spoken).chat.exclusion.format(
            why=question.get("ask", ""),
            value=question.get("value", ""),
            retest_date=question.get("retest_date", ""),
        ),
        version=2,
    )


def _written(final: Mapping[str, Any]) -> int:
    """The document, and the exclusion only if it was confirmed, written down.

    The blocks are resolved once and handed to the writer, the way the
    terminal does it: resolving them twice is two answers to what adherence
    filled in.
    """
    with tools.reported(), tools.opened() as connection:
        blocks = logs.to_performed(connection, final["document"])
        return logger_graph.performed(connection, final, blocks)


ITEM = "• {name} · {prescription}"
WHY = "_{reason}_"
NOTE = "⚠️ {note}"

PARSE_MODE = "MarkdownV2"
"""The dialect `proposal` writes and `_offering` sends a plan as."""


def served(found: mesocycles.Today, budget_min: int, spoken: language.Language) -> str:
    """Today's workout off the mesocycle, with the last load beside each exercise."""
    heading = language.texts(spoken).plan.served.format(
        slot=found.slot, slots=found.slots, cycle=found.cycle, cycles=found.cycles
    )
    body = proposal(plans.from_prescribed(found.blocks), budget_min, spoken, loads=True)
    return f"{heading}\n\n{body}"


def mesocycle_proposal(
    offered: plans.Mesocycle, request: plans.MesocycleRequest, spoken: language.Language
) -> str:
    """The whole mesocycle as the chat shows it: the cycles and why, then one workout per slot."""
    from telegram.helpers import escape_markdown

    parts = [
        language.texts(spoken).plan.mesocycle.format(cycles=offered.cycles),
        WHY.format(reason=escape_markdown(offered.why, version=2)),
    ]
    for slot, (workout, asked) in enumerate(
        zip(offered.workouts, request.slots, strict=True), start=1
    ):
        parts.extend(
            [
                "",
                language.texts(spoken).plan.slot.format(
                    slot=slot,
                    slots=len(request.slots),
                    groups=escape_markdown(", ".join(asked.groups), version=2),
                ),
                proposal(workout, asked.budget_min, spoken),
            ]
        )
    return "\n".join(parts)


def proposal(
    plan: plans.WorkoutPlan,
    budget_min: int | None,
    spoken: language.Language,
    loads: bool = False,
) -> str:
    """The plan as the chat shows it, in the markup Telegram renders.

    Off `plans.shown`, which is also what the terminal's lines are folded
    from. Only the markup differs: the terminal aligns a column of ASCII
    because a console has one font and no bold, and neither constraint reaches
    a phone.

    Everything the catalog or the model wrote is escaped. MarkdownV2 makes a
    dot and a hyphen syntax, and an exercise named *Push-Up* is enough for
    Telegram to refuse the message -- which loses the plan, not the formatting.
    """
    from telegram.helpers import escape_markdown

    def marked(said: str) -> str:
        return escape_markdown(said, version=2)

    words = language.texts(spoken).plan
    units = {"reps": words.reps, "seconds": words.seconds}

    with tools.reported(), tools.opened() as connection:
        reading = plans.shown(connection, plan, plans.to_blocks(plan), budget_min, loads)

    lines: list[str] = []
    for block in reading.blocks:
        lines.append(
            words.heading.format(
                position=block.position,
                rounds=block.rounds,
                rest=block.rest,
                minutes=block.seconds // 60,
                seconds=block.seconds % 60,
            )
        )
        for item in block.items:
            lines.append(
                ITEM.format(
                    name=marked(item.name),
                    prescription=units[item.prescription.unit].format(
                        amount=item.prescription.amount
                    ),
                )
                + _last(item.last, marked, words)
            )
            if item.said is not None:
                # Its own line and marked, not folded into the block's reason:
                # this is the agent proposing something the user said no to,
                # and it has to be the thing they notice.
                lines.append(words.said_no.format(why=marked(item.said)))
        lines.append(WHY.format(reason=marked(block.reason)))
        lines.append("")
    if reading.budget_min is None:
        lines.append(words.total_alone.format(total=reading.total_min))
    else:
        lines.append(words.total.format(total=reading.total_min, budget=reading.budget_min))
    if reading.note:
        lines.append(NOTE.format(note=marked(reading.note)))
    return "\n".join(lines)


def _last(last: Any, marked: Callable[[str], str], words: language.PlanLines) -> str:
    if last is None:
        return ""
    if last.value is None:
        return words.last_unknown
    return words.last.format(load=marked(f"{last.value:g}"))


def _reading(thread: str, spoken: language.Language | None = None) -> RunnableConfig:
    """A thread, the user whose conclusions its runs read and keep, and the language a run writes in."""
    configurable: dict[str, Any] = {
        "thread_id": thread,
        conclusions.USER: thread.partition("/")[0],
    }
    if spoken is not None:
        configurable[language.KEY] = spoken
    return {"configurable": configurable}


def turns(graph: run_record.Graph, thread: str) -> list[str]:
    """What the user has written on this thread, in the order they wrote it.

    Off the entrance, which is where `said` now lives: it is the conversation
    the entrance reads, and the planner's `starting` goes on leaving its own
    copy of the key alone (ADR-0006).
    """
    said: list[str] = graph.get_state(_reading(thread)).values.get("said", [])
    return list(said)


def application(declared: Settings, coach: Turns) -> Application[Any, Any, Any, Any, Any, Any]:
    """The Telegram application, with its handlers wired to `coach`.

    `concurrent_updates`, because the queue depends on it: processed one at a
    time, the second message is not even received until the run it is supposed
    to be queued behind has finished, and there is nothing left to acknowledge.
    """
    # Imported here rather than at the top: `trainer --help` should not pay for
    # an HTTP stack nobody asked to start, which is why `trainer mcp` imports
    # its server the same way.
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
    )

    built = (
        ApplicationBuilder().token(declared.token).concurrent_updates(True).build()
    )
    built.add_handler(CommandHandler("start", _on_start(coach)))
    built.add_handler(MessageHandler(messages_only(), _on_message(coach)))
    built.add_handler(CallbackQueryHandler(_on_tap(coach)))
    return built


def messages_only() -> Any:
    """What the message handler runs behind: new text, not a command, not an edit.

    `UpdateType.MESSAGE` is the load-bearing half. `filters.TEXT` matches on
    `effective_message`, which is the *edited* message when one is edited, so
    without it an edit reaches the handler and dies there in silence. Excluded
    here, not answering an edit is a decision rather than an accident:
    re-running minutes of planning because a typo was fixed is not obviously
    what was meant, and ticket 03's buttons are how a plan gets changed.

    A function rather than a constant, because `telegram` is imported late.
    """
    from telegram.ext import filters

    return filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE


Handler = Callable[["Update", "ContextTypes.DEFAULT_TYPE"], Coroutine[Any, Any, None]]
"""What python-telegram-bot accepts as a callback: a coroutine function, which
is narrower than an awaitable one and is what its own signatures ask for."""


def _on_start(coach: Turns) -> Handler:
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        who = _who(update)
        if who is None:
            return
        user_id, chat_id = who
        await coach.started(user_id, chat_id, chatting(context, chat_id, _spoken_in(update)))

    return handle


def _on_message(coach: Turns) -> Handler:
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        who = _who(update)
        # `effective_message` rather than `message`: which field carried the
        # text is the filter's business, and a body that reads only `message`
        # goes silent on anything the filter lets through in another one.
        message = update.effective_message
        if who is None or message is None or not message.text:
            return
        user_id, chat_id = who
        await coach.arriving(
            user_id, chat_id, message.text, chatting(context, chat_id, _spoken_in(update))
        )

    return handle


def _on_tap(coach: Turns) -> Handler:
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        tap = update.callback_query
        who = _who(update)
        if tap is None or who is None:
            return
        # Answered first, whatever the tap turns out to be: until this call
        # returns, the button is still spinning on the user's phone -- and a
        # refusal is a whole plan away from its next word.
        await tap.answer()
        if not isinstance(tap.data, str):
            return
        user_id, chat_id = who
        await coach.tapped(user_id, chat_id, tap.data, chatting(context, chat_id, _spoken_in(update)))

    return handle


def _who(update: Update) -> tuple[int, int] | None:
    """Who sent it and where, or nothing at all.

    An update carries neither on some kinds -- a poll answer, a channel post --
    and there is nobody to answer and no thread to run on. `Turns` decides
    whether the user is the owner; this only decides whether there is a user.
    """
    if update.effective_user is None or update.effective_chat is None:
        return None
    return update.effective_user.id, update.effective_chat.id


def _said(chat: Chat) -> language.ChatLines:
    """The chat's own lines, in its language."""
    return language.texts(chat.language).chat


def _spoken_in(update: Update) -> language.Language:
    """The language the sender's Telegram app is set to, as the chat speaks it."""
    user = update.effective_user
    return language.of(None if user is None else user.language_code)


def chatting(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, spoken: language.Language
) -> Chat:
    """One chat's three channels, built once per update.

    The draft id is minted here, so it is one per turn and therefore one per
    run: a queued turn arrives with a chat of its own, and two runs sharing an
    id would animate each other's progress into one preview.
    """
    return Chat(
        say=_saying(context, chat_id),
        offer=_offering(context, chat_id),
        draft=_drafting(context, chat_id),
        language=spoken,
    )


def _saying(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Say:
    async def say(line: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=line)

    return say


def _offering(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Offer:
    """A plan with its buttons, in one row per answer."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    async def offer(text: str, buttons: Sequence[tuple[str, str]]) -> None:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=PARSE_MODE,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(label, callback_data=data)]
                    for data, label in buttons
                ]
            )
            if buttons
            else None,
        )

    return offer


DRAFT_IDS = 2**31 - 1
"""The range a draft id is drawn from. Telegram asks only that it be non-zero."""


def _drafting(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Draft:
    """The progress channel: one draft, re-sent under the same id so it updates in place.

    Plain text and no parse mode. Progress is the words of a run in flight,
    and a stray asterisk in something the model called a tool with would be a
    send Telegram refuses -- silently losing the one thing that says the bot
    is still working.
    """
    draft_id = random.randrange(1, DRAFT_IDS)

    async def draft(text: str) -> None:
        await context.bot.send_message_draft(
            chat_id=chat_id, draft_id=draft_id, text=text
        )

    return draft


def graphs(
    cast: models.Roster,
    saver: BaseCheckpointSaver[Any],
    archive: Path,
    store: BaseStore | None = None,
) -> Graphs:
    """The graphs, each on the model the roster gives its node (ADR-0006, item 3)."""
    plans_on = planner.build(cast["planner"], checkpointer=saver, archive=archive, store=store)
    preparing: set[str] = set()
    stopping: dict[str, threading.Event] = {}
    return Graphs(
        entrance=entrance.build(
            cast["entrance"],
            checkpointer=saver,
            archive=archive,
            prepared=prepared(plans_on, preparing),
            store=store,
            planning=planning(preparing, stopping),
            proposing=proposing(plans_on, stopping),
        ),
        planner=plans_on,
        logger=logger_graph.build(
            cast["logger"], checkpointer=saver, archive=archive, store=store
        ),
        onboarding=onboarding.build(
            cast["onboarding"], checkpointer=saver, archive=archive, store=store
        ),
        supervisor=supervisor_graph.build(
            cast["supervisor"], checkpointer=saver, archive=archive, store=store
        ),
        archive=archive,
        preparing=preparing,
        stopping=stopping,
    )


def serve(
    declared: Settings,
    cast: models.Roster,
    saver: BaseCheckpointSaver[Any],
    store: BaseStore,
) -> None:
    """Long-poll until interrupted, holding the models, the checkpointer, the store and the graphs.

    All of them for the life of the process (ADR-0004, item 6): the compiled
    graphs are what the threads are stored against.

    The checkpointer is opened by the caller rather than here, the way every
    command opens its database. It is the one thing in the startup block that
    can be refused -- pointed at the training database it is a `CheckpointError`
    -- and opened inside this call the whole block has already been printed,
    telling the user the process is healthy immediately before it is not.
    """
    built = graphs(cast, saver, run_record.archive(), store)
    coach = Turns(
        owner_id=declared.owner_id,
        run=talking(built),
        resume=answering(built),
        relay=relaying(built),
        interject=interjecting(built),
    )
    application(declared, coach).run_polling()
