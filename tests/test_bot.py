"""The bot: who it answers, which thread a chat is, and what a message that arrives mid-run becomes.

Offline, like the rest of the suite. The Telegram client is never built: what
is driven here is the part that decides, with the updates constructed by hand.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from collections.abc import Iterator
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
from trainer import plan as plans
from trainer import tools
from test_planner import BARBELL_45, CATALOG, PATTERNS, Scripted, plan_of
from trainer.coach import bot, checkpoints, planner, progress
from trainer.engine import catalog, database, migrations, workouts

OWNER = 6421
STRANGER = 99
CHAT = 6421

FIXTURE_SPLIT = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
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
    coach = bot.Coach(owner_id=OWNER, run=never)

    asyncio.run(coach.arriving(STRANGER, CHAT, "ciao", channel(say, nowhere)))

    assert said == []


def test_start_from_anybody_else_is_answered_with_nothing() -> None:
    """Checked before anything else looks at the message, so the command a
    stranger sends is as ignored as the prose."""
    said, say = spoken()
    coach = bot.Coach(owner_id=OWNER, run=never)

    asyncio.run(coach.started(STRANGER, CHAT, channel(say)))

    assert said == []


def test_start_answers_the_owner() -> None:
    said, say = spoken()
    coach = bot.Coach(owner_id=OWNER, run=never)

    asyncio.run(coach.started(OWNER, CHAT, channel(say)))

    assert said == [bot.STARTED]


def test_a_stranger_leaves_nothing_in_the_thread(
    tmp_path: Path, database_file: Path
) -> None:
    """Not just unanswered: a message nobody may send must not reach the state
    either, or the next run plans against a sentence the owner never wrote."""
    said, say = spoken()
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))

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

        coach = bot.Coach(owner_id=OWNER, run=slow)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        await started.wait()

        await coach.arriving(OWNER, CHAT, "due", channel(say, nowhere))
        assert said == [bot.QUEUED], "the second message was dropped"

        release.set()
        await first
        return said

    assert asyncio.run(scenario()) == [bot.QUEUED, "fatto: uno", "fatto: due"]


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

        coach = bot.Coach(owner_id=OWNER, run=sometimes)
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

        coach = bot.Coach(owner_id=OWNER, run=falls_over)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        await started.wait()
        await coach.arriving(OWNER, CHAT, "due", channel(say, nowhere))

        release.set()
        await first
        return said

    assert asyncio.run(scenario()) == [bot.QUEUED, bot.FAILED, "fatto: due"]


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

        coach = bot.Coach(owner_id=OWNER, run=run)
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

        coach = bot.Coach(owner_id=OWNER, run=never)
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

        coach = bot.Coach(owner_id=OWNER, run=slow)
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
    written = [plan_of("Barbell_Squat"), plan_of("Barbell_Squat")]

    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(documents=written[:1]), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
        first = Channels()
        asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", first.chat))

    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(documents=written[1:]), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
        second = Channels()
        asyncio.run(coach.arriving(OWNER, CHAT, "e domani?", second.chat))

        assert bot.turns(graph, bot.thread_for(CHAT)) == [
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
        graph = planner.build(
            Scripted(documents=[plan_of("Barbell_Squat"), plan_of("Barbell_Squat")]),
            checkpointer=saver,
        )
        coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
        asyncio.run(coach.arriving(OWNER, CHAT, "la mia", Channels().chat))
        asyncio.run(
            coach.arriving(OWNER, CHAT + 1, "l'altra", Channels().chat)
        )

        assert bot.turns(graph, bot.thread_for(CHAT)) == ["la mia"]
        assert bot.turns(graph, bot.thread_for(CHAT + 1)) == ["l'altra"]


# -- what am I doing today? ----------------------------------------------------


def asking(graph: planner.Planner, text: str = "cosa faccio oggi?") -> Channels:
    """The owner asks, on their own chat. Everything that came back, by channel."""
    watched = Channels()
    coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
    asyncio.run(coach.arriving(OWNER, CHAT, text, watched.chat))
    return watched


def test_asking_what_today_is_reaches_a_plan_with_buttons(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The message names nothing. The groups come from where the rotation is,
    the minutes from the declared cap, and the equipment from the
    declaration."""
    graph = planner.build(
        Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=InMemorySaver()
    )

    watched = asking(graph)

    assert watched.said == [], "the plan is offered, never said"
    (text, buttons) = watched.offers[0]
    assert "Barbell Squat" in text
    assert [label for _, label in buttons] == [label for _, label in bot.BUTTONS]


def test_the_request_the_chat_planned_against_was_derived_and_not_asked_for(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Nothing in the message says barbell, 45 minutes or legs."""
    graph = planner.build(
        Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=InMemorySaver()
    )

    asking(graph)

    # Read back through the checkpointer, which is where the tuples the
    # request is built out of arrive as lists: msgpack has one sequence.
    planned = graph.get_state(
        {"configurable": {"thread_id": bot.thread_for(CHAT)}}
    ).values["request"]
    assert list(planned.equipment) == ["barbell"]
    assert planned.budget_min == 45
    assert list(planned.groups) == ["legs"]
    assert [tuple(share) for share in planned.allocation] == [("legs", 45)]


def test_the_chat_and_the_terminal_plan_against_one_request(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The chat passes an empty `Asked` and the terminal passes what its flags
    collected; against the same state the two are one request. Compared field
    by field because the chat's comes back through the checkpointer, where
    every tuple arrives as a list.
    """
    graph = planner.build(
        Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=InMemorySaver()
    )

    asking(graph)

    from_the_chat = graph.get_state(
        {"configurable": {"thread_id": bot.thread_for(CHAT)}}
    ).values["request"]
    from_the_terminal = plans.requested(
        catalogued, date.today().isoformat(), plans.Asked()
    ).request
    assert list(from_the_chat.equipment) == list(from_the_terminal.equipment)
    assert from_the_chat.budget_min == from_the_terminal.budget_min
    assert list(from_the_chat.groups) == list(from_the_terminal.groups)
    assert [tuple(share) for share in from_the_chat.allocation] == list(
        from_the_terminal.allocation
    )
    assert list(from_the_chat.preferences) == list(from_the_terminal.preferences)


def test_tapping_accept_on_what_the_chat_offered_writes_the_workout(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The first door that reaches ticket 03's resume: asked for, offered,
    accepted, written -- and written by the graph, never by the bot."""
    graph = planner.build(
        Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=InMemorySaver()
    )
    thread = bot.thread_for(CHAT)
    sent = asking(graph).offers
    assert workout_rows(catalogued) == []

    said, say = spoken()
    _, offer = offered()
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))
    asyncio.run(coach.tapped(OWNER, CHAT, sent[0][1][0][0], channel(say, offer)))

    assert said == [bot.WRITTEN]
    (written,) = workout_rows(catalogued)
    assert written[1] == "prescribed"
    assert bot.turns(graph, thread) == ["cosa faccio oggi?"]


def test_asking_again_supersedes_the_plan_still_waiting(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """A second question is a second plan, and the buttons under the first one
    stop answering anything -- which is what `SUPERSEDED` is for."""
    graph = planner.build(
        Scripted(documents=[plan_of("Barbell_Squat"), plan_of("Barbell_Squat")]),
        checkpointer=InMemorySaver(),
    )
    first = asking(graph).offers
    second = asking(graph, "e adesso?").offers

    assert first[0][1][0][0] != second[0][1][0][0], "the same proposal id twice"
    said, say = spoken()
    _, offer = offered()
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))
    asyncio.run(coach.tapped(OWNER, CHAT, first[0][1][0][0], channel(say, offer)))

    assert said == [bot.SUPERSEDED]
    assert workout_rows(catalogued) == []


def test_a_second_question_is_planned_against_its_own_brief(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The thread keeps the messages of the run before it, and `turn` writes
    the brief only when it finds none. Left there, the second plan is asked
    for as a follow-up to a conversation about the first."""
    model = Scripted(documents=[plan_of("Barbell_Squat"), plan_of("Barbell_Squat")])
    graph = planner.build(model, checkpointer=InMemorySaver())

    asking(graph)
    briefs = sum("Plan the workout." in m.text for m in model.seen[-1])
    asking(graph, "e adesso?")

    assert sum("Plan the workout." in m.text for m in model.seen[-1]) == briefs


def test_no_training_configuration_stops_the_run_and_stays_on_the_machine(
    catalogued: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without the file there is nothing to derive the equipment, the minutes
    or the groups from. The chat is told the run cannot happen; *which* state
    it is goes to the log, because the engine says it with the absolute path
    of the file to copy and of the directory to copy it into.
    """
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))
    graph = planner.build(Scripted(), checkpointer=InMemorySaver())

    with caplog.at_level(logging.WARNING, logger="trainer.coach.bot"):
        watched = asking(graph)

    assert watched.offers == []
    assert watched.said == [bot.BLOCKED]
    assert watched.drafts == [], "a state is answered before any run is promised"
    assert "no training configuration yet" in caplog.text
    assert str(tmp_path / "absent.toml") in caplog.text


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
    graph = planner.build(Scripted(), checkpointer=InMemorySaver())

    with caplog.at_level(logging.WARNING, logger="trainer.coach.bot"):
        watched = asking(graph)

    assert watched.offers == []
    assert watched.said == [bot.BLOCKED]
    assert watched.drafts == []
    assert "trainer enrich derive" in caplog.text


def test_a_database_nobody_imported_stops_the_run_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The same path, on the other precondition a plan needs. `trainer bot`
    can start against a machine that has no catalog yet."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))
    graph = planner.build(Scripted(), checkpointer=InMemorySaver())

    with caplog.at_level(logging.WARNING, logger="trainer.coach.bot"):
        watched = asking(graph)

    assert watched.offers == []
    assert watched.said == [bot.BLOCKED]
    assert "trainer db init" in caplog.text


def test_every_precondition_is_one_line_and_the_same_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which state it is must not be readable off the chat at all. Three
    different wordings would tell a reader of the chat as much as quoting the
    engine did, one guess at a time.
    """
    graph = planner.build(Scripted(), checkpointer=InMemorySaver())

    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))
    without_config = asking(graph).said
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))
    without_database = asking(graph).said

    assert without_config == without_database == [bot.BLOCKED]


def test_the_blocked_line_has_nothing_to_substitute_into() -> None:
    """The bug this closes, in one line. `BLOCKED` used to end in `{state}`
    and was formatted with the engine's own sentence -- absolute paths and
    all -- on its way to a third party's servers. A constant with no slot in
    it cannot carry one again by accident.

    The three tests above are the other half: whatever the state, the chat
    gets this and only this.
    """
    assert "{" not in bot.BLOCKED


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

    coach = bot.Coach(owner_id=OWNER, run=run)
    sent = Sent()

    asyncio.run(bot._on_message(coach)(update_of("cosa faccio oggi?"), cast(Any, sent)))

    assert seen == [(bot.thread_for(CHAT), "cosa faccio oggi?")]
    assert sent.lines == [(CHAT, "fatto")]


def test_a_constructed_update_from_a_stranger_is_answered_with_nothing() -> None:
    coach = bot.Coach(owner_id=OWNER, run=never)
    sent = Sent()

    asyncio.run(
        bot._on_message(coach)(update_of("ciao", user_id=STRANGER), cast(Any, sent))
    )

    assert sent.lines == []


def test_start_reaches_the_coach_through_a_constructed_update() -> None:
    coach = bot.Coach(owner_id=OWNER, run=never)
    sent = Sent()

    asyncio.run(bot._on_start(coach)(update_of("/start"), cast(Any, sent)))

    assert sent.lines == [(CHAT, bot.STARTED)]


def test_an_update_with_nobody_in_it_is_left_alone() -> None:
    """Some updates carry neither a user nor a chat -- a poll answer, a channel
    post. There is nobody to answer and no thread to run on."""
    coach = bot.Coach(owner_id=OWNER, run=never)
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
    """A graph stopped at a proposed plan, on the owner's thread."""
    graph = planner.build(model, checkpointer=InMemorySaver())
    thread = bot.thread_for(CHAT)
    final = graph.invoke({"request": BARBELL_45}, {"configurable": {"thread_id": thread}})
    return graph, thread, final


def tap_on(final: dict[str, Any], thread: str, action: str) -> str:
    return bot.carried(bot.Tap(action, thread, final["__interrupt__"][0].id))


def workout_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in connection.execute("SELECT id, state FROM workouts")]


def still_waiting(graph: planner.Planner, thread: str) -> tuple[str, ...]:
    return graph.get_state({"configurable": {"thread_id": thread}}).next


def test_a_valid_plan_reaches_the_chat_with_three_buttons(
    catalogued: sqlite3.Connection,
) -> None:
    """And the run is waiting on it, not finished."""
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()

    asyncio.run(bot.told(final, thread, channel(say, offer)))

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
    asyncio.run(bot.told(final, thread, channel(spoken()[1], offer)))

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
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))

    asyncio.run(coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.KEPT), channel(say, offer)))

    assert said == [bot.WRITTEN]
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
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))

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
        documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")],
    )
    graph, thread, final = waiting_on_a_plan(model)
    sent, offer = offered()
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))

    asyncio.run(
        coach.tapped(
            OWNER, CHAT, tap_on(final, thread, bot.SHORTER), channel(spoken()[1], offer)
        )
    )

    asked = graph.get_state({"configurable": {"thread_id": thread}}).values["request"]
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
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))
    stale = bot.carried(bot.Tap(bot.KEPT, thread, "a-proposal-from-three-days-ago"))

    asyncio.run(coach.tapped(OWNER, CHAT, stale, channel(say, offer)))

    assert said == [bot.SUPERSEDED]
    assert sent == []
    assert workout_rows(catalogued) == []
    assert still_waiting(graph, thread) == ("propose",)


def test_the_same_plan_cannot_be_accepted_twice(catalogued: sqlite3.Connection) -> None:
    """The second tap answers a plan that has been answered: one workout and not
    two, and `record_prescribed` has no upsert that would hide the difference."""
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))
    data = tap_on(final, thread, bot.KEPT)

    asyncio.run(coach.tapped(OWNER, CHAT, data, channel(say, offer)))
    asyncio.run(coach.tapped(OWNER, CHAT, data, channel(say, offer)))

    assert said == [bot.WRITTEN, bot.SUPERSEDED]
    assert len(workout_rows(catalogued)) == 1


def test_a_tap_from_anybody_else_resumes_nothing(catalogued: sqlite3.Connection) -> None:
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))

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

        coach = bot.Coach(owner_id=OWNER, run=slow, resume=bot.answering(graph))
        running = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", channel(say, nowhere)))
        await started.wait()
        await coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.KEPT), channel(say, offer))

        release.set()
        await running
        return said

    assert asyncio.run(scenario()) == [bot.QUEUED, "fatto: uno", bot.WRITTEN]
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
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))
    sent = Sent()
    update = callback_of(tap_on(final, thread, bot.KEPT))
    update.callback_query.set_bot(cast(Any, sent))  # type: ignore[union-attr]

    asyncio.run(bot._on_tap(coach)(update, cast(Any, sent)))

    assert sent.answered == ["tap-1"], "the button was left spinning"
    assert sent.lines == [(CHAT, bot.WRITTEN)]
    assert len(workout_rows(catalogued)) == 1


def test_a_constructed_tap_from_a_stranger_resumes_nothing(
    catalogued: sqlite3.Connection,
) -> None:
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))
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
        resume = bot.answering(graph)

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
        documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
    )


def test_the_plan_is_a_message_sent_after_the_last_draft(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """The acceptance criterion of the whole ticket, at the layer that talks to
    Telegram. A draft lasts about thirty seconds; the plan has to still be
    there tomorrow, so it is an ordinary message and it goes last."""
    graph = planner.build(refusing_then_planning(), checkpointer=InMemorySaver())
    coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
    sent = Sent()

    asyncio.run(bot._on_message(coach)(update_of("cosa faccio oggi?"), cast(Any, sent)))

    assert sent.order[-1] == "message", "the chat was left holding a draft"
    assert sent.order.count("message") == 1
    assert "draft" in sent.order[:-1], "nothing was streamed while it worked"
    assert sent.offers, "the plan came without its buttons"


def test_the_whole_run_updates_one_draft_in_place(
    catalogued: sqlite3.Connection, declared: Path
) -> None:
    """One non-zero id for the run, so Telegram animates the changes instead of
    stacking a preview per line."""
    graph = planner.build(refusing_then_planning(), checkpointer=InMemorySaver())
    coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
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
    graph = planner.build(refusing_then_planning(), checkpointer=InMemorySaver())
    watched = asking(graph)

    assert watched.drafts[0] == bot.WORKING
    assert "" not in watched.drafts, "an empty draft asks the client to invent one"
    assert watched.drafts[-1].splitlines() == [
        progress.WRITING,
        f"il validatore ha rifiutato: {plans.ADMISSIBLE}",
        progress.REWRITING,
        "piano valido, 1 blocco",
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
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))

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

    graph = planner.build(
        Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=InMemorySaver()
    )
    watched = Channels()
    coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
    chat = bot.Chat(say=watched.chat.say, offer=watched.chat.offer, draft=refused)

    asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", chat))

    assert watched.said == []
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
    graph = planner.build(Falling(), checkpointer=InMemorySaver())
    coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))

    asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", watched.chat))

    assert watched.said == [bot.FAILED]
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
        graph = planner.build(Falling(), checkpointer=InMemorySaver())
        coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))
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
        graph = planner.build(
            Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver
        )
        watched = Channels()
        coach = bot.Coach(owner_id=OWNER, run=bot.planning(graph))

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
        graph = planner.build(
            Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver
        )

        final = graph.invoke(
            {"request": BARBELL_45}, {"configurable": {"thread_id": "terminal"}}
        )

        assert final["__interrupt__"], "the terminal's own door still works"
