"""The progress line, read off the graph's own stream.

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
from test_planner import BARBELL_45, CATALOG, PATTERNS, Scripted, graph_of, mesocycle_of, plan_of
from trainer import plan as plans
from trainer import tools
from trainer.coach import language, planner, progress
from trainer.engine import catalog, database, migrations

SAID = language.texts(language.ITALIAN).progress


@pytest.fixture()
def catalogued(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


def looking() -> AIMessage:
    """A turn that asks two tools."""
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


def streamed(model: Scripted, **built: Any) -> progress.Progress:
    """A whole run, with `Progress` fed the chunks LangGraph emits."""
    graph = graph_of(model, checkpointer=InMemorySaver(), **built)
    lines = progress.Progress()
    for chunk in graph.stream(
        {"request": BARBELL_45},
        {"configurable": {"thread_id": "t"}},
        stream_mode="updates",
    ):
        lines.reading(chunk)
    return lines


def test_a_run_is_one_line_that_changes_phase(
    catalogued: sqlite3.Connection,
) -> None:
    """The tools the planner called are one phase, whatever they were; the
    draft shows the phase the run is in and nothing before it."""
    lines = streamed(
        Scripted(turns=[looking(), AIMessage(content="Planned.")],
                 documents=[plan_of("Barbell_Squat")])
    )

    assert lines.lines == [SAID.looking, SAID.writing, SAID.checking, "piano valido, 1 blocco"]
    assert lines.text() == "piano valido, 1 blocco"


def test_a_refusal_is_a_phase_of_its_own_before_the_rewrite(
    catalogued: sqlite3.Connection,
) -> None:
    """The validator's refusal going back to the planner is the decision of
    ADR-0004, and this is the only place a person can watch it happen."""
    lines = streamed(
        Scripted(
            turns=[AIMessage(content="Planned."), AIMessage(content="Again.")],
            # Barbell only today, so the dumbbell press is refused as
            # inadmissible and the second plan is the one that stands.
            documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
        )
    )

    assert lines.lines == [
        SAID.writing,
        SAID.checking,
        SAID.refused.format(rules=plans.ADMISSIBLE),
        SAID.rewriting,
        SAID.checking,
        "piano valido, 1 blocco",
    ]


def test_a_spent_call_budget_goes_straight_to_writing(
    catalogued: sqlite3.Connection,
) -> None:
    """With no budget left the planner is not asked again, so the turn that
    would have said *writing* never comes: the tools say it instead."""
    lines = streamed(
        Scripted(turns=[looking()], documents=[plan_of("Barbell_Squat")]), budget=2
    )

    assert lines.lines[:2] == [SAID.looking, SAID.writing]


def test_a_run_that_never_reaches_a_valid_plan_says_so(
    catalogued: sqlite3.Connection,
) -> None:
    lines = streamed(
        Scripted(documents=[plan_of("Dumbbell_Bench_Press")] * planner.ATTEMPTS)
    )

    assert lines.text() == SAID.exhausted.format(attempts=planner.ATTEMPTS)


def mesocycle_turn(**arguments: Any) -> dict[str, Any]:
    """A planner turn on a three-workout cycle, asking the admissible set with `arguments`."""
    slots = (
        plans.Request(equipment=("barbell",), budget_min=45, groups=("legs",)),
        plans.Request(equipment=("barbell",), budget_min=45, groups=("chest", "back")),
        plans.Request(equipment=("barbell",), budget_min=30, groups=("legs",)),
    )
    reply = AIMessage(
        content="",
        tool_calls=[{"name": "admissible_set", "args": arguments, "id": "c"}],
    )
    return {"planner": {"request": plans.MesocycleRequest(slots=slots), "messages": [reply]}}


def test_a_mesocycle_names_the_workout_being_looked_at() -> None:
    lines = progress.Progress()

    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45, muscle_groups=["back", "chest"]))

    assert lines.text() == SAID.looking_workout.format(workout=2, count=3)


def test_two_workouts_on_the_same_groups_are_told_apart_by_order() -> None:
    """The brief asks for the workouts in order, so the second legs day is the
    one after the workout the run was last looking at."""
    lines = progress.Progress()

    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45, muscle_groups=["legs"]))
    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45, muscle_groups=["chest", "back"]))
    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=30, muscle_groups=["legs"]))

    assert lines.lines == [
        SAID.looking_workout.format(workout=n, count=3) for n in (1, 2, 3)
    ]


def test_a_call_that_names_no_workout_keeps_the_one_before() -> None:
    lines = progress.Progress()

    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45, muscle_groups=["chest", "back"]))
    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45))

    assert lines.lines == [SAID.looking_workout.format(workout=2, count=3)]


def test_a_valid_mesocycle_is_counted_in_workouts() -> None:
    lines = progress.Progress()
    proposed = mesocycle_of(plan_of("Barbell_Squat"), plan_of("Barbell_Squat"))

    lines.reading({"validate": {"violations": (), "plan": proposed}})

    assert lines.text() == SAID.valid.format(blocks=SAID.workouts.format(count=2))


def test_a_report_is_read_in_phases_too() -> None:
    lines = progress.Progress(progress.LOG)
    looked = AIMessage(
        content="",
        tool_calls=[{"name": "prescribed_workout", "args": {"workout_id": 3}, "id": "c"}],
    )

    lines.reading({"logger": {"messages": [looked]}})
    lines.reading({"tools": {"messages": [None]}})
    lines.reading({"logger": {"messages": [AIMessage(content="Done.")]}})
    lines.reading({"emit": {"messages": []}})
    lines.reading({"validate": {"refused": None}})

    assert lines.lines == [SAID.reading_report, SAID.writing_report, SAID.read]


def test_the_draft_is_the_current_line_alone() -> None:
    """What outlives the plan by Telegram's thirty seconds is one line, not a log."""
    lines = progress.Progress()
    lines.lines = [f"linea {n}" for n in range(100)]

    assert lines.text() == "linea 99"


def test_one_line_past_the_limit_is_cut() -> None:
    """A refusal carries whatever the validator or the model wrote, and one
    line can be longer than Telegram carries on its own -- at which point
    every send for the rest of the run is refused, and refused silently,
    because a draft that fails is logged and nothing more.
    """
    lines = progress.Progress()
    lines.lines = ["il report non è passato: " + "x" * (progress.LIMIT * 2)]

    assert len(lines.text()) <= progress.LIMIT


def test_nothing_read_yet_is_an_empty_draft() -> None:
    """Which the bot replaces with a working line of its own."""
    assert progress.Progress().text() == ""


def test_a_chunk_that_is_not_a_node_is_left_alone() -> None:
    """`__interrupt__` arrives on the same stream and is a tuple, not a delta."""
    lines = progress.Progress()

    assert not lines.reading({"__interrupt__": ("whatever",)})
    assert lines.lines == []


def test_a_phase_already_shown_is_nothing_new() -> None:
    """Two turns of tools in a row are one phase, and the draft is not re-sent for it."""
    lines = progress.Progress()

    assert lines.reading({"planner": {"messages": [looking()]}})
    assert not lines.reading({"planner": {"messages": [looking()]}})
    assert lines.lines == [SAID.looking]


def test_a_plan_turned_down_says_the_run_is_starting_again() -> None:
    """The `propose` node hands back a fresh run when the user refuses, and
    minutes of silence follow it."""
    lines = progress.Progress()

    assert lines.reading({"propose": dict(planner.starting(BARBELL_45))})
    assert lines.lines == [SAID.again]


def test_a_new_run_writes_rather_than_rewrites() -> None:
    """A refusal belongs to the run it happened in; the next proposal is written fresh."""
    lines = progress.Progress()
    lines.reading({"validate": {"violations": (plans.Violation(plans.ADMISSIBLE, "x"),), "attempts": 1}})
    lines.reading({"propose": dict(planner.starting(BARBELL_45))})
    lines.reading({"planner": {"messages": [AIMessage(content="Planned.")]}})

    assert lines.text() == SAID.writing


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


def test_a_question_to_the_user_is_no_phase() -> None:
    """It reaches the chat as a message; the draft keeps the phase it was in."""
    lines = progress.Progress(progress.LOG)
    asked = AIMessage(
        content="",
        tool_calls=[{"name": progress.ASKING, "args": {"question": "quante serie?"}, "id": "c"}],
    )

    assert not lines.reading({"logger": {"messages": [asked]}})
    assert lines.lines == []


def test_no_workout_is_named_before_a_call_names_one() -> None:
    lines = progress.Progress()

    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45))

    assert lines.text() == SAID.looking


def test_a_rewrite_names_no_workout_until_it_looks_at_one() -> None:
    """The rewrite may start anywhere in the cycle, so the last workout looked at says nothing about it."""
    lines = progress.Progress()
    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=30, muscle_groups=["legs"]))
    lines.reading({"validate": {"violations": (plans.Violation(plans.ADMISSIBLE, "x"),), "attempts": 1}})
    lines.reading(mesocycle_turn(equipment=["barbell"], budget_min=45))

    assert lines.text() == SAID.looking


def test_the_arguments_a_workout_is_recognised_by_are_the_tools_own() -> None:
    """A renamed argument would leave every mesocycle line saying no workout, and no other test would notice."""
    admissible = tools.schema(tools.admissible_set)["parameters"]["properties"]
    allocate = tools.schema(tools.allocate)["parameters"]["properties"]

    assert {progress.GROUPS, progress.BUDGET} <= set(admissible)
    assert {progress.SHARES, progress.MINUTES} <= set(allocate)
