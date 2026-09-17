"""A run read back off the checkpointer, finished or cut mid-flight.

The demo this exists for is pulling the plug: the log says why a run stopped,
and these say what it was doing. So the case that matters most here is the
unfinished one -- a run that never reached the validator must read back as
what it reached, and never as a run that ended some way it did not.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig

from conftest import enrich
from test_planner import BARBELL_45, CATALOG, PATTERNS, Scripted, calling, plan_of
from trainer.coach import checkpoints, planner, runs
from trainer.coach import record as run_record
from trainer.engine import catalog, database, migrations

SCRIPTED = run_record.Run(model="a-stand-in", provider="scripted", budget=7)


@pytest.fixture()
def catalogued(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


class Unplugged(Scripted):
    """A model that stops answering, the way a machine losing power does.

    `KeyboardInterrupt` and not an exception, because `turn` catches anything
    the provider raises and hands it back to the model: what is being
    simulated here is the process dying between two super-steps, not a
    provider refusing a turn.
    """

    survives: int = 0

    def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> ChatResult:
        if self.survives <= 0:
            raise KeyboardInterrupt("the plug came out")
        self.survives -= 1
        return super()._generate(messages, *args, **kwargs)


def test_a_finished_run_reads_back_with_what_it_did_and_what_it_cost(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    model = Scripted(
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(model, checkpointer=saver)
        graph.invoke({"request": BARBELL_45}, run_record.on("one", SCRIPTED))

    with checkpoints.saver(path) as saver:
        found = runs.read(saver, "one")

    assert found is not None
    conversation, values = found
    assert conversation.outcome == run_record.VALID
    assert conversation.on == SCRIPTED
    written = run_record.of(values, conversation.on.model, conversation.on.provider)
    assert [call["name"] for call in written["calls"]] == ["allocate"]
    assert len(written["attempts"]) == 1
    assert written["tokens"] == {"input": 0, "output": 0}
    assert {node["node"] for node in written["nodes"]} >= {"planner", "tools", "emit"}


def test_a_run_cut_mid_flight_reads_back_what_it_had_reached(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """The case the ticket exists for: no plan, no refusal, and no error."""
    model = Unplugged(
        survives=1,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(model, checkpointer=saver)
        with pytest.raises(KeyboardInterrupt):
            graph.invoke({"request": BARBELL_45}, run_record.on("one", SCRIPTED))

    with checkpoints.saver(path) as saver:
        found = runs.read(saver, "one")

    assert found is not None
    conversation, values = found
    assert conversation.outcome == run_record.UNFINISHED
    written = run_record.of(values, conversation.on.model, conversation.on.provider)
    assert written["outcome"] == run_record.UNFINISHED
    assert [call["name"] for call in written["calls"]] == ["allocate"]
    assert written["attempts"] == []
    assert written["plan"] is None
    assert [node["node"] for node in written["nodes"]] == ["planner", "tools"]


def test_the_record_read_back_is_the_record_the_run_returned(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """msgpack has one sequence, so a resumed state holds lists where it was
    written tuples. The record must not read differently for having come off
    disk."""
    model = Scripted(
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Dumbbell_Bench_Press"), plan_of("Barbell_Squat")],
    )
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(model, checkpointer=saver)
        final = graph.invoke({"request": BARBELL_45}, run_record.on("one", SCRIPTED))
        live = run_record.written(final, SCRIPTED.model, SCRIPTED.provider)

    with checkpoints.saver(path) as saver:
        found = runs.read(saver, "one")

    assert found is not None
    conversation, values = found
    on = conversation.on
    assert run_record.written(values, on.model, on.provider) == live


def test_every_conversation_is_listed_most_recently_moved_first(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(
            Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver
        )
        graph.invoke({"request": BARBELL_45}, run_record.on("first", SCRIPTED))
        graph = planner.build(
            Scripted(
                documents=[
                    plan_of("Dumbbell_Bench_Press") for _ in range(planner.ATTEMPTS)
                ]
            ),
            checkpointer=saver,
        )
        graph.invoke({"request": BARBELL_45}, run_record.on("second", SCRIPTED))

    with checkpoints.saver(path) as saver:
        listed = runs.conversations(saver)

    assert [conversation.thread for conversation in listed] == ["second", "first"]
    assert [conversation.outcome for conversation in listed] == [
        run_record.REFUSED,
        run_record.VALID,
    ]
    assert all(runs.line(conversation).isascii() for conversation in listed)


def test_a_thread_appears_once_however_many_checkpoints_it_has(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """A run writes a checkpoint per super-step, and what is being listed is
    conversations."""
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(
            Scripted(
                turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
                documents=[plan_of("Barbell_Squat")],
            ),
            checkpointer=saver,
        )
        graph.invoke({"request": BARBELL_45}, run_record.on("one", SCRIPTED))
        listed = runs.conversations(saver)

    assert [conversation.thread for conversation in listed] == ["one"]


def test_a_thread_nobody_wrote_reads_back_as_nothing(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    with checkpoints.saver(tmp_path / "checkpoints.sqlite") as saver:
        assert runs.read(saver, "never") is None
        assert runs.conversations(saver) == []


def test_a_run_checkpointed_before_its_identity_was_carried_reads_back_as_unknown(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """Sessions 6 to 8 wrote threads with no model in their metadata, and they
    are on the user's disk. Refusing to read one would take the history with
    it."""
    plain: RunnableConfig = {"configurable": {"thread_id": "old"}}
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(
            Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver
        )
        graph.invoke({"request": BARBELL_45}, plain)

    with checkpoints.saver(path) as saver:
        found = runs.read(saver, "old")

    assert found is not None
    conversation, _ = found
    assert conversation.on.model == run_record.UNKNOWN
    assert conversation.on.provider == run_record.UNKNOWN


def test_the_summary_says_what_each_node_cost(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """Per-node seconds are in the record and were never on a screen. The
    minutes are the thing being measured."""
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(
            Scripted(documents=[plan_of("Barbell_Squat")]), checkpointer=saver
        )
        graph.invoke({"request": BARBELL_45}, run_record.on("one", SCRIPTED))
        found = runs.read(saver, "one")

    assert found is not None
    conversation, values = found
    lines = run_record.summary(
        values, conversation.on.model, conversation.on.provider, conversation.on.budget
    )

    assert any("emit" in line and "s" in line for line in lines)
    assert f"of {SCRIPTED.budget} tool calls" in lines[0]
    assert all(line.isascii() for line in lines)


def test_an_empty_turn_is_still_a_conversation_worth_listing(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    """The bot writes what the user said before it plans anything. A thread
    that got no further still has to be pickable."""
    path = tmp_path / "checkpoints.sqlite"

    with checkpoints.saver(path) as saver:
        graph = planner.build(Scripted(), checkpointer=saver)
        graph.update_state(run_record.on("one", SCRIPTED), {"said": ["cosa faccio?"]})
        listed = runs.conversations(saver)

    assert [conversation.outcome for conversation in listed] == [run_record.UNFINISHED]
    assert listed[0].on == SCRIPTED


def test_a_timestamp_is_shown_to_the_minute_in_ascii() -> None:
    assert runs.moment("2026-09-17T19:04:05.123456+00:00").isascii()
    assert len(runs.moment("2026-09-17T19:04:05.123456+00:00")) == len("2026-09-17 19:04")


def test_a_timestamp_nobody_can_read_is_shown_as_it_was_written() -> None:
    assert runs.moment("not a time") == "not a time"


def test_a_state_with_nothing_in_it_invents_no_outcome() -> None:
    assert run_record.of({}, "m", "p")["outcome"] == run_record.UNFINISHED
