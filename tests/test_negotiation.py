"""The negotiation alone: plan proposals opened, answered and prepared, with no chat in sight."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from test_bot import (
    A_MESOCYCLE,
    DIRECTED,
    NEXT,
    catalogued,
    declared,
    on_its_last_workout,
    performed_once,
    workout_rows,
)
from test_planner import BARBELL_45, SCRIPTED, STAND_IN, Scripted, graph_of, plan_of
from trainer import plan as plans
from trainer import tools
from trainer.coach import models, planner, supervisor
from trainer.coach import negotiation as negotiations
from trainer.engine import mesocycles

__all__ = ["catalogued", "declared"]

PLANNING: RunnableConfig = {"configurable": {"thread_id": "chat:1/plan"}}
DIRECTING: RunnableConfig = {"configurable": {"thread_id": "chat:1/supervise"}}


def negotiation_of(
    planned: Scripted, archive: Path, preparing: set[str] | None = None
) -> negotiations.Negotiation:
    """A negotiation over a scripted planner and supervisor, sharing one checkpointer."""
    held = InMemorySaver()
    archive = archive / "runs"
    return negotiations.Negotiation(
        graph_of(planned, checkpointer=held, archive=archive),
        archive=archive,
        supervisor=supervisor.build(
            models.Chat(Scripted(documents=[DIRECTED, DIRECTED]), SCRIPTED, STAND_IN),
            checkpointer=held,
            archive=archive,
        ),
        preparing=preparing,
    )


def asked_for_a_mesocycle() -> plans.MesocycleRequest:
    with tools.opened() as connection:
        return plans.mesocycle_requested(connection, date.today().isoformat(), plans.Asked())


def test_a_request_is_proposed_and_waits(catalogued: sqlite3.Connection, tmp_path: Path) -> None:
    talks = negotiation_of(Scripted(documents=[plan_of("Barbell_Squat")]), tmp_path)

    offered = talks.open(PLANNING, BARBELL_45)

    assert isinstance(offered, negotiations.Proposed)
    assert offered.plan == plan_of("Barbell_Squat")
    assert talks.pending(PLANNING).id == offered.id  # type: ignore[union-attr]
    assert not offered.unasked
    assert workout_rows(catalogued) == []


def test_two_answers_to_one_proposal_write_one_workout(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(Scripted(documents=[plan_of("Barbell_Squat")]), tmp_path)
    offered = talks.open(PLANNING, BARBELL_45)
    assert isinstance(offered, negotiations.Proposed)

    first = talks.answer(PLANNING, offered.id, planner.accepted())
    second = talks.answer(PLANNING, offered.id, planner.accepted())

    assert isinstance(first, negotiations.Accepted) and first.workout is not None
    assert second == negotiations.Superseded()
    assert len(workout_rows(catalogued)) == 1
    assert talks.pending(PLANNING) is None


def test_opening_a_request_supersedes_the_pending_one(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(
        Scripted(documents=[plan_of("Barbell_Squat"), plan_of("Barbell_Squat")]), tmp_path
    )
    old = talks.open(PLANNING, BARBELL_45)
    new = talks.open(PLANNING, BARBELL_45)
    assert isinstance(old, negotiations.Proposed) and isinstance(new, negotiations.Proposed)

    assert old.id != new.id
    assert talks.answer(PLANNING, old.id, planner.accepted()) == negotiations.Superseded()
    assert workout_rows(catalogued) == []
    assert talks.pending(PLANNING).id == new.id  # type: ignore[union-attr]


def test_a_stale_id_writes_nothing(catalogued: sqlite3.Connection, tmp_path: Path) -> None:
    talks = negotiation_of(Scripted(documents=[plan_of("Barbell_Squat")]), tmp_path)
    offered = talks.open(PLANNING, BARBELL_45)

    answered = talks.answer(PLANNING, "a-proposal-from-three-days-ago", planner.accepted())

    assert answered == negotiations.Superseded()
    assert workout_rows(catalogued) == []
    assert talks.pending(PLANNING).id == offered.id  # type: ignore[union-attr]


def test_a_turned_down_plan_is_followed_by_another_in_the_same_negotiation(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(
        Scripted(documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")]),
        tmp_path,
    )
    offered = talks.open(PLANNING, BARBELL_45)
    assert isinstance(offered, negotiations.Proposed)

    again = talks.answer(PLANNING, offered.id, planner.refused("non mi va"))

    assert isinstance(again, negotiations.Proposed) and again.id != offered.id
    assert workout_rows(catalogued) == []
    (negotiation,) = (tmp_path / "runs").iterdir()
    assert len(list(negotiation.iterdir())) == 1, "the turned-down run, written"


def test_a_plan_refused_to_the_end_is_offered_to_nobody(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(
        Scripted(documents=[plan_of("Not_In_The_Catalog")] * planner.ATTEMPTS), tmp_path
    )

    refused = talks.open(PLANNING, BARBELL_45)

    assert isinstance(refused, negotiations.Refused) and refused.violations
    assert refused.record["ending"] == "refused"
    assert talks.pending(PLANNING) is None


def test_the_next_mesocycle_is_prepared_directed_and_unasked(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    last = on_its_last_workout(catalogued)
    performed_once(catalogued, "Standing_Military_Press", last)
    planned = Scripted(documents=[NEXT])
    talks = negotiation_of(planned, tmp_path)

    prepared = talks.prepare(PLANNING, DIRECTING)

    assert isinstance(prepared, negotiations.Proposed) and prepared.unasked
    assert isinstance(prepared.request, plans.MesocycleRequest)
    assert prepared.request.continuing is not None
    assert prepared.request.continuing.direction == mesocycles.Direction(**DIRECTED.model_dump())
    assert not talks.preparing(PLANNING), "released once offered"
    assert talks.prepare(PLANNING, DIRECTING) is None, "offered already"
    assert len(planned.seen) == 1


def test_preparing_the_next_is_nothing_while_a_mesocycle_is_offered(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    planned = Scripted(documents=[A_MESOCYCLE, NEXT])
    talks = negotiation_of(planned, tmp_path)
    assert isinstance(talks.open(PLANNING, asked_for_a_mesocycle()), negotiations.Proposed)
    last = on_its_last_workout(catalogued)
    performed_once(catalogued, "Standing_Military_Press", last)

    assert talks.prepare(PLANNING, DIRECTING) is None
    assert len(planned.seen) == 1


def test_preparing_the_next_is_nothing_while_it_is_being_prepared(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    last = on_its_last_workout(catalogued)
    performed_once(catalogued, "Standing_Military_Press", last)
    planned = Scripted(documents=[NEXT])
    talks = negotiation_of(planned, tmp_path, preparing={"chat:1/plan"})

    assert talks.preparing(PLANNING)
    assert talks.prepare(PLANNING, DIRECTING) is None
    assert planned.seen == []


def test_preparing_is_nothing_when_no_mesocycle_has_ended(
    catalogued: sqlite3.Connection, declared: Path, tmp_path: Path
) -> None:
    on_its_last_workout(catalogued)
    planned = Scripted(documents=[NEXT])
    talks = negotiation_of(planned, tmp_path)

    assert talks.prepare(PLANNING, DIRECTING) is None
    assert planned.seen == []


def test_a_run_stopped_between_steps_offers_nothing_and_is_written_as_stopped(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    planned = Scripted(documents=[plan_of("Barbell_Squat")])
    talks = negotiation_of(planned, tmp_path)
    seen: list[bool] = []

    def watching(chunk: dict[str, object]) -> None:
        seen.append(talks.running(PLANNING))
        talks.stop(PLANNING)

    stopped = talks.open(PLANNING, BARBELL_45, progress=watching)

    assert isinstance(stopped, negotiations.Stopped)
    assert stopped.record["ending"] == "stopped"
    assert seen[0], "running while it streams"
    assert not talks.running(PLANNING)
    assert talks.pending(PLANNING) is None, "a stopped run leaves nothing to tap"
    assert len(planned.seen) == 1, "nothing after the call already sent"
    assert planned.documents, "the plan was never emitted"
    (written,) = (tmp_path / "runs" / stopped.record["negotiation"]).iterdir()
    assert '"ending": "stopped"' in written.read_text(encoding="utf-8")


def test_stopping_with_nothing_in_flight_stops_nothing(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(Scripted(documents=[plan_of("Barbell_Squat")]), tmp_path)

    assert not talks.running(PLANNING)
    assert not talks.stop(PLANNING)
    assert isinstance(talks.open(PLANNING, BARBELL_45), negotiations.Proposed)


def test_the_ask_after_a_stop_opens_in_its_negotiation_following_it(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(
        Scripted(documents=[plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")]),
        tmp_path,
    )
    def correcting(chunk: dict[str, object]) -> None:
        talks.stop(PLANNING)

    stopped = talks.open(PLANNING, BARBELL_45, progress=correcting)
    assert isinstance(stopped, negotiations.Stopped)

    after = talks.open(PLANNING, BARBELL_45, carrying=talks.continuing(PLANNING))

    assert isinstance(after, negotiations.Proposed)
    assert after.plan == plan_of("Barbell_Squat")
    accepted = talks.answer(PLANNING, after.id, planner.accepted())
    assert isinstance(accepted, negotiations.Accepted)
    assert accepted.record["negotiation"] == stopped.record["negotiation"]
    assert accepted.record["follows"] == stopped.record["run"]
    assert len(workout_rows(catalogued)) == 1


def test_a_stop_that_comes_as_the_run_ends_does_not_relabel_its_ending(
    catalogued: sqlite3.Connection, tmp_path: Path
) -> None:
    talks = negotiation_of(Scripted(documents=[plan_of("Barbell_Squat")]), tmp_path)
    offered = talks.open(PLANNING, BARBELL_45)
    assert isinstance(offered, negotiations.Proposed)

    def late(chunk: dict[str, object]) -> None:
        if "prescribe" in chunk:
            talks.stop(PLANNING)

    accepted = talks.answer(PLANNING, offered.id, planner.accepted(), progress=late)

    assert isinstance(accepted, negotiations.Accepted)
    assert accepted.record["ending"] == "accepted"
    assert len(workout_rows(catalogued)) == 1
