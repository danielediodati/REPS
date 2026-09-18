"""The Telegram bot: long-polls from the graph's process, and answers only the owner."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from trainer import plan as plans
from trainer import tools
from trainer.coach import logfile, models, planner, progress
from trainer.coach import record as run_record

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import Application, ContextTypes

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
OWNER_ENV = "TELEGRAM_OWNER_ID"

EXAMPLE = ".env.example"
"""Where both settings are documented, named by every state that misses one."""

logger = logging.getLogger(__name__)

STARTED = "Sono il tuo allenatore. Scrivimi quando vuoi."

IN_THE_LOG = f"Il motivo è scritto in {logfile.LOG_NAME}."
"""Where the detail is, said the same way by both lines that have one.

The file name and not its path. The user reading this is on a phone and the
person who can open it is at the machine -- the same person, at another moment
-- and an absolute path would put this installation's account name and disk
layout on a third party's servers for no gain.
"""

BLOCKED = (
    "Non posso pianificare: c'è qualcosa da sistemare sul PC. " + IN_THE_LOG
)
"""A precondition the machine gets wrong, said without saying which.

No `training.toml`, so there is nothing to derive today's equipment, minutes
or groups from; no database; a catalog nobody enriched. Each is a **state**
rather than a run that fell over -- answered with `FAILED` it would read as
the provider having dropped the plan -- and each already names itself and the
command that fixes it.

**It names itself to the machine and not to the chat.** The engine's states
carry absolute paths: the file to copy, the directory to copy it into, the
database that is not there. Quoted into Telegram they would leave this
installation's account name and the shape of its disk on a third party's
servers, permanently and for no gain -- nobody copies a file from a phone, so
the path is not something a reader there can act on anyway. The state goes to
the log, where the person who can act on it is already sitting, and this names
the file it is in.

This is the rule and not an exception to it: **nothing raised leaves this
machine.** `FAILED` says the same thing about a run that fell over.
"""

WORKING = "Ci penso."
"""The draft's first frame, before the graph has done anything worth saying.

An empty draft is Telegram's *Thinking...* placeholder, which is Bot API 10.0
and is drawn by the clients that know it. A line of our own is drawn wherever
a draft is drawn at all, and the first minute of a local run is exactly when
the user most needs to see something.
"""

QUEUED = "Sto ancora lavorando a quello di prima. Questo lo faccio subito dopo."

FAILED = "Qualcosa è andato storto mentre ci lavoravo. Riprova. " + IN_THE_LOG
"""Said when a run raises.

A provider that falls over mid-run is the ordinary case on a laptop, and the
user is looking at a phone. An exception that reaches only the log is a bot
that has stopped answering, and the draft the run was writing into is gone
thirty seconds later with nothing left behind to say what happened.
"""


class BotError(RuntimeError):
    """A Telegram setting the environment gets wrong, stated with its fix."""


@dataclass(frozen=True)
class Settings:
    """The two things the bot cannot start without."""

    token: str
    owner_id: int


def settings() -> Settings:
    """The bot's settings, from the environment.

    Never from `training.toml`, which holds what the user declares about
    their training (ADR-0003). A token is a credential and an owner id is
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
    """
    return f"chat:{chat_id}"


KEPT = "ok"
TURNED_DOWN = "no"
SHORTER = "30"

SHORTER_MINUTES = 30

BUTTONS = (
    (KEPT, "Va bene"),
    (TURNED_DOWN, "Non mi va"),
    (SHORTER, f"Solo {SHORTER_MINUTES} minuti"),
)
"""The three answers a proposed plan takes, as (action, label)."""

SAID = {
    TURNED_DOWN: "Non mi va questo allenamento.",
    SHORTER: f"Ho solo {SHORTER_MINUTES} minuti.",
}
"""What a tap means in words, because the planner is told why and not which button."""

WRITTEN = "Fatto. È il tuo allenamento di oggi."

SUPERSEDED = (
    "Quel piano non è più quello in corso: scrivimi di nuovo e te ne preparo un altro."
)
"""A tap on a plan the thread has moved past. Not an error, and never silence."""

NO_PLAN = (
    "Non sono riuscito a farti un piano che stia dentro i vincoli. Riprova a scrivermi."
)

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
    if action not in dict(BUTTONS) or not thread or not proposal:
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

Ephemeral, about thirty seconds, so what goes down it is the whole progress so
far and never the newest line alone: a draft is not a transcript and nothing
that has to survive the run may go this way.
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


Run = Callable[[str, str, Chat], Awaitable[None]]
"""The work one message causes, on one thread: `planning` below."""

Resume = Callable[[str, "Tap", Chat], Awaitable[None]]
"""The work one tap causes: it answers the interrupt the plan is waiting on."""

Turn = str | Tap
"""One piece of work on a thread: something the user wrote, or a button they tapped."""

Waiting = tuple[Turn, Chat]
"""A turn queued behind a run, with the chat it arrived on."""


@dataclass
class _Conversation:
    """One chat's turn-taking: whether a run is in flight, and what arrived during it."""

    busy: bool = False
    waiting: list[Waiting] = field(default_factory=list)


class Coach:
    """One run at a time per thread, for the owner and nobody else."""

    def __init__(self, owner_id: int, run: Run, resume: Resume | None = None) -> None:
        self._owner_id = owner_id
        self._run = run
        self._resume = resume
        self._threads: dict[str, _Conversation] = {}

    async def started(self, user_id: int, chat_id: int, chat: Chat) -> None:
        """Answer `/start`, if the owner sent it."""
        if not self._answers(user_id):
            return
        await self._tell(thread_for(chat_id), chat, STARTED)

    async def arriving(
        self, user_id: int, chat_id: int, text: str, chat: Chat
    ) -> None:
        """One message, run now or queued behind the run already in flight.

        Queued rather than dropped, and never a second run on the same thread:
        on Ollama a run is minutes, and cancelling one to start another throws
        all of them away. *"Actually, 30 minutes"* is not this -- it is ticket
        03's interrupt, which resumes the run instead of racing it.
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
        if conversation.busy:
            # Queued before the acknowledgement is attempted, not after: a chat
            # that cannot be written to must not also cost the message.
            conversation.waiting.append((turn, chat))
            await self._tell(thread, chat, QUEUED)
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
            else:
                await self._run(thread, turn, chat)
        except Exception:
            logger.exception("the run on %s failed", thread)
            await self._tell(thread, chat, FAILED)

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

    def _answers(self, user_id: int) -> bool:
        """Whether this is the owner, checked before anything looks at the message."""
        if user_id == self._owner_id:
            return True
        logger.info("ignored an update from user %s", user_id)
        return False


def planning(graph: planner.Planner, archive: Path) -> Run:
    """One message, planned: today's request assembled, the graph run, the plan offered.

    The request comes from `plan.requested`, which the terminal calls too --
    the chat names almost nothing, and everything it does not name is derived
    from the declaration and from the performed workouts rather than asked
    for. What the user wrote goes into the thread as `said` and nothing reads
    it: this ticket plans today's workout whatever the words were, and reading
    them is the router's job in session 8.

    A run started here supersedes any plan the thread was still waiting on.
    Invoking with fresh input drops the pending proposal, and a tap on it
    afterwards finds an interrupt id that no longer matches, which is what
    `SUPERSEDED` answers.

    Assembling the request is a synchronous read of SQLite and of the
    declaration, and it is the half that can be refused -- so it happens
    before the draft opens. Promising minutes of work and then answering with
    a state is worse than answering with the state.
    """

    async def run(thread: str, text: str, chat: Chat) -> None:
        graph.update_state(_reading(thread), {"said": [text]})
        try:
            request = await asyncio.to_thread(_todays_request)
        except tools.ToolFailure as state:
            # Logged here rather than left to the caller: `_attempt` catches
            # what escapes a run, and this is a state the run never reached.
            # With the traceback, which is not noise on a state: it says which
            # of the preconditions the run stopped on.
            logger.warning("%s cannot plan: %s", thread, state, exc_info=True)
            await chat.say(BLOCKED)
            return
        final = await _ending(
            graph, planner.starting(request), thread, chat, archive
        )
        await told(final, thread, chat)

    return run


DRAFT_SECONDS = 20.0
"""How often the draft is re-sent when the run has produced nothing new.

Under Telegram's thirty, because a draft nobody refreshes disappears and a
planner turn on Ollama is minutes long: between two lines the screen would go
back to being empty, which is the state this ticket exists to end.
"""


async def streamed(
    graph: planner.Planner,
    given: Any,
    on: RunnableConfig,
    chat: Chat,
) -> dict[str, Any]:
    """One run, with its progress in the chat while it happens.

    The stream is the point: the tools the planner calls and the violations it
    is sent back are the refusal loop of ADR-0004, and without them on screen
    that loop is a property of the code that nobody can see.

    **On a thread, and not `astream`.** The graph is checkpointed by
    `checkpoints.saver()`, a `SqliteSaver`, which has no async methods at all
    -- the first thing `astream` does is ask it for `aget_tuple`, and it
    refuses. The async saver is not a swap either: it has no *sync* methods,
    and `trainer plan` invokes this same graph synchronously against the same
    file. One checkpointer serves both doors, so the door that is async is the
    one that adapts.

    Which is what the call it replaced already did. `asyncio.to_thread` around
    `invoke` was there because a round trip to the model is minutes on Ollama
    and would otherwise stop the process long-polling Telegram; the thread is
    the same, and what is new is that it reports as it goes instead of only at
    the end.

    The last `values` chunk carries what `invoke` would have returned, the
    pending interrupt included, so `told` reads the same shape either way.
    """
    lines = progress.Progress()
    final: dict[str, Any] = {}
    loop = asyncio.get_running_loop()
    arriving: asyncio.Queue[Any] = asyncio.Queue()
    done = object()

    def pump() -> None:
        """The graph, run off the loop, posting each chunk back to it.

        `call_soon_threadsafe` rather than touching the queue directly: this
        runs on a worker thread, and an asyncio queue is not safe to put to
        from one. What the run raises is posted like any other item, so it is
        raised again on the loop where the caller can see it, instead of dying
        inside a thread nobody is waiting on.
        """
        try:
            for emitted in graph.stream(given, on, stream_mode=["updates", "values"]):
                loop.call_soon_threadsafe(arriving.put_nowait, emitted)
        except BaseException as error:  # noqa: BLE001 -- re-raised on the loop
            loop.call_soon_threadsafe(arriving.put_nowait, error)
        else:
            loop.call_soon_threadsafe(arriving.put_nowait, done)

    async with drafting(chat.draft, lines) as update:
        pumping = asyncio.create_task(asyncio.to_thread(pump))
        try:
            while True:
                item = await arriving.get()
                if item is done:
                    break
                if isinstance(item, BaseException):
                    raise item
                mode, chunk = cast(tuple[str, dict[str, Any]], item)
                if mode == "values":
                    final = chunk
                elif lines.reading(chunk):
                    await update()
        finally:
            # The thread has already posted its last item by the time either
            # exit is reached, so this collects it rather than waiting on it.
            await pumping
    return final


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

    It opens on `WORKING` rather than on nothing, because the first line the
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
                await draft(lines.text() or WORKING)
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


def _todays_request() -> plans.Request:
    """Today's request, off the same function the terminal assembles it with."""
    with tools.reported(), tools.opened() as connection:
        return plans.requested(connection, date.today().isoformat()).request


def answering(graph: planner.Planner, archive: Path) -> Resume:
    """The tap, answered: the thread resumes and the run goes on from there (ADR-0005).

    The write is the graph's, in the node after the resume. Nothing here
    touches the database, which is what keeps the interface out of the
    training facts.
    """

    async def resume(thread: str, tap: Tap, chat: Chat) -> None:
        pending = graph.get_state(_reading(thread)).interrupts
        if not pending or pending[0].id != tap.proposal:
            # The thread has moved on, or this plan was already answered. A
            # tap on it is a question about a plan that is no longer the one
            # in hand, and silence would read as a bot that is down.
            await chat.say(SUPERSEDED)
            return
        # Streamed like any other run: a refusal plans the whole workout
        # again, which is the same minutes of silence a question costs.
        final = await _ending(graph, Command(resume=_answer(tap)), thread, chat, archive)
        await told(final, thread, chat)

    return resume


async def _ending(
    graph: planner.Planner, given: Any, thread: str, chat: Chat, archive: Path
) -> dict[str, Any]:
    """One run, streamed, and its ending written even when it is the graph falling over.

    A node cannot write after it has raised (ADR-0007, item 1), and the coach
    above this catches the exception to say `FAILED` -- so the run would
    otherwise be the one kind that leaves nothing behind, which is the kind
    you most want to read.
    """
    try:
        return await streamed(graph, given, _reading(thread), chat)
    except Exception:
        await asyncio.to_thread(
            run_record.failed, graph, _reading(thread), tools.CALL_BUDGET, archive
        )
        raise


def _answer(tap: Tap) -> planner.Answer:
    """The button, as the planner reads it: kept, or turned down in words.

    A button is not a sentence, and the planner is told *why* rather than
    which of three things was pressed -- the same field the user's own words
    will reach it through when session 8's router reads what they typed.
    """
    if tap.action == KEPT:
        return planner.accepted()
    if tap.action == SHORTER:
        return planner.refused(SAID[SHORTER], minutes=SHORTER_MINUTES)
    return planner.refused(SAID[TURNED_DOWN])


async def told(final: dict[str, Any], thread: str, chat: Chat) -> None:
    """What the chat is left holding when a run stops: a plan, the workout, or neither.

    An ordinary message in every case. The draft the run was writing into is a
    thirty-second preview and is gone by the time the user reads this, which is
    the difference between watching a run and being told what it decided.
    """
    waiting = final.get("__interrupt__")
    if waiting:
        proposed = final["plan"]
        await chat.offer(
            proposal(proposed, final["request"].budget_min),
            [
                (carried(Tap(action, thread, waiting[0].id)), label)
                for action, label in BUTTONS
            ],
        )
    elif final.get("workout") is not None:
        await chat.say(WRITTEN)
    else:
        # Every attempt refused by the validator. There is no plan to offer,
        # and saying nothing would leave the user waiting on a run that ended.
        await chat.say(NO_PLAN)


HEADING = "*Blocco {position}* · {rounds} giri · {rest}s di recupero · {minutes}:{seconds:02d}"
ITEM = "• {name} · {prescription}"
SAID_NO = "  ⚠️ avevi detto di no: {why}"
WHY = "_{reason}_"
TOTAL = "*Totale* {total} min su {budget}"

PARSE_MODE = "MarkdownV2"
"""The dialect `proposal` writes and `_offering` sends a plan as."""


def proposal(plan: plans.WorkoutPlan, budget_min: int) -> str:
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

    with tools.reported(), tools.opened() as connection:
        reading = plans.shown(connection, plan, plans.to_blocks(plan), budget_min)

    lines: list[str] = []
    for block in reading.blocks:
        lines.append(
            HEADING.format(
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
                    name=marked(item.name), prescription=marked(item.prescription)
                )
            )
            if item.said is not None:
                # Its own line and marked, not folded into the block's reason:
                # this is the agent proposing something the user said no to,
                # and it has to be the thing they notice.
                lines.append(SAID_NO.format(why=marked(item.said)))
        lines.append(WHY.format(reason=marked(block.reason)))
        lines.append("")
    lines.append(TOTAL.format(total=reading.total_min, budget=reading.budget_min))
    return "\n".join(lines)


def _reading(thread: str) -> RunnableConfig:
    """A thread, for a call that only reads: it writes no checkpoint to stamp."""
    return {"configurable": {"thread_id": thread}}


def turns(graph: planner.Planner, thread: str) -> list[str]:
    """What the user has written on this thread, in the order they wrote it."""
    said: list[str] = graph.get_state(_reading(thread)).values.get("said", [])
    return list(said)


def application(declared: Settings, coach: Coach) -> Application[Any, Any, Any, Any, Any, Any]:
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


def _on_start(coach: Coach) -> Handler:
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        who = _who(update)
        if who is None:
            return
        user_id, chat_id = who
        await coach.started(user_id, chat_id, chatting(context, chat_id))

    return handle


def _on_message(coach: Coach) -> Handler:
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        who = _who(update)
        # `effective_message` rather than `message`: which field carried the
        # text is the filter's business, and a body that reads only `message`
        # goes silent on anything the filter lets through in another one.
        message = update.effective_message
        if who is None or message is None or not message.text:
            return
        user_id, chat_id = who
        await coach.arriving(user_id, chat_id, message.text, chatting(context, chat_id))

    return handle


def _on_tap(coach: Coach) -> Handler:
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
        await coach.tapped(user_id, chat_id, tap.data, chatting(context, chat_id))

    return handle


def _who(update: Update) -> tuple[int, int] | None:
    """Who sent it and where, or nothing at all.

    An update carries neither on some kinds -- a poll answer, a channel post --
    and there is nobody to answer and no thread to run on. `Coach` decides
    whether the user is the owner; this only decides whether there is a user.
    """
    if update.effective_user is None or update.effective_chat is None:
        return None
    return update.effective_user.id, update.effective_chat.id


def chatting(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Chat:
    """One chat's three channels, built once per update.

    The draft id is minted here, so it is one per turn and therefore one per
    run: a queued turn arrives with a chat of its own, and two runs sharing an
    id would animate each other's progress into one preview.
    """
    return Chat(
        say=_saying(context, chat_id),
        offer=_offering(context, chat_id),
        draft=_drafting(context, chat_id),
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
            ),
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


def serve(
    declared: Settings, on: models.Chat, saver: BaseCheckpointSaver[Any]
) -> None:
    """Long-poll until interrupted, holding the model, the checkpointer and the graph.

    All three for the life of the process (ADR-0004, item 6): the compiled
    graph is what the threads are stored against.

    The checkpointer is opened by the caller rather than here, the way every
    command opens its database. It is the one thing in the startup block that
    can be refused -- pointed at the training database it is a `CheckpointError`
    -- and opened inside this call the whole block has already been printed,
    telling the user the process is healthy immediately before it is not.
    """
    archive = run_record.archive()
    graph = planner.build(on, checkpointer=saver, archive=archive)
    coach = Coach(
        owner_id=declared.owner_id,
        run=planning(graph, archive),
        resume=answering(graph, archive),
    )
    application(declared, coach).run_polling()
