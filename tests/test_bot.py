"""The bot: who it answers, which thread a chat is, and what a message that arrives mid-run becomes.

Offline, like the rest of the suite. The Telegram client is never built: what
is driven here is the part that decides, with the updates constructed by hand.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage
from telegram import Bot, CallbackQuery, Chat, Message, Update, User
from telegram.error import InvalidToken, RetryAfter, TimedOut

from langgraph.checkpoint.memory import InMemorySaver

from conftest import enrich
from trainer import tools
from trainer import plan as plans
from trainer import tools
from test_logger import graph_of as logger_graph_of
from test_logger import prescribe, proposing, report, scripted
from test_planner import (
    BARBELL_45,
    CATALOG,
    PATTERNS,
    SCRIPTED,
    STAND_IN,
    Scripted,
    calling,
    graph_of,
    mesocycle_of,
    plan_of,
)
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from trainer.coach import bot, checkpoints, entrance, logfile, models, onboarding, planner, progress
from trainer.coach import logger as coach_logger
from trainer.coach import record as run_record
from trainer.engine import catalog, config, database, exclusions, mesocycles, migrations, workouts

OWNER = 6421
STRANGER = 99
CHAT = 6421

FIXTURE_SPLIT = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
goal = "hypertrophy"
split = [["legs"], ["shoulders"]]
equipment = ["barbell"]
"""
"""A declaration `CATALOG` can answer.

It holds one barbell squat (legs) and one barbell press (shoulders), so a
rotation over those two groups with barbell declared is one the admissible set
is not empty for -- which is what lets a run here reach a plan instead of a
refusal about a group nothing covers. The suite's own `DECLARED_CONFIG` trains
chest and arms, which this catalog has nothing barbell for.
"""


A_MESOCYCLE = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))
"""What the planner offers when the chat asks for a mesocycle against `FIXTURE_SPLIT`."""


@pytest.fixture()
def declared(declared_training: Path) -> Path:
    """The suite's configuration, rewritten to what this catalog can train."""
    declared_training.write_text(FIXTURE_SPLIT, encoding="utf-8")
    return declared_training


def spoken() -> tuple[list[str], bot.Say]:
    """A chat that remembers what was said into it."""
    said: list[str] = []

    async def say(line: str) -> None:
        said.append(line)

    return said, say


class Channels:
    """One chat, remembering everything that went down each of its three channels."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.offers: list[tuple[str, list[tuple[str, str]]]] = []
        self.drafts: list[str] = []
        self.chat = bot.Chat(say=self._say, offer=self._offer, draft=self._draft)

    async def _say(self, line: str) -> None:
        self.said.append(line)

    async def _offer(self, text: str, buttons: Any) -> None:
        self.offers.append((text, list(buttons)))

    async def _draft(self, text: str) -> None:
        self.drafts.append(text)


def channel(say: bot.Say | None = None, offer: bot.Offer | None = None) -> bot.Chat:
    """A chat built out of whichever channels a test is watching."""
    watched = Channels()
    return bot.Chat(
        say=say if say is not None else watched.chat.say,
        offer=offer if offer is not None else watched.chat.offer,
        draft=watched.chat.draft,
    )


async def never(thread: str, text: str, chat: bot.Chat) -> None:
    """A run that must not happen. Whatever refused it should have refused it first."""
    raise AssertionError(f"a run started on {thread} for {text!r}")


async def nowhere(text: str, buttons: Any) -> None:
    """The offer channel, where a test is not looking at what goes down it."""
    raise AssertionError(f"a plan was offered: {text!r}")


async def echoed(thread: str, situation: str, chat: bot.Chat) -> None:
    """A relay that says the situation itself.

    For the tests watching the turn-taking rather than the entrance: what goes
    into the chat is the model's sentence, and what this asserts is *which
    situation was put to it*.
    """
    await chat.say(situation)


# -- the entrance, scripted ----------------------------------------------------

SAYS = "ci penso"
"""What the stand-in entrance answers when the script asks nothing else of it."""

MACHINE = "machine"
"""The name the entrance puts on a turn the machine opened, as `entrance.talk` sets it."""

FRONT_MODEL = "a-small-fast-one"
FRONT_PROVIDER = "front"
"""What the entrance runs on here, named apart from the subgraphs' stand-in:
the run document has to say which model answered which node, and two graphs
under one name could not show that."""


class Talking(BaseChatModel):
    """The entrance, scripted: what it reaches for, and what it says.

    A turn the machine opened is answered by handing the situation straight
    back, so a test asserts *which situation was put to the model* rather than
    which constant reached the chat -- which is the whole of ADR-0006.
    """

    handoff: str = ""
    """The subgraph every user turn reaches for, or nothing to answer directly."""

    says: str = SAYS
    turns: list[AIMessage] = []
    """Turns written in advance, taken before `handoff` is looked at."""

    seen: list[list[BaseMessage]] = []
    bound: list[list[str]] = []

    @property
    def _llm_type(self) -> str:
        return "talking"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self._turn(messages))])

    def _turn(self, messages: list[BaseMessage]) -> AIMessage:
        last = messages[-1]
        if isinstance(last, HumanMessage) and last.name == MACHINE:
            # The situation is the last paragraph of what it was handed.
            return AIMessage(content=last.text.split("\n\n")[-1])
        if self.turns:
            return self.turns.pop(0)
        if isinstance(last, HumanMessage) and self.handoff:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self.handoff,
                        "args": {},
                        "id": f"call_{self.handoff}",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content=self.says)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self.bound.append(
            [str(one.get("function", {}).get("name", "")) for one in tools]  # type: ignore[union-attr]
        )
        return self.bind(tools=tools, **kwargs)


def graphs_of(
    plan: planner.Planner | None = None,
    *,
    front: BaseChatModel | None = None,
    log: coach_logger.Logger | None = None,
    interview: onboarding.Onboarding | None = None,
    saver: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
) -> bot.Graphs:
    """The three graphs the bot holds, each on a stand-in.

    The entrance hands off to the planner unless a test says otherwise,
    because that is what most of this file is about: what happens once a
    message has been decided to be a request for today's workout.

    All three are checkpointed even when a test brought no saver, the way the
    bot holds them: the door reads the logger's pending question off its
    checkpoint before it decides what a message is, and an uncheckpointed
    graph has no state to read.
    """
    kept = archive if archive is not None else run_record.archive()
    held = saver if saver is not None else InMemorySaver()
    plans_on = plan if plan is not None else graph_of(Scripted(), checkpointer=held)
    preparing: set[str] = set()
    return bot.Graphs(
        entrance=entrance.build(
            models.Chat(
                front if front is not None else Talking(handoff=entrance.PLAN_MESOCYCLE),
                FRONT_PROVIDER,
                FRONT_MODEL,
            ),
            checkpointer=held,
            archive=kept,
            prepared=bot.prepared(plans_on, preparing),
        ),
        planner=plans_on,
        logger=log if log is not None else logger_graph_of(Scripted(), checkpointer=held),
        onboarding=interview
        if interview is not None
        else onboarding.build(
            models.Chat(Scripted(), FRONT_PROVIDER, FRONT_MODEL), checkpointer=held
        ),
        archive=kept,
        preparing=preparing,
    )


def turns_of(graphs: bot.Graphs) -> bot.Turns:
    """The turn-taking, wired to these graphs exactly as `bot.serve` wires it."""
    return bot.Turns(
        owner_id=OWNER,
        run=bot.talking(graphs),
        resume=bot.answering(graphs),
        relay=bot.relaying(graphs),
    )


# -- the settings --------------------------------------------------------------


def test_a_missing_token_names_the_variable_and_where_to_put_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`conftest.py` takes every credential away, so this is the state under
    test rather than something about this machine."""
    monkeypatch.setenv(bot.OWNER_ENV, str(OWNER))

    with pytest.raises(bot.BotError) as raised:
        bot.settings()

    assert bot.TOKEN_ENV in str(raised.value)
    assert ".env.example" in str(raised.value)


def test_a_missing_owner_names_the_variable_and_where_to_put_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(bot.TOKEN_ENV, "123:a-stand-in")
    monkeypatch.delenv(bot.OWNER_ENV, raising=False)

    with pytest.raises(bot.BotError) as raised:
        bot.settings()

    assert bot.OWNER_ENV in str(raised.value)
    assert ".env.example" in str(raised.value)


def test_an_owner_that_is_not_a_number_is_a_state_and_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user id is a number and a username is not, and reaching for the handle
    you know is the obvious mistake. Left to `int`, it arrives as a ValueError
    about base 10."""
    monkeypatch.setenv(bot.TOKEN_ENV, "123:a-stand-in")
    monkeypatch.setenv(bot.OWNER_ENV, "@daniele")

    with pytest.raises(bot.BotError) as raised:
        bot.settings()

    assert bot.OWNER_ENV in str(raised.value)
    assert "@daniele" in str(raised.value)


def test_the_settings_that_are_there_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(bot.TOKEN_ENV, "123:a-stand-in")
    monkeypatch.setenv(bot.OWNER_ENV, str(OWNER))

    declared = bot.settings()

    assert declared.token == "123:a-stand-in"
    assert declared.owner_id == OWNER


# -- the token, as Telegram sees it --------------------------------------------


def test_a_token_telegram_refuses_is_a_state_naming_botfather(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PTB's own message quotes the token, so the state must not carry it."""

    async def refused(self: Any, *args: Any, **kwargs: Any) -> User:
        raise InvalidToken("The token `123:a-stand-in` was rejected by the server.")

    monkeypatch.setattr(Bot, "get_me", refused)

    with pytest.raises(bot.BotError) as raised:
        bot.identified(bot.Settings(token="123:a-stand-in", owner_id=OWNER))

    assert "@BotFather" in str(raised.value)
    assert "a-stand-in" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_telegram_out_of_reach_is_a_state_and_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unreachable(self: Any, *args: Any, **kwargs: Any) -> User:
        raise TimedOut("Timed out")

    monkeypatch.setattr(Bot, "get_me", unreachable)

    with pytest.raises(bot.BotError, match="cannot be reached"):
        bot.identified(bot.Settings(token="123:a-stand-in", owner_id=OWNER))


def test_flood_control_on_the_check_is_a_state_and_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`RetryAfter` is neither a refused token nor a network error."""
    # The library warns about its own `retry_after` type unless opted in.
    monkeypatch.setenv("PTB_TIMEDELTA", "1")

    async def flooded(self: Any, *args: Any, **kwargs: Any) -> User:
        raise RetryAfter(timedelta(seconds=30))

    monkeypatch.setattr(Bot, "get_me", flooded)

    with pytest.raises(bot.BotError, match="start it again later"):
        bot.identified(bot.Settings(token="123:a-stand-in", owner_id=OWNER))


def test_the_check_closes_the_connection_it_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Bot.shutdown` is a no-op on a bot that was never initialized."""
    checked: list[Bot] = []

    async def known(self: Bot, *args: Any, **kwargs: Any) -> User:
        checked.append(self)
        return User(id=1, is_bot=True, first_name="REPS", username="reps_coach_bot")

    monkeypatch.setattr(Bot, "get_me", known)

    bot.identified(bot.Settings(token="123:a-stand-in", owner_id=OWNER))

    assert checked
    assert all(request._client.is_closed for request in checked[0]._request)  # type: ignore[attr-defined]


def test_a_token_telegram_knows_is_answered_with_the_bots_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def known(self: Any, *args: Any, **kwargs: Any) -> User:
        return User(id=1, is_bot=True, first_name="REPS", username="reps_coach_bot")

    monkeypatch.setattr(Bot, "get_me", known)

    assert bot.identified(bot.Settings(token="123:a-stand-in", owner_id=OWNER)) == (
        "@reps_coach_bot"
    )


# -- one chat is one thread ----------------------------------------------------


def test_a_chat_is_always_the_same_thread() -> None:
    """The thread is derived from the chat id and never invented, which is what
    lets the conversation survive a restart: the checkpointer is on disk."""
    assert bot.thread_for(CHAT) == bot.thread_for(CHAT)
    assert bot.thread_for(CHAT) != bot.thread_for(CHAT + 1)
    assert str(CHAT) in bot.thread_for(CHAT)


# -- the owner, and nobody else ------------------------------------------------


def test_a_message_from_anybody_else_is_answered_with_nothing() -> None:
    said, say = spoken()
    coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)

    asyncio.run(coach.arriving(STRANGER, CHAT, "ciao", channel(say, nowhere)))

    assert said == []


def test_start_from_anybody_else_is_answered_with_nothing() -> None:
    """Checked before anything else looks at the message, so the command a
    stranger sends is as ignored as the prose."""
    said, say = spoken()
    coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)

    asyncio.run(coach.started(STRANGER, CHAT, channel(say)))

    assert said == []


def test_start_answers_the_owner() -> None:
    said, say = spoken()
    coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)

    asyncio.run(coach.started(OWNER, CHAT, channel(say)))

    assert said == [entrance.HELLO]


def test_a_stranger_leaves_nothing_in_the_thread(
    tmp_path: Path, database_file: Path
) -> None:
    """Not just unanswered: a message nobody may send must not reach the state
    either, or the next run plans against a sentence the owner never wrote."""
    said, say = spoken()
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = graph_of(Scripted(), checkpointer=saver)
        graphs = graphs_of(graph)
        coach = turns_of(graphs)

        asyncio.run(coach.arriving(STRANGER, CHAT, "pianifica per me", channel(say, nowhere)))

        assert said == []
        assert bot.turns(graph, bot.thread_for(CHAT)) == []


# -- a message arriving while a run is in flight -------------------------------


def test_a_second_message_during_a_run_is_queued_and_then_answered() -> None:
    """Queued and acknowledged, never dropped and never a second run on the
    same thread: on Ollama a restart throws away minutes of work."""

    async def scenario() -> list[str]:
        said, say = spoken()
        started, release = asyncio.Event(), asyncio.Event()
        inside = 0

        async def slow(
            thread: str, text: str, chat: bot.Chat
        ) -> None:
            nonlocal inside
            inside += 1
            assert inside == 1, "two runs at once on one thread"
            started.set()
            await release.wait()
            await say(f"fatto: {text}")
            inside -= 1

        coach = bot.Turns(owner_id=OWNER, run=slow, relay=echoed)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        await started.wait()

        await coach.arriving(OWNER, CHAT, "due", channel(say, nowhere))
        assert said == [entrance.QUEUED], "the second message was dropped"

        release.set()
        await first
        return said

    assert asyncio.run(scenario()) == [entrance.QUEUED, "fatto: uno", "fatto: due"]


def test_a_run_that_fails_does_not_wedge_the_thread() -> None:
    """The next message has to be answerable. A flag left set by an exception
    is a bot that says *in coda* forever and never runs again."""

    async def scenario() -> list[str]:
        said, say = spoken()
        runs = 0

        async def sometimes(
            thread: str, text: str, chat: bot.Chat
        ) -> None:
            """The same coach, so the flag the first run left is the one the
            second message meets."""
            nonlocal runs
            runs += 1
            if runs == 1:
                raise RuntimeError("the provider went away")
            await say(f"fatto: {text}")

        coach = bot.Turns(owner_id=OWNER, run=sometimes, relay=echoed)
        await coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere))
        await coach.arriving(OWNER, CHAT, "due", channel(say, nowhere))
        return said

    assert asyncio.run(scenario()) == [bot.FAILED, "fatto: due"]


def test_a_message_queued_behind_a_run_that_fails_is_still_answered() -> None:
    """The flag was cleared and the queue was not.

    So a message the bot had just promised *subito dopo* was never run at all
    -- and was not dropped either: the next thing the user said drained it
    afterwards, running a sentence from before against a context that had
    moved on.
    """

    async def scenario() -> list[str]:
        said, say = spoken()
        started, release = asyncio.Event(), asyncio.Event()

        async def falls_over(
            thread: str, text: str, chat: bot.Chat
        ) -> None:
            if text == "uno":
                started.set()
                await release.wait()
                raise RuntimeError("the provider went away")
            await say(f"fatto: {text}")

        coach = bot.Turns(owner_id=OWNER, run=falls_over, relay=echoed)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        await started.wait()
        await coach.arriving(OWNER, CHAT, "due", channel(say, nowhere))

        release.set()
        await first
        return said

    assert asyncio.run(scenario()) == [entrance.QUEUED, bot.FAILED, "fatto: due"]


def test_a_chat_that_cannot_be_written_to_does_not_take_the_queue_with_it() -> None:
    """Measured in the field, on the first real run: the send timed out inside
    `say`, so saying *it went wrong* went down the channel that had just gone
    wrong and raised again -- out of `arriving`, dropping what was queued.

    Nothing reaches the user here, because nothing can. What is under test is
    that the bot is still running and still working through its queue.
    """

    async def scenario() -> list[str]:
        attempted: list[str] = []
        started, release = asyncio.Event(), asyncio.Event()

        async def unreachable(line: str) -> None:
            raise RuntimeError("Timed out")

        async def run(
            thread: str, text: str, chat: bot.Chat
        ) -> None:
            attempted.append(text)
            if text == "uno":
                started.set()
                await release.wait()
            await chat.say(f"fatto: {text}")

        coach = bot.Turns(owner_id=OWNER, run=run, relay=echoed)
        first = asyncio.create_task(
            coach.arriving(OWNER, CHAT, "uno", channel(unreachable, nowhere))
        )
        await started.wait()
        await coach.arriving(OWNER, CHAT, "due", channel(unreachable, nowhere))

        release.set()
        await first
        return attempted

    assert asyncio.run(scenario()) == ["uno", "due"]


def test_start_survives_a_chat_that_cannot_be_written_to() -> None:
    async def scenario() -> None:
        async def unreachable(line: str) -> None:
            raise RuntimeError("Timed out")

        coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)
        await coach.started(OWNER, CHAT, channel(unreachable))

    asyncio.run(scenario())


def test_two_chats_do_not_wait_for_each_other() -> None:
    """The queue is per thread. One chat is one conversation, and a bot that
    serialised every chat would be a queue nobody asked for -- there is one
    owner today, and the same bot answers the group it is added to tomorrow."""

    async def scenario() -> list[str]:
        said, say = spoken()
        started, release = asyncio.Event(), asyncio.Event()

        async def slow(
            thread: str, text: str, chat: bot.Chat
        ) -> None:
            if text == "uno":
                started.set()
                await release.wait()
            await say(f"fatto: {text}")

        coach = bot.Turns(owner_id=OWNER, run=slow, relay=echoed)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        # Waited for rather than yielded to once: ticket 02 puts a graph run
        # behind this, and the first `await` it adds ahead of `release` would
        # make the order below flaky instead of red.
        await started.wait()
        await coach.arriving(OWNER, CHAT + 1, "due", channel(say, nowhere))
        release.set()
        await first
        return said

    assert asyncio.run(scenario()) == ["fatto: due", "fatto: uno"]


# -- across a restart ----------------------------------------------------------


def test_the_thread_survives_a_restart(
    tmp_path: Path, catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Two compiled graphs over one checkpoint file, the way two runs of
    `trainer bot` are. The conversation is the checkpointer's (ADR-0004, item
    5), so the second process finds what the first was told."""
    path = tmp_path / "checkpoints.sqlite"
    written: list[plans.WorkoutPlan | plans.Mesocycle] = [A_MESOCYCLE, A_MESOCYCLE]

    with checkpoints.saver(path) as saver:
        graph = graph_of(Scripted(documents=written[:1]), checkpointer=saver)
        graphs = graphs_of(graph, saver=saver)
        coach = turns_of(graphs)
        first = Channels()
        asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", first.chat))

    with checkpoints.saver(path) as saver:
        graph = graph_of(Scripted(documents=written[1:]), checkpointer=saver)
        graphs = graphs_of(graph, saver=saver)
        coach = turns_of(graphs)
        second = Channels()
        asyncio.run(coach.arriving(OWNER, CHAT, "e domani?", second.chat))

        assert bot.turns(graphs.entrance, bot.thread_for(CHAT)) == [
            "cosa faccio oggi?",
            "e domani?",
        ]
        # The turns alone would pass over two runs that never happened: they
        # are written before the run starts, and a run that falls over is
        # answered with `FAILED` rather than raised. Both plans, or nothing.
        assert first.offers and second.offers


def test_two_chats_are_two_threads(
    tmp_path: Path, catalogued: sqlite3.Connection, declared: Path
) -> None:
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = graph_of(
            Scripted(documents=[A_MESOCYCLE, A_MESOCYCLE]),
            checkpointer=saver,
        )
        graphs = graphs_of(graph, saver=saver)
        coach = turns_of(graphs)
        asyncio.run(coach.arriving(OWNER, CHAT, "la mia", Channels().chat))
        asyncio.run(
            coach.arriving(OWNER, CHAT + 1, "l'altra", Channels().chat)
        )

        assert bot.turns(graphs.entrance, bot.thread_for(CHAT)) == ["la mia"]
        assert bot.turns(graphs.entrance, bot.thread_for(CHAT + 1)) == ["l'altra"]


# -- what am I doing today? ----------------------------------------------------


def asking(graphs: bot.Graphs, text: str = "cosa faccio oggi?") -> Channels:
    """The owner asks, on their own chat. Everything that came back, by channel."""
    watched = Channels()
    coach = turns_of(graphs)
    asyncio.run(coach.arriving(OWNER, CHAT, text, watched.chat))
    return watched


def planning_on(chat_id: int = CHAT) -> RunnableConfig:
    """The thread the planner runs on for this chat, as a config to read it with."""
    return {
        "configurable": {"thread_id": bot.under(bot.thread_for(chat_id), bot.PLANNING)}
    }


def logging_on(chat_id: int = CHAT) -> RunnableConfig:
    """The thread the logger runs on for this chat."""
    return {
        "configurable": {"thread_id": bot.under(bot.thread_for(chat_id), bot.LOGGING)}
    }


def test_asking_for_a_mesocycle_reaches_it_whole_with_two_buttons(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Every slot is offered, and a mesocycle is kept or turned down: a
    shorter one is an adaptation of a day (10.3), not of it."""
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]), checkpointer=InMemorySaver()
    )

    watched = asking(graphs_of(graph), "preparami un mesociclo")

    assert watched.said == [SAYS], "the entrance answers; the mesocycle is offered"
    (text, buttons) = watched.offers[0]
    assert "Barbell Squat" in text and "Standing Military Press" in text
    assert "4 cicli" in text
    assert [label for _, label in buttons] == [label for _, label in bot.MESOCYCLE_BUTTONS]


def test_the_request_the_chat_planned_against_was_derived_and_not_asked_for(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Nothing in the message says barbell, 45 minutes, legs or shoulders."""
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]), checkpointer=InMemorySaver()
    )

    asking(graphs_of(graph))

    # Read back through the checkpointer, which is where the tuples the
    # request is built out of arrive as lists: msgpack has one sequence.
    planned = graph.get_state(planning_on()).values["request"]
    assert [list(slot.groups) for slot in planned.slots] == [["legs"], ["shoulders"]]
    assert [slot.budget_min for slot in planned.slots] == [45, 45]
    assert [list(slot.equipment) for slot in planned.slots] == [["barbell"], ["barbell"]]


def test_the_chat_and_the_terminal_plan_against_one_request(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The chat passes an empty `Asked` and `trainer plan --mesocycle` passes
    what its flags collected; against the same state the two are one request.
    Compared field by field because the chat's comes back through the
    checkpointer, where every tuple arrives as a list.
    """
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]), checkpointer=InMemorySaver()
    )

    asking(graphs_of(graph))

    from_the_chat = graph.get_state(planning_on()).values["request"]
    from_the_terminal = plans.mesocycle_requested(
        catalogued, date.today().isoformat(), plans.Asked()
    )
    for chat, terminal in zip(from_the_chat.slots, from_the_terminal.slots, strict=True):
        assert list(chat.equipment) == list(terminal.equipment)
        assert chat.budget_min == terminal.budget_min
        assert list(chat.groups) == list(terminal.groups)
        assert [tuple(share) for share in chat.allocation] == list(terminal.allocation)
        assert list(chat.preferences) == list(terminal.preferences)


def test_tapping_accept_on_the_mesocycle_keeps_it_and_prescribes_nothing(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Asked for, offered, accepted, kept -- by the graph, never by the bot.
    A workout is prescribed when it is served (ADR-0008 item 4)."""
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]), checkpointer=InMemorySaver()
    )
    thread = bot.thread_for(CHAT)
    graphs = graphs_of(graph)
    sent = asking(graphs).offers

    said, say = spoken()
    _, offer = offered()
    coach = turns_of(graphs)
    asyncio.run(coach.tapped(OWNER, CHAT, sent[0][1][0][0], channel(say, offer)))

    assert said == [entrance.KEPT]
    assert mesocycles.active(catalogued) is not None
    assert workout_rows(catalogued) == []
    assert bot.turns(graphs.entrance, thread) == ["cosa faccio oggi?"]


# -- what am I doing today? ----------------------------------------------------


def served_from(catalogued: sqlite3.Connection) -> bot.Graphs:
    """A kept mesocycle, and a chat whose every message asks what today is."""
    mesocycles.record_mesocycle(
        catalogued,
        tuple(
            tuple(
                workouts.PrescribedBlock(block=block, reason=shape.reason)
                for shape, block in zip(
                    workout.blocks, plans.to_blocks(workout), strict=True
                )
            )
            for workout in A_MESOCYCLE.workouts
        ),
        cycles=A_MESOCYCLE.cycles,
        why=A_MESOCYCLE.why,
        on=date.today().isoformat(),
    )
    return graphs_of(
        graph_of(Scripted(), checkpointer=InMemorySaver()),
        front=Talking(handoff=entrance.TODAYS_WORKOUT),
    )


def test_todays_workout_is_read_off_the_mesocycle_without_the_planner(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = served_from(catalogued)

    watched = asking(graphs)

    assert watched.said == [SAYS]
    ((text, buttons),) = watched.offers
    assert "Barbell Squat" in text and "Standing Military Press" not in text
    assert "ultimo carico: non lo so" in text
    assert buttons == [], "a served workout is not a proposal"
    assert graphs.planner.get_state(planning_on()).values == {}, "the planner ran"
    (written,) = workout_rows(catalogued)
    assert written[1] == "prescribed"


def test_the_entrance_is_told_there_is_a_workout_to_send(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = served_from(catalogued)

    asking(graphs)

    told = graphs.entrance.get_state(
        {"configurable": {"thread_id": bot.thread_for(CHAT)}}
    ).values["messages"]
    assert entrance.SERVING in [message.text for message in told]


def test_the_last_load_is_beside_the_exercise(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = served_from(catalogued)
    workouts.record_performed(
        catalogued,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id="Barbell_Squat",
                        unit="reps",
                        amount=5,
                        amount_source="reported",
                        load_kg=102.5,
                        load_kg_source="reported",
                    ),
                ),
                rounds=3,
                rounds_source="reported",
                rest=120,
                rest_source="reported",
            ),
        ),
        on="2026-09-01",
        report="squat",
    )
    workouts.record_performed(
        catalogued,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id="Standing_Military_Press",
                        unit="reps",
                        amount=5,
                        amount_source="reported",
                    ),
                ),
                rounds=3,
                rounds_source="reported",
                rest=120,
                rest_source="reported",
            ),
        ),
        on="2026-09-02",
        report="press",
    )

    ((text, _),) = asking(graphs).offers

    assert "Barbell Squat" in text
    assert "ultimo carico 102\\.5 kg" in text, "escaped: a dot is MarkdownV2 syntax"


def test_asked_twice_it_is_one_prescribed_workout(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = served_from(catalogued)

    first = asking(graphs).offers
    second = asking(graphs, "e oggi?").offers

    assert first == second
    assert len(workout_rows(catalogued)) == 1


def test_reporting_it_moves_the_next_serving_to_the_next_slot(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = served_from(catalogued)
    asking(graphs)
    (served,) = workout_rows(catalogued)
    workouts.record_performed(
        catalogued,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id="Barbell_Squat",
                        unit="reps",
                        amount=8,
                        amount_source="reported",
                    ),
                ),
                rounds=3,
                rounds_source="reported",
                rest=120,
                rest_source="reported",
            ),
        ),
        on=date.today().isoformat(),
        report="squat",
        workout_id=int(served[0]),
    )

    ((text, _),) = asking(graphs).offers

    assert "Standing Military Press" in text and "Barbell Squat" not in text
    assert [state for _, state in workout_rows(catalogued)] == ["performed", "prescribed"]


def test_with_no_mesocycle_the_entrance_offers_one_and_nothing_is_served(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = graphs_of(
        graph_of(Scripted(), checkpointer=InMemorySaver()),
        front=Talking(handoff=entrance.TODAYS_WORKOUT),
    )

    watched = asking(graphs)

    told = graphs.entrance.get_state(
        {"configurable": {"thread_id": bot.thread_for(CHAT)}}
    ).values["messages"]
    assert entrance.NO_MESOCYCLE in [message.text for message in told]
    assert watched.said == [SAYS]
    assert watched.offers == []
    assert workout_rows(catalogued) == []


def test_asking_again_supersedes_the_plan_still_waiting(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """A second question is a second plan, and the buttons under the first one
    stop answering anything -- which is what `SUPERSEDED` is for."""
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE, A_MESOCYCLE]),
        checkpointer=InMemorySaver(),
    )
    first = asking(graphs_of(graph)).offers
    second = asking(graphs_of(graph), "e adesso?").offers

    assert first[0][1][0][0] != second[0][1][0][0], "the same proposal id twice"
    said, say = spoken()
    _, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    asyncio.run(coach.tapped(OWNER, CHAT, first[0][1][0][0], channel(say, offer)))

    assert said == [entrance.SUPERSEDED]
    assert workout_rows(catalogued) == []


def test_a_second_question_is_planned_against_its_own_brief(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The thread keeps the messages of the run before it, and `turn` writes
    the brief only when it finds none. Left there, the second plan is asked
    for as a follow-up to a conversation about the first."""
    model = Scripted(documents=[A_MESOCYCLE, A_MESOCYCLE])
    graph = graph_of(model, checkpointer=InMemorySaver())

    asking(graphs_of(graph))
    briefs = sum("Plan the workout." in m.text for m in model.seen[-1])
    asking(graphs_of(graph), "e adesso?")

    assert sum("Plan the workout." in m.text for m in model.seen[-1]) == briefs


def test_with_nothing_declared_the_first_message_gets_the_first_question(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """ADR-0013: nothing declared is a state, and the interview is its fix.
    The entrance is not asked: there is nothing it could answer yet."""
    declared.unlink()
    saver = InMemorySaver()
    front = Talking(handoff=entrance.PLAN_MESOCYCLE)
    graphs = graphs_of(
        front=front,
        interview=interview_of(AIMessage(content="Per cosa ti alleni?"), saver=saver),
        saver=saver,
    )

    watched = asking(graphs, "ciao")

    assert watched.said == ["Per cosa ti alleni?"]
    assert front.seen == [], "no entrance turn"


def test_a_catalog_nobody_enriched_stops_the_run_before_it_starts(
    database_file: Path, declared: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The gap `/code-review` found: `trainer plan` had checked this itself
    since ticket 3.2 and the bot had no equivalent, so a machine that had
    imported but not enriched was promised minutes of planning and then given
    a run that fell over inside a tool call."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
    graph = graph_of(Scripted(), checkpointer=InMemorySaver())

    with caplog.at_level(logging.WARNING, logger="trainer.coach.bot"):
        watched = asking(graphs_of(graph))

    assert watched.offers == []
    assert watched.said == [SAYS, bot.BLOCKED]
    assert watched.drafts == []
    assert "trainer enrich derive" in caplog.text


def test_a_database_nobody_imported_stops_the_run_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The same path, on the other precondition a plan needs. `trainer bot`
    can start against a machine that has no catalog yet."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))
    graph = graph_of(Scripted(), checkpointer=InMemorySaver())

    with caplog.at_level(logging.WARNING, logger="trainer.coach.bot"):
        watched = asking(graphs_of(graph))

    assert watched.offers == []
    assert watched.said == [SAYS, bot.BLOCKED]
    assert "trainer db init" in caplog.text


def test_every_precondition_is_one_line_and_the_same_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which state it is must not be readable off the chat at all. Three
    different wordings would tell a reader of the chat as much as quoting the
    engine did, one guess at a time.
    """
    graph = graph_of(Scripted(), checkpointer=InMemorySaver())

    empty = tmp_path / "empty.sqlite"
    with closing(database.connect(empty)) as opened:
        migrations.migrate(opened, migrations.discover())
    monkeypatch.setenv("TRAINER_DB", str(empty))
    without_catalog = asking(graphs_of(graph)).said
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))
    without_database = asking(graphs_of(graph)).said

    assert without_catalog == without_database == [SAYS, bot.BLOCKED]


def test_the_blocked_line_has_nothing_to_substitute_into() -> None:
    """The bug this closes, in one line. `BLOCKED` used to end in `{state}`
    and was formatted with the engine's own sentence -- absolute paths and
    all -- on its way to a third party's servers. A constant with no slot in
    it cannot carry one again by accident.

    The three tests above are the other half: whatever the state, the chat
    gets this and only this.
    """
    assert "{" not in bot.BLOCKED


def test_both_lines_name_the_log_and_neither_carries_a_path() -> None:
    """*«dove gira il bot»* named no file. These name one, the same way, and
    still without saying where it is: an absolute path is what ticket 07/02
    kept out of the chat in the first place."""
    for line in (bot.BLOCKED, bot.FAILED):
        assert logfile.LOG_NAME in line
        assert str(logfile.log_path()) not in line
        assert "\\" not in line and "/" not in line


def test_a_state_that_stops_a_run_is_written_to_the_log_file(
    catalogued: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of `BLOCKED`: the chat is told there is something to fix,
    and the file the chat named holds which thing, with the path and the
    command that fixes it."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))
    logfile.start((bot.TOKEN_ENV, bot.OWNER_ENV))
    graph = graph_of(Scripted(), checkpointer=InMemorySaver())

    watched = asking(graphs_of(graph))

    written = logfile.log_path().read_text(encoding="utf-8")
    assert watched.said == [SAYS, bot.BLOCKED]
    assert "trainer db init" in written
    assert str(tmp_path / "absent.sqlite") in written
    assert "Traceback" in written


def test_a_run_that_falls_over_is_written_to_the_log_file(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """And the other half of `FAILED`. Without this the user is told to look
    at a file that says nothing about the evening they lost."""

    class Falling(Scripted):
        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("the provider fell over")

    logfile.start((bot.TOKEN_ENV, bot.OWNER_ENV))
    graph = graph_of(Falling(), checkpointer=InMemorySaver())

    watched = asking(graphs_of(graph))

    written = logfile.log_path().read_text(encoding="utf-8")
    assert watched.said == [SAYS, bot.FAILED]
    assert "RuntimeError: the provider fell over" in written
    assert "Traceback" in written


# -- the handlers, driven with updates constructed by hand ---------------------


def update_of(
    text: str, user_id: int = OWNER, chat_id: int = CHAT, edited: bool = False
) -> Update:
    """One Telegram update, built here. No client exists and nothing is sent."""
    message = Message(
        message_id=1,
        date=datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc),
        chat=Chat(id=chat_id, type=Chat.PRIVATE),
        from_user=User(id=user_id, is_bot=False, first_name="Daniele"),
        text=text,
    )
    if edited:
        return Update(update_id=1, edited_message=message)
    return Update(update_id=1, message=message)


class Sent:
    """The context a handler is passed, collecting what would have been sent.

    It stands in for the bot as well, because a tap is answered on the bot the
    query carries rather than through the context.
    """

    def __init__(self) -> None:
        self.lines: list[tuple[int, str]] = []
        self.offers: list[tuple[int, str, Any]] = []
        self.drafts: list[tuple[int, int, str]] = []
        self.modes: list[str | None] = []
        self.answered: list[str] = []
        self.order: list[str] = []
        """Which method was called, in the order Telegram would have seen them."""
        self.bot: Any = self

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
        parse_mode: str | None = None,
    ) -> None:
        if reply_markup is None:
            self.lines.append((chat_id, text))
        else:
            self.offers.append((chat_id, text, reply_markup))
        self.modes.append(parse_mode)
        self.order.append("message")

    async def send_message_draft(self, chat_id: int, draft_id: int, text: str) -> None:
        self.drafts.append((chat_id, draft_id, text))
        self.order.append("draft")

    async def answer_callback_query(self, callback_query_id: str, **kwargs: Any) -> bool:
        self.answered.append(callback_query_id)
        return True


def test_a_constructed_update_reaches_the_coach_and_is_answered() -> None:
    """The handler layer, which every test above this one went around: who
    sent it, which chat it is, and the text out of the message."""
    seen: list[tuple[str, str]] = []

    async def run(thread: str, text: str, chat: bot.Chat) -> None:
        seen.append((thread, text))
        await chat.say("fatto")

    coach = bot.Turns(owner_id=OWNER, run=run, relay=echoed)
    sent = Sent()

    asyncio.run(bot._on_message(coach)(update_of("cosa faccio oggi?"), cast(Any, sent)))

    assert seen == [(bot.thread_for(CHAT), "cosa faccio oggi?")]
    assert sent.lines == [(CHAT, "fatto")]


def test_a_constructed_update_from_a_stranger_is_answered_with_nothing() -> None:
    coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)
    sent = Sent()

    asyncio.run(
        bot._on_message(coach)(update_of("ciao", user_id=STRANGER), cast(Any, sent))
    )

    assert sent.lines == []


def test_start_reaches_the_coach_through_a_constructed_update() -> None:
    coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)
    sent = Sent()

    asyncio.run(bot._on_start(coach)(update_of("/start"), cast(Any, sent)))

    assert sent.lines == [(CHAT, entrance.HELLO)]


def test_an_update_with_nobody_in_it_is_left_alone() -> None:
    """Some updates carry neither a user nor a chat -- a poll answer, a channel
    post. There is nobody to answer and no thread to run on."""
    coach = bot.Turns(owner_id=OWNER, run=never, relay=echoed)
    sent = Sent()

    asyncio.run(bot._on_message(coach)(Update(update_id=1), cast(Any, sent)))

    assert sent.lines == []


def test_an_edited_message_is_not_a_new_message() -> None:
    """`filters.TEXT` matches on `effective_message`, which is the edited
    message when one is edited. Without `UpdateType.MESSAGE` an edit reaches
    the handler, finds nothing where it looks, and dies there in silence --
    the user corrects a typo and the bot does nothing at all, neither a run
    nor a word. Excluded by the filter, leaving an edit alone is a decision."""
    assert bot.messages_only().check_update(update_of("cosa faccio oggi?"))
    assert not bot.messages_only().check_update(update_of("corretto", edited=True))


# -- the plan, its buttons, and the tap that answers it (ADR-0005) --------------


@pytest.fixture()
def catalogued(database_file: Path) -> Iterator[sqlite3.Connection]:
    """The planner's catalog, so a plan can be rendered and written."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


def offered() -> tuple[list[tuple[str, list[tuple[str, str]]]], bot.Offer]:
    """A chat that remembers the plans and the buttons put in it."""
    sent: list[tuple[str, list[tuple[str, str]]]] = []

    async def offer(text: str, buttons: Any) -> None:
        sent.append((text, list(buttons)))

    return sent, offer


def waiting_on_a_plan(model: Any) -> tuple[planner.Planner, str, dict[str, Any]]:
    """A graph stopped at a proposed plan, on the planner's thread for this chat.

    The tap carries the *chat's* thread, which is the entrance's, and the
    planner's is derived from it: a button has 64 bytes and one of the two is
    computable from the other.
    """
    graph = graph_of(model, checkpointer=InMemorySaver())
    final = graph.invoke({"request": BARBELL_45}, planning_on())
    return graph, bot.thread_for(CHAT), final


def tap_on(final: dict[str, Any], thread: str, action: str) -> str:
    return bot.carried(bot.Tap(action, thread, final["__interrupt__"][0].id))


def workout_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in connection.execute("SELECT id, state FROM workouts")]


def still_waiting(graph: planner.Planner, thread: str) -> tuple[str, ...]:
    """Where the planner's run on this chat's thread got to."""
    return graph.get_state(planning_on()).next


def test_a_valid_plan_reaches_the_chat_with_three_buttons(
    catalogued: sqlite3.Connection,
) -> None:
    """And the run is waiting on it, not finished."""
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()

    asyncio.run(bot.told(graphs_of(graph), final, thread, channel(say, offer)))

    (text, buttons) = sent[0]
    assert "Barbell Squat" in text
    assert [label for _, label in buttons] == [label for _, label in bot.BUTTONS]
    assert said == []
    assert still_waiting(graph, thread) == ("propose",)
    assert workout_rows(catalogued) == []


def test_every_button_fits_what_telegram_carries(catalogued: sqlite3.Connection) -> None:
    """64 bytes, and the thread and the proposal both have to travel in them."""
    _, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    sent, offer = offered()
    asyncio.run(bot.told(graphs_of(), final, thread, channel(spoken()[1], offer)))

    taps = []
    for data, _ in sent[0][1]:
        assert len(data.encode("utf-8")) <= 64, data
        read = bot.tap_of(data)
        assert read is not None
        assert read.thread == thread
        taps.append(read.action)
    assert taps == [action for action, _ in bot.BUTTONS]


def test_tapping_accept_writes_exactly_one_prescribed_workout(
    catalogued: sqlite3.Connection,
) -> None:
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)

    asyncio.run(coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.KEPT), channel(say, offer)))

    assert said == [entrance.PRESCRIBED]
    (written,) = workout_rows(catalogued)
    assert written[1] == "prescribed"
    (block,) = workouts.prescribed(catalogued, int(written[0]))
    assert [item.exercise_id for item in block.block.items] == ["Barbell_Squat"]


def test_tapping_no_proposes_another_plan_and_writes_nothing(
    catalogued: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread, final = waiting_on_a_plan(model)
    said, say = spoken()
    sent, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)

    asyncio.run(
        coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.TURNED_DOWN), channel(say, offer))
    )

    (text, buttons) = sent[0]
    assert "Standing Military Press" in text
    assert len(buttons) == len(bot.BUTTONS)
    assert said == []
    assert workout_rows(catalogued) == []
    assert still_waiting(graph, thread) == ("propose",)


def test_tapping_thirty_minutes_plans_against_thirty(
    catalogued: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Shorter.")],
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press", minutes=30)],
    )
    graph, thread, final = waiting_on_a_plan(model)
    sent, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)

    asyncio.run(
        coach.tapped(
            OWNER, CHAT, tap_on(final, thread, bot.SHORTER), channel(spoken()[1], offer)
        )
    )

    asked = graph.get_state(planning_on()).values["request"]
    assert asked.budget_min == bot.SHORTER_MINUTES
    assert "min su 30" in sent[0][0], "rendered against the time it was asked for"


def test_a_tap_on_a_plan_that_has_been_superseded_says_what_happens_next(
    catalogued: sqlite3.Connection,
) -> None:
    """The thread has moved on, or this plan was already answered. Not an error,
    and never a silent no-op."""
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    stale = bot.carried(bot.Tap(bot.KEPT, thread, "a-proposal-from-three-days-ago"))

    asyncio.run(coach.tapped(OWNER, CHAT, stale, channel(say, offer)))

    assert said == [entrance.SUPERSEDED]
    assert sent == []
    assert workout_rows(catalogued) == []
    assert still_waiting(graph, thread) == ("propose",)


def test_the_same_plan_cannot_be_accepted_twice(catalogued: sqlite3.Connection) -> None:
    """The second tap answers a plan that has been answered: one workout and not
    two, and `record_prescribed` has no upsert that would hide the difference."""
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    data = tap_on(final, thread, bot.KEPT)

    asyncio.run(coach.tapped(OWNER, CHAT, data, channel(say, offer)))
    asyncio.run(coach.tapped(OWNER, CHAT, data, channel(say, offer)))

    assert said == [entrance.PRESCRIBED, entrance.SUPERSEDED]
    assert len(workout_rows(catalogued)) == 1


def test_a_tap_from_anybody_else_resumes_nothing(catalogued: sqlite3.Connection) -> None:
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)

    asyncio.run(coach.tapped(STRANGER, CHAT, tap_on(final, thread, bot.KEPT), channel(say, offer)))

    assert said == []
    assert workout_rows(catalogued) == []
    assert still_waiting(graph, thread) == ("propose",)


def test_a_callback_that_is_not_one_of_ours_is_left_alone() -> None:
    """Whatever it is, it is not an answer to a plan, and guessing which button
    it meant would resume a thread on something nobody chose."""
    assert bot.tap_of("ok") is None
    assert bot.tap_of("something|chat:1|proposal") is None
    assert bot.tap_of("ok|chat:1|") is None


def test_a_tap_arriving_during_a_run_is_queued_and_then_answered(
    catalogued: sqlite3.Connection,
) -> None:
    """A tap is work like any other: a refusal plans the whole workout again."""

    async def scenario() -> list[str]:
        graph, thread, final = waiting_on_a_plan(
            Scripted(documents=[plan_of("Barbell_Squat")])
        )
        said, say = spoken()
        sent, offer = offered()
        started, release = asyncio.Event(), asyncio.Event()

        async def slow(
            thread: str, text: str, chat: bot.Chat
        ) -> None:
            started.set()
            await release.wait()
            await say("fatto: " + text)

        graphs = graphs_of(graph)
        coach = bot.Turns(
            owner_id=OWNER, run=slow, resume=bot.answering(graphs), relay=echoed
        )
        running = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        await started.wait()
        await coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.KEPT), channel(say, offer))

        release.set()
        await running
        return said

    assert asyncio.run(scenario()) == [entrance.QUEUED, "fatto: uno", entrance.PRESCRIBED]
    assert len(workout_rows(catalogued)) == 1


def callback_of(data: str, user_id: int = OWNER, chat_id: int = CHAT) -> Update:
    """One tap, built here. No client exists and nothing is sent."""
    query = CallbackQuery(
        id="tap-1",
        from_user=User(id=user_id, is_bot=False, first_name="Daniele"),
        chat_instance="whatever",
        data=data,
        message=Message(
            message_id=2,
            date=datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc),
            chat=Chat(id=chat_id, type=Chat.PRIVATE),
        ),
    )
    return Update(update_id=2, callback_query=query)


def test_a_constructed_tap_reaches_the_coach_and_resumes_its_thread(
    catalogued: sqlite3.Connection,
) -> None:
    """The handler layer: which button, on which thread, and the spinner on the
    user's phone stopped before a run that takes minutes begins."""
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    sent = Sent()
    update = callback_of(tap_on(final, thread, bot.KEPT))
    update.callback_query.set_bot(cast(Any, sent))  # type: ignore[union-attr]

    asyncio.run(bot._on_tap(coach)(update, cast(Any, sent)))

    assert sent.answered == ["tap-1"], "the button was left spinning"
    assert sent.lines == [(CHAT, entrance.PRESCRIBED)]
    assert len(workout_rows(catalogued)) == 1


def test_a_constructed_tap_from_a_stranger_resumes_nothing(
    catalogued: sqlite3.Connection,
) -> None:
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    sent = Sent()
    update = callback_of(tap_on(final, thread, bot.KEPT), user_id=STRANGER)
    update.callback_query.set_bot(cast(Any, sent))  # type: ignore[union-attr]

    asyncio.run(bot._on_tap(coach)(update, cast(Any, sent)))

    assert sent.lines == []
    assert workout_rows(catalogued) == []
    assert still_waiting(graph, thread) == ("propose",)


def test_the_buttons_reach_telegram_as_a_keyboard() -> None:
    """One row per answer, and the callback data survives the round trip."""
    sent = Sent()

    offer = bot._offering(cast(Any, sent), CHAT)
    asyncio.run(offer("il piano", [("ok|chat:1|abc", "Va bene")]))

    (chat_id, text, markup) = sent.offers[0]
    assert (chat_id, text) == (CHAT, "il piano")
    ((button,),) = markup.inline_keyboard
    assert (button.text, button.callback_data) == ("Va bene", "ok|chat:1|abc")


def test_the_button_says_the_time_it_actually_asks_for() -> None:
    """The label and the sentence the planner is given are one number.

    Copied into the label, they drift the day the number changes: the plan is
    built for twenty minutes and the button the user tapped still said thirty.
    """
    assert str(bot.SHORTER_MINUTES) in dict(bot.BUTTONS)[bot.SHORTER]
    assert str(bot.SHORTER_MINUTES) in bot.SAID[bot.SHORTER]


def test_a_run_does_not_block_the_bot_while_the_model_thinks(
    catalogued: sqlite3.Connection,
) -> None:
    """The graph's nodes are synchronous and a round trip to the model is
    minutes of it on Ollama. Run on the event loop, one of them blocks the
    process that long-polls Telegram: no second tap, no message queued, and
    not even the QUEUED that promises one, until the plan comes back.
    `astream` is what keeps them off it.

    The model here does not return until the loop has run something else. On
    the loop, the two wait for each other and nothing arrives.
    """

    class Blocking(Scripted):
        """A model whose turn does not end until the loop has moved."""

        went_on: Any = None

        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            assert self.went_on.wait(5), "the loop never ran while the model worked"
            return super()._generate(messages, *args, **kwargs)

    async def scenario() -> list[str]:
        went_on = threading.Event()
        went_on.set()
        model = Blocking(
            went_on=went_on,
            turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
            documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
        )
        graph, thread, final = waiting_on_a_plan(model)
        went_on.clear()
        watched = Channels()
        resume = bot.answering(graphs_of(graph))

        async def answering() -> None:
            await resume(
                thread,
                bot.Tap(bot.TURNED_DOWN, thread, final["__interrupt__"][0].id),
                watched.chat,
            )

        tapped = asyncio.create_task(answering())
        # Long enough for the loop to have run the task and reached the model:
        # with the call on the loop, this sleep is what never returns.
        await asyncio.sleep(0.05)
        went_on.set()
        await tapped
        return [text for text, _ in watched.offers]

    (offered_plan,) = asyncio.run(scenario())
    assert "Standing Military Press" in offered_plan


# -- the run, watched while it happens -----------------------------------------


def refusing_then_planning() -> Scripted:
    """A run the validator turns down once: the loop this ticket makes visible."""
    return Scripted(
        turns=[AIMessage(content="Planned."), AIMessage(content="Again.")],
        documents=[
            mesocycle_of(plan_of("Dumbbell_Bench_Press"), plan_of("Standing_Military_Press")),
            A_MESOCYCLE,
        ],
    )


def test_the_plan_is_a_message_sent_after_the_last_draft(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The acceptance criterion of the whole ticket, at the layer that talks to
    Telegram. A draft lasts about thirty seconds; the plan has to still be
    there tomorrow, so it is an ordinary message and it goes last."""
    graph = graph_of(refusing_then_planning(), checkpointer=InMemorySaver())
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    sent = Sent()

    asyncio.run(bot._on_message(coach)(update_of("cosa faccio oggi?"), cast(Any, sent)))

    assert sent.order[-1] == "message", "the chat was left holding a draft"
    # Two: the entrance answering the turn at once, and the plan behind it.
    assert sent.order.count("message") == 2
    assert sent.order[0] == "message", "the turn was not answered before the work"
    assert "draft" in sent.order[1:-1], "nothing was streamed while it worked"
    assert sent.offers, "the plan came without its buttons"


def test_the_whole_run_updates_one_draft_in_place(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """One non-zero id for the run, so Telegram animates the changes instead of
    stacking a preview per line."""
    graph = graph_of(refusing_then_planning(), checkpointer=InMemorySaver())
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    sent = Sent()

    asyncio.run(bot._on_message(coach)(update_of("cosa faccio oggi?"), cast(Any, sent)))

    ids = {draft_id for _, draft_id, _ in sent.drafts}
    assert len(ids) == 1
    assert 0 not in ids
    assert {chat_id for chat_id, _, _ in sent.drafts} == {CHAT}


def test_the_draft_opens_on_a_line_of_our_own(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The first line the graph produces is a minute away on Ollama, and an
    empty draft asks the client for a *Thinking...* placeholder it may not
    know how to draw -- Bot API 10.0, and newer than most installed clients.
    A line of ours renders wherever a draft renders at all.
    """
    graph = graph_of(refusing_then_planning(), checkpointer=InMemorySaver())
    watched = asking(graphs_of(graph))

    assert watched.drafts[0] == bot.WORKING
    assert "" not in watched.drafts, "an empty draft asks the client to invent one"
    assert watched.drafts[-1].splitlines() == [
        progress.WRITING,
        f"il validatore ha rifiutato: {plans.ADMISSIBLE}",
        progress.REWRITING,
        "piano valido, 2 allenamenti",
    ]


def test_a_refusal_is_streamed_too(catalogued: sqlite3.Connection) -> None:
    """Turning a plan down plans the whole workout again, which is the same
    minutes of silence asking for one costs."""
    graph, thread, final = waiting_on_a_plan(
        Scripted(
            turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
            documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
        )
    )
    watched = Channels()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)

    asyncio.run(
        coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.TURNED_DOWN), watched.chat)
    )

    assert progress.AGAIN in watched.drafts[-1]
    assert "Standing Military Press" in watched.offers[0][0]


def test_a_draft_that_cannot_be_sent_does_not_cost_the_plan(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Progress is not the answer. A link that drops the preview must still
    deliver the workout -- the failure the ticket's own comment predicted."""

    async def refused(text: str) -> None:
        raise RuntimeError("Timed out")

    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]), checkpointer=InMemorySaver()
    )
    watched = Channels()
    graphs = graphs_of(graph)
    coach = turns_of(graphs)
    chat = bot.Chat(say=watched.chat.say, offer=watched.chat.offer, draft=refused)

    asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", chat))

    assert watched.said == [SAYS]
    assert "Barbell Squat" in watched.offers[0][0]


def test_the_draft_is_kept_alive_while_a_run_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A planner turn on Ollama is minutes long and a draft expires in about
    thirty seconds. Between two lines the screen would go back to empty, which
    is the state this ticket exists to end."""
    monkeypatch.setattr(bot, "DRAFT_SECONDS", 0.01)

    async def scenario() -> list[str]:
        drafts: list[str] = []

        async def draft(text: str) -> None:
            drafts.append(text)

        lines = progress.Progress()
        lines.lines = ["scrivo il piano"]
        async with bot.drafting(draft, lines):
            await asyncio.sleep(0.05)
        return drafts

    drafts = asyncio.run(scenario())
    assert len(drafts) > 1, "the draft was left to expire"
    assert drafts[-1] == "scrivo il piano"


# -- the plan, as Telegram shows it --------------------------------------------


def test_the_chat_and_the_terminal_render_one_plan(
    catalogued: sqlite3.Connection,
) -> None:
    """Different markup over the same reading: the exercises, the block costs
    and the total are the engine's answers and not two of them."""
    plan = plan_of("Barbell_Squat", "Standing_Military_Press")
    reading = plans.shown(catalogued, plan, plans.to_blocks(plan), 45)

    text = bot.proposal(plan, 45)

    assert f"min su {45}" in text
    assert str(reading.total_min) in text
    for block in reading.blocks:
        for item in block.items:
            assert item.name in text


def test_what_the_user_said_no_to_is_the_line_they_notice(
    catalogued: sqlite3.Connection,
) -> None:
    plan = plan_of("Barbell_Squat").model_copy(
        update={
            "despite": [
                plans.Acknowledgement(
                    exercise_id="Barbell_Squat", why="non c'è altro per le gambe"
                )
            ]
        }
    )

    text = bot.proposal(plan, 45)

    assert "avevi detto di no: non c'è altro per le gambe" in text


def test_the_plan_escapes_what_telegram_would_read_as_markup(
    catalogued: sqlite3.Connection,
) -> None:
    """MarkdownV2 makes a dot and a hyphen syntax. Unescaped, a reason the
    model wrote is enough for Telegram to refuse the message -- which loses the
    plan, not the formatting.
    """
    plan = plan_of("Barbell_Squat", reason="30-45 min. di lavoro")

    text = bot.proposal(plan, 45)

    assert "30\\-45 min\\. di lavoro" in text


def test_a_plan_is_sent_in_the_dialect_it_was_written_in() -> None:
    """The escaping and the parse mode are one decision. Sent without the mode
    the user reads the backslashes; sent in another the markup is refused."""
    sent = Sent()

    offer = bot._offering(cast(Any, sent), CHAT)
    asyncio.run(offer("il piano", [("ok|chat:1|abc", "Va bene")]))

    assert sent.modes == [bot.PARSE_MODE]


def test_progress_carries_no_markup() -> None:
    """A tool argument the model wrote goes into the draft as it arrived, and
    an asterisk in one must not be a send Telegram refuses."""
    sent = Sent()

    draft = bot._drafting(cast(Any, sent), CHAT)
    asyncio.run(draft("cerco «bench*press» in catalogo"))

    assert sent.drafts == [(CHAT, sent.drafts[0][1], "cerco «bench*press» in catalogo")]
    assert sent.modes == [], "a draft was sent with a parse mode"



def test_a_provider_that_falls_over_mid_stream_is_said_out_loud(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Seen on Ollama: the model emitted a tool call its own server could not
    parse back, and `_generate` raised inside the stream.

    The draft stops where it stopped -- it is a preview, and it expires on its
    own -- and the chat is told in words. Nothing about the provider reaches
    it: `FAILED` is a constant, for the same reason `BLOCKED` is.
    """

    class Falling(Scripted):
        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(
                r"error parsing tool call: raw='{\"plan\":[' "
                r"(C:\Users\someone\.ollama\models\blobs\sha256-e7b2)"
            )

    watched = Channels()
    graph = graph_of(Falling(), checkpointer=InMemorySaver())
    graphs = graphs_of(graph)
    coach = turns_of(graphs)

    asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", watched.chat))

    assert watched.said == [SAYS, bot.FAILED]
    assert watched.offers == []
    assert "someone" not in "".join(watched.said + watched.drafts)


def test_the_draft_stops_when_the_run_it_was_watching_raises(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The keep-alive is a task, and a task nobody cancels outlives the run
    that started it -- re-sending a dead run's progress every twenty seconds
    for as long as the bot stays up.
    """

    class Falling(Scripted):
        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("the provider fell over")

    async def scenario() -> set[str]:
        watched = Channels()
        graph = graph_of(Falling(), checkpointer=InMemorySaver())
        graphs = graphs_of(graph)
        coach = turns_of(graphs)
        mine = asyncio.current_task()

        await coach.arriving(OWNER, CHAT, "cosa faccio oggi?", watched.chat)

        return {
            task.get_coro().__qualname__  # type: ignore[union-attr]
            for task in asyncio.all_tasks()
            if task is not mine
        }

    assert asyncio.run(scenario()) == set()


def test_a_run_streams_against_the_checkpointer_the_bot_actually_uses(
    tmp_path: Path, catalogued: sqlite3.Connection, declared: Path
) -> None:
    """`SqliteSaver` has no async methods, and every other streaming test here
    runs on `InMemorySaver`, which has them. Between the two, `trainer bot`
    could not plan at all: the first thing the stream did was ask the saver
    for `aget_tuple`, and it refused.

    It reached the user as *«qualcosa è andato storto»*, because `_attempt`
    turns anything a run raises into `FAILED` -- which is right for the user
    and is exactly what hid this. So the assertion is on the **plan**: a test
    that only reads the state back sees a thread that was written to before
    the run began, and passes over a run that never happened.
    """
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = graph_of(
            Scripted(documents=[A_MESOCYCLE]), checkpointer=saver
        )
        watched = Channels()
        graphs = graphs_of(graph)
        coach = turns_of(graphs)

        asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", watched.chat))

        assert watched.said != [bot.FAILED], "the run fell over"
        assert "Barbell Squat" in watched.offers[0][0]
        assert watched.drafts, "nothing was streamed"


def test_the_terminal_and_the_bot_share_one_checkpointer(
    tmp_path: Path, catalogued: sqlite3.Connection
) -> None:
    """Why the bot streams on a thread instead of on `astream`.

    `trainer plan` invokes this graph synchronously against the same file, and
    the async saver has no sync methods -- so a checkpointer chosen to suit
    the bot would take the terminal away. One saver, and the async door is the
    one that adapts.
    """
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        assert not hasattr(saver, "aget_tuple") or saver.__class__.__name__ == "SqliteSaver"
        graph = graph_of(
            Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver
        )

        final = graph.invoke(
            {"request": BARBELL_45}, {"configurable": {"thread_id": "terminal"}}
        )

        assert final["__interrupt__"], "the terminal's own door still works"


def test_a_run_from_the_chat_reads_back_afterwards(
    tmp_path: Path, catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The other half of the demo. A plan proposed in Telegram and never
    answered is still a run somebody can ask what it did."""
    from trainer.coach import runs

    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = graph_of(
            Scripted(documents=[A_MESOCYCLE]), checkpointer=saver
        )
        graphs = graphs_of(graph)
        coach = turns_of(graphs)
        asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", Channels().chat))

    with checkpoints.saver(path) as saver:
        held = runs.negotiations(runs.kept(run_record.archive()), runs.live(saver))

    (negotiation,) = held
    assert negotiation.outcome == runs.WAITING, "nobody has answered the plan"
    assert negotiation.live is not None
    assert negotiation.live.thread == bot.under(bot.thread_for(CHAT), bot.PLANNING)
    written = runs.of(negotiation.live, tools.CALL_BUDGET)
    assert written["plan"]["workouts"][0]["blocks"][0]["items"][0]["exercise_id"] == "Barbell_Squat"


# -- the report, in the chat ---------------------------------------------------


def reporting(log: coach_logger.Logger) -> bot.Graphs:
    """The three graphs, with a chat whose every message is a report."""
    return graphs_of(front=Talking(handoff=entrance.LOG_WORKOUT), log=log)


def workout_states(connection: sqlite3.Connection) -> list[str]:
    return [state for _, state in workout_rows(connection)]


def test_a_report_in_the_chat_reaches_the_logger_and_is_written(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The second subgraph the entrance routes to. Nothing about the message
    says which one: the entrance read it."""
    identifier = prescribe(catalogued)
    model = scripted(
        AIMessage(content="chiaro"),
        emits=report(workout_id=identifier, report="squat, 4 giri"),
    )
    graphs = reporting(logger_graph_of(model, checkpointer=InMemorySaver()))

    watched = asking(graphs, "ieri squat, 4 giri")

    assert watched.said == [SAYS, entrance.LOGGED]
    assert workout_states(catalogued) == ["performed"]


def test_a_clarifying_question_is_said_and_the_next_message_answers_it(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The open question of the two (ADR-0006): prose the user writes, so it is
    a message to reply to. The reply is the answer to the run and not a new
    turn -- which is the graph's own state, never something the entrance is
    asked to work out."""
    identifier = prescribe(catalogued)
    model = scripted(
        calling("ask_user", question="Fatica o fastidio?"),
        AIMessage(content="chiaro"),
        emits=report(workout_id=identifier, report="squat, 4 su 10"),
    )
    graphs = reporting(logger_graph_of(model, checkpointer=InMemorySaver()))
    coach = turns_of(graphs)
    asked, answered = Channels(), Channels()

    asyncio.run(coach.arriving(OWNER, CHAT, "squat, 4 su 10", asked.chat))
    asyncio.run(coach.arriving(OWNER, CHAT, "fastidio", answered.chat))

    assert asked.said == [SAYS, "Fatica o fastidio?"]
    assert answered.said == [entrance.LOGGED], "the answer went round the entrance"
    assert workout_states(catalogued) == ["performed"]


def test_a_proposed_exclusion_is_two_buttons_and_nothing_is_written_until_one(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The closed question of the two. An exclusion on `shoulder` takes 251 of
    the catalog's 582 exercises out of what may ever be prescribed, so it is
    confirmed before anything writes it (ADR-0004)."""
    identifier = prescribe(catalogued)
    graphs = reporting(
        logger_graph_of(proposing(identifier), checkpointer=InMemorySaver())
    )
    coach = turns_of(graphs)
    watched = Channels()

    asyncio.run(coach.arriving(OWNER, CHAT, "la spalla tirava", watched.chat))

    (text, buttons) = watched.offers[0]
    assert [label for _, label in buttons] == [label for _, label in bot.CONFIRM]
    assert "shoulder" in text
    assert workout_rows(catalogued) == [(identifier, "prescribed")]
    assert exclusions.active(catalogued, date.today().isoformat()) == ()


def test_tapping_yes_on_the_exclusion_writes_it_with_the_workout(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    identifier = prescribe(catalogued)
    graphs = reporting(
        logger_graph_of(proposing(identifier), checkpointer=InMemorySaver())
    )
    coach = turns_of(graphs)
    watched = Channels()
    asyncio.run(coach.arriving(OWNER, CHAT, "la spalla tirava", watched.chat))
    (_, buttons) = watched.offers[0]

    asyncio.run(coach.tapped(OWNER, CHAT, buttons[0][0], watched.chat))

    assert watched.said == [SAYS, entrance.LOGGED]
    assert workout_states(catalogued) == ["performed"]
    assert exclusions.active(catalogued, date.today().isoformat()) != ()


def test_tapping_no_on_the_exclusion_writes_the_workout_and_not_the_exclusion(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The report keeps the user's words either way, so the remark that
    prompted it is still on the row."""
    identifier = prescribe(catalogued)
    graphs = reporting(
        logger_graph_of(proposing(identifier), checkpointer=InMemorySaver())
    )
    coach = turns_of(graphs)
    watched = Channels()
    asyncio.run(coach.arriving(OWNER, CHAT, "la spalla tirava", watched.chat))
    (_, buttons) = watched.offers[0]

    asyncio.run(coach.tapped(OWNER, CHAT, buttons[1][0], watched.chat))

    assert workout_states(catalogued) == ["performed"]
    assert exclusions.active(catalogued, date.today().isoformat()) == ()


def test_a_button_on_an_exclusion_the_thread_moved_past_is_not_silence(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    identifier = prescribe(catalogued)
    graphs = reporting(
        logger_graph_of(proposing(identifier), checkpointer=InMemorySaver())
    )
    coach = turns_of(graphs)
    watched = Channels()
    stale = bot.carried(
        bot.Tap(bot.CONFIRMED, bot.thread_for(CHAT), "an-exclusion-from-last-week")
    )

    asyncio.run(coach.tapped(OWNER, CHAT, stale, watched.chat))

    assert watched.said == [entrance.SUPERSEDED]
    assert exclusions.active(catalogued, date.today().isoformat()) == ()


def test_the_two_sets_of_buttons_are_told_apart_by_what_they_carry() -> None:
    """A tap has 64 bytes and has to find its graph in them. The actions are
    disjoint, so the action is enough and no byte goes on saying which."""
    assert set(dict(bot.BUTTONS)) & set(dict(bot.CONFIRM)) == set()
    assert set(bot.ACTIONS) == set(dict(bot.BUTTONS)) | set(dict(bot.CONFIRM))


# -- two models, one run -------------------------------------------------------


def documents(archive: Path) -> list[dict[str, Any]]:
    return [
        json.loads(document.read_text(encoding="utf-8"))
        for document in sorted(archive.glob("*/*.json"))
    ]


def test_the_run_document_names_the_model_that_answered_each_node(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    """From ADR-0006 there is no one model per run. The entrance answers its
    own node on a small fast model and the planner answers the rest on the one
    `LLM_BACKEND` names, and the document says which did which."""
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]),
        checkpointer=InMemorySaver(),
        archive=tmp_path / "runs",
    )
    graphs = graphs_of(graph, archive=tmp_path / "runs")
    sent = asking(graphs).offers

    asyncio.run(turns_of(graphs).tapped(OWNER, CHAT, sent[0][1][0][0], Channels().chat))

    accepted = next(
        one for one in documents(tmp_path / "runs") if one["ending"] == run_record.ACCEPTED
    )
    named = {
        node["node"]: (node["model"], node["provider"]) for node in accepted["nodes"]
    }
    assert named["entrance"] == (FRONT_MODEL, FRONT_PROVIDER)
    assert named["planner"] == (STAND_IN, SCRIPTED)
    assert named["emit"] == (STAND_IN, SCRIPTED)
    assert named["validate"] == (STAND_IN, SCRIPTED)
    # The closing node's own seconds are not in the document it writes, which
    # is why `prescribe` is not among these (see `record.closing`).
    assert set(named.values()) == {(FRONT_MODEL, FRONT_PROVIDER), (STAND_IN, SCRIPTED)}


def test_a_planning_turn_is_one_run_and_not_two(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    """The user asked once. The entrance is the first node of that run and the
    planner carries it on, so the turn leaves one document and not one per
    graph."""
    graph = graph_of(
        Scripted(documents=[A_MESOCYCLE]),
        checkpointer=InMemorySaver(),
        archive=tmp_path / "runs",
    )
    graphs = graphs_of(graph, archive=tmp_path / "runs")
    sent = asking(graphs).offers

    asyncio.run(turns_of(graphs).tapped(OWNER, CHAT, sent[0][1][0][0], Channels().chat))

    accepted = [
        one
        for one in documents(tmp_path / "runs")
        if one["ending"] == run_record.ACCEPTED
    ]
    assert len(accepted) == 1
    assert accepted[0]["nodes"][0]["node"] == "entrance", "the run starts at the door"


# -- the turn is answered before the work is done ------------------------------


def test_the_turn_is_answered_before_the_planner_has_finished(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """ADR-0006, item 6, and the reason the entrance runs on a model of its
    own. A plan is minutes; a chat that says nothing for four of them is the
    silence this replaces."""

    class Blocking(Scripted):
        went_on: Any = None

        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            assert self.went_on.wait(5), "the planner was never released"
            return super()._generate(messages, *args, **kwargs)

    async def scenario() -> tuple[list[str], list[Any], list[Any]]:
        went_on = threading.Event()
        graph = graph_of(
            Blocking(went_on=went_on, documents=[A_MESOCYCLE]),
            checkpointer=InMemorySaver(),
        )
        graphs = graphs_of(graph)
        watched = Channels()
        running = asyncio.create_task(
            turns_of(graphs).arriving(OWNER, CHAT, "cosa faccio oggi?", watched.chat)
        )
        for _ in range(500):
            if watched.said:
                break
            await asyncio.sleep(0.01)
        answered, waiting = list(watched.said), list(watched.offers)
        went_on.set()
        await running
        return answered, waiting, list(watched.offers)

    answered, waiting, arrived = asyncio.run(scenario())
    assert answered == [SAYS], "the turn waited on the planner"
    assert waiting == [], "the plan cannot have arrived yet"
    assert arrived, "and it follows in the same chat"


# -- the five lines that stopped being constants -------------------------------


def test_the_five_lines_are_gone_and_the_two_that_stay_are_constants() -> None:
    """ADR-0006's consequence, as a test. `BLOCKED` and `FAILED` stay because
    they are the two cases where the model is absent or not to be trusted."""
    for gone in ("STARTED", "QUEUED", "WRITTEN", "SUPERSEDED", "NO_PLAN"):
        assert not hasattr(bot, gone), gone
    assert bot.BLOCKED and bot.FAILED


def test_every_situation_the_entrance_can_say_is_one_the_bot_names() -> None:
    """A situation nobody puts to it is a sentence the chat can never get, and
    the five that were constants are exactly the ones that must not go that way
    again."""
    source = Path(bot.__file__).read_text(encoding="utf-8")
    named = {
        name
        for name, value in vars(entrance).items()
        if isinstance(value, str) and value in entrance.SITUATIONS
    }
    for name in named:
        assert f"entrance.{name}" in source, name
    assert len(named) == len(entrance.SITUATIONS)


def test_the_entrance_saying_nothing_is_answered_like_a_model_that_is_absent(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """A turn that came back with no words is the model failing rather than
    choosing silence, and silence is what this whole ticket replaces."""
    graphs = graphs_of(front=Talking(handoff="", says=""))
    watched = Channels()

    asyncio.run(turns_of(graphs).arriving(OWNER, CHAT, "ciao", watched.chat))

    assert watched.said == [bot.FAILED]


def test_an_entrance_that_falls_over_does_not_wedge_the_greeting(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The greeting has to survive a model that is not there: an exception on
    the way to Telegram would take the update handler with it."""

    class Absent(Talking):
        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("no model here")

    graphs = graphs_of(front=Absent())
    watched = Channels()

    asyncio.run(turns_of(graphs).started(OWNER, CHAT, watched.chat))

    assert watched.said == [bot.FAILED]


def test_the_closed_question_escapes_what_telegram_would_read_as_markup() -> None:
    """The `why` is a model's sentence and the retest date is full of hyphens,
    which MarkdownV2 makes syntax. Unescaped, the send is refused and the
    question is lost -- not the formatting."""
    asked = bot.exclusion(
        {
            "kind": coach_logger.EXCLUSION,
            "ask": "la spalla tirava sui military-press (2 serie)",
            "granularity": "joint",
            "value": "shoulder",
            "retest_date": "2026-10-15",
        }
    )

    assert "2026\\-10\\-15" in asked
    assert "military\\-press" in asked
    assert "\\(2 serie\\)" in asked
    assert "shoulder" in asked


def test_tapping_no_on_a_mesocycle_offers_another(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graph = graph_of(
        Scripted(
            turns=[AIMessage(content="Planned."), AIMessage(content="Another.")],
            documents=[A_MESOCYCLE, A_MESOCYCLE.model_copy(update={"cycles": 2})],
        ),
        checkpointer=InMemorySaver(),
    )
    graphs = graphs_of(graph)
    sent = asking(graphs).offers
    no = next(data for data, label in sent[0][1] if bot.tap_of(data).action == bot.TURNED_DOWN)  # type: ignore[union-attr]
    watched = Channels()

    asyncio.run(turns_of(graphs).tapped(OWNER, CHAT, no, watched.chat))

    ((text, buttons),) = watched.offers
    assert "2 cicli" in text
    assert len(buttons) == len(bot.MESOCYCLE_BUTTONS)
    assert mesocycles.active(catalogued) is None


# -- a change and an adaptation (ADR-0008 item 6) ------------------------------


def adapting_from(catalogued: sqlite3.Connection, *turns: AIMessage, planned: Any) -> bot.Graphs:
    """A kept mesocycle, an entrance that reaches for `turns` and then serves, and a planner."""
    served_from(catalogued)
    return graphs_of(
        graph_of(planned, checkpointer=InMemorySaver()),
        front=Talking(handoff=entrance.TODAYS_WORKOUT, turns=list(turns)),
    )


def test_an_adaptation_is_offered_accepted_and_served_and_the_mesocycle_stays(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = adapting_from(
        catalogued,
        calling(entrance.ADAPT_TODAY, said="solo 30 minuti oggi", minutes=30),
        planned=Scripted(documents=[plan_of("Barbell_Squat", rounds=2, minutes=30)]),
    )
    kept = mesocycles.active(catalogued)

    sent = asking(graphs, "solo 30 minuti oggi").offers
    ((text, buttons),) = sent
    assert "30" in text
    assert [label for _, label in buttons] == [label for _, label in bot.BUTTONS]

    said, say = spoken()
    asyncio.run(turns_of(graphs).tapped(OWNER, CHAT, buttons[0][0], channel(say)))

    assert said == [entrance.PRESCRIBED]
    assert mesocycles.active(catalogued) == kept
    ((served, _),) = asking(graphs).offers
    assert "*Blocco 1* · 2 giri" in served, "asked again, the adapted workout is today's"
    assert [state for _, state in workout_rows(catalogued)] == ["prescribed"]


def test_a_change_is_offered_accepted_and_kept_counting_on(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    changed = mesocycle_of(plan_of("Barbell_Squat", rounds=2), plan_of("Standing_Military_Press"))
    graphs = adapting_from(
        catalogued,
        calling(entrance.CHANGE_MESOCYCLE, said="meno giri di squat"),
        planned=Scripted(raw=[changed.model_dump_json()]),
    )
    before = mesocycles.active(catalogued)
    assert before is not None

    ((_, buttons),) = asking(graphs, "d'ora in poi meno giri di squat").offers
    assert [label for _, label in buttons] == [label for _, label in bot.MESOCYCLE_BUTTONS]
    said, say = spoken()
    asyncio.run(turns_of(graphs).tapped(OWNER, CHAT, buttons[0][0], channel(say)))

    assert said == [entrance.KEPT]
    after = mesocycles.active(catalogued)
    assert after is not None and after.id != before.id
    assert after.accepted_after == before.accepted_after
    assert after.slots[0][0].block.rounds == 2


# -- the next mesocycle, prepared (ADR-0008 item 5) ----------------------------


NEXT = mesocycle_of(plan_of("Barbell_Squat", rounds=2), plan_of("Standing_Military_Press"), cycles=3)
"""What the planner prepares once the last cycle is performed."""


def performed_once(
    catalogued: sqlite3.Connection, exercise_id: str, workout_id: int | None = None
) -> None:
    """One workout reported, against `workout_id` when there is one."""
    workouts.record_performed(
        catalogued,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id=exercise_id,
                        unit="reps",
                        amount=5,
                        amount_source="reported",
                        load_kg=100,
                        load_kg_source="reported",
                    ),
                ),
                rounds=3,
                rounds_source="reported",
                rest=120,
                rest_source="reported",
            ),
        ),
        on=date.today().isoformat(),
        report=exercise_id,
        workout_id=workout_id,
    )


def on_its_last_workout(catalogued: sqlite3.Connection) -> int:
    """A one-cycle mesocycle with its first workout performed and its last one served."""
    mesocycles.record_mesocycle(
        catalogued,
        tuple(
            tuple(
                workouts.PrescribedBlock(block=block, reason=shape.reason)
                for shape, block in zip(workout.blocks, plans.to_blocks(workout), strict=True)
            )
            for workout in A_MESOCYCLE.workouts
        ),
        cycles=1,
        why=A_MESOCYCLE.why,
        on=date.today().isoformat(),
    )
    _, first = mesocycles.record_served(catalogued, date.today().isoformat())
    performed_once(catalogued, "Barbell_Squat", first)
    _, last = mesocycles.record_served(catalogued, date.today().isoformat())
    return last


def finishing(
    catalogued: sqlite3.Connection,
    planned: Scripted,
    front: Talking | None = None,
    saver: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
) -> bot.Graphs:
    """A chat about to report the workout that completes its mesocycle's last cycle."""
    last = on_its_last_workout(catalogued)
    held = saver if saver is not None else InMemorySaver()
    return graphs_of(
        graph_of(planned, checkpointer=held),
        front=front if front is not None else Talking(handoff=entrance.LOG_WORKOUT),
        log=logger_graph_of(
            scripted(AIMessage(content="chiaro"), emits=report(workout_id=last, report="press")),
            checkpointer=held,
            archive=archive,
        ),
        saver=held,
        archive=archive,
    )


async def reported_and_prepared(graphs: bot.Graphs, watched: Channels) -> int:
    """The report, then the preparation it started; how many drafts the report alone left."""
    await turns_of(graphs).arriving(OWNER, CHAT, "fatto il press", watched.chat)
    drafted = len(watched.drafts)
    await asyncio.gather(*graphs.background)
    return drafted


def told_the_entrance(graphs: bot.Graphs) -> list[str]:
    return [
        message.text
        for message in graphs.entrance.get_state(
            {"configurable": {"thread_id": bot.thread_for(CHAT)}}
        ).values["messages"]
    ]


def test_the_report_that_completes_the_last_cycle_prepares_the_next_mesocycle(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    planned = Scripted(documents=[NEXT])
    graphs = finishing(catalogued, planned)
    watched = Channels()

    drafted = asyncio.run(reported_and_prepared(graphs, watched))

    assert watched.said == [SAYS, entrance.LOGGED, entrance.NEXT_MESOCYCLE]
    ((text, buttons),) = watched.offers
    assert "3 cicli" in text
    assert [label for _, label in buttons] == [label for _, label in bot.MESOCYCLE_BUTTONS]
    assert len(watched.drafts) == drafted, "the preparation opens no draft"
    state = graphs.planner.get_state(planning_on()).values
    assert state["unasked"] is True
    assert state["request"].continuing is not None, "briefed with the mesocycle that ended"
    assert len(planned.seen) == 1, "one planning run, and only one"


def test_a_report_that_does_not_complete_the_last_cycle_prepares_nothing(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    identifier = prescribe(catalogued)
    graphs = graphs_of(
        graph_of(Scripted(documents=[NEXT]), checkpointer=InMemorySaver()),
        front=Talking(handoff=entrance.LOG_WORKOUT),
        log=logger_graph_of(
            scripted(AIMessage(content="chiaro"), emits=report(workout_id=identifier, report="squat")),
            checkpointer=InMemorySaver(),
        ),
    )
    watched = Channels()

    asyncio.run(reported_and_prepared(graphs, watched))

    assert watched.said == [SAYS, entrance.LOGGED]
    assert watched.offers == []
    assert graphs.planner.get_state(planning_on()).values == {}


def test_only_the_report_that_ends_it_prepares_the_next(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Every report after it is past the end, and prepares nothing again."""
    last = on_its_last_workout(catalogued)
    assert bot._next() is None, "one workout still to go"

    performed_once(catalogued, "Standing_Military_Press", last)
    assert bot._next() is not None

    performed_once(catalogued, "Barbell_Squat")
    assert bot._next() is None


def test_a_message_while_it_is_prepared_is_answered_and_gets_no_second(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Outside the queue: the preparation is not a turn, so nothing waits behind it.
    Asking for a mesocycle meanwhile is told it is on its way, and plans nothing."""

    class Blocking(Scripted):
        went_on: Any = None

        def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
            assert self.went_on.wait(5), "the loop never ran while the model worked"
            return super()._generate(messages, *args, **kwargs)

    went_on = threading.Event()
    planned = Blocking(went_on=went_on, documents=[NEXT])
    front = Talking(handoff=entrance.LOG_WORKOUT)
    graphs = finishing(catalogued, planned, front)

    async def scenario() -> tuple[Channels, Channels]:
        reporting_chat, asking_chat = Channels(), Channels()
        coach = turns_of(graphs)
        await coach.arriving(OWNER, CHAT, "fatto il press", reporting_chat.chat)
        await asyncio.sleep(0.05)
        assert graphs.preparing, "the preparation is under way"
        front.handoff = entrance.PLAN_MESOCYCLE
        await coach.arriving(OWNER, CHAT, "preparami un mesociclo", asking_chat.chat)
        went_on.set()
        await asyncio.gather(*graphs.background)
        return reporting_chat, asking_chat

    reporting_chat, asking_chat = asyncio.run(scenario())

    assert asking_chat.said == [SAYS], "answered, not queued"
    assert asking_chat.offers == [], "on its way: nothing offered twice"
    assert entrance.WAITING_MESOCYCLE in told_the_entrance(graphs)
    assert len(reporting_chat.offers) == 1
    assert len(planned.seen) == 1, "never a second planning run"


def test_asking_for_a_mesocycle_while_one_waits_gets_the_prepared_one(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    planned = Scripted(documents=[NEXT, A_MESOCYCLE])
    front = Talking(handoff=entrance.LOG_WORKOUT)
    graphs = finishing(catalogued, planned, front)
    prepared = Channels()
    asyncio.run(reported_and_prepared(graphs, prepared))

    front.handoff = entrance.PLAN_MESOCYCLE
    again = asking(graphs, "preparami un mesociclo")

    assert again.offers == prepared.offers, "the same mesocycle, the same buttons"
    assert len(planned.seen) == 1, "never a second planning run"
    ((_, buttons),) = again.offers
    said, say = spoken()
    asyncio.run(turns_of(graphs).tapped(OWNER, CHAT, buttons[0][0], channel(say)))
    assert said == [entrance.KEPT]
    kept = mesocycles.active(catalogued)
    assert kept is not None and kept.cycles == 3


def test_todays_workout_after_the_last_cycle_points_at_the_one_waiting(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    front = Talking(handoff=entrance.LOG_WORKOUT)
    graphs = finishing(catalogued, Scripted(documents=[NEXT]), front)
    asyncio.run(reported_and_prepared(graphs, Channels()))

    front.handoff = entrance.TODAYS_WORKOUT
    watched = asking(graphs)

    assert entrance.WAITING_MESOCYCLE in told_the_entrance(graphs)
    assert entrance.NO_MESOCYCLE not in told_the_entrance(graphs)
    assert len(watched.offers) == 1, "the prepared one, again"


def test_an_adaptation_after_the_last_cycle_points_at_the_one_waiting(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    front = Talking(handoff=entrance.LOG_WORKOUT)
    planned = Scripted(documents=[NEXT])
    graphs = finishing(catalogued, planned, front)
    asyncio.run(reported_and_prepared(graphs, Channels()))

    front.handoff = ""
    front.turns = [calling(entrance.ADAPT_TODAY, said="solo 30 minuti", minutes=30)]
    asking(graphs, "solo 30 minuti oggi")

    assert entrance.WAITING_MESOCYCLE in told_the_entrance(graphs)
    assert len(planned.seen) == 1


def test_the_prepared_negotiation_reads_as_the_machines_and_waiting(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    from trainer.coach import runs

    path = tmp_path / "checkpoints.sqlite"
    archive = tmp_path / "runs"
    with checkpoints.saver(path) as saver:
        graphs = finishing(catalogued, Scripted(documents=[NEXT]), saver=saver, archive=archive)
        asyncio.run(reported_and_prepared(graphs, Channels()))
        held = runs.negotiations(runs.kept(archive), runs.live(saver))

    (prepared,) = [one for one in held if one.unasked]
    assert prepared.outcome == runs.WAITING
    assert "opened by the machine" in runs.line(prepared)


def test_a_mesocycle_the_user_asked_for_and_has_not_answered_is_not_prepared_over(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """It already is the next one: preparing another would supersede it, and be a second."""
    planned = Scripted(documents=[A_MESOCYCLE, NEXT])
    front = Talking(handoff=entrance.PLAN_MESOCYCLE)
    graphs = finishing(catalogued, planned, front)
    asked = asking(graphs, "preparami un mesociclo")

    front.handoff = entrance.LOG_WORKOUT
    watched = Channels()
    asyncio.run(reported_and_prepared(graphs, watched))

    assert watched.offers == []
    assert len(planned.seen) == 1, "never a second planning run"
    assert graphs.planner.get_state(planning_on()).interrupts[0].id in asked.offers[0][1][0][0]


# -- onboarding ----------------------------------------------------------------

SETTLED = {
    "cycle_length": 2,
    "duration_cap_min": 45,
    "split": [["legs"], ["shoulders"]],
    "equipment": ["barbell"],
    "goal": "hypertrophy",
}
"""What the interview settles here: `FIXTURE_SPLIT`, which `CATALOG` can plan."""


def declaring(*made: tuple[str, dict[str, Any]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{n}", "type": "tool_call"}
            for n, (name, args) in enumerate(made)
        ],
    )


def interview_of(*turns: AIMessage, saver: BaseCheckpointSaver[Any]) -> onboarding.Onboarding:
    return onboarding.build(
        models.Chat(Scripted(turns=list(turns)), FRONT_PROVIDER, FRONT_MODEL),
        checkpointer=saver,
    )


def setting_up(interview: onboarding.Onboarding, saver: BaseCheckpointSaver[Any], plan: planner.Planner | None = None) -> bot.Graphs:
    return graphs_of(
        plan,
        front=Talking(handoff=entrance.SET_UP),
        interview=interview,
        saver=saver,
    )


def test_asking_to_set_up_reaches_the_interview_and_its_first_question(
    catalogued: sqlite3.Connection,
) -> None:
    saver = InMemorySaver()
    graphs = setting_up(interview_of(AIMessage(content="Per cosa ti alleni?"), saver=saver), saver)

    watched = asking(graphs, "voglio impostare l'allenamento")

    assert watched.said == [SAYS, "Per cosa ti alleni?"]


def test_the_interview_ends_in_the_file_and_a_mesocycle_offered(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    saver = InMemorySaver()
    declared.unlink()
    interview = interview_of(
        AIMessage(content="Dimmi tutto: obiettivo, allenamenti, attrezzi, tempo."),
        declaring((onboarding.DECLARE, SETTLED), (onboarding.FINISH, {})),
        saver=saver,
    )
    plan = graph_of(Scripted(documents=[A_MESOCYCLE]), checkpointer=saver)
    graphs = setting_up(interview, saver, plan)
    coach = turns_of(graphs)
    asyncio.run(coach.arriving(OWNER, CHAT, "impostiamo", Channels().chat))
    answered = Channels()

    asyncio.run(coach.arriving(OWNER, CHAT, "massa, gambe e spalle, bilanciere, 45", answered.chat))

    assert config.load(catalogued).split == (("legs",), ("shoulders",))
    assert answered.said == [entrance.ONBOARDED]
    (text, buttons) = answered.offers[0]
    assert "Barbell Squat" in text
    assert [label for _, label in buttons] == [label for _, label in bot.MESOCYCLE_BUTTONS]


def test_the_interview_survives_a_restart(
    tmp_path: Path, catalogued: sqlite3.Connection
) -> None:
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        graphs = setting_up(interview_of(AIMessage(content="Per cosa ti alleni?"), saver=saver), saver)
        asyncio.run(turns_of(graphs).arriving(OWNER, CHAT, "impostiamo", Channels().chat))

    with checkpoints.saver(path) as saver:
        graphs = setting_up(
            interview_of(AIMessage(content="E quanti allenamenti a rotazione?"), saver=saver),
            saver,
        )
        watched = Channels()
        asyncio.run(turns_of(graphs).arriving(OWNER, CHAT, "massa", watched.chat))

    assert watched.said == ["E quanti allenamenti a rotazione?"], "no entrance turn, no question twice"


def test_an_exclusion_the_interview_proposes_is_confirmed_by_a_tap(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    saver = InMemorySaver()
    interview = interview_of(
        declaring(
            (
                onboarding.PROPOSE_EXCLUSION,
                {"value": "vertical push", "retest_date": "2099-01-01", "why": "la spalla"},
            )
        ),
        declaring((onboarding.DECLARE, SETTLED), (onboarding.FINISH, {})),
        saver=saver,
    )
    plan = graph_of(Scripted(documents=[A_MESOCYCLE]), checkpointer=saver)
    graphs = setting_up(interview, saver, plan)
    coach = turns_of(graphs)
    watched = Channels()
    asyncio.run(coach.arriving(OWNER, CHAT, "impostiamo", watched.chat))
    (text, buttons) = watched.offers[0]
    assert "vertical push" in text
    yes = next(data for data, label in buttons if data.startswith(bot.CONFIRMED + bot.SEPARATOR))

    asyncio.run(coach.tapped(OWNER, CHAT, yes, Channels().chat))

    assert exclusions.active(catalogued, date.today().isoformat()) == (
        exclusions.Exclusion("pattern", "vertical push"),
    )


# -- a declaration changed (ADR-0012) --------------------------------------------

WRITTEN = FIXTURE_SPLIT
"""`SETTLED`, as TOML."""


def changing_with(*turns: AIMessage, plan: planner.Planner | None = None) -> bot.Graphs:
    """A chat whose every message changes a declaration, and an interview scripted by `turns`."""
    saver = InMemorySaver()
    return graphs_of(
        plan,
        front=Talking(handoff=entrance.CHANGE_DECLARATION),
        interview=interview_of(*turns, saver=saver),
        saver=saver,
    )


def test_a_bought_barbell_changes_the_equipment_and_nothing_else(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    before = WRITTEN.replace('equipment = ["barbell"]', 'equipment = ["dumbbell"]')
    declared.write_text(before, encoding="utf-8")
    graphs = changing_with(
        declaring(
            (onboarding.DECLARE, {"equipment": ["dumbbell", "barbell"]}), (onboarding.FINISH, {})
        )
    )

    watched = asking(graphs, "ho comprato un bilanciere")

    newest, older = config.versions(catalogued)
    assert newest.declaration == onboarding.settled(SETTLED | {"equipment": ["dumbbell", "barbell"]})
    assert older.declaration == onboarding.settled(SETTLED | {"equipment": ["dumbbell"]})
    assert watched.said == [SAYS, entrance.DECLARED], "no mesocycle running: nothing planned"
    assert watched.offers == []


def test_a_change_the_mesocycle_can_keep_says_why_and_plans_nothing(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    declared.write_text(WRITTEN, encoding="utf-8")
    served_from(catalogued)
    kept = mesocycles.active(catalogued)
    graphs = changing_with(
        declaring(
            (onboarding.DECLARE, {"equipment": ["barbell", "dumbbell"]}),
            (onboarding.CHOOSE, {"path": onboarding.KEEP, "why": "Il mesociclo regge: lo finiamo."}),
        )
    )

    watched = asking(graphs, "ho comprato dei manubri")

    assert watched.said == [SAYS, "Il mesociclo regge: lo finiamo."]
    assert watched.offers == []
    assert mesocycles.active(catalogued) == kept
    assert config.load(catalogued).equipment == ("barbell", "dumbbell")


def test_a_rewrite_chosen_is_offered_through_the_mesocycles_loop(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    declared.write_text(WRITTEN, encoding="utf-8")
    served_from(catalogued)
    longer = mesocycle_of(
        plan_of("Barbell_Squat", minutes=60), plan_of("Standing_Military_Press", minutes=60)
    )
    graphs = changing_with(
        declaring(
            (onboarding.DECLARE, {"duration_cap_min": 60}),
            (onboarding.CHOOSE, {"path": onboarding.REWRITE, "why": "Con un'ora lo allungo."}),
        ),
        plan=graph_of(Scripted(raw=[longer.model_dump_json()]), checkpointer=InMemorySaver()),
    )

    watched = asking(graphs, "d'ora in poi ho un'ora")

    assert watched.said == [SAYS, "Con un'ora lo allungo."]
    ((_, buttons),) = watched.offers
    assert [label for _, label in buttons] == [label for _, label in bot.MESOCYCLE_BUTTONS]
    assert config.load(catalogued).duration_cap_min == 60


def test_only_thirty_minutes_today_is_an_adaptation_and_leaves_the_file_alone(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    graphs = adapting_from(
        catalogued,
        calling(entrance.ADAPT_TODAY, said="solo 30 minuti oggi", minutes=30),
        planned=Scripted(documents=[plan_of("Barbell_Squat", rounds=2, minutes=30)]),
    )

    ((text, _),) = asking(graphs, "solo 30 minuti oggi").offers

    assert "30" in text
    assert len(config.versions(catalogued)) == 1, "no version written"
    interview = graphs.onboarding.get_state(
        {"configurable": {"thread_id": bot.under(bot.thread_for(CHAT), bot.ONBOARDING)}}
    )
    assert not interview.values, "no onboarding ran"
