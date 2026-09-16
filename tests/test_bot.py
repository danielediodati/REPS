"""The bot: who it answers, which thread a chat is, and what a message that arrives mid-run becomes.

Offline, like the rest of the suite. The Telegram client is never built: what
is driven here is the part that decides, with the updates constructed by hand.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage
from telegram import Bot, CallbackQuery, Chat, Message, Update, User
from telegram.error import InvalidToken, RetryAfter, TimedOut

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Interrupt

from conftest import enrich
from test_planner import BARBELL_45, CATALOG, PATTERNS, Scripted, plan_of
from trainer.coach import bot, checkpoints, planner
from trainer.engine import catalog, database, migrations, workouts

OWNER = 6421
STRANGER = 99
CHAT = 6421


def spoken() -> tuple[list[str], bot.Say]:
    """A chat that remembers what was said into it."""
    said: list[str] = []

    async def say(line: str) -> None:
        said.append(line)

    return said, say


async def never(thread: str, text: str, say: bot.Say) -> None:
    """A run that must not happen. Whatever refused it should have refused it first."""
    raise AssertionError(f"a run started on {thread} for {text!r}")


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

    asyncio.run(coach.arriving(STRANGER, CHAT, "ciao", say))

    assert said == []


def test_start_from_anybody_else_is_answered_with_nothing() -> None:
    """Checked before anything else looks at the message, so the command a
    stranger sends is as ignored as the prose."""
    said, say = spoken()
    coach = bot.Coach(owner_id=OWNER, run=never)

    asyncio.run(coach.started(STRANGER, CHAT, say))

    assert said == []


def test_start_answers_the_owner() -> None:
    said, say = spoken()
    coach = bot.Coach(owner_id=OWNER, run=never)

    asyncio.run(coach.started(OWNER, CHAT, say))

    assert said == [bot.STARTED]


def test_a_stranger_leaves_nothing_in_the_thread(
    tmp_path: Path, database_file: Path
) -> None:
    """Not just unanswered: a message nobody may send must not reach the state
    either, or the next run plans against a sentence the owner never wrote."""
    said, say = spoken()
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.recording(graph))

        asyncio.run(coach.arriving(STRANGER, CHAT, "pianifica per me", say))

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

        async def slow(thread: str, text: str, say: bot.Say) -> None:
            nonlocal inside
            inside += 1
            assert inside == 1, "two runs at once on one thread"
            started.set()
            await release.wait()
            await say(f"fatto: {text}")
            inside -= 1

        coach = bot.Coach(owner_id=OWNER, run=slow)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", say))
        await started.wait()

        await coach.arriving(OWNER, CHAT, "due", say)
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

        async def sometimes(thread: str, text: str, say: bot.Say) -> None:
            """The same coach, so the flag the first run left is the one the
            second message meets."""
            nonlocal runs
            runs += 1
            if runs == 1:
                raise RuntimeError("the provider went away")
            await say(f"fatto: {text}")

        coach = bot.Coach(owner_id=OWNER, run=sometimes)
        await coach.arriving(OWNER, CHAT, "uno", say)
        await coach.arriving(OWNER, CHAT, "due", say)
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

        async def falls_over(thread: str, text: str, say: bot.Say) -> None:
            if text == "uno":
                started.set()
                await release.wait()
                raise RuntimeError("the provider went away")
            await say(f"fatto: {text}")

        coach = bot.Coach(owner_id=OWNER, run=falls_over)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", say))
        await started.wait()
        await coach.arriving(OWNER, CHAT, "due", say)

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

        async def run(thread: str, text: str, say: bot.Say) -> None:
            attempted.append(text)
            if text == "uno":
                started.set()
                await release.wait()
            await say(f"fatto: {text}")

        coach = bot.Coach(owner_id=OWNER, run=run)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", unreachable))
        await started.wait()
        await coach.arriving(OWNER, CHAT, "due", unreachable)

        release.set()
        await first
        return attempted

    assert asyncio.run(scenario()) == ["uno", "due"]


def test_start_survives_a_chat_that_cannot_be_written_to() -> None:
    async def scenario() -> None:
        async def unreachable(line: str) -> None:
            raise RuntimeError("Timed out")

        coach = bot.Coach(owner_id=OWNER, run=never)
        await coach.started(OWNER, CHAT, unreachable)

    asyncio.run(scenario())


def test_two_chats_do_not_wait_for_each_other() -> None:
    """The queue is per thread. One chat is one conversation, and a bot that
    serialised every chat would be a queue nobody asked for -- there is one
    owner today, and the same bot answers the group it is added to tomorrow."""

    async def scenario() -> list[str]:
        said, say = spoken()
        started, release = asyncio.Event(), asyncio.Event()

        async def slow(thread: str, text: str, say: bot.Say) -> None:
            if text == "uno":
                started.set()
                await release.wait()
            await say(f"fatto: {text}")

        coach = bot.Coach(owner_id=OWNER, run=slow)
        first = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", say))
        # Waited for rather than yielded to once: ticket 02 puts a graph run
        # behind this, and the first `await` it adds ahead of `release` would
        # make the order below flaky instead of red.
        await started.wait()
        await coach.arriving(OWNER, CHAT + 1, "due", say)
        release.set()
        await first
        return said

    assert asyncio.run(scenario()) == ["fatto: due", "fatto: uno"]


# -- across a restart ----------------------------------------------------------


def test_the_thread_survives_a_restart(tmp_path: Path, database_file: Path) -> None:
    """Two compiled graphs over one checkpoint file, the way two runs of
    `trainer bot` are. The conversation is the checkpointer's (ADR-0004, item
    5), so the second process finds what the first was told."""
    said, say = spoken()
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.recording(graph))
        asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", say))

    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.recording(graph))
        asyncio.run(coach.arriving(OWNER, CHAT, "e domani?", say))

        assert bot.turns(graph, bot.thread_for(CHAT)) == [
            "cosa faccio oggi?",
            "e domani?",
        ]


def test_two_chats_are_two_threads(tmp_path: Path, database_file: Path) -> None:
    said, say = spoken()

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.recording(graph))
        asyncio.run(coach.arriving(OWNER, CHAT, "la mia", say))
        asyncio.run(coach.arriving(OWNER, CHAT + 1, "l'altra", say))

        assert bot.turns(graph, bot.thread_for(CHAT)) == ["la mia"]
        assert bot.turns(graph, bot.thread_for(CHAT + 1)) == ["l'altra"]


def test_the_owners_message_is_answered(tmp_path: Path, database_file: Path) -> None:
    """Ticket 01 has no plan to give back yet -- 02 puts it in the chat -- so
    what it owes is an answer that is true."""
    said, say = spoken()

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        coach = bot.Coach(owner_id=OWNER, run=bot.recording(graph))
        asyncio.run(coach.arriving(OWNER, CHAT, "cosa faccio oggi?", say))

    assert said == [bot.RECEIVED]


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
        self.answered: list[str] = []
        self.bot: Any = self

    async def send_message(
        self, chat_id: int, text: str, reply_markup: Any = None
    ) -> None:
        if reply_markup is None:
            self.lines.append((chat_id, text))
        else:
            self.offers.append((chat_id, text, reply_markup))

    async def answer_callback_query(self, callback_query_id: str, **kwargs: Any) -> bool:
        self.answered.append(callback_query_id)
        return True


def test_a_constructed_update_reaches_the_coach_and_is_answered() -> None:
    """The handler layer, which every test above this one went around: who
    sent it, which chat it is, and the text out of the message."""
    seen: list[tuple[str, str]] = []

    async def run(thread: str, text: str, say: bot.Say) -> None:
        seen.append((thread, text))
        await say("fatto")

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

    asyncio.run(bot.told(final, thread, say, offer))

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
    asyncio.run(bot.told(final, thread, spoken()[1], offer))

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

    asyncio.run(coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.KEPT), say, offer))

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
        coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.TURNED_DOWN), say, offer)
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
            OWNER, CHAT, tap_on(final, thread, bot.SHORTER), spoken()[1], offer
        )
    )

    asked = graph.get_state({"configurable": {"thread_id": thread}}).values["request"]
    assert asked.budget_min == bot.SHORTER_MINUTES
    assert "of 30" in sent[0][0], "rendered against the time it was asked for"


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

    asyncio.run(coach.tapped(OWNER, CHAT, stale, say, offer))

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

    asyncio.run(coach.tapped(OWNER, CHAT, data, say, offer))
    asyncio.run(coach.tapped(OWNER, CHAT, data, say, offer))

    assert said == [bot.WRITTEN, bot.SUPERSEDED]
    assert len(workout_rows(catalogued)) == 1


def test_a_tap_from_anybody_else_resumes_nothing(catalogued: sqlite3.Connection) -> None:
    graph, thread, final = waiting_on_a_plan(Scripted(documents=[plan_of("Barbell_Squat")]))
    said, say = spoken()
    sent, offer = offered()
    coach = bot.Coach(owner_id=OWNER, run=never, resume=bot.answering(graph))

    asyncio.run(coach.tapped(STRANGER, CHAT, tap_on(final, thread, bot.KEPT), say, offer))

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

        async def slow(thread: str, text: str, say: bot.Say) -> None:
            started.set()
            await release.wait()
            await say("fatto: " + text)

        coach = bot.Coach(owner_id=OWNER, run=slow, resume=bot.answering(graph))
        running = asyncio.create_task(coach.arriving(OWNER, CHAT, "uno", say))
        await started.wait()
        await coach.tapped(OWNER, CHAT, tap_on(final, thread, bot.KEPT), say, offer)

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


def test_a_resume_does_not_block_the_bot_while_the_model_thinks() -> None:
    """`graph.invoke` is a synchronous round trip to the model -- minutes of it
    on Ollama. Run on the event loop, it blocks the process that long-polls
    Telegram: no second tap, no message queued, and not even the QUEUED that
    promises one, until the plan comes back.

    The graph here is a stand-in that blocks until the loop has run something
    else. On the loop, the two wait for each other and nothing arrives.
    """

    async def scenario() -> list[str]:
        went_on = threading.Event()
        worked: list[str] = []

        class Blocking:
            """A graph whose invoke does not return until the loop has moved."""

            def get_state(self, config: Any) -> Any:
                return SimpleNamespace(interrupts=(Interrupt(value={}, id="proposal"),))

            def invoke(self, command: Any, config: Any) -> dict[str, Any]:
                assert went_on.wait(5), "the loop never ran while the graph worked"
                worked.append("planned")
                return {"workout": 1}

        resume = bot.answering(cast(Any, Blocking()))
        said, say = spoken()
        _, offer = offered()
        thread = bot.thread_for(CHAT)

        async def answering() -> None:
            await resume(thread, bot.Tap(bot.KEPT, thread, "proposal"), say, offer)

        tapped = asyncio.create_task(answering())
        # Long enough for the loop to have run the task and reached the
        # graph: with the call on the loop, this sleep is what never returns.
        await asyncio.sleep(0.05)
        went_on.set()
        await tapped
        return worked + said

    assert asyncio.run(scenario()) == ["planned", bot.WRITTEN]
