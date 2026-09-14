"""The Telegram bot: long-polls from the graph's process, and answers only the owner."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from trainer.coach import models, planner

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import Application, ContextTypes

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
OWNER_ENV = "TELEGRAM_OWNER_ID"

EXAMPLE = ".env.example"
"""Where both settings are documented, named by every state that misses one."""

logger = logging.getLogger(__name__)

STARTED = "Sono il tuo allenatore. Scrivimi quando vuoi."

RECEIVED = "Ricevuto. Ancora non so pianificare: per ora tengo il filo del discorso."
"""What ticket 01 can honestly answer.

The plan arrives in the chat in ticket 02, against the request ticket 04
assembles. Until then the bot says what is true rather than staying silent,
which reads as a bot that is down.
"""

QUEUED = "Sto ancora lavorando a quello di prima. Questo lo faccio subito dopo."

FAILED = "Qualcosa è andato storto mentre ci lavoravo. Riprova."
"""Said when a run raises.

A provider that falls over mid-run is the ordinary case on a laptop, and the
user is looking at a phone. An exception that reaches only the log is a bot
that has stopped answering, which is the thing `RECEIVED` exists to avoid.
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

    Never from `training.toml`, which holds the four things the user declares
    about their training (ADR-0003). A token is a credential and an owner id is
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


def thread_for(chat_id: int) -> str:
    """One chat is one thread (ADR-0004, item 6).

    Derived from the chat id rather than invented per run, which is what lets
    the conversation survive a restart: the checkpointer is on disk, and the
    next process computes the same thread id for the same chat.
    """
    return f"chat:{chat_id}"


Say = Callable[[str], Awaitable[None]]
"""One line into the chat. The bot's side of a conversation, as a function, so
what decides can be driven by a test that collects the lines instead of sending
them."""

Run = Callable[[str, str, Say], Awaitable[None]]
"""The work one message causes, on one thread. Ticket 01's is `recording`;
ticket 02 replaces it with the planner graph streaming its progress."""


@dataclass
class _Conversation:
    """One chat's turn-taking: whether a run is in flight, and what arrived during it."""

    busy: bool = False
    waiting: list[str] = field(default_factory=list)


class Coach:
    """One run at a time per thread, for the owner and nobody else."""

    def __init__(self, owner_id: int, run: Run) -> None:
        self._owner_id = owner_id
        self._run = run
        self._threads: dict[str, _Conversation] = {}

    async def started(self, user_id: int, chat_id: int, say: Say) -> None:
        """Answer `/start`, if the owner sent it."""
        if not self._answers(user_id):
            return
        await self._tell(thread_for(chat_id), say, STARTED)

    async def arriving(self, user_id: int, chat_id: int, text: str, say: Say) -> None:
        """One message, run now or queued behind the run already in flight.

        Queued rather than dropped, and never a second run on the same thread:
        on Ollama a run is minutes, and cancelling one to start another throws
        all of them away. *"Actually, 30 minutes"* is not this -- it is the
        interrupt ticket 03 builds, which resumes the run instead of racing it.
        """
        if not self._answers(user_id):
            return
        thread = thread_for(chat_id)
        conversation = self._threads.setdefault(thread, _Conversation())
        if conversation.busy:
            # Queued before the acknowledgement is attempted, not after: a chat
            # that cannot be written to must not also cost the message.
            conversation.waiting.append(text)
            await self._tell(thread, say, QUEUED)
            return

        conversation.busy = True
        try:
            queued: str | None = text
            while queued is not None:
                await self._attempt(thread, queued, say)
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

    async def _attempt(self, thread: str, text: str, say: Say) -> None:
        """One run, with its failure said out loud instead of left as silence.

        Caught per message rather than around the queue: one run that fell over
        must not cancel the messages behind it, which were promised an answer.
        """
        try:
            await self._run(thread, text, say)
        except Exception:
            logger.exception("the run on %s failed", thread)
            await self._tell(thread, say, FAILED)

    async def _tell(self, thread: str, say: Say, line: str) -> None:
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
            await say(line)
        except Exception:
            logger.exception("could not write to %s", thread)

    def _answers(self, user_id: int) -> bool:
        """Whether this is the owner, checked before anything looks at the message."""
        if user_id == self._owner_id:
            return True
        logger.info("ignored an update from user %s", user_id)
        return False


def recording(graph: planner.Planner) -> Run:
    """Ticket 01's run: the turn goes into the thread, and the user gets an answer.

    The graph is held and its state is written, but no node runs. Planning
    needs a `plan.Request`, and assembling one is ticket 04's -- built here as
    well it would be the second copy of a thing this project has already been
    bitten by. What ticket 01 owes is the process, the thread and the queue.
    """

    async def record(thread: str, text: str, say: Say) -> None:
        graph.update_state(_on(thread), {"messages": [HumanMessage(text)]})
        await say(RECEIVED)

    return record


def _on(thread: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread}}


def turns(graph: planner.Planner, thread: str) -> list[str]:
    """What has been said on this thread, in the order it was said."""
    kept: list[AnyMessage] = graph.get_state(_on(thread)).values.get("messages", [])
    return [message.text for message in kept]


def application(declared: Settings, coach: Coach) -> Application[Any, Any, Any, Any, Any, Any]:
    """The Telegram application, with its handlers wired to `coach`.

    `concurrent_updates`, because the queue depends on it: processed one at a
    time, the second message is not even received until the run it is supposed
    to be queued behind has finished, and there is nothing left to acknowledge.
    """
    # Imported here rather than at the top: `trainer --help` should not pay for
    # an HTTP stack nobody asked to start, which is why `trainer mcp` imports
    # its server the same way.
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler

    built = (
        ApplicationBuilder().token(declared.token).concurrent_updates(True).build()
    )
    built.add_handler(CommandHandler("start", _on_start(coach)))
    built.add_handler(MessageHandler(messages_only(), _on_message(coach)))
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
        await coach.started(user_id, chat_id, _saying(context, chat_id))

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
        await coach.arriving(user_id, chat_id, message.text, _saying(context, chat_id))

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


def _saying(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Say:
    async def say(line: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=line)

    return say


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
    graph = planner.build(on.model, checkpointer=saver)
    coach = Coach(owner_id=declared.owner_id, run=recording(graph))
    application(declared, coach).run_polling()
