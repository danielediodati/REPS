"""The entrance graph, against a scripted chat model.

The node that talks (ADR-0006). What is driven here is the deciding: what it
answers itself, what it hands to a subgraph, and what it is allowed to know
when it answers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from conftest import enrich
from test_planner import CATALOG, LEGS_AND_SHOULDERS, PATTERNS, Scripted, calling
from trainer import tools
from trainer.coach import entrance, models
from trainer.coach import record as records
from trainer.engine import catalog, database, duration, mesocycles, migrations, workouts

FRONT = "a-small-fast-one"
FRONT_PROVIDER = "front"


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


def graph_of(model: Scripted, **built: Any) -> entrance.Entrance:
    """The entrance on a scripted model, named the way a real one is."""
    return entrance.build(models.Chat(model, FRONT_PROVIDER, FRONT), **built)


def says(line: str) -> AIMessage:
    return AIMessage(content=line)


CIAO = "ciao, come funzioni?"


# -- what it answers itself ----------------------------------------------------


def test_a_turn_that_is_neither_a_report_nor_a_request_is_answered_here(
    connection: sqlite3.Connection,
) -> None:
    """Nothing about it reaches a subgraph. A plan is minutes and a greeting is
    not one."""
    model = Scripted(turns=[says("Sono il tuo allenatore, scrivimi pure.")])

    final = graph_of(model).invoke(entrance.heard(CIAO))

    assert final["answer"] == "Sono il tuo allenatore, scrivimi pure."
    assert final["handoff"] == ""


def test_what_it_answered_itself_is_a_run_that_ended(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A turn it answered is over, and a closed run is a document (ADR-0007)."""
    model = Scripted(turns=[says("ci sono")])

    final = graph_of(model, archive=tmp_path).invoke(entrance.heard(CIAO))

    assert final["ending"] == records.DONE
    assert (tmp_path / final["negotiation"] / f"{final['run']}.json").exists()


def test_the_conversation_outlives_the_run(connection: sqlite3.Connection) -> None:
    """Unlike either subgraph's history, which is one run long. The entrance is
    the only node that remembers the turn before, which is what stops it asking
    the same question twice."""
    model = Scripted(turns=[says("uno"), says("due")])
    graph = graph_of(model, checkpointer=InMemorySaver())
    thread: RunnableConfig = {"configurable": {"thread_id": "one"}}

    graph.invoke(entrance.heard("prima"), thread)
    final = graph.invoke(entrance.heard("seconda"), thread)

    assert final["said"] == ["prima", "seconda"]
    written = [m.text for m in model.seen[-1] if isinstance(m, HumanMessage)]
    assert written == ["prima", "seconda"]


# -- what it hands on ----------------------------------------------------------


def test_a_request_for_a_mesocycle_reaches_the_planner(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[calling(entrance.PLAN_MESOCYCLE), says("Ci penso, arriva a momenti.")]
    )

    final = graph_of(model).invoke(entrance.heard("preparami un mesociclo"))

    assert final["handoff"] == entrance.PLAN_MESOCYCLE
    assert final["answer"] == "Ci penso, arriva a momenti."


def test_a_request_for_today_is_answered_by_reading_the_mesocycle(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A read and not the planner: no subgraph carries the run on, so it ends here."""
    model = Scripted(turns=[calling(entrance.TODAYS_WORKOUT), says("Eccolo.")])

    final = graph_of(model, archive=tmp_path, today=lambda: entrance.SERVING).invoke(
        entrance.heard("cosa faccio oggi?")
    )

    assert final["handoff"] == entrance.TODAYS_WORKOUT
    told = [m.text for m in final["messages"] if isinstance(m, ToolMessage)]
    assert told == [entrance.SERVING]
    assert final["ending"] == records.DONE


def test_with_no_mesocycle_the_read_says_so(connection: sqlite3.Connection) -> None:
    """Against the engine itself: nothing was ever accepted in this database."""
    model = Scripted(turns=[calling(entrance.TODAYS_WORKOUT), says("Non ne hai uno.")])

    final = graph_of(model).invoke(entrance.heard("cosa faccio oggi?"))

    told = [m.text for m in final["messages"] if isinstance(m, ToolMessage)]
    assert told == [entrance.NO_MESOCYCLE]


def test_a_database_that_is_not_there_is_unreadable_not_absent(
    database_file: Path,
) -> None:
    """A missing precondition is not a missing mesocycle: offering to plan one
    would promise something the machine cannot do."""
    assert entrance.reading_today() == entrance.UNREADABLE


def test_a_report_reaches_the_logger(connection: sqlite3.Connection) -> None:
    model = Scripted(turns=[calling(entrance.LOG_WORKOUT), says("Me lo segno.")])

    final = graph_of(model).invoke(entrance.heard("ho fatto squat, 4 serie"))

    assert final["handoff"] == entrance.LOG_WORKOUT


def test_a_turn_it_handed_on_is_not_a_run_that_ended(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """The subgraph carries the same run on: the user asked once, so what they
    asked is one run and the entrance is its first node."""
    model = Scripted(turns=[calling(entrance.PLAN_MESOCYCLE), says("ci penso")])

    final = graph_of(model, archive=tmp_path).invoke(entrance.heard("oggi?"))

    assert final["ending"] == ""
    assert list(tmp_path.glob("*/*.json")) == []


def test_what_it_hands_on_carries_the_run_and_the_seconds_it_spent(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[calling(entrance.PLAN_MESOCYCLE), says("ci penso")])

    final = graph_of(model).invoke(entrance.heard("oggi?"))
    carried = entrance.carried(final)

    assert carried["run"] == final["run"]
    assert carried["negotiation"] == final["negotiation"]
    assert carried["ending"] == "" and carried["ended"] == ""
    assert [node for node, *_ in carried["timings"]] == [
        node for node, *_ in final["timings"]
    ]
    assert carried["timings"], "the entrance's seconds would be nobody's"


def test_a_second_subgraph_in_one_turn_is_not_started(
    connection: sqlite3.Connection,
) -> None:
    """One thing at a time. Two runs started from one turn is two drafts and
    two plans for a chat that asked once."""
    both = AIMessage(
        content="",
        tool_calls=[
            {"name": entrance.PLAN_MESOCYCLE, "args": {}, "id": "a", "type": "tool_call"},
            {"name": entrance.LOG_WORKOUT, "args": {}, "id": "b", "type": "tool_call"},
        ],
    )
    model = Scripted(turns=[both, says("ci penso")])

    final = graph_of(model).invoke(entrance.heard("oggi? ah, e ieri ho fatto squat"))

    assert final["handoff"] == entrance.PLAN_MESOCYCLE
    answered = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in answered] == ["a", "b"]
    assert answered[1].text == entrance.ONE_AT_A_TIME


def test_a_handed_off_turn_is_not_offered_the_tools_again(
    connection: sqlite3.Connection,
) -> None:
    """The turn after a handoff has nothing left to do but speak, and a tool
    call there is a second run nobody asked for."""
    model = Scripted(turns=[calling(entrance.PLAN_MESOCYCLE), says("ci penso")])

    graph_of(model).invoke(entrance.heard("oggi?"))

    assert entrance.PLAN_MESOCYCLE in model.bound[0]
    assert len(model.bound) == 1, "the second turn was offered tools"


# -- what it may not decide (ADR-0006, item 4) ---------------------------------


def test_no_handoff_takes_an_argument_from_the_entrance() -> None:
    """Which workout is due, and what the report says, are not the entrance's
    to name. A parameter here is a place for it to invent one -- and `report`
    above all, which is the user's own words and is what a hypothesis is
    formed from."""
    for handed in (entrance.todays_workout, entrance.plan_mesocycle, entrance.log_workout):
        assert tools.schema(handed)["parameters"]["properties"] == {}


def test_an_adaptation_and_a_change_carry_what_was_asked_and_never_a_workout() -> None:
    """The constraint is read out of what the user wrote, which is the
    entrance's to read; the slot it applies to is still the rotation's."""
    adapting = tools.schema(entrance.adapt_today)["parameters"]
    changing = tools.schema(entrance.change_mesocycle)["parameters"]

    assert set(adapting["properties"]) == {"said", "minutes", "without", "exclude"}
    assert adapting["required"] == ["said"]
    assert set(changing["properties"]) == {"said"}


def test_the_entrance_reads_the_engine_only_through_the_shared_surface() -> None:
    """Every tool it has is one of the surface's, which is read-only: there is
    no path from this node to a training fact that is not a tool result."""
    assert set(entrance.TOOLS) <= {tool.__name__ for tool in tools.TOOLS}
    assert "admissible_set" not in entrance.TOOLS, "choosing inside it is planning"


def test_the_entrance_states_no_training_fact_it_did_not_get_from_a_tool(
    connection: sqlite3.Connection,
) -> None:
    """The guarantee, at the only place it can be kept: what the model is
    *shown*.

    Everything in front of it is the system prompt, what the user wrote, what
    it wrote itself, or what a tool answered. A training fact reaching it any
    other way -- a brief, a row read beside the graph, a number folded into a
    prompt -- would be one it could state without a tool having said it.
    """
    workouts.record_performed(
        connection,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id="Barbell_Squat",
                        unit="reps",
                        amount=8,
                        amount_source="reported",
                    ),
                ),
                rounds=4,
                rounds_source="reported",
                rest=120,
                rest_source="reported",
            ),
        ),
        on="2026-09-10",
        report="squat",
    )
    model = Scripted(
        turns=[
            calling("pattern_history", pattern="squat", cycles=1),
            says("Quattro giri."),
        ]
    )

    final = graph_of(model).invoke(entrance.heard("quanto squat ho fatto?"))

    shown = model.seen[-1]
    assert isinstance(shown[0], SystemMessage) and shown[0].text == entrance.TALKING
    for message in shown[1:]:
        assert isinstance(message, (HumanMessage, AIMessage, ToolMessage)), message
    assert [m.text for m in shown if isinstance(m, HumanMessage)] == [
        "quanto squat ho fatto?"
    ]
    answered = [m for m in shown if isinstance(m, ToolMessage)]
    assert answered and '"volume": 4' in answered[0].text
    assert final["answer"] == "Quattro giri."


def test_a_read_is_answered_and_the_turn_goes_round_again(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[calling("unreported_workouts"), says("Niente in sospeso.")]
    )

    final = graph_of(model).invoke(entrance.heard("ho lasciato qualcosa indietro?"))

    assert final["spent"] == 1
    assert final["answer"] == "Niente in sospeso."


def test_the_reads_come_off_the_table_once_the_budget_is_spent(
    connection: sqlite3.Connection,
) -> None:
    """The one bound a model cannot talk its way past, kept the way both
    subgraphs keep theirs."""
    model = Scripted(
        turns=[calling("unreported_workouts"), calling("unreported_workouts"), says("ok")]
    )

    graph_of(model, budget=1).invoke(entrance.heard("e adesso?"))

    assert "unreported_workouts" in model.bound[0]
    assert "unreported_workouts" not in model.bound[-1]
    assert entrance.PLAN_MESOCYCLE in model.bound[-1], "the subgraphs are not budgeted"


# -- saying what happened ------------------------------------------------------


def test_a_situation_is_said_in_the_models_own_words(
    connection: sqlite3.Connection,
) -> None:
    """The whole of ADR-0006: the machine names what happened and the sentence
    is the model's. A branch whose words are written in advance is the router
    this replaced."""
    model = Scripted(turns=[says("È tuo. Buon allenamento!")])

    final = graph_of(model).invoke(entrance.relayed(entrance.PRESCRIBED))

    assert final["answer"] == "È tuo. Buon allenamento!"
    assert entrance.PRESCRIBED in model.seen[-1][-1].text
    assert model.bound == [], "nothing to do but speak"


def test_saying_what_happened_is_a_run_that_ended(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    model = Scripted(turns=[says("fatto")])

    final = graph_of(model, archive=tmp_path).invoke(entrance.relayed(entrance.LOGGED))

    assert final["ending"] == records.DONE


@pytest.mark.parametrize("situation", entrance.SITUATIONS)
def test_every_situation_the_machine_can_name_reaches_the_model(
    situation: str, connection: sqlite3.Connection
) -> None:
    """Each of these was a fixed Italian line before ADR-0006. What must not
    come back is a situation nobody can say."""
    model = Scripted(turns=[says("detto")])

    final = graph_of(model).invoke(entrance.relayed(situation))

    assert final["answer"] == "detto"
    assert situation in model.seen[-1][-1].text


def test_the_situations_are_instructions_and_not_the_words_the_user_reads() -> None:
    """They are written in English, like every other prompt in this project,
    and the chat is in Italian. A situation that read like a finished sentence
    would be a constant reaching the user by another name."""
    for situation in entrance.SITUATIONS:
        assert situation.isascii(), situation


# -- the run record ------------------------------------------------------------


def test_every_node_of_the_entrance_names_the_model_that_answered_it(
    connection: sqlite3.Connection,
) -> None:
    """From ADR-0006 there is no one model per run: a planning run holds the
    entrance's nodes and the planner's, and the document has to say which
    answered which."""
    model = Scripted(turns=[says("ci sono")])

    final = graph_of(model).invoke(entrance.heard(CIAO))
    written = records.of(final, tools.CALL_BUDGET)

    assert {node["node"] for node in written["nodes"]} == {"entrance", "answer"}
    assert {node["model"] for node in written["nodes"]} == {FRONT}
    assert {node["provider"] for node in written["nodes"]} == {FRONT_PROVIDER}


def test_a_run_studio_started_still_has_an_identity(
    connection: sqlite3.Connection,
) -> None:
    """Studio opens a thread with the graph's own input and nothing else, and
    a run has to be readable back whichever door opened it."""
    model = Scripted(turns=[says("ok")])

    final = graph_of(model).invoke({"messages": [HumanMessage(CIAO)]})

    assert final["run"] and final["negotiation"]


# -- one definition of what a run is -------------------------------------------


GRAPHS = ("entrance.py", "planner.py", "logger.py")


def test_no_graph_keeps_its_own_copy_of_what_a_run_is() -> None:
    """`record` is the one definition: the identity a run is born with, and the
    wrapper that stamps who answered a node.

    Session 9 item 02 left three small copies of both -- a `starting`, a
    `timed` and a `turn` that mints an identity for a run Studio opened, once
    per graph. The entrance would have been the fourth of each, which is the
    point at which a second answer to *what is a run* stops being harmless.
    """
    for name in GRAPHS:
        source = (Path(records.__file__).parent / name).read_text(encoding="utf-8")
        assert "def timed(" not in source, name
        assert "records.timing(on)" in source, name
        assert "uuid4" not in source, name
        assert "records.born(state)" in source, name


def test_a_read_past_the_budget_is_not_run(connection: sqlite3.Connection) -> None:
    """`talk` stops offering the reads and this stops running them, which are
    not the same guarantee: a model that calls a tool it was not offered would
    otherwise spend the surface past its budget one turn at a time, with
    nothing but LangGraph's recursion limit to end the run."""
    model = Scripted(
        turns=[
            calling("unreported_workouts"),
            calling("unreported_workouts"),
            says("ok"),
        ]
    )

    final = graph_of(model, budget=1).invoke(entrance.heard("e adesso?"))

    assert final["spent"] == 1, "the second read ran anyway"
    answered = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert answered[-1].text == entrance.SPENT
    assert final["answer"] == "ok"



# -- a change and an adaptation (ADR-0008 item 6) ------------------------------


def test_a_constraint_for_today_reaches_an_adaptation(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[
            calling(entrance.ADAPT_TODAY, said="solo 30 minuti oggi", minutes=30),
            says("Lo adatto, arriva a momenti."),
        ]
    )

    final = graph_of(model, checking=lambda name, asked: None).invoke(
        entrance.heard("solo 30 minuti oggi")
    )

    assert final["handoff"] == entrance.ADAPT_TODAY
    assert final["asked"] == {"said": "solo 30 minuti oggi", "minutes": 30}
    assert final["ending"] == "", "the planner carries the run on"


def test_a_change_for_good_reaches_a_change(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[calling(entrance.CHANGE_MESOCYCLE, said="basta affondi"), says("Lo cambio.")]
    )

    final = graph_of(model, checking=lambda name, asked: None).invoke(
        entrance.heard("basta affondi")
    )

    assert final["handoff"] == entrance.CHANGE_MESOCYCLE
    assert final["asked"] == {"said": "basta affondi"}


def test_a_request_that_cannot_be_assembled_goes_back_to_the_model(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Nothing starts, and the model is told why, so it can call again or ask."""
    model = Scripted(
        turns=[
            calling(entrance.ADAPT_TODAY, said="niente manubri", without=["manubri"]),
            says("Che attrezzi hai oggi?"),
        ]
    )

    final = graph_of(
        model, archive=tmp_path, checking=lambda name, asked: "no such equipment"
    ).invoke(entrance.heard("niente manubri oggi"))

    assert final["handoff"] == ""
    told = [m.text for m in final["messages"] if isinstance(m, ToolMessage)]
    assert told == ["no such equipment"]
    assert entrance.ADAPT_TODAY in model.bound[1], "offered again, to call it right"
    assert final["ending"] == records.DONE


def test_the_prompt_tells_a_change_from_an_adaptation_and_asks_when_it_cannot() -> None:
    assert entrance.ADAPT_TODAY in entrance.TALKING
    assert entrance.CHANGE_MESOCYCLE in entrance.TALKING
    assert "cannot tell" in entrance.TALKING


@pytest.fixture()
def following(connection: sqlite3.Connection, declared_training: Path) -> int:
    """A mesocycle this catalog can serve, accepted."""
    declared_training.write_text(LEGS_AND_SHOULDERS, encoding="utf-8")

    def one(exercise_id: str) -> tuple[workouts.PrescribedBlock, ...]:
        return (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(duration.BlockItem(exercise_id=exercise_id, reps=5),),
                    rounds=3,
                    rest=120,
                ),
                reason="the lift of the day",
            ),
        )

    return mesocycles.record_mesocycle(
        connection,
        (one("Barbell_Squat"), one("Standing_Military_Press")),
        cycles=3,
        why="settle the loads",
        on="2026-09-22",
    )


def test_an_adaptation_the_engine_can_assemble_starts(following: int) -> None:
    assert entrance.startable(entrance.ADAPT_TODAY, {"said": "30 minuti", "minutes": 30}) is None
    assert entrance.startable(entrance.CHANGE_MESOCYCLE, {"said": "basta squat"}) is None


def test_equipment_misnamed_goes_back_with_what_the_catalog_calls_it(following: int) -> None:
    said = entrance.startable(
        entrance.ADAPT_TODAY, {"said": "niente bilanciere", "without": ["bilanciere"]}
    )

    assert said is not None and "bilanciere" in said and "barbell" in said


def test_with_no_mesocycle_there_is_nothing_to_adapt_or_change(
    connection: sqlite3.Connection,
) -> None:
    for handoff in (entrance.ADAPT_TODAY, entrance.CHANGE_MESOCYCLE):
        assert entrance.startable(handoff, {"said": "x"}) == entrance.NO_MESOCYCLE


def test_a_single_value_where_a_list_belongs_is_read_as_one_value(following: int) -> None:
    """Observed on llama3.1: `without: "elastici"`, which iterated is eight letters."""
    said = entrance.startable(
        entrance.ADAPT_TODAY, {"said": "niente bilanciere", "without": "bilanciere"}
    )

    assert said is not None and "'bilanciere'" in said


def test_an_adaptation_past_the_budget_is_not_started(connection: sqlite3.Connection) -> None:
    """Checked, it can be refused and called again, so the budget bounds it like a read."""
    model = Scripted(
        turns=[calling(entrance.ADAPT_TODAY, said="30 minuti", minutes=30), says("non posso")]
    )

    final = graph_of(model, budget=0, checking=lambda name, asked: None).invoke(
        entrance.heard("solo 30 minuti oggi")
    )

    assert final["handoff"] == ""
    told = [m.text for m in final["messages"] if isinstance(m, ToolMessage)]
    assert told == [entrance.SPENT]
