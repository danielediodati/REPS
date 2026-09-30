"""The onboarding interview, against a scripted chat model."""

from __future__ import annotations

import sqlite3
import tomllib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from conftest import enrich
from test_planner import CATALOG, PATTERNS, Scripted, mesocycle_of, plan_of
from trainer import plan as plans
from trainer import tools
from trainer.coach import checkpoints, conclusions, logger, models, onboarding
from trainer.engine import catalog, config, database, exclusions, mesocycles, migrations, workouts

TODAY = "2026-09-30"
THREAD: RunnableConfig = {"configurable": {"thread_id": "chat:1/onboard", conclusions.USER: "chat:1"}}

EVERYTHING = {
    "cycle_length": 2,
    "duration_cap_min": 45,
    "split": [["legs"], ["shoulders"]],
    "equipment": ["barbell"],
    "goal": "hypertrophy",
}


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


def graph_of(model: Scripted, **built: Any) -> onboarding.Onboarding:
    built.setdefault("checkpointer", InMemorySaver())
    return onboarding.build(models.Chat(model, "scripted", "a-stand-in"), **built)


def says(line: str) -> AIMessage:
    return AIMessage(content=line)


def calls(*made: tuple[str, dict[str, Any]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{n}", "type": "tool_call"}
            for n, (name, args) in enumerate(made)
        ],
    )


def begin(graph: onboarding.Onboarding, connection: sqlite3.Connection) -> dict[str, Any]:
    started = onboarding.starting("voglio impostare l'allenamento", TODAY, onboarding.vocabulary(connection))
    return dict(graph.invoke(started, THREAD))


def answer(graph: onboarding.Onboarding, reply: Any) -> dict[str, Any]:
    return dict(graph.invoke(Command(resume=reply), THREAD))


def asked(final: dict[str, Any]) -> dict[str, Any]:
    return dict(final["__interrupt__"][0].value)


def answers_to(model: Scripted, name: str) -> list[ToolMessage]:
    """What the model was told about each call to `name`, in the order it was told."""
    last = model.seen[-1]
    return [m for m in last if isinstance(m, ToolMessage) and m.name == name]


def test_the_models_message_is_the_question_and_the_interview_waits_on_it(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[says("Per cosa ti alleni?")])

    final = begin(graph_of(model), connection)

    assert asked(final) == {"kind": logger.CLARIFY, "ask": "Per cosa ti alleni?"}


def test_the_prompt_spells_the_declarations_in_the_datas_words(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[says("Per cosa ti alleni?")])

    begin(graph_of(model), connection)

    prompt = model.seen[0][0].text
    assert "vertical push" in prompt and "barbell" in prompt and "hypertrophy" in prompt


def test_a_scripted_conversation_writes_the_version_in_force(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            says("Per cosa ti alleni?"),
            calls((onboarding.DECLARE, {"goal": "hypertrophy"})),
            says("Quanti allenamenti diversi, e cosa alleni in ciascuno?"),
            calls((onboarding.DECLARE, {"cycle_length": 2, "split": [["legs"], ["shoulders"]]})),
            says("Che attrezzi hai e quanto tempo?"),
            calls(
                (onboarding.DECLARE, {"equipment": ["barbell"], "duration_cap_min": 45}),
                (onboarding.FINISH, {}),
            ),
        ]
    )
    graph = graph_of(model)
    begin(graph, connection)
    answer(graph, "massa")
    answer(graph, "due: gambe e spalle")
    final = answer(graph, "bilanciere, 45 minuti")

    assert final["finished"] and "__interrupt__" not in final
    onboarding.written(final)
    read = config.load(connection)
    assert read.cycle_length == 2
    assert read.duration_cap_min == 45
    assert read.split == (("legs",), ("shoulders",))
    assert read.volume_denominator == "cycle"
    assert read.equipment == ("barbell",)
    assert read.goal == "hypertrophy"


def test_an_answer_covering_equipment_and_minutes_leaves_neither_to_settle(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            says("Che attrezzi hai e quanto tempo?"),
            calls((onboarding.DECLARE, {"equipment": ["barbell"], "duration_cap_min": 45})),
            says("Per cosa ti alleni?"),
        ]
    )
    graph = graph_of(model)
    begin(graph, connection)

    final = answer(graph, "ho un bilanciere e 45 minuti")

    (told,) = answers_to(model, onboarding.DECLARE)
    assert "equipment" not in told.text and "duration_cap_min" not in told.text
    assert "goal" in told.text and "split" in told.text
    assert final["declared"] == {"equipment": ["barbell"], "duration_cap_min": 45}


def test_finishing_with_the_goal_missing_is_sent_back(
    connection: sqlite3.Connection,
) -> None:
    missing_goal = {key: value for key, value in EVERYTHING.items() if key != "goal"}
    model = Scripted(
        turns=[
            calls((onboarding.DECLARE, missing_goal), (onboarding.FINISH, {})),
            says("E per cosa ti alleni?"),
        ]
    )

    final = begin(graph_of(model), connection)

    (told,) = answers_to(model, onboarding.FINISH)
    assert told.status == "error" and "goal" in told.text
    assert not final["finished"]
    assert asked(final)["ask"] == "E per cosa ti alleni?"


def test_a_declaration_config_refuses_is_sent_back_with_its_reason(
    connection: sqlite3.Connection,
) -> None:
    short_split = EVERYTHING | {"split": [["legs"]]}
    model = Scripted(
        turns=[
            calls((onboarding.DECLARE, short_split), (onboarding.FINISH, {})),
            says("Cosa alleni il secondo giorno?"),
        ]
    )

    begin(graph_of(model), connection)

    (told,) = answers_to(model, onboarding.FINISH)
    assert told.status == "error" and "split" in told.text


def test_equipment_the_catalog_does_not_have_is_sent_back_with_what_it_has(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calls(
                (onboarding.DECLARE, EVERYTHING | {"equipment": ["kettlebell magica"]}),
                (onboarding.FINISH, {}),
            ),
            says("Che attrezzi hai, esattamente?"),
        ]
    )

    begin(graph_of(model), connection)

    (told,) = answers_to(model, onboarding.FINISH)
    assert told.status == "error" and "kettlebell magica" in told.text and "barbell" in told.text


def test_stopped_mid_way_the_next_process_resumes_where_it_was(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "checkpoints.sqlite"
    with checkpoints.saver(path) as saver:
        begin(graph_of(Scripted(turns=[says("Per cosa ti alleni?")]), checkpointer=saver), connection)

    later = Scripted(turns=[says("E quanti allenamenti a rotazione?")])
    with checkpoints.saver(path) as saver:
        final = answer(graph_of(later, checkpointer=saver), "massa")

    assert asked(final)["ask"] == "E quanti allenamenti a rotazione?"
    history = [m.text for m in later.seen[0]]
    assert "Per cosa ti alleni?" in history and "massa" in history


def proposing(value: str = "vertical push") -> Scripted:
    return Scripted(
        turns=[
            calls(
                (
                    onboarding.PROPOSE_EXCLUSION,
                    {"value": value, "retest_date": "2026-11-30", "why": "la spalla ti tira"},
                )
            ),
            calls((onboarding.DECLARE, EVERYTHING), (onboarding.FINISH, {})),
        ]
    )


def test_a_proposed_exclusion_is_put_to_the_user_classified(
    connection: sqlite3.Connection,
) -> None:
    final = begin(graph_of(proposing()), connection)

    assert asked(final) == {
        "kind": logger.EXCLUSION,
        "ask": "la spalla ti tira",
        "granularity": "pattern",
        "value": "vertical push",
        "retest_date": "2026-11-30",
    }


def test_a_confirmed_exclusion_is_written_and_a_declined_one_is_not(
    connection: sqlite3.Connection,
) -> None:
    graph = graph_of(proposing())
    begin(graph, connection)
    confirmed = answer(graph, True)
    onboarding.written(confirmed)

    assert exclusions.active(connection, TODAY) == (exclusions.Exclusion("pattern", "vertical push"),)

    connection.execute("DELETE FROM exclusions")
    graph = graph_of(proposing())
    begin(graph, connection)
    declined = answer(graph, False)
    onboarding.written(declined)

    assert exclusions.active(connection, TODAY) == ()


def test_an_exclusion_answered_in_words_writes_nothing_and_says_so(
    connection: sqlite3.Connection,
) -> None:
    model = proposing()
    graph = graph_of(model)
    begin(graph, connection)

    final = answer(graph, "dipende, solo col bilanciere")

    assert final["exclusions"] == []
    assert "dipende, solo col bilanciere" in final["said"]


def test_an_exercise_is_not_an_exclusion_and_the_catalogs_words_come_back(
    connection: sqlite3.Connection,
) -> None:
    model = proposing("Barbell_Squat")

    final = begin(graph_of(model), connection)

    (told,) = answers_to(model, onboarding.PROPOSE_EXCLUSION)
    assert told.status == "error" and "vertical push" in told.text
    assert final["finished"]


def test_a_retest_date_that_is_not_after_today_is_sent_back(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calls(
                (
                    onboarding.PROPOSE_EXCLUSION,
                    {"value": "squat", "retest_date": TODAY, "why": "il ginocchio"},
                )
            ),
            says("Quando vuoi riprovare?"),
        ]
    )

    begin(graph_of(model), connection)

    (told,) = answers_to(model, onboarding.PROPOSE_EXCLUSION)
    assert told.status == "error" and TODAY in told.text


def test_a_sentence_the_user_wrote_in_the_interview_is_remembered(
    connection: sqlite3.Connection,
) -> None:
    store = InMemoryStore()
    model = Scripted(
        turns=[
            says("C'è qualcosa che non ti piace fare?"),
            calls(
                (
                    conclusions.REMEMBER,
                    {"conclusion": "Non ama le distensioni.", "quote": "odio le distensioni"},
                )
            ),
            says("Capito. Per cosa ti alleni?"),
        ]
    )
    graph = graph_of(model, store=store)
    begin(graph, connection)

    answer(graph, "Odio le distensioni, sempre.")

    (kept,) = conclusions.live(store, "chat:1")
    assert kept.quote == "odio le distensioni"


def test_remember_is_offered_only_with_a_store(connection: sqlite3.Connection) -> None:
    model = Scripted(turns=[says("Ciao!")])

    begin(graph_of(model), connection)

    assert conclusions.REMEMBER not in model.bound[0]
    assert onboarding.FINISH in model.bound[0]


def test_past_the_budget_only_finish_is_offered_until_they_answer(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calls((onboarding.DECLARE, {"goal": "hypertrophy"})),
            calls((onboarding.DECLARE, {"goal": "hypertrophy"})),
            says("Quanti allenamenti?"),
            says("E quanto tempo?"),
        ]
    )
    graph = graph_of(model, budget=2)
    begin(graph, connection)
    answer(graph, "tre")

    assert model.bound[2] == [onboarding.FINISH]
    assert onboarding.DECLARE in model.bound[3]


def test_starting_again_forgets_the_last_interview(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[
            calls((onboarding.DECLARE, {"goal": "hypertrophy"})),
            says("Quanti allenamenti?"),
            says("Da capo: per cosa ti alleni?"),
        ]
    )
    graph = graph_of(model)
    begin(graph, connection)

    final = begin(graph, connection)

    assert final["declared"] == {}
    assert len(model.seen[-1]) == 2, "the system prompt and the message that asked"


# -- a declaration changed (ADR-0012) --------------------------------------------

DECLARED = """\
cycle_length = 2
duration_cap_min = 45
volume_denominator = "cycle"
split = [["legs"], ["shoulders"]]
equipment = ["barbell"]
goal = "hypertrophy"
"""
"""`EVERYTHING`, as TOML."""


def kept(connection: sqlite3.Connection, mesocycle: plans.Mesocycle) -> None:
    """The mesocycle accepted, so it is the one running."""
    mesocycles.record_mesocycle(
        connection,
        tuple(
            tuple(
                workouts.PrescribedBlock(block=block, reason=shape.reason)
                for shape, block in zip(workout.blocks, plans.to_blocks(workout), strict=True)
            )
            for workout in mesocycle.workouts
        ),
        cycles=mesocycle.cycles,
        why=mesocycle.why,
        on=TODAY,
    )


@pytest.fixture()
def running(connection: sqlite3.Connection, declared_training: Path) -> sqlite3.Connection:
    """`EVERYTHING` declared, and a mesocycle legal under it running."""
    declared_training.write_text(DECLARED, encoding="utf-8")
    config.load(connection)
    kept(connection, mesocycle_of(plan_of("Barbell_Squat"), plan_of("Standing_Military_Press")))
    return connection


def after(**changed: Any) -> config.TrainingConfig:
    return onboarding.settled(EVERYTHING | changed)


def test_a_mesocycle_still_legal_can_be_kept_rewritten_or_replaced(
    running: sqlite3.Connection,
) -> None:
    paths = onboarding.open_paths(running, TODAY, EVERYTHING, after(equipment=["barbell", "dumbbell"]))

    assert paths == (onboarding.KEEP, onboarding.REWRITE, onboarding.NEW_NOW)


def test_equipment_the_mesocycle_uses_taken_away_is_never_kept(
    running: sqlite3.Connection,
) -> None:
    paths = onboarding.open_paths(running, TODAY, EVERYTHING, after(equipment=["dumbbell"]))

    assert onboarding.KEEP not in paths
    assert paths == (onboarding.REWRITE, onboarding.NEW_NOW)


def test_a_changed_goal_is_never_rewritten(running: sqlite3.Connection) -> None:
    paths = onboarding.open_paths(running, TODAY, EVERYTHING, after(goal="strength"))

    assert onboarding.REWRITE not in paths
    assert paths == (onboarding.NEW_NOW, onboarding.KEEP)


def test_a_longer_cap_makes_the_running_mesocycle_too_short_to_keep(
    running: sqlite3.Connection,
) -> None:
    paths = onboarding.open_paths(running, TODAY, EVERYTHING, after(duration_cap_min=90))

    assert onboarding.KEEP not in paths


def test_a_rotation_of_another_length_is_not_rewritten_slot_by_slot(
    running: sqlite3.Connection,
) -> None:
    paths = onboarding.open_paths(
        running, TODAY, EVERYTHING, after(cycle_length=1, split=[["legs", "shoulders"]])
    )

    assert paths == (onboarding.NEW_NOW,)


def test_with_no_mesocycle_running_there_is_nothing_to_choose(
    connection: sqlite3.Connection,
) -> None:
    assert onboarding.open_paths(connection, TODAY, EVERYTHING, after(equipment=["dumbbell"])) == ()


def change(graph: onboarding.Onboarding, said: str) -> dict[str, Any]:
    with tools.opened() as connection:
        words = onboarding.vocabulary(connection)
    started = onboarding.changing(said, TODAY, words, EVERYTHING)
    return dict(graph.invoke(started, THREAD))


def test_a_change_starts_from_what_is_declared_and_the_prompt_quotes_it(
    running: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[says("Quale bilanciere?")])

    final = change(graph_of(model), "ho comprato dei manubri")

    assert final["declared"] == EVERYTHING
    prompt = model.seen[0][0].text
    assert "ho comprato dei manubri" in model.seen[0][1].text
    assert '"hypertrophy"' in prompt and onboarding.CHOOSE in prompt


def test_finishing_a_change_lists_the_paths_open_and_ends_nothing(
    running: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calls((onboarding.DECLARE, {"equipment": ["dumbbell"]}), (onboarding.FINISH, {})),
            says("Riscrivo il mesociclo?"),
        ]
    )

    final = change(graph_of(model), "ho venduto il bilanciere")

    (told,) = answers_to(model, onboarding.FINISH)
    assert onboarding.REWRITE in told.text and onboarding.KEEP not in told.text
    assert not final["finished"]


def test_a_path_that_is_not_open_is_refused(running: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[
            calls(
                (onboarding.DECLARE, {"equipment": ["dumbbell"]}),
                (onboarding.CHOOSE, {"path": onboarding.KEEP, "why": "va bene così"}),
            ),
            says("Allora?"),
        ]
    )

    final = change(graph_of(model), "ho venduto il bilanciere")

    (told,) = answers_to(model, onboarding.CHOOSE)
    assert told.status == "error" and onboarding.REWRITE in told.text
    assert not final["finished"]


def test_an_open_path_chosen_ends_the_change_with_why(running: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[
            calls(
                (onboarding.DECLARE, {"equipment": ["dumbbell"]}),
                (onboarding.CHOOSE, {"path": onboarding.REWRITE, "why": "senza bilanciere va rifatto"}),
            ),
        ]
    )

    final = change(graph_of(model), "ho venduto il bilanciere")

    assert final["finished"]
    assert (final["chosen"], final["why"]) == (onboarding.REWRITE, "senza bilanciere va rifatto")


def test_past_the_budget_a_change_can_still_choose_its_path(
    running: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calls((onboarding.DECLARE, {"equipment": ["dumbbell"]})),
            calls((onboarding.FINISH, {})),
            calls((onboarding.CHOOSE, {"path": onboarding.REWRITE, "why": "va rifatto"})),
        ]
    )

    final = change(graph_of(model, budget=2), "ho venduto il bilanciere")

    assert model.bound[2] == [onboarding.FINISH, onboarding.CHOOSE]
    assert final["finished"] and final["chosen"] == onboarding.REWRITE


def test_a_change_that_changes_nothing_is_sent_back(running: sqlite3.Connection) -> None:
    model = Scripted(turns=[calls((onboarding.FINISH, {})), says("Cosa è cambiato?")])

    change(graph_of(model), "ho sempre il bilanciere")

    (told,) = answers_to(model, onboarding.FINISH)
    assert told.status == "error"


def test_with_no_mesocycle_running_a_change_finishes_without_a_choice(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[calls((onboarding.DECLARE, {"equipment": ["dumbbell"]}), (onboarding.FINISH, {}))]
    )

    final = change(graph_of(model), "ho venduto il bilanciere")

    assert final["finished"] and final["chosen"] == ""


def test_a_change_written_is_a_new_version_and_the_old_one_stays(
    running: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            calls(
                (onboarding.DECLARE, {"equipment": ["barbell", "dumbbell"]}),
                (onboarding.CHOOSE, {"path": onboarding.KEEP, "why": "resta valido"}),
            ),
        ]
    )
    final = change(graph_of(model), "ho comprato dei manubri")

    onboarding.written(final)

    newest, older = config.versions(running)
    assert newest.declaration == after(equipment=["barbell", "dumbbell"])
    assert older.declaration == onboarding.settled(EVERYTHING)
