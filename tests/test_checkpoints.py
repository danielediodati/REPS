"""What the checkpointer writes is what it reads back, and nothing else gets in.

The serializer accepted anything and warned that a future version would stop
reading it, so the failure this file guards against is a thread that resumes
with dictionaries where its models were -- LangGraph hands back the raw
keyword arguments for a type it will not construct, and says so in a log line
nobody was watching.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from langchain_core.runnables import RunnableConfig

from langgraph.checkpoint.serde import jsonplus

from conftest import enrich
from test_planner import BARBELL_45, CATALOG, PATTERNS, Scripted, plan_of
from trainer import plan as plans
from trainer.coach import checkpoints, planner
from trainer.engine import catalog, database, migrations
from trainer.engine.exclusions import Exclusion


@pytest.fixture()
def catalogued(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened

THREAD: RunnableConfig = {"configurable": {"thread_id": "one"}}


def test_the_declared_types_come_back_as_themselves(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """Written by one process, read by the next: the demo's restart."""
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver)
        graph.invoke({"request": BARBELL_45}, THREAD)

    with checkpoints.saver(path) as saver:
        values = planner.build(
            Scripted(documents=[]), checkpointer=saver
        ).get_state(THREAD).values

    assert isinstance(values["request"], plans.Request)
    assert isinstance(values["plan"], plans.WorkoutPlan)
    assert values["plan"] == plan_of("Barbell_Squat")
    # Field by field, and the sequences as lists: msgpack has one sequence, so
    # a tuple field of a dataclass comes back a list and the dataclass is no
    # longer equal to the one that was written. It is not what this ticket is
    # about -- nothing compares or hashes a Request -- but asserting equality
    # here would assert it is.
    read = values["request"]
    assert read.budget_min == BARBELL_45.budget_min
    assert list(read.equipment) == list(BARBELL_45.equipment)


def test_a_refusal_comes_back_as_violations(tmp_path: Path) -> None:
    """The third type, which only a refused attempt puts in the state."""
    violation = plans.Violation(rule="fits_the_time", says="60 of 45 minutes")

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        read = saver.serde.loads_typed(saver.serde.dumps_typed((violation,)))

    assert isinstance(read[0], plans.Violation)
    assert read[0] == violation


def test_an_exclusion_inside_the_request_comes_back_as_itself(tmp_path: Path) -> None:
    """The fourth type, and the one the ticket did not list.

    `turn` folds today's standing exclusions into the request before the model
    is called, so every thread with an exclusion in force carries one.
    """
    request = plans.Request(
        equipment=("barbell",),
        budget_min=45,
        exclusions=(Exclusion("pattern", "vertical push"),),
    )

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        read = saver.serde.loads_typed(saver.serde.dumps_typed(request))

    assert isinstance(read.exclusions[0], Exclusion)
    assert read.exclusions[0] == Exclusion("pattern", "vertical push")


def test_an_undeclared_type_is_refused_where_it_is_written(tmp_path: Path) -> None:
    """Loudly, and at the write.

    Blocked at the read it comes back as a dictionary and the run dies further
    on, in a place that says nothing about serialization.
    """

    @dataclass(frozen=True)
    class Undeclared:
        why: str

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        with pytest.raises(checkpoints.CheckpointError, match="Undeclared"):
            saver.serde.dumps_typed({"held": Undeclared(why="nobody declared me")})


def test_nothing_in_the_state_is_written_unregistered(
    catalogued: sqlite3.Connection, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A run and a resume, with LangGraph's serializer logging at WARNING.

    Its two warnings -- *deserializing unregistered type* and *blocked
    deserialization* -- are the two ways this can be wrong, and both are said
    once per type per process, so a suite that ran the graph before this test
    would have used up the only notice.
    """
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver)
        graph.invoke({"request": BARBELL_45}, THREAD)

    # Both are said once per type per process, and this suite has run the
    # graph many times by now, so the only notice was used up long ago.
    jsonplus._warned_unregistered_types.clear()
    jsonplus._warned_blocked_types.clear()

    with caplog.at_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus"):
        with checkpoints.saver(path) as saver:
            planner.build(Scripted(documents=[]), checkpointer=saver).get_state(THREAD)

    assert caplog.records == []


def test_an_undeclared_type_inside_a_declared_one_is_found(tmp_path: Path) -> None:
    """The case `Exclusion` was: a dataclass keeps its fields as objects.

    A pydantic model is dumped whole and its nested models travel as plain
    data, so the walk stops there; a dataclass does not, and each field value
    is written on its own. The request is a declared type, so reaching the
    undeclared value means the walk went through its fields -- which is the
    branch a `Request` gaining a field of a new type would depend on.
    """

    @dataclass(frozen=True)
    class Undeclared:
        why: str

    held = cast(tuple[str, ...], (Undeclared(why="nested"),))
    request = plans.Request(equipment=("barbell",), budget_min=45, preferences=held)

    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        with pytest.raises(checkpoints.CheckpointError, match="Undeclared"):
            saver.serde.dumps_typed(request)

    assert checkpoints.undeclared(plans.Request(equipment=("barbell",), budget_min=45)) is None
