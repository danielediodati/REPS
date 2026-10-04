"""The supervisor: when it runs, what it reads, and the direction it leaves with the next mesocycle."""

from __future__ import annotations

import dataclasses
import inspect
import json
import typing
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from test_planner import (  # noqa: F401 -- `connection` and `two_slots` are fixtures
    SCRIPTED,
    STAND_IN,
    Scripted,
    calling,
    connection,
    mesocycle_of,
    pausing,
    plan_of,
    ran_out,
    two_slots,
)
from trainer import plan as plans
from trainer import tools
from trainer.coach import checkpoints, models, planner, record, supervisor
from trainer.engine import mesocycles, variation

DIRECTION = supervisor.Direction(
    theme="unilateral strength",
    changes="the squat goes to a split squat; reps and rest stay",
    why="two mesocycles alike, the loads have stalled",
    varies=["exercises"],
)

PROSE = "PLANNERS-OWN-PROSE"
"""Written into every place the planner or the user's report keeps prose, to be looked for in what the supervisor reads."""


def graph_of(model: Scripted, **built: Any) -> supervisor.Supervisor:
    return supervisor.build(models.Chat(model, SCRIPTED, STAND_IN), **built)


def ended(connection: sqlite3.Connection, two_slots: plans.MesocycleRequest) -> plans.MesocycleRequest:
    """A one-cycle mesocycle performed to its end, and the request for the one that follows."""
    ran_out(connection, two_slots)
    return plans.next_requested(connection, "2026-09-22")


def test_it_writes_the_direction_onto_the_request_for_the_next_mesocycle(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    asked = ended(connection, two_slots)
    model = Scripted(
        turns=[calling("mesocycle_history"), AIMessage(content="enough")],
        documents=[DIRECTION],
    )

    directed = supervisor.directed(graph_of(model), asked, {})

    assert directed.continuing is not None
    assert directed.continuing.direction == mesocycles.Direction(**DIRECTION.model_dump())
    assert dataclasses.replace(directed.continuing, direction=None) == asked.continuing
    assert model.bound[0] == list(supervisor.TOOLS)


def test_it_does_not_run_on_the_first_mesocycle_or_on_a_change(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    model = Scripted(documents=[DIRECTION])
    graph = graph_of(model)
    assert supervisor.directed(graph, two_slots, {}) is two_slots, "the first"

    ran_out(connection, two_slots)
    asked = ended(connection, two_slots)
    changing = dataclasses.replace(
        asked,
        changing=plans.Changing(
            mesocycle=1, accepted_after=0, cycle=1, current=mesocycle_of(plan_of("Barbell_Squat")), said="meno squat"
        ),
    )
    assert supervisor.directed(graph, changing, {}) is changing, "a change"
    assert model.seen == []


def test_it_starts_from_the_mesocycle_that_ended_with_the_goal_and_its_methodology(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    asked = ended(connection, two_slots)
    model = Scripted(documents=[DIRECTION])

    supervisor.directed(graph_of(model), asked, {})

    system, briefed = (message.text for message in model.seen[0][:2])
    assert variation.committed().for_supervisor.strip() in system
    assert "## Ranges by goal" in system
    assert "3 x (Barbell_Squat" in briefed
    assert "goal is hypertrophy" in briefed
    assert "It had no direction" in briefed
    assert asked.continuing is not None and asked.continuing.ended.why not in briefed


def test_its_run_is_kept_like_every_other_with_the_direction_it_wrote(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest, tmp_path: Path
) -> None:
    asked = ended(connection, two_slots)
    graph = graph_of(
        Scripted(turns=[calling("mesocycle_history")], documents=[DIRECTION]),
        archive=tmp_path,
        checkpointer=InMemorySaver(serde=checkpoints.Declared()),
    )

    supervisor.directed(graph, asked, {"configurable": {"thread_id": "one"}}, tmp_path)

    (kept,) = tmp_path.glob("*/*.json")
    written = json.loads(kept.read_text(encoding="utf-8"))
    assert written["ending"] == record.DONE
    assert written["direction"] == DIRECTION.model_dump()
    assert [call["name"] for call in written["calls"]] == ["mesocycle_history"]
    assert [node["node"] for node in written["nodes"]][:2] == ["supervisor", "tools"]
    assert record.summary(written), "readable by `trainer runs` like any other"


def test_what_it_may_vary_is_the_engines_list() -> None:
    (listed,) = typing.get_args(supervisor.Direction.model_fields["varies"].annotation)
    assert typing.get_args(listed) == mesocycles.VARIES


@pytest.mark.parametrize("varies", [[], ["load"]])
def test_a_direction_varying_nothing_it_may_is_asked_for_again(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest, varies: list[str]
) -> None:
    asked = ended(connection, two_slots)
    written = json.dumps({"theme": "t", "changes": "c", "why": "w", "varies": varies})
    model = Scripted(raw=[written], documents=[DIRECTION])

    directed = supervisor.directed(graph_of(model), asked, {})

    assert directed.continuing is not None and directed.continuing.direction is not None
    assert directed.continuing.direction.varies == ("exercises",)
    assert len(model.schemas) == 2


def test_a_blank_direction_is_asked_for_again(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    asked = ended(connection, two_slots)
    model = Scripted(raw=['{"theme": " ", "changes": "x", "why": "y", "varies": ["rest"]}'], documents=[DIRECTION])

    directed = supervisor.directed(graph_of(model), asked, {})

    assert directed.continuing is not None and directed.continuing.direction is not None
    assert len(model.schemas) == 2


def test_the_planner_keeps_the_direction_with_the_mesocycle_it_accepts(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    asked = supervisor.directed(graph_of(Scripted(documents=[DIRECTION])), ended(connection, two_slots), {})
    plans_on, thread = pausing(
        Scripted(documents=[mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press"))])
    )

    plans_on.invoke(planner.starting(asked, unasked=True), thread)
    plans_on.invoke(Command(resume=planner.accepted()), thread)

    kept = mesocycles.active(connection)
    assert kept is not None
    assert kept.direction == mesocycles.Direction(**DIRECTION.model_dump())
    assert [past.direction is None for past in mesocycles.history(connection)] == [True, False]


def test_no_tool_it_holds_returns_the_planners_or_the_users_prose(
    connection: sqlite3.Connection, two_slots: plans.MesocycleRequest
) -> None:
    ended(connection, two_slots)
    connection.execute("UPDATE mesocycles SET why = ?", (PROSE,))
    connection.execute("UPDATE mesocycle_blocks SET reason = ?", (PROSE,))
    connection.execute("UPDATE workout_blocks SET reason = ? WHERE reason IS NOT NULL", (PROSE,))
    connection.execute("UPDATE workouts SET report = ? WHERE report IS NOT NULL", (PROSE,))
    connection.commit()
    arguments = {
        "mesocycle_id": 1,
        "cycles": 3,
        "pattern": "squat",
        "exercise_id": "Barbell_Squat",
    }

    for tool in tools.registered("supervisor", supervisor.TOOLS):
        given = {name: arguments[name] for name in inspect.signature(tool).parameters}
        result = tools.execute(tools.Call("call", tool.__name__, given), (tool,), supervisor.KEEPS)

        assert not result.failed, (tool.__name__, result.content)
        assert PROSE not in result.content, tool.__name__


def test_it_never_holds_the_tool_that_reads_a_prescriptions_reasons() -> None:
    assert "prescribed_workout" not in supervisor.TOOLS
    assert "unreported_workouts" not in supervisor.TOOLS


@pytest.mark.parametrize("tool", ["mesocycle_history", "mesocycle_held", "mesocycle_volume"])
def test_the_planner_is_not_offered_the_history_tools(tool: str) -> None:
    assert tool not in planner.TOOLS
