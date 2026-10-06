"""Memory with a source: a conclusion is kept only when the user's own sentence is behind it."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from test_bot import (  # noqa: F401 -- fixtures
    A_MESOCYCLE,
    CHAT,
    OWNER,
    Channels,
    Talking,
    catalogued,
    declared,
    turns_of,
)
from test_logger import TODAY, connection, prescribe, report, scripted  # noqa: F401 -- fixture
from test_logger import graph_of as logger_graph_of
from test_planner import BARBELL_45, SCRIPTED, STAND_IN, Scripted, calling
from trainer.coach import bot, checkpoints, conclusions, entrance, logger, models, planner
from trainer.coach import record as run_record

HATE = "I hate pressing"
USER = "chat:1"
ON: RunnableConfig = {"configurable": {"thread_id": USER, conclusions.USER: USER}}


def remembering(conclusion: str, quote: str) -> AIMessage:
    return calling(conclusions.REMEMBER, conclusion=conclusion, quote=quote)


def front(model: Talking | Scripted, store: InMemoryStore) -> entrance.Entrance:
    return entrance.build(
        models.Chat(model, "front", "a-small-fast-one"),
        checkpointer=InMemorySaver(),
        store=store,
    )


def answer_to_remember(model: Talking | Scripted) -> ToolMessage:
    """What the model was told when it called `remember`."""
    (told,) = [
        message
        for message in model.seen[-1]
        if isinstance(message, ToolMessage) and message.name == conclusions.REMEMBER
    ]
    return told


# -- admission -----------------------------------------------------------------


def test_a_quote_is_admitted_word_for_word() -> None:
    assert conclusions.admitted(HATE, ["ciao", f"Honestly, {HATE}, always have."])


def test_case_spacing_and_typographic_quotes_are_not_a_paraphrase() -> None:
    """A phone types a curly apostrophe, and a model quoting it types a straight one."""
    assert conclusions.admitted("la cyclette  MI annoia.", ["La cyclette mi annoia"])
    assert conclusions.admitted("l'ellittica no", ["l’ellittica no, grazie"])


def test_a_paraphrased_quote_is_refused() -> None:
    assert not conclusions.admitted("I don't like pressing", [HATE])
    assert not conclusions.admitted("odio le spinte", [HATE])


def test_an_empty_quote_is_in_nothing() -> None:
    """The empty string is in every message, and would admit anything."""
    assert not conclusions.admitted("", [HATE])
    assert not conclusions.admitted(" «». ", [HATE])


# -- the entrance --------------------------------------------------------------


def test_a_quote_the_user_never_wrote_is_refused_and_the_refusal_reaches_the_model() -> None:
    store = InMemoryStore()
    model = Scripted(turns=[remembering("dislikes squats", "squats bore me"), AIMessage("ok")])

    front(model, store).invoke(entrance.heard(HATE), ON)

    told = answer_to_remember(model)
    assert told.status == "error"
    assert "not in anything the user wrote" in told.text
    assert conclusions.live(store, USER) == []


def test_a_paraphrase_said_to_the_entrance_is_refused() -> None:
    store = InMemoryStore()
    model = Scripted(
        turns=[remembering("dislikes pressing", "I don't like pressing"), AIMessage("ok")]
    )

    front(model, store).invoke(entrance.heard(HATE), ON)

    assert answer_to_remember(model).status == "error"
    assert conclusions.live(store, USER) == []


def test_a_sentence_the_user_wrote_is_kept_provisional_with_its_quote_and_date() -> None:
    store = InMemoryStore()
    model = Scripted(turns=[remembering("hates pressing", HATE), AIMessage("ok")])

    front(model, store).invoke(entrance.heard(HATE), ON)

    assert answer_to_remember(model).status == "success"
    (kept,) = conclusions.live(store, USER)
    assert (kept.conclusion, kept.quote, kept.state) == (
        "hates pressing",
        HATE,
        conclusions.PROVISIONAL,
    )
    assert kept.on


def test_a_sentence_from_an_earlier_turn_on_the_thread_is_the_users_too() -> None:
    store = InMemoryStore()
    model = Scripted(
        turns=[AIMessage("capito"), remembering("hates pressing", HATE), AIMessage("ok")]
    )
    graph = front(model, store)

    graph.invoke(entrance.heard(HATE), ON)
    graph.invoke(entrance.heard("e quindi?"), ON)

    assert [one.quote for one in conclusions.live(store, USER)] == [HATE]


def test_remembering_the_same_thing_twice_keeps_it_once() -> None:
    """The logger's tools node runs again from the top when an interrupt resumes it."""
    store = InMemoryStore()
    for _ in range(2):
        conclusions.kept(store, USER, {"conclusion": "hates pressing", "quote": HATE}, [HATE], TODAY)

    assert len(conclusions.live(store, USER)) == 1


def test_a_door_that_names_no_user_keeps_nothing() -> None:
    store = InMemoryStore()
    model = Scripted(turns=[remembering("hates pressing", HATE), AIMessage("ok")])

    front(model, store).invoke(
        entrance.heard(HATE), {"configurable": {"thread_id": "anonymous"}}
    )

    assert answer_to_remember(model).text == conclusions.NOWHERE
    assert store.search(("conclusions",)) == []


def test_remember_is_offered_only_where_there_is_a_store() -> None:
    kept, unkept = Scripted(turns=[AIMessage("ok")]), Scripted(turns=[AIMessage("ok")])

    front(kept, InMemoryStore()).invoke(entrance.heard("ciao"), ON)
    entrance.build(models.Chat(unkept, "front", "one")).invoke(entrance.heard("ciao"))

    assert conclusions.REMEMBER in kept.bound[0]
    assert conclusions.REMEMBER not in unkept.bound[0]


def test_a_retired_conclusion_is_not_live() -> None:
    store = InMemoryStore()
    conclusions.kept(store, USER, {"conclusion": "hates pressing", "quote": HATE}, [HATE], TODAY)
    (item,) = store.search(conclusions.namespace(USER))
    store.put(item.namespace, item.key, item.value | {"state": conclusions.RETIRED})

    assert conclusions.live(store, USER) == []


# -- the logger ----------------------------------------------------------------


def test_the_logger_keeps_a_sentence_from_the_report_and_refuses_one_from_nowhere(
    connection: sqlite3.Connection,
) -> None:
    said = "fatto tutto, ma la cyclette mi annoia"
    identifier = prescribe(connection)
    store = InMemoryStore()
    model = scripted(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": conclusions.REMEMBER,
                    "args": {"conclusion": "the bike bores them", "quote": "la cyclette mi annoia"},
                    "id": "kept",
                    "type": "tool_call",
                },
                {
                    "name": conclusions.REMEMBER,
                    "args": {"conclusion": "loves running", "quote": "adoro correre"},
                    "id": "refused",
                    "type": "tool_call",
                },
            ],
        ),
        AIMessage(content="tutto chiaro"),
        emits=report(workout_id=identifier, report=said),
    )

    logger_graph_of(model, store=store).invoke(
        logger.starting(said, TODAY, awaiting=identifier), {"configurable": {"thread_id": "log", conclusions.USER: USER}}
    )

    answers = {
        message.tool_call_id: message.status
        for message in model.seen[-1]
        if isinstance(message, ToolMessage)
    }
    assert answers == {"kept": "success", "refused": "error"}
    assert [one.quote for one in conclusions.live(store, USER)] == ["la cyclette mi annoia"]


# -- the planner ---------------------------------------------------------------


def test_the_brief_carries_every_live_conclusion_with_its_quote() -> None:
    known = [conclusions.Conclusion("hates pressing", HATE, conclusions.PROVISIONAL, TODAY)]

    written = planner.brief(BARBELL_45, known)

    assert "hates pressing" in written and f'"{HATE}"' in written
    assert "none of it is a rule" in written
    assert written.endswith("Plan the workout.")
    assert "hates pressing" not in planner.brief(BARBELL_45)


# -- through the bot, across a restart ------------------------------------------


def cast_of(front: models.Chat, plans: Scripted) -> models.Roster:
    """Every node on a stand-in: the talking ones on `front`, the planning ones on `plans`."""
    on = models.Chat(plans, SCRIPTED, STAND_IN)
    return {
        "entrance": front,
        "onboarding": front,
        "planner": on,
        "supervisor": on,
        "logger": models.Chat(Scripted(), SCRIPTED, STAND_IN),
    }


def test_i_hate_pressing_survives_a_restart_and_reaches_the_next_mesocycles_brief(
    tmp_path: Path, catalogued: sqlite3.Connection, declared: Path
) -> None:
    """Two processes over one home, the way two runs of `trainer bot` are."""
    checkpoints_file = tmp_path / "checkpoints.sqlite"
    store_file = tmp_path / conclusions.DEFAULT_NAME

    told = Talking(turns=[remembering("hates pressing", HATE), AIMessage(content="capito")])
    with checkpoints.saver(checkpoints_file) as saver, conclusions.opened(store_file) as store:
        first = bot.graphs(
            cast_of(models.Chat(told, "front", "a-small-fast-one"), Scripted()),
            saver,
            run_record.archive(),
            store,
        )
        asyncio.run(turns_of(first).arriving(OWNER, CHAT, HATE, Channels().chat))

    planning = Scripted(documents=[A_MESOCYCLE])
    with checkpoints.saver(checkpoints_file) as saver, conclusions.opened(store_file) as store:
        second = bot.graphs(
            cast_of(models.Chat(Talking(handoff=entrance.PLAN_MESOCYCLE), "front", "a-small-fast-one"), planning),
            saver,
            run_record.archive(),
            store,
        )
        watched = Channels()
        asyncio.run(
            turns_of(second).arriving(OWNER, CHAT, "preparami un mesociclo", watched.chat)
        )

    assert watched.offers, "the mesocycle was planned and offered"
    (brief,) = [
        message.text
        for message in planning.seen[0]
        if isinstance(message, HumanMessage) and "Plan the mesocycle." in message.text
    ]
    assert "hates pressing" in brief and HATE in brief
