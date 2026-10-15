"""The progress lines, read off the graph's own stream.

Offline like the rest of the suite: a scripted chat model, the real tools
against a fixture catalog, and no network anywhere.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from conftest import enrich
from test_planner import BARBELL_45, CATALOG, PATTERNS, Scripted, graph_of, plan_of
from trainer import plan as plans
from trainer.coach import logger as coach_logger
from trainer.coach import language, planner, progress
from trainer.engine import catalog, database, migrations


@pytest.fixture()
def catalogued(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


def looking() -> AIMessage:
    """A turn that asks the two tools whose line carries what they were given."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "admissible_set",
                "args": {"equipment": ["barbell"], "budget_min": 45},
                "id": "call-1",
            },
            {
                "name": "remaining_budget",
                "args": {"partial_plan": [], "budget_min": 45},
                "id": "call-2",
            },
        ],
    )


def streamed(model: Scripted) -> list[str]:
    """A whole run, with `Progress` fed the chunks LangGraph emits."""
    graph = graph_of(model, checkpointer=InMemorySaver())
    lines = progress.Progress()
    for chunk in graph.stream(
        {"request": BARBELL_45},
        {"configurable": {"thread_id": "t"}},
        stream_mode="updates",
    ):
        lines.reading(chunk)
    return lines.lines


def test_a_run_is_narrated_from_the_stream_it_produced(
    catalogued: sqlite3.Connection,
) -> None:
    """The tools the planner called, in the words they were called with, and
    then the plan being written."""
    lines = streamed(
        Scripted(turns=[looking(), AIMessage(content="Planned.")],
                 documents=[plan_of("Barbell_Squat")])
    )

    assert lines == [
        "guardo cosa puoi fare oggi con barbell e 45 minuti",
        "controllo quanto tempo resta → 45 min",
        language.texts(language.ITALIAN).progress.writing,
        "piano valido, 1 blocco",
    ]


def test_a_refusal_names_the_rules_it_broke_before_the_retry(
    catalogued: sqlite3.Connection,
) -> None:
    """The central line of the whole ticket: the validator's refusal going
    back to the planner is the decision of ADR-0004, and this is the only
    place a person can watch it happen.
    """
    lines = streamed(
        Scripted(
            turns=[AIMessage(content="Planned."), AIMessage(content="Again.")],
            # Barbell only today, so the dumbbell press is refused as
            # inadmissible and the second plan is the one that stands.
            documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
        )
    )

    assert lines == [
        language.texts(language.ITALIAN).progress.writing,
        f"il validatore ha rifiutato: {plans.ADMISSIBLE}",
        language.texts(language.ITALIAN).progress.rewriting,
        "piano valido, 1 blocco",
    ]


def test_a_run_that_never_reaches_a_valid_plan_says_so(
    catalogued: sqlite3.Connection,
) -> None:
    lines = streamed(
        Scripted(documents=[plan_of("Dumbbell_Bench_Press")] * planner.ATTEMPTS)
    )

    assert lines[-1] == language.texts(language.ITALIAN).progress.exhausted.format(attempts=planner.ATTEMPTS)


def test_every_tool_a_streamed_run_can_call_has_a_line(
    catalogued: sqlite3.Connection,
) -> None:
    """A tool added to a streamed graph's surface with no line of its own
    would reach the chat as `uso volume_deficit`, which is the code talking.

    Both graphs, because from session 9 both are streamed into the draft; the
    logger's question is a call like any other and shows as one.
    """
    streamed_tools = set(planner.TOOLS) | set(coach_logger.TOOLS) | {coach_logger.ask_user.__name__}
    for spoken in language.LANGUAGES:
        assert set(language.texts(spoken).progress.calls) == streamed_tools, spoken


def test_a_tool_the_model_called_wrong_is_still_a_line(
    catalogued: sqlite3.Connection,
) -> None:
    """The arguments are the model's and it gets them wrong. A progress line
    missing one says `?` where the word would have been, and a failed call
    says it failed -- neither is worth an exception on the way to the user."""
    lines = streamed(
        Scripted(
            turns=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "admissible_set", "args": {"budget_min": 45}, "id": "c"}
                    ],
                ),
                AIMessage(content="Planned."),
            ],
            documents=[plan_of("Barbell_Squat")],
        )
    )

    assert lines[0] == f"guardo cosa puoi fare oggi con ? e 45 minuti → {language.texts(language.ITALIAN).progress.failed}"


def test_the_draft_is_cut_to_what_telegram_carries() -> None:
    """A long run outruns the message limit. The oldest lines go, because the
    one the user is waiting on is the newest."""
    lines = progress.Progress()
    lines.lines = [f"linea {n} " + "x" * 100 for n in range(100)]

    text = lines.text()

    assert len(text) <= progress.LIMIT
    assert text.endswith(lines.lines[-1])
    assert lines.lines[0] not in text


def test_one_line_past_the_limit_is_cut_as_well() -> None:
    """Dropping whole lines is not enough. `search_exercises` is called with
    whatever phrase the model wrote, and one line can be longer than Telegram
    carries on its own -- at which point every send for the rest of the run is
    refused, and refused silently, because a draft that fails is logged and
    nothing more.
    """
    lines = progress.Progress()
    lines.lines = ["cerco «" + "x" * (progress.LIMIT * 2) + "» in catalogo"]

    assert len(lines.text()) <= progress.LIMIT


def test_nothing_read_yet_is_an_empty_draft() -> None:
    """Which is Telegram's *Thinking...* placeholder, and what the first
    minutes of a local run have to show."""
    assert progress.Progress().text() == ""


def test_a_chunk_that_is_not_a_node_is_left_alone() -> None:
    """`__interrupt__` arrives on the same stream and is a tuple, not a delta."""
    lines = progress.Progress()

    assert not lines.reading({"__interrupt__": ("whatever",)})
    assert lines.lines == []


def test_a_plan_turned_down_says_the_run_is_starting_again() -> None:
    """The `propose` node hands back a fresh run when the user refuses, and
    minutes of silence follow it."""
    lines = progress.Progress()

    assert lines.reading({"propose": dict(planner.starting(BARBELL_45))})
    assert lines.lines == [language.texts(language.ITALIAN).progress.again]


def test_an_accepted_plan_is_not_a_new_run() -> None:
    lines = progress.Progress()

    assert not lines.reading({"propose": {"accepted": True}})
    assert lines.lines == []


def test_the_lines_are_what_a_reader_of_italian_would_write() -> None:
    """One block is one block. The count comes off the plan, so a plan with a
    single block must not read `1 blocchi`."""
    lines = progress.Progress()
    lines.reading({"validate": {"violations": (), "plan": plan_of("Barbell_Squat")}})
    lines.reading(
        {"validate": {"violations": (), "plan": plan_of("Barbell_Squat", "Standing_Military_Press")}}
    )

    assert lines.lines == ["piano valido, 1 blocco", "piano valido, 2 blocchi"]


def test_an_unknown_tool_is_named_rather_than_dropped() -> None:
    """Never reached while the test above is green, and a line all the same:
    a run that is doing something must not look like a run doing nothing."""
    lines = progress.Progress()
    reply = AIMessage(
        content="", tool_calls=[{"name": "invented", "args": {}, "id": "c"}]
    )
    answers: list[Any] = [None]

    lines.reading({"planner": {"messages": [reply]}})
    lines.reading({"tools": {"messages": answers}})

    assert lines.lines == ["uso invented"]
