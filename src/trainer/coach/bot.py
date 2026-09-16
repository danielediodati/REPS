"""The Telegram bot: long-polls from the graph's process, and answers only the owner."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from trainer import plan as plans
from trainer import tools
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

WORKING = "Ci penso. Su questo portatile ci vuole qualche minuto."
"""Said before the run starts, because the run is minutes long.

Ticket 02 replaces this with the graph's progress streamed into a draft.
Until then one line is what stands between a plan being written and a bot
that looks like it has stopped answering.
"""

BLOCKED = "Non posso pianificare finché non sistemi questo:\n\n{state}"
"""A precondition the machine gets wrong, in the engine's own words.

No `training.toml`, so there is nothing to derive today's equipment, minutes
or groups from; no database; a catalog nobody enriched. Each already names
itself and the command that fixes it, and each is a **state** rather than a
run that fell over -- answered with `FAILED` it would read as the provider
having dropped the plan.

Quoted rather than re-phrased. `config.NoTrainingConfig` names the example
file to copy and the five things it declares, and a second wording of the same
state kept here is the one that goes stale.
"""

QUEUED = "Sto ancora lavorando a quello di prima. Questo lo faccio subito dopo."

FAILED = "Qualcosa è andato storto mentre ci lavoravo. Riprova."
"""Said when a run raises.

A provider that falls over mid-run is the ordinary case on a laptop, and the
user is looking at a phone. An exception that reaches only the log is a bot
that has stopped answering, which is the thing `WORKING` exists to avoid.
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

Run = Callable[[str, str, "Offer", Say], Awaitable[None]]
"""The work one message causes, on one thread: `planning` below.

It takes the `Offer` as well as the `Say`, because what a run produces is a
plan with buttons under it -- the same thing a resumed run produces, for the
same reason."""

Offer = Callable[[str, Sequence[tuple[str, str]]], Awaitable[None]]
"""A plan with its buttons: the text, and (callback data, label) pairs.
Telegram's own objects are built in `_offering`, so what decides stays as
testable as the rest."""

Resume = Callable[[str, "Tap", Say, Offer], Awaitable[None]]
"""The work one tap causes: it answers the interrupt the plan is waiting on."""

Turn = str | Tap
"""One piece of work on a thread: something the user wrote, or a button they tapped."""

Waiting = tuple[Turn, "Say", "Offer"]
"""A turn queued behind a run, with the channels it arrived on.

They travel with the turn rather than belonging to the run draining the queue:
a chat the plan is sent to is the chat the turn came from, and a queue drained
down somebody else's channel answers the wrong conversation.
"""


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

    async def started(self, user_id: int, chat_id: int, say: Say) -> None:
        """Answer `/start`, if the owner sent it."""
        if not self._answers(user_id):
            return
        await self._tell(thread_for(chat_id), say, STARTED)

    async def arriving(
        self, user_id: int, chat_id: int, text: str, say: Say, offer: Offer
    ) -> None:
        """One message, run now or queued behind the run already in flight.

        Queued rather than dropped, and never a second run on the same thread:
        on Ollama a run is minutes, and cancelling one to start another throws
        all of them away. *"Actually, 30 minutes"* is not this -- it is ticket
        03's interrupt, which resumes the run instead of racing it.
        """
        if not self._answers(user_id):
            return
        await self._turn(thread_for(chat_id), text, say, offer)

    async def tapped(
        self, user_id: int, chat_id: int, data: str, say: Say, offer: Offer
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
        await self._turn(tap.thread, tap, say, offer)

    async def _turn(self, thread: str, turn: Turn, say: Say, offer: Offer) -> None:
        conversation = self._threads.setdefault(thread, _Conversation())
        if conversation.busy:
            # Queued before the acknowledgement is attempted, not after: a chat
            # that cannot be written to must not also cost the message.
            conversation.waiting.append((turn, say, offer))
            await self._tell(thread, say, QUEUED)
            return

        conversation.busy = True
        try:
            queued: Waiting | None = (turn, say, offer)
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

    async def _attempt(self, thread: str, turn: Turn, say: Say, offer: Offer) -> None:
        """One run, with its failure said out loud instead of left as silence.

        Caught per message rather than around the queue: one run that fell over
        must not cancel the messages behind it, which were promised an answer.
        """
        try:
            if isinstance(turn, Tap):
                assert self._resume is not None, "a tap reached a coach with no graph"
                await self._resume(thread, turn, say, offer)
            else:
                await self._run(thread, turn, offer, say)
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


def planning(graph: planner.Planner) -> Run:
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
    before `WORKING` is said. Promising minutes of work and then answering
    with a state is worse than answering with the state.
    """

    async def run(thread: str, text: str, offer: Offer, say: Say) -> None:
        graph.update_state(_on(thread), {"said": [text]})
        try:
            request = await asyncio.to_thread(_todays_request)
        except tools.ToolFailure as state:
            await say(BLOCKED.format(state=state))
            return
        await say(WORKING)
        # Off the loop, for the reason `answering` runs its resume off it:
        # `invoke` is a synchronous round trip to the model, minutes of it on
        # Ollama, and run here it would block the process that is long-polling
        # Telegram.
        final = await asyncio.to_thread(
            graph.invoke, planner.starting(request), _on(thread)
        )
        await told(final, thread, say, offer)

    return run


def _todays_request() -> plans.Request:
    """Today's request, off the same function the terminal assembles it with."""
    with tools.reported(), tools.opened() as connection:
        return plans.requested(connection, date.today().isoformat()).request


def answering(graph: planner.Planner) -> Resume:
    """The tap, answered: the thread resumes and the run goes on from there (ADR-0005).

    The write is the graph's, in the node after the resume. Nothing here
    touches the database, which is what keeps the interface out of the
    training facts.
    """

    async def resume(thread: str, tap: Tap, say: Say, offer: Offer) -> None:
        pending = graph.get_state(_on(thread)).interrupts
        if not pending or pending[0].id != tap.proposal:
            # The thread has moved on, or this plan was already answered. A
            # tap on it is a question about a plan that is no longer the one
            # in hand, and silence would read as a bot that is down.
            await say(SUPERSEDED)
            return
        # Off the loop, because `invoke` is a synchronous round trip to the
        # model -- minutes of it on Ollama. Run here, it would block the
        # process that is long-polling Telegram: no second tap, no message
        # queued, not even the acknowledgement promising one, until the plan
        # came back. The queue exists precisely so that a run in flight does
        # not cost the bot its answers.
        final = await asyncio.to_thread(
            graph.invoke, Command(resume=_answer(tap)), _on(thread)
        )
        await told(final, thread, say, offer)

    return resume


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


async def told(
    final: dict[str, Any], thread: str, say: Say, offer: Offer
) -> None:
    """What the chat is told when a run stops: a plan to answer, the workout, or neither."""
    waiting = final.get("__interrupt__")
    if waiting:
        proposed = final["plan"]
        await offer(
            proposal(proposed, final["request"].budget_min),
            [
                (carried(Tap(action, thread, waiting[0].id)), label)
                for action, label in BUTTONS
            ],
        )
    elif final.get("workout") is not None:
        await say(WRITTEN)
    else:
        # Every attempt refused by the validator. There is no plan to offer,
        # and saying nothing would leave the user waiting on a run that ended.
        await say(NO_PLAN)


def proposal(plan: plans.WorkoutPlan, budget_min: int) -> str:
    """The plan as the chat shows it.

    The terminal's lines, for now: ticket 02 owns how a plan reads in
    Telegram, and a second rendering written here is the one that would be
    left behind when it lands.
    """
    with tools.reported(), tools.opened() as connection:
        return "\n".join(
            plans.render(connection, plan, plans.to_blocks(plan), budget_min)
        )


def _on(thread: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread}}


def turns(graph: planner.Planner, thread: str) -> list[str]:
    """What the user has written on this thread, in the order they wrote it."""
    said: list[str] = graph.get_state(_on(thread)).values.get("said", [])
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
        await coach.arriving(
            user_id,
            chat_id,
            message.text,
            _saying(context, chat_id),
            _offering(context, chat_id),
        )

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
        await coach.tapped(
            user_id, chat_id, tap.data, _saying(context, chat_id), _offering(context, chat_id)
        )

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


def _offering(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Offer:
    """A plan with its buttons, in one row per answer."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    async def offer(text: str, buttons: Sequence[tuple[str, str]]) -> None:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(label, callback_data=data)]
                    for data, label in buttons
                ]
            ),
        )

    return offer


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
    coach = Coach(
        owner_id=declared.owner_id, run=planning(graph), resume=answering(graph)
    )
    application(declared, coach).run_polling()
