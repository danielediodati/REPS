"""The logger graph, against a scripted chat model.

The second subgraph, on the same tools as the planner. What changes is which
tools are on the table, what its results carry, and that a turn can be a
question to the user -- an `interrupt()` that waits days, where the loop this
replaces had a marked line in prose and three paragraphs of reasoning in front
of it.
"""

from __future__ import annotations

import ast
import inspect
import json
import sqlite3
import textwrap
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from conftest import enrich
from test_planner import CATALOG, PATTERNS, SCRIPTED, STAND_IN, Scripted, calling
from trainer import log as logs
from trainer import tools
from trainer.coach import checkpoints, logger, models
from trainer.coach import record as run_record
from trainer.engine import catalog, database, duration, exclusions, migrations, workouts

TODAY = "2026-09-10"
THREAD: RunnableConfig = {"configurable": {"thread_id": "one"}}

WRITERS = ("record_prescribed", "record_performed")
"""The two functions that change what the database says happened."""


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


def prescribe(connection: sqlite3.Connection, on: str = "2026-09-09") -> int:
    """One prescribed workout on the fixture catalog: squats and a press.

    Written straight through the engine. The guard that only a door may call a
    writer is about `src/trainer`, and a test that could not set up a
    prescription could not exercise a single thing this graph does.
    """
    return workouts.record_prescribed(
        connection,
        (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(
                        duration.BlockItem(exercise_id="Barbell_Squat", reps=8),
                        duration.BlockItem(
                            exercise_id="Standing_Military_Press", reps=10
                        ),
                    ),
                    rounds=4,
                    rest=150,
                ),
                reason="legs and a press",
            ),
        ),
        on=on,
    )


def report(**fields: Any) -> logs.PerformedWorkout:
    """A document in the shape the logger emits, deviations only."""
    base: dict[str, Any] = {"report": "tutto come scritto"}
    base.update(fields)
    return logs.PerformedWorkout(**base)


def done(
    exercise_id: str, source: logs.Provenance = "reported", **fields: Any
) -> logs.PerformedBlock:
    """One block as it was performed, with the provenance under test on it."""
    block: dict[str, Any] = {
        "items": [
            logs.PerformedItem(
                exercise_id=exercise_id, unit="reps", amount=8, amount_source=source
            )
        ],
        "rounds": 3,
        "rounds_source": source,
        "rest": 150,
        "rest_source": source,
    }
    block.update(fields)
    return logs.PerformedBlock(**block)


def graph_of(model: Scripted, **built: Any) -> logger.Logger:
    """The logger graph on a scripted model, named the way a real one is."""
    built.setdefault("checkpointer", InMemorySaver())
    return logger.build(models.Chat(model, SCRIPTED, STAND_IN), **built)


def scripted(
    *turns: AIMessage, emits: logs.PerformedWorkout, times: int = 1
) -> Scripted:
    """A model whose turns and emitted document were written in advance.

    The document goes in as `raw`, because the stand-in is the planner's and
    its `documents` are plans -- what both graphs actually ask a provider for
    is a string, which is the seam these tests want anyway.

    `times` is how many runs it has to answer. A model is consumed as it goes,
    so a suite that runs the same row twice needs the script twice.
    """
    return Scripted(
        turns=list(turns) * times, raw=[emits.model_dump_json()] * times
    )


def until_done(graph: logger.Logger, given: Any, answers: Any = None) -> dict[str, Any]:
    """Run to the end, answering every question the way `answers` says.

    `answers` is a callable taking the question and returning what to resume
    with, or `None` to decline everything -- which is what a caller with
    nobody to ask does.
    """
    while True:
        final = graph.invoke(given, THREAD)
        waiting = final.get("__interrupt__")
        if not waiting:
            return dict(final)
        question = waiting[0].value
        given = Command(resume=answers(question) if answers else False)


# -- the tools this graph offers ----------------------------------------------


def test_the_logger_offers_six_tools_and_none_of_them_writes() -> None:
    """The number is the ticket's, and the claim under it is the session's: if
    the model can call the write, the model decides when the database changes.

    Checked against the functions the graph actually registers rather than
    against its list of names -- a name that resolved to something else would
    pass a test written about the constant.
    """
    offered = tools.registered("logger", logger.TOOLS)

    assert len(offered) == 6
    for tool in offered:
        source = ast.parse(textwrap.dedent(inspect.getsource(tool)))
        named = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(source)
            if isinstance(node, (ast.Attribute, ast.Name))
        }
        assert not named & set(WRITERS), f"{tool.__name__} reaches a writer"
        assert "add" not in named, f"{tool.__name__} may write an exclusion"


def test_asking_is_a_tool_the_engine_does_not_have() -> None:
    """`ask_user` is the graph's, not the surface's: it answers it itself, and
    a tool the engine served would be the engine talking to the user."""
    assert logger.ask_user.__name__ not in {tool.__name__ for tool in tools.TOOLS}
    assert tools.schema(logger.ask_user)["parameters"]["required"] == ["question"]

    with pytest.raises(AssertionError):
        logger.ask_user("never")


def test_the_logger_cannot_call_a_tool_the_planner_has(
    connection: sqlite3.Connection,
) -> None:
    """A tool that exists is not a tool this graph was offered. It comes back
    as a result it can recover from, listing what it does have."""
    model = scripted(
        calling("admissible_set", equipment=["barbell"], budget_min=45),
        AIMessage(content="chiaro"),
        emits=report(blocks=[done("Barbell_Squat")], report="fatto"),
    )

    final = until_done(graph_of(model), logger.starting("fatto", TODAY))

    answered = [message for message in final["messages"] if message.type == "tool"]
    assert "no tool called 'admissible_set'" in answered[0].text
    assert "prescribed_workout" in answered[0].text


# -- one report, read ----------------------------------------------------------


def test_a_run_reads_the_prescription_and_emits_a_document(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    model = scripted(
        calling("prescribed_workout", workout_id=identifier),
        AIMessage(content="tutto chiaro"),
        emits=report(
            workout_id=identifier,
            blocks=[done("Barbell_Squat", rounds=3)],
            report="solo tre serie di squat",
        ),
    )

    final = until_done(
        graph_of(model),
        logger.starting("solo tre serie di squat", TODAY, awaiting=identifier),
    )

    assert final["refused"] is None
    assert final["document"].workout_id == identifier
    assert final["questions"] == [], "nothing in that sentence needed clarifying"
    assert final["spent"] == 1


def test_the_brief_names_the_workout_that_is_open_and_the_words_that_were_said() -> None:
    written = logger.brief(
        "panca pesante", TODAY, awaiting=12, prescribed_on="2026-09-09"
    )

    assert "prescribed_workout(12)" in written
    assert "2026-09-09" in written
    assert "panca pesante" in written
    assert TODAY in written, "a re-test date has to be after a day it knows"


def test_the_brief_says_when_nothing_is_waiting_for_a_report() -> None:
    """Training nobody planned is training. The state is named rather than
    left for the model to infer from a workout id it was not given."""
    written = logger.brief("sono andato a correre", TODAY)

    assert "No prescribed workout is waiting" in written
    assert "null" in written


def test_a_substitution_reaches_the_catalog_only_after_the_prescribed_set_fails(
    connection: sqlite3.Connection,
) -> None:
    """The candidates are the exercises of the prescribed workout. Catalog
    search is the fallback, called exactly when the closed set has nothing that
    can be what the user meant -- which is exactly when there was a
    substitution, and that is the interesting case."""
    identifier = prescribe(connection)
    model = scripted(
        calling("prescribed_workout", workout_id=identifier),
        calling("search_exercises", text="dumbbell bench"),
        AIMessage(content="tutto chiaro"),
        emits=report(
            workout_id=identifier,
            blocks=[done("Dumbbell_Bench_Press")],
            report="ho scambiato i military con la panca coi manubri",
        ),
    )

    final = until_done(
        graph_of(model),
        logger.starting("ho scambiato i military", TODAY, awaiting=identifier),
    )

    written = run_record.of(final, tools.CALL_BUDGET)
    assert [call["name"] for call in written["calls"]] == [
        "prescribed_workout",
        "search_exercises",
    ]
    assert final["refused"] is None
    substituted = final["document"].blocks[0].items[0].exercise_id
    assert catalog.exercise(connection, substituted) is not None


def test_an_id_the_model_remembered_rather_than_read_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """A well-formed dead id passes anything that does not check the catalog,
    and the error becomes volume filed under the wrong exercise, silently.

    It is refused rather than made impossible, and that is the trade this
    graph makes for showing the model exercise names at all."""
    identifier = prescribe(connection)
    model = scripted(
        AIMessage(content="tutto chiaro"),
        emits=report(
            workout_id=identifier,
            blocks=[done("Barbell_Bench_Press_Medium_Grip")],
            report="panca",
        ),
        times=logger.ATTEMPTS,
    )

    final = until_done(
        graph_of(model), logger.starting("panca", TODAY, awaiting=identifier)
    )

    assert final["refused"] is not None
    assert "Barbell_Bench_Press_Medium_Grip" in final["refused"]
    assert final["document"].blocks, "the document is still recorded whole"


def test_a_model_that_finishes_by_calling_a_tool_asks_nothing(
    connection: sqlite3.Connection,
) -> None:
    """On Groq, Qwen ended its reading with a tool call whatever it had to
    say, and the only free one was `ask_user`: *"No question needed"* reached
    the user as a question. `done_reading` is the call that ends a reading."""
    identifier = prescribe(connection)
    model = scripted(
        calling("prescribed_workout", workout_id=identifier),
        calling(logger.done_reading.__name__),
        emits=report(workout_id=identifier, report="tutto liscio"),
    )

    final = until_done(
        graph_of(model), logger.starting("tutto liscio", TODAY, awaiting=identifier)
    )

    assert final["questions"] == []
    assert final["refused"] is None
    assert final["document"].workout_id == identifier


def test_a_spent_call_budget_goes_to_emit(connection: sqlite3.Connection) -> None:
    identifier = prescribe(connection)
    model = scripted(
        calling("prescribed_workout", workout_id=identifier),
        calling("prescribed_workout", workout_id=identifier),
        emits=report(workout_id=identifier, report="fatto"),
    )

    final = until_done(
        graph_of(model, budget=1),
        logger.starting("fatto", TODAY, awaiting=identifier),
    )

    assert final["spent"] == 1
    assert final["document"] is not None


# -- the clarifying question ---------------------------------------------------


def test_a_report_that_does_not_determine_a_value_stops_on_an_interrupt(
    connection: sqlite3.Connection,
) -> None:
    """*"4 out of 10"* is effort **or** discomfort, and TRAINER.md's own
    sentence does not say which. The graph asks rather than filling it in --
    and it stops, which is what lets the answer come days later."""
    identifier = prescribe(connection)
    model = scripted(
        calling("ask_user", question="Quel 4 su 10 e' fatica o fastidio?"),
        AIMessage(content="tutto chiaro"),
        emits=report(workout_id=identifier, report="squat, 4 su 10"),
    )
    graph = graph_of(model)

    final = graph.invoke(
        logger.starting("squat, 4 su 10", TODAY, awaiting=identifier), THREAD
    )

    (waiting,) = final["__interrupt__"]
    assert waiting.value["kind"] == logger.CLARIFY
    assert waiting.value["ask"] == "Quel 4 su 10 e' fatica o fastidio?"
    assert final["document"] is None, "it has emitted nothing yet"


def test_the_answer_reaches_the_model_and_the_run_carries_on(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    model = scripted(
        calling("ask_user", question="Fatica o fastidio?"),
        AIMessage(content="tutto chiaro"),
        emits=report(workout_id=identifier, report="squat, 4 su 10"),
    )
    graph = graph_of(model)
    graph.invoke(logger.starting("squat, 4 su 10", TODAY, awaiting=identifier), THREAD)

    final = graph.invoke(Command(resume="fastidio, non fatica"), THREAD)

    assert final["questions"] == [("Fatica o fastidio?", "fastidio, non fatica")]
    assert final["spent"] == 0, "asking is not a tool call"
    said = "\n".join(message.text for message in model.seen[-1])
    assert "fastidio, non fatica" in said


def test_a_question_answered_days_later_resumes_the_same_run(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A pending question can wait without losing the thread: the process goes
    away between the question and the answer, and the run it resumes is the
    one that asked."""
    identifier = prescribe(connection)
    path = tmp_path / "checkpoints.sqlite"
    model = scripted(
        calling("ask_user", question="Fatica o fastidio?"),
        AIMessage(content="tutto chiaro"),
        emits=report(workout_id=identifier, report="squat, 4 su 10"),
    )

    with checkpoints.saver(path) as saver:
        graph = graph_of(model, checkpointer=saver)
        opened = graph.invoke(
            logger.starting("squat, 4 su 10", TODAY, awaiting=identifier), THREAD
        )
        asked = opened["run"]

    with checkpoints.saver(path) as saver:
        graph = graph_of(model, checkpointer=saver)
        final = graph.invoke(Command(resume="fastidio"), THREAD)

    assert final["run"] == asked, "the same run, not another"
    assert final["document"] is not None
    assert final["questions"] == [("Fatica o fastidio?", "fastidio")]


def test_a_turn_that_calls_a_tool_and_asks_does_both(
    connection: sqlite3.Connection,
) -> None:
    """One turn, two calls, and a node that stops in the middle of them. The
    reads beside the question run again on the resume, which is why every tool
    on this surface is one."""
    identifier = prescribe(connection)
    model = scripted(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "prescribed_workout",
                    "args": {"workout_id": identifier},
                    "id": "call_read",
                    "type": "tool_call",
                },
                {
                    "name": "ask_user",
                    "args": {"question": "Fatica o fastidio?"},
                    "id": "call_ask",
                    "type": "tool_call",
                },
            ],
        ),
        AIMessage(content="tutto chiaro"),
        emits=report(workout_id=identifier, report="squat, 4 su 10"),
    )
    graph = graph_of(model)

    final = until_done(
        graph,
        logger.starting("squat, 4 su 10", TODAY, awaiting=identifier),
        answers=lambda _: "fastidio",
    )

    assert final["spent"] == 1, "the read is a call; the question is not"
    assert final["questions"] == [("Fatica o fastidio?", "fastidio")]
    assert final["document"] is not None


def test_the_question_budget_stops_a_model_that_only_asks(
    connection: sqlite3.Connection,
) -> None:
    """It emits with what it has rather than looping -- the same property the
    call budget has, applied to the other thing a turn can be. Somebody has
    just trained and is answering these on a phone."""
    model = scripted(
        *[calling("ask_user", question=f"Numero {n}?") for n in range(5)],
        emits=report(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    final = until_done(
        graph_of(model),
        logger.starting("4 su 10", TODAY),
        answers=lambda _: "si",
    )

    put = [said for _, said in final["questions"] if said == "si"]
    assert len(put) == logger.ASK_BUDGET, "only three reached the user"
    assert final["questions"][logger.ASK_BUDGET][1] == logger.SPENT_ASKING
    assert final["document"] is not None, "it emitted with what it had"


def test_asking_leaves_the_table_once_the_budget_is_spent(
    connection: sqlite3.Connection,
) -> None:
    """A budget is only a budget if the model cannot reach past it.

    Answered with a sentence and left on the table, `ask_user` is a tool a
    model can keep calling without ever spending a tool call -- the run then
    loops between the two nodes until LangGraph's recursion limit ends it,
    which is not the budget doing its job.
    """
    model = scripted(
        *[calling("ask_user", question=f"Numero {n}?") for n in range(5)],
        emits=report(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    until_done(
        graph_of(model), logger.starting("4 su 10", TODAY), answers=lambda _: "si"
    )

    asked = logger.ask_user.__name__
    offered = [asked in table for table in model.bound]
    assert offered[: logger.ASK_BUDGET] == [True] * logger.ASK_BUDGET
    assert not any(offered[logger.ASK_BUDGET :]), "it is off the table after three"
    assert all("prescribed_workout" in table for table in model.bound), (
        "the reads stay; it is the asking that ran out"
    )


# -- the exclusion it may propose ----------------------------------------------


def proposing(identifier: int, retest: str = "2026-10-15") -> Scripted:
    return scripted(
        AIMessage(content="tutto chiaro"),
        emits=report(
            workout_id=identifier,
            report="la spalla tirava sui military",
            proposed_exclusion=logs.ProposedExclusion(
                value="shoulder", retest_date=retest, why="la spalla tirava"
            ),
        ),
        times=logger.ATTEMPTS,
    )


def test_a_proposed_exclusion_stops_for_confirmation(
    connection: sqlite3.Connection,
) -> None:
    """An exclusion is a hard boundary used only for safety, and it is
    confirmed before it is written -- never inferred from a report."""
    identifier = prescribe(connection)
    graph = graph_of(proposing(identifier))

    final = graph.invoke(
        logger.starting("la spalla tirava", TODAY, awaiting=identifier), THREAD
    )

    (waiting,) = final["__interrupt__"]
    assert waiting.value["kind"] == logger.EXCLUSION
    assert waiting.value["value"] == "shoulder"
    assert waiting.value["granularity"] == "joint", "the catalog decides which"
    assert waiting.value["retest_date"] == "2026-10-15"
    assert exclusions.active(connection, TODAY) == ()


def test_an_exclusion_nobody_confirmed_is_never_written(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)

    final = until_done(
        graph_of(proposing(identifier)),
        logger.starting("la spalla tirava", TODAY, awaiting=identifier),
        answers=lambda _: False,
    )
    logger.performed(connection, final, logs.to_performed(connection, final["document"]))

    assert final["confirmed"] is False
    assert exclusions.active(connection, TODAY) == ()


def test_a_confirmed_exclusion_is_written_with_the_workout(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)

    final = until_done(
        graph_of(proposing(identifier)),
        logger.starting("la spalla tirava", TODAY, awaiting=identifier),
        answers=lambda _: True,
    )
    logger.performed(connection, final, logs.to_performed(connection, final["document"]))

    assert final["confirmed"] is True
    assert [one.value for one in exclusions.active(connection, TODAY)] == ["shoulder"]


def test_a_re_test_date_that_has_already_passed_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """A wall that was never a wall is the same failure as a wall with no way
    back, with the sign flipped: nothing re-reads the row, and the render
    prints a confident sentence about a movement that is not excluded."""
    identifier = prescribe(connection)

    final = until_done(
        graph_of(proposing(identifier, retest="2026-01-01")),
        logger.starting("spalla", TODAY, awaiting=identifier),
    )

    assert final["refused"] is not None
    assert "2026-01-01" in final["refused"]
    assert final.get("__interrupt__") is None, "a refused document asks nothing"


# -- the run it leaves behind --------------------------------------------------


def test_a_run_of_the_logger_leaves_a_run_document(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """The same document a run of the planner leaves, written by the same
    function into the same archive (ADR-0007)."""
    from trainer.coach import runs

    identifier = prescribe(connection)
    archive = tmp_path / "runs"
    model = scripted(
        calling("prescribed_workout", workout_id=identifier),
        AIMessage(content="chiaro"),
        emits=report(workout_id=identifier, report="fatto"),
    )

    until_done(
        graph_of(model, archive=archive),
        logger.starting("fatto", TODAY, awaiting=identifier),
    )

    (kept,) = runs.kept(archive)
    assert kept.ending == run_record.DONE
    assert [call["name"] for call in kept.document["calls"]] == ["prescribed_workout"]
    assert {node["model"] for node in kept.document["nodes"]} == {STAND_IN}


def test_a_document_refused_to_the_last_attempt_ends_the_run_as_refused(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    from trainer.coach import runs

    identifier = prescribe(connection)
    archive = tmp_path / "runs"
    model = scripted(
        AIMessage(content="chiaro"),
        emits=report(
            workout_id=identifier,
            blocks=[done("Barbell_Bench_Press_Medium_Grip")],
            report="panca",
        ),
        times=logger.ATTEMPTS,
    )

    until_done(
        graph_of(model, archive=archive),
        logger.starting("panca", TODAY, awaiting=identifier),
    )

    (kept,) = runs.kept(archive)
    assert kept.ending == run_record.REFUSED
    assert len(kept.document["attempts"]) == logger.ATTEMPTS


def test_a_refusal_goes_back_to_the_model_and_it_corrects_the_document(
    connection: sqlite3.Connection,
) -> None:
    """The validator's sentence is what the model reads next, and the run it
    corrects ends `done` with both attempts on the record."""
    identifier = prescribe(connection)
    wrong = report(
        workout_id=identifier, blocks=[done("TRACIONE")], report="trazioni"
    )
    right = report(workout_id=identifier, blocks=[done("Barbell_Squat")], report="trazioni")
    model = Scripted(
        turns=[AIMessage(content="chiaro"), AIMessage(content="ora ho capito")],
        raw=[wrong.model_dump_json(), right.model_dump_json()],
    )

    final = until_done(
        graph_of(model), logger.starting("trazioni", TODAY, awaiting=identifier)
    )

    assert final["refused"] is None
    assert final["document"] == right
    assert final["ending"] == run_record.DONE
    told = [message.text for message in model.seen[-1]]
    assert any("TRACIONE" in said and "catalog" in said for said in told)
    assert len(run_record.of(final, tools.CALL_BUDGET)["attempts"]) == 2


# -- nothing the graph does writes ---------------------------------------------


def test_the_graph_leaves_the_workout_count_unchanged(
    connection: sqlite3.Connection,
) -> None:
    """ROADMAP.md § Session 5: writes are never tools. The graph emits; the
    door that asked writes, through `logger.performed`."""
    identifier = prescribe(connection)
    model = scripted(
        calling("prescribed_workout", workout_id=identifier),
        AIMessage(content="chiaro"),
        emits=report(workout_id=identifier, report="fatto"),
    )

    final = until_done(
        graph_of(model), logger.starting("fatto", TODAY, awaiting=identifier)
    )

    assert final["refused"] is None
    assert _workouts(connection) == 1, "the prescription, and nothing the graph wrote"


def test_the_door_that_asked_writes_the_workout_and_reads_the_flags(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    model = scripted(
        AIMessage(content="chiaro"),
        emits=report(
            workout_id=identifier,
            blocks=[done("Barbell_Squat", rounds=3)],
            report="solo tre serie",
        ),
    )
    final = until_done(
        graph_of(model), logger.starting("solo tre serie", TODAY, awaiting=identifier)
    )

    blocks = logs.to_performed(connection, final["document"])
    written = logger.performed(connection, final, blocks)

    assert written == identifier, "the prescription became the performed workout"
    found = workouts.workout(connection, written)
    assert found is not None and found.state == "performed"
    assert blocks, "adherence filled the rest in"
    assert [item.exercise_id for block in blocks for item in block.items] == [
        "Barbell_Squat",
        "Standing_Military_Press",
    ]


def test_an_interrupted_conversation_writes_nothing_at_all(
    connection: sqlite3.Connection,
) -> None:
    """The question is asked and nobody answers. Nothing about a report
    reaches the database -- not the workout, not the exclusion, and not a word
    of the conversation.

    Session 6's issue 5 is the non-negotiable test that LangGraph never
    persists domain and SQLite never persists conversation; a half-finished
    report parked in a table would make it red before it is written.
    """
    identifier = prescribe(connection)
    said = "la spalla tirava, 4 su 10"
    model = scripted(
        calling("ask_user", question="Fatica o fastidio?"),
        AIMessage(content="chiaro"),
        emits=report(workout_id=identifier, report=said),
    )

    graph_of(model).invoke(logger.starting(said, TODAY, awaiting=identifier), THREAD)

    found = workouts.workout(connection, identifier)
    assert found is not None and found.state == "prescribed"
    assert exclusions.active(connection, TODAY) == ()
    assert said not in _everything_stored(connection)


def _workouts(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute("SELECT COUNT(*) AS total FROM workouts").fetchone()["total"]
    )


def _everything_stored(connection: sqlite3.Connection) -> str:
    """Every value in every table this schema has, as one string.

    Blunt on purpose: the claim is that no conversation is persisted anywhere,
    and a test that named the tables it expected to be empty would pass for a
    table added next session to hold exactly that.
    """
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    found: list[str] = []
    for table in tables:
        for row in connection.execute(f'SELECT * FROM "{table["name"]}"'):  # a name
            found.extend(str(value) for value in tuple(row))
    return "\n".join(found)


# -- what the logging prompt has to say ----------------------------------------


def test_the_logging_prompt_carries_the_rules_this_ticket_decided() -> None:
    """Each of these is a rule with nowhere else to live: no code can make a
    model resolve an id inside a closed set first, and a rule the model was
    never told is a finding that is the prompt's fault."""
    for rule in (
        "prescribed_workout",
        "search_exercises",
        "never write an id you remember",
        "leave it null",
        "verbatim",
        "never ask for it",
        f"at most {logger.ASK_BUDGET} in all",
        "never an exercise id",
        "the validator",
        logger.ask_user.__name__,
        logger.done_reading.__name__,
    ):
        assert rule.lower() in logger.LOGGING.lower(), rule


def test_the_prompt_says_what_is_not_a_question() -> None:
    """On Groq, Qwen asked in 11 of 12 reports that determined their answer:
    for the reps of a block the user called normal, and to confirm an
    exclusion the graph confirms on its own."""
    prompt = logger.LOGGING.lower()
    assert "a number they did not mention is not a question" in prompt
    assert "never ask to confirm an exclusion" in prompt


def test_the_prompt_does_not_forbid_what_the_set_expects() -> None:
    """The first pass on the graph found `LOGGING` saying *never `assumed`*
    while the set expected it; the model split between the two."""
    assert "never `assumed`" not in logger.LOGGING.lower()


def test_the_prompt_no_longer_teaches_a_marker() -> None:
    """The question was a line of prose the loop had to recognise, and there is
    no length, tone or punctuation that separates a model thinking out loud
    from a model asking. It is a tool call now, and nothing reads prose."""
    assert "QUESTION:" not in logger.LOGGING
    assert "write a line that starts with" not in logger.LOGGING.lower()


def test_a_bare_number_has_no_way_of_becoming_an_rpe_without_being_offered() -> None:
    """`rpe` carries no provenance, because it is recorded only when the user
    volunteers it -- so `assumed` and `asked` cannot arise for it. The rule the
    prompt states is the one that keeps a bare number off it, and the shape is
    what stops a filled-in one being dressed as something the user was asked."""
    assert "rpe" not in logs.PerformedItem.model_fields
    assert set(logs.PerformedBlock.model_fields) & {"rpe_source"} == set()
    assert "never ask for it" in logger.LOGGING.lower()


def test_the_logger_is_shown_the_exercise_names_the_user_says_out_loud(
    connection: sqlite3.Connection,
) -> None:
    """The planner drops `name`, because a plan is written in ids and a model
    shown both copied the readable one into `exercise_id`. This graph has the
    opposite job: resolving *"the bench"* against the prescribed workout is
    not possible when everything in it is an id nobody says out loud."""
    identifier = prescribe(connection)

    result = tools.execute(
        tools.Call(id="c", name="prescribed_workout", arguments={"workout_id": identifier}),
        tools.registered("logger", logger.TOOLS),
        logger.KEEPS,
    )

    assert "Barbell Squat" in result.content
    assert "name" in json.loads(result.content)["blocks"][0]["items"][0]


def test_a_run_started_without_a_name_is_still_a_run(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Studio and the HTTP API hand the graph a report and nothing else. It is
    still a run, and it still leaves a document (ADR-0007)."""
    from trainer.coach import runs

    archive = tmp_path / "runs"
    model = scripted(
        AIMessage(content="chiaro"),
        emits=report(blocks=[done("Barbell_Squat")], report="fatto a casa"),
    )

    graph_of(model, archive=archive).invoke(
        {"report": "fatto a casa", "today": TODAY}, THREAD
    )

    (kept,) = runs.kept(archive)
    assert kept.negotiation and kept.run
    assert kept.ending == run_record.DONE
