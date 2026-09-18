"""Negotiations read back: the documents in the home, and the run still in flight.

The demo this exists for is pulling the plug. The log says why a run stopped;
these say what it was doing, what it came to, and how many plans an evening
took -- which is the measurement session 10 is built on, and the one the old
state machine deleted by being asked the question.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from conftest import enrich
from test_planner import (
    BARBELL_45,
    CATALOG,
    PATTERNS,
    SCRIPTED,
    STAND_IN,
    Scripted,
    calling,
    graph_of,
    plan_of,
)
from trainer import tools
from trainer import plan as plans
from trainer.coach import checkpoints, planner, runs
from trainer.coach import record as run_record
from trainer.engine import catalog, database, migrations

THREAD: RunnableConfig = {"configurable": {"thread_id": "one"}}


@pytest.fixture()
def catalogued(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


@pytest.fixture()
def archive(tmp_path: Path) -> Path:
    return tmp_path / "runs"


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


def negotiating(archive: Path, *plans_offered: plans.WorkoutPlan) -> planner.Planner:
    """A graph that can pause, keeps what it closes, and has a plan per run ready."""
    model = Scripted(
        turns=[AIMessage(content="Planned.") for _ in plans_offered],
        documents=list(plans_offered),
    )
    return graph_of(model, checkpointer=InMemorySaver(), archive=archive)


def held(archive: Path) -> list[runs.Negotiation]:
    return runs.negotiations(runs.kept(archive), ())


THREE = (
    plan_of("Barbell_Squat"),
    plan_of("Standing_Military_Press"),
    plan_of("Barbell_Squat", "Standing_Military_Press"),
)
"""Three plans of one evening: admissible today, and different from each other.

Different by their exercise ids and not only as documents, because
`_not_a_plan_already_refused` compares an older refusal on its ids -- so two
plans of the same exercises would be the rule firing, which is a different
test.
"""


# -- a run ends, and the ending is written ------------------------------------


def test_two_refusals_and_an_acceptance_leave_three_run_documents(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    """The evening the measurement is about. Each run says what it offered and
    what was said to it; only the last one wrote a workout."""
    graph = negotiating(archive, *THREE)
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.refused("troppo lunga")), THREAD)
    graph.invoke(Command(resume=planner.refused("non mi va la panca")), THREAD)
    final = graph.invoke(Command(resume=planner.accepted()), THREAD)

    kept = runs.kept(archive)

    assert [run.ending for run in kept] == [
        run_record.TURNED_DOWN,
        run_record.TURNED_DOWN,
        run_record.ACCEPTED,
    ]
    assert [run.document["because"] for run in kept] == [
        "troppo lunga",
        "non mi va la panca",
        "",
    ]
    assert [run.document["plan"] for run in kept] == [
        offered.model_dump() for offered in THREE
    ]
    assert [run.document["workout"] for run in kept] == [None, None, final["workout"]]


def test_the_evening_is_one_negotiation_and_not_three_unrelated_rows(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    graph = negotiating(archive, *THREE)
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.refused("troppo lunga")), THREAD)
    graph.invoke(Command(resume=planner.refused("non mi va la panca")), THREAD)
    graph.invoke(Command(resume=planner.accepted()), THREAD)

    (negotiation,) = held(archive)

    assert len(negotiation.runs) == 3
    assert negotiation.outcome == run_record.ACCEPTED
    assert "3 runs" in runs.line(negotiation)
    assert runs.line(negotiation).isascii()


def test_each_run_says_which_refusal_it_was_born_from(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    """A pile of runs is unreadable; a chain is not."""
    graph = negotiating(archive, *THREE)
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.refused("no")), THREAD)
    graph.invoke(Command(resume=planner.refused("nemmeno")), THREAD)

    first, second = runs.kept(archive)

    assert first.follows is None
    assert second.follows == first.run
    assert first.negotiation == second.negotiation


def test_a_run_the_validator_refuses_to_the_end_is_written_as_refused(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    graph = negotiating(
        archive, *[plan_of("Dumbbell_Bench_Press") for _ in range(planner.ATTEMPTS)]
    )
    graph.invoke(planner.starting(BARBELL_45), THREAD)

    (kept,) = runs.kept(archive)

    assert kept.ending == run_record.REFUSED
    assert len(kept.document["attempts"]) == planner.ATTEMPTS


def test_a_run_that_fell_over_is_ended_by_whoever_caught_it(
    catalogued: sqlite3.Connection, archive: Path, tmp_path: Path
) -> None:
    """A node cannot write after it has raised, so the catcher writes for it."""
    path = tmp_path / "checkpoints.sqlite"
    model = Unplugged(
        survives=1,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )

    with checkpoints.saver(path) as saver:
        graph = graph_of(model, checkpointer=saver, archive=archive)
        with pytest.raises(KeyboardInterrupt):
            graph.invoke(planner.starting(BARBELL_45), THREAD)
        run_record.failed(graph, THREAD, tools.CALL_BUDGET, archive)

    (kept,) = runs.kept(archive)

    assert kept.ending == run_record.FAILED
    assert [call["name"] for call in kept.document["calls"]] == ["allocate"]


def test_a_run_that_ended_is_not_ended_a_second_time(
    catalogued: sqlite3.Connection, archive: Path, tmp_path: Path
) -> None:
    """`failed` is called by a catcher that does not know where the run got
    to, and a run the graph already closed must not be overwritten as fallen
    over."""
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        graph = graph_of(
            Scripted(documents=[plan_of("Barbell_Squat")]),
            checkpointer=saver,
            archive=archive,
        )
        graph.invoke(planner.starting(BARBELL_45), THREAD)
        graph.invoke(Command(resume=planner.accepted()), THREAD)
        run_record.failed(graph, THREAD, tools.CALL_BUDGET, archive)

    (kept,) = runs.kept(archive)

    assert kept.ending == run_record.ACCEPTED


def test_a_graph_with_no_archive_keeps_nothing(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    """The eval suites run this graph dozens of times to measure it, and their
    runs in the home would be the history session 10 reads."""
    graph_of(Scripted(documents=[plan_of("Barbell_Squat")])).invoke(
        planner.starting(BARBELL_45)
    )

    assert runs.kept(archive) == []
    assert not archive.exists()


# -- what the reader finds, as opposed to what was written --------------------


def test_a_plan_nobody_answered_is_waiting_rather_than_cut(
    catalogued: sqlite3.Connection, archive: Path, tmp_path: Path
) -> None:
    """Derived at read time, off the checkpoint's own pending writes: reading
    it through the graph would have this reader build a planner."""
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        graph = graph_of(
            Scripted(documents=[plan_of("Barbell_Squat")]),
            checkpointer=saver,
            archive=archive,
        )
        graph.invoke(planner.starting(BARBELL_45), THREAD)

    with checkpoints.saver(path) as saver:
        (negotiation,) = runs.negotiations(runs.kept(archive), runs.live(saver))

    assert negotiation.outcome == runs.WAITING
    assert negotiation.runs == ()
    assert "waiting since" in runs.line(negotiation)
    assert runs.line(negotiation).isascii()


def test_a_run_cut_mid_flight_is_reported_as_cut(
    catalogued: sqlite3.Connection, archive: Path, tmp_path: Path
) -> None:
    """No ending was written and no question is pending: the process died
    between two super-steps. The session 8 demo, now saying so."""
    path = tmp_path / "checkpoints.sqlite"
    model = Unplugged(
        survives=1,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )

    with checkpoints.saver(path) as saver:
        graph = graph_of(model, checkpointer=saver, archive=archive)
        with pytest.raises(KeyboardInterrupt):
            graph.invoke(planner.starting(BARBELL_45), THREAD)

    with checkpoints.saver(path) as saver:
        (negotiation,) = runs.negotiations(runs.kept(archive), runs.live(saver))
        written = runs.of(negotiation.live, tools.CALL_BUDGET) if negotiation.live else {}

    assert negotiation.outcome == runs.CUT
    assert [call["name"] for call in written["calls"]] == ["allocate"]
    assert written["attempts"] == []
    assert written["plan"] is None


def test_the_live_run_of_a_negotiation_that_already_closed_one_is_not_read_twice(
    catalogued: sqlite3.Connection, archive: Path, tmp_path: Path
) -> None:
    """An accepted run stays in the checkpointer until the next ask. It has a
    document beside it, so it is a closed run and not a cut one."""
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        graph = graph_of(
            Scripted(documents=[plan_of("Barbell_Squat")]),
            checkpointer=saver,
            archive=archive,
        )
        graph.invoke(planner.starting(BARBELL_45), THREAD)
        graph.invoke(Command(resume=planner.accepted()), THREAD)

    with checkpoints.saver(path) as saver:
        (negotiation,) = runs.negotiations(runs.kept(archive), runs.live(saver))

    assert negotiation.open is False
    assert negotiation.outcome == run_record.ACCEPTED
    assert "1 run" in runs.line(negotiation)


def test_the_reader_needs_no_provider_no_graph_and_no_model(
    catalogued: sqlite3.Connection, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LLM_BACKEND` naming a provider that cannot be built is the state you
    reach for this tool in."""
    monkeypatch.setenv("LLM_BACKEND", "groq")
    graph = negotiating(archive, plan_of("Barbell_Squat"))
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.accepted()), THREAD)

    (negotiation,) = held(archive)

    assert negotiation.outcome == run_record.ACCEPTED
    assert run_record.summary(negotiation.runs[0].document)


# -- the archive as a directory -----------------------------------------------


def test_nothing_at_the_top_of_a_document_names_a_model(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    graph = negotiating(archive, plan_of("Barbell_Squat"))
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.accepted()), THREAD)

    (kept,) = runs.kept(archive)

    assert "model" not in kept.document
    assert "provider" not in kept.document
    assert {node["model"] for node in kept.document["nodes"]} == {STAND_IN}
    assert {node["provider"] for node in kept.document["nodes"]} == {SCRIPTED}
    assert STAND_IN in run_record.summary(kept.document)[0]


def test_a_run_carries_only_its_own_attempts_and_its_own_seconds(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    """The second run of a negotiation starts from the first one's state. Left
    to accumulate, the plan refused at nine is an attempt of the run at ten."""
    graph = negotiating(archive, *THREE)
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.refused("no")), THREAD)
    graph.invoke(Command(resume=planner.refused("nemmeno")), THREAD)

    first, second = runs.kept(archive)

    assert len(first.document["attempts"]) == 1
    assert len(second.document["attempts"]) == 1, "its own attempt, not also the first's"
    assert [node["node"] for node in second.document["nodes"]] == [
        "planner",
        "emit",
        "validate",
    ]


def test_a_file_that_is_not_a_record_does_not_take_the_history_with_it(
    archive: Path,
) -> None:
    archive.mkdir(parents=True)
    (archive / "20260918-190000-aaaa").mkdir()
    (archive / "20260918-190000-aaaa" / "broken.json").write_text("{not json", "utf-8")
    (archive / "20260918-190000-aaaa" / "good.json").write_text(
        json.dumps({"negotiation": "20260918-190000-aaaa", "run": "good"}), "utf-8"
    )

    assert [run.run for run in runs.kept(archive)] == ["good"]


def test_a_home_with_no_archive_holds_no_negotiation(archive: Path) -> None:
    assert runs.kept(archive) == []
    assert runs.negotiations((), ()) == []


def test_a_negotiation_is_found_by_its_name_or_by_one_of_its_runs(
    catalogued: sqlite3.Connection, archive: Path
) -> None:
    graph = negotiating(archive, plan_of("Barbell_Squat"))
    graph.invoke(planner.starting(BARBELL_45), THREAD)
    graph.invoke(Command(resume=planner.accepted()), THREAD)
    listed = held(archive)
    (one,) = listed

    assert runs.named(listed, one.negotiation) is one
    assert runs.named(listed, one.runs[0].run) is one
    assert runs.named(listed, "nobody") is None
    assert runs.run_named(one, one.runs[0].run) is one.runs[0]
    assert runs.run_named(one, "nobody") is None


# -- what a checkpoint written before this ticket reads back as ---------------


def test_a_state_written_before_a_run_had_a_name_still_reads_back() -> None:
    """Sessions 6 to 8 wrote timings as a node and its seconds, with nobody
    named, and those checkpoints are on the user's disk."""
    written = run_record.of(
        {"timings": [("planner", 1.25)], "spent": 2}, tools.CALL_BUDGET
    )

    assert written["nodes"] == [
        {"node": "planner", "model": "", "provider": "", "seconds": 1.25}
    ]
    assert written["negotiation"] == ""
    assert written["ending"] == ""
    assert run_record.summary(written)[0].startswith("nobody on record")


def test_a_state_with_nothing_in_it_invents_no_ending() -> None:
    assert run_record.of({}, tools.CALL_BUDGET)["ending"] == ""


def test_a_timestamp_is_shown_to_the_minute_in_ascii() -> None:
    assert runs.moment("2026-09-17T19:04:05.123456+00:00").isascii()
    assert len(runs.moment("2026-09-17T19:04:05.123456+00:00")) == len("2026-09-17 19:04")


def test_a_timestamp_nobody_can_read_is_shown_as_it_was_written() -> None:
    assert runs.moment("not a time") == "not a time"


def test_a_checkpoint_written_before_this_ticket_still_lists(
    archive: Path, tmp_path: Path
) -> None:
    """Sessions 6 to 8 checkpointed a state with no negotiation and no run, and
    those files are on the user's disk. The reader lists such a thread under
    its own name, as a run nobody closed -- which is what it is."""
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        held = empty_checkpoint()
        held["channel_values"] = {
            "spent": 1,
            "attempts": 0,
            "timings": [("planner", 0.5), ("tools", 0.25)],
        }
        saver.put(
            {"configurable": {"thread_id": "chat:6421", "checkpoint_ns": ""}},
            held,
            {},
            {},
        )

    with checkpoints.saver(path) as saver:
        (negotiation,) = runs.negotiations(runs.kept(archive), runs.live(saver))
        written = runs.of(negotiation.live, tools.CALL_BUDGET) if negotiation.live else {}

    assert negotiation.negotiation == "chat:6421"
    assert negotiation.outcome == runs.CUT
    assert [node["node"] for node in written["nodes"]] == ["planner", "tools"]
    assert runs.line(negotiation).isascii()


def test_a_run_cut_mid_flight_is_read_back_against_the_budget_it_had(
    catalogued: sqlite3.Connection, archive: Path, tmp_path: Path
) -> None:
    """`trainer plan --call-budget 2` killed mid-flight leaves no document, so
    the reader derives one -- and it was never told what bounded the run."""
    path = tmp_path / "checkpoints.sqlite"
    model = Unplugged(
        survives=1,
        turns=[calling("allocate", minutes=45, proportions={"legs": 1.0})],
        documents=[plan_of("Barbell_Squat")],
    )

    with checkpoints.saver(path) as saver:
        graph = graph_of(model, budget=2, checkpointer=saver, archive=archive)
        with pytest.raises(KeyboardInterrupt):
            graph.invoke(planner.starting(BARBELL_45), THREAD)

    with checkpoints.saver(path) as saver:
        (negotiation,) = runs.negotiations(runs.kept(archive), runs.live(saver))
        assert negotiation.live is not None
        written = runs.of(negotiation.live, tools.CALL_BUDGET)

    assert written["budget"] == 2
    assert "1 of 2 tool calls" in run_record.summary(written)[0]
