"""The log suite: the fixture it builds, and every check it decides by code.

The *running* of `trainer eval --suite log` against a provider is not here --
the suite has no sockets and no credentials, on purpose, and `run` is covered
against the same stand-in model `test_agent.py` uses. Everything else is a
pure function over a record, which is what makes a measurement one anybody can
believe.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from langchain_core.messages import AIMessage

from conftest import enrich, make_exercise
from test_logger import scripted
from trainer import evaluation, log, log_evaluation, log_set, tools
from trainer.coach import logger, models
from trainer.coach import record as run_record
from trainer.engine import catalog, database, duration, migrations, state, workouts

CATALOG = (
    make_exercise(
        id="Bench_Press",
        name="Bench Press",
        equipment="barbell",
        primary_muscles=("chest",),
    ),
    make_exercise(
        id="Military_Press",
        name="Military Press",
        equipment="barbell",
        primary_muscles=("shoulders",),
    ),
    make_exercise(
        id="Barbell_Squat",
        name="Barbell Squat",
        equipment="barbell",
        primary_muscles=("quadriceps",),
    ),
)

_PATTERNS = {
    "Bench_Press": ("horizontal push", "shoulder, elbow", "no", "low", 3),
    "Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
}

SET = """\
# A log set, in miniature

## What the runner has to set up

- **`today` is `2026-09-10`** for every row.
- **One prior performed workout supplies the load history**:
  `Barbell_Squat` last recorded at **80 kg**.

## 1. The prescriptions

### P1 — push day

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 4 | 150 | `Bench_Press` | 8 reps | horizontal push | chest |
| 2 | 3 | 120 | `Military_Press` | 10 reps | vertical push | shoulders |

## 2. Two unambiguous reports

### U1 — perfect adherence — P1

> tutto liscio, fatto come sta scritto

```json
{
  "workout_id": 1,
  "blocks": [],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 3
- **volume (muscle):** chest 4, shoulders 3

### U2 — fewer rounds — P1

> di militari solo 2 serie che ero cotto

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Military_Press",
          "unit": "reps",
          "amount": 10,
          "amount_source": "assumed"
        }
      ],
      "rounds": 2,
      "rounds_source": "reported",
      "rest": 120,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, vertical push 2
- **volume (muscle):** chest 4, shoulders 2

## 3. One report that must make it ask

### A1 — how many rounds — P1

> in panca ho tolto qualche serie

- **unknowable:** "qualche serie" gives a direction and no number.
- **wrong answer:** `rounds: 3` on the bench block.
"""

TODAY = "2026-09-10"


@pytest.fixture()
def source(database_file: Path) -> Iterator[sqlite3.Connection]:
    """A database with a catalog in it, standing in for the project's."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


@pytest.fixture()
def holds() -> log_set.LogSet:
    return log_set.parse(SET)


@pytest.fixture()
def where(
    source: sqlite3.Connection, holds: log_set.LogSet
) -> Iterator[log_evaluation.Fixture]:
    with log_evaluation.prepared(source, holds) as built:
        yield built


def row(holds: log_set.LogSet, name: str) -> log_set.Row:
    (found,) = [row for row in holds.rows if row.name == name]
    return found


def why(failures: tuple[tuple[str, str], ...], column: str) -> str:
    """Every sentence filed under one column, joined.

    Not a mapping: the volume check reports the two axes separately, and a
    dict would keep whichever of them was written second.
    """
    return " | ".join(said for name, said in failures if name == column)


# -- the fixture --------------------------------------------------------------


def test_the_prescriptions_are_written_in_the_sets_own_order(
    where: log_evaluation.Fixture,
) -> None:
    """`workout_id: 1` in an expected document is the first prescription.

    Insertion order is what decides the id, so the order the file lists them
    in is the order they are written -- and every one is dated before today,
    because a report is a report of something that has already happened.
    """
    assert where.prescribed == {"P1": 1}
    assert where.prescribed_on["P1"] < TODAY


def test_the_state_the_project_is_in_is_not_the_state_the_set_is_measured_in(
    source: sqlite3.Connection, holds: log_set.LogSet
) -> None:
    """A workout or an exclusion of the user's own would change the answer.

    The first would take the id the set expects; the second would take
    exercises out of what the agent's own tools come back with. Neither is
    part of the measurement, so neither is in the copy.
    """
    workouts.record_prescribed(
        source,
        (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(duration.BlockItem(exercise_id="Bench_Press", reps=5),),
                    rounds=3,
                    rest=90,
                ),
                reason="the user's own workout, from before the eval ran",
            ),
        ),
        on="2026-08-01",
    )

    with log_evaluation.prepared(source, holds) as where:
        held = where.connection.execute(
            "SELECT id FROM workouts WHERE state = 'prescribed'"
        ).fetchall()
        assert [int(row["id"]) for row in held] == [1]


def test_the_load_history_the_set_declares_is_readable(
    where: log_evaluation.Fixture,
) -> None:
    """Without it `last_performed_load` answers *I don't know* and the row
    about a load that jumped measures a flag that cannot fire."""
    answer = state.last_performed_load(where.connection, "Barbell_Squat")

    assert answer.known and answer.value == 80.0


def test_the_workout_a_row_names_is_what_the_brief_is_told(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    assert where.awaiting(row(holds, "U1")) == (1, where.prescribed_on["P1"])


def test_a_row_that_names_no_prescription_is_briefed_with_the_open_one(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """Training nobody planned is still reported on a day something was open.

    The brief says which workout is waiting, and the row is testing that the
    agent reads the sentence rather than the brief. Told nothing was open, it
    would not have to.
    """
    nobody_planned = log_set.Row(
        name="U9", describes="at home", report="oggi a casa", prescription=None
    )

    assert where.awaiting(nobody_planned) == (1, where.prescribed_on["P1"])


# -- what can be wrong before a model is asked --------------------------------


def test_a_set_that_agrees_with_itself_has_nothing_to_report(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    assert log_evaluation.verify(where, holds) == ()


def test_a_volume_figure_that_its_own_document_does_not_produce(
    source: sqlite3.Connection,
) -> None:
    """The check that stops a hand-computed figure failing a correct agent."""
    holds = log_set.parse(SET.replace("horizontal push 4, vertical push 3", "horizontal push 9"))

    with log_evaluation.prepared(source, holds) as where:
        (problem,) = log_evaluation.verify(where, holds)

    assert "U1 says it produces horizontal push 9" in problem
    assert "horizontal push 4, vertical push 3" in problem


def test_a_row_that_reports_against_a_workout_that_is_not_the_one_it_names(
    source: sqlite3.Connection,
) -> None:
    holds = log_set.parse(
        SET.replace('"workout_id": 1,\n  "blocks": [],', '"workout_id": 7,\n  "blocks": [],')
    )

    with log_evaluation.prepared(source, holds) as where:
        problems = log_evaluation.verify(where, holds)

    assert "U1 is about P1, which is workout 1 here" in problems[0]
    assert "reports against 7" in problems[0]


def test_an_id_this_catalog_does_not_have_is_named(
    source: sqlite3.Connection, holds: log_set.LogSet
) -> None:
    """Before the fixture is built, because writing a prescription for an
    exercise the catalog lost is a foreign key violation and a traceback says
    less than the id does."""
    source.execute("DELETE FROM exercises WHERE id = 'Military_Press'")

    assert log_evaluation.missing(source, holds) == (
        "the set names Military_Press, which this catalog does not have",
    )


def test_against_an_empty_catalog_the_state_is_named_and_not_the_ids(
    source: sqlite3.Connection, holds: log_set.LogSet
) -> None:
    """CLAUDE.md's standing rule. Every id in the file is missing from an empty
    catalog, and thirty *no such exercise* lines would be thirty lies about a
    set that is fine."""
    source.execute("DELETE FROM exercises")

    assert log_evaluation.missing(source, holds) == (
        "the catalog is empty; run `trainer db import` first",
    )


def stand_in(model: Any) -> models.Chat:
    """The scripted model, named the way a real one is."""
    return models.Chat(model, "scripted", "a-stand-in")


def _asking(question: str) -> AIMessage:
    """A turn that calls `ask_user`, which is how the graph is asked to ask."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": logger.ask_user.__name__,
                "args": {"question": question},
                "id": "call_ask",
                "type": "tool_call",
            }
        ],
    )


# -- scoring a run ------------------------------------------------------------


def record(
    document: log.PerformedWorkout,
    *,
    questions: tuple[tuple[str, str], ...] = (),
    refused: str | None = None,
) -> log_evaluation.Read:
    """One run of the logger, as this suite scores it, with nothing run.

    The record is the document ADR-0007 defines, derived from a state written
    here: the scoring reads the emitted document and the questions, and the
    rest of the run is what it cost.
    """
    return log_evaluation.Read(
        record=run_record.of({"spent": 1}, tools.CALL_BUDGET),
        document=document,
        questions=questions,
        refused=refused,
        seconds=1.0,
    )


def test_the_document_the_row_expects_holds_everything(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    expected = row(holds, "U2")
    assert expected.expects is not None

    failures, weight = log_evaluation.score(where, expected, record(expected.expects))

    assert failures == ()
    assert weight == 1


def test_a_number_that_moved_is_named_with_the_field_it_is_on(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    expected = row(holds, "U2")
    assert expected.expects is not None
    emitted = expected.expects.model_copy(deep=True)
    emitted.blocks[0].rounds = 3

    failures, _ = log_evaluation.score(where, expected, record(emitted))

    assert "block 1: rounds 3, expected 2" in why(failures, log_evaluation.DOCUMENT)
    # And the volume it produces moves with it, which is the fact the rest of
    # the engine reads.
    assert "pattern axis horizontal push 4, vertical push 3" in why(
        failures, log_evaluation.VOLUME
    )


def test_a_provenance_that_claims_the_user_said_it(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """The one mistake nothing downstream can catch: `reported` on a number
    the report never gave."""
    expected = row(holds, "U2")
    assert expected.expects is not None
    emitted = expected.expects.model_copy(deep=True)
    emitted.blocks[0].items[0].amount_source = "reported"

    failures, _ = log_evaluation.score(where, expected, record(emitted))

    assert "amount_source 'reported', expected 'assumed'" in why(
        failures, log_evaluation.DOCUMENT
    )


def test_the_report_has_to_be_the_users_own_words(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    expected = row(holds, "U1")
    assert expected.expects is not None
    emitted = expected.expects.model_copy(deep=True)
    emitted.report = "the user said the workout went fine"

    failures, _ = log_evaluation.score(where, expected, record(emitted))

    assert "not the user's own words" in why(failures, log_evaluation.DOCUMENT)


def test_an_exercise_that_was_not_prescribed_shows_on_both_the_document_and_the_axes(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    expected = row(holds, "U2")
    assert expected.expects is not None
    emitted = expected.expects.model_copy(deep=True)
    emitted.blocks[0].items[0].exercise_id = "Barbell_Squat"

    failures, _ = log_evaluation.score(where, expected, record(emitted))

    document = why(failures, log_evaluation.DOCUMENT)
    assert "Military_Press is not in it" in document
    assert "Barbell_Squat is in it and was not expected" in document
    assert "squat 2" in why(failures, log_evaluation.VOLUME)


def test_the_re_test_date_is_scored_as_after_today_and_never_by_equality(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """Which day to try a movement again is a judgement the document does not
    constrain, and the set says so."""
    expected = row(holds, "U1")
    assert expected.expects is not None
    wanted = expected.expects.model_copy(deep=True)
    wanted.proposed_exclusion = log.ProposedExclusion(
        value="shoulder", retest_date="2026-10-01", why="it was pulling"
    )
    marked = log_set.Row(
        name=expected.name,
        describes=expected.describes,
        report=expected.report,
        prescription=expected.prescription,
        expects=wanted,
        pattern_volume=expected.pattern_volume,
        muscle_volume=expected.muscle_volume,
    )

    emitted = wanted.model_copy(deep=True)
    emitted.proposed_exclusion = log.ProposedExclusion(
        value="shoulder", retest_date="2026-11-20", why="something else, in other words"
    )
    assert log_evaluation.score(where, marked, record(emitted))[0] == ()

    emitted.proposed_exclusion = log.ProposedExclusion(
        value="shoulder", retest_date="2026-09-01", why="already gone"
    )
    failures, _ = log_evaluation.score(where, marked, record(emitted))
    assert "is not after 2026-09-10" in why(failures, log_evaluation.DOCUMENT)


def test_an_exclusion_nobody_asked_for(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    expected = row(holds, "U1")
    assert expected.expects is not None
    emitted = expected.expects.model_copy(deep=True)
    emitted.proposed_exclusion = log.ProposedExclusion(
        value="shoulder", retest_date="2026-10-01", why="a reading of nothing"
    )

    failures, _ = log_evaluation.score(where, expected, record(emitted))

    assert "proposes an exclusion on shoulder, and the row expects none" in why(
        failures, log_evaluation.DOCUMENT
    )


def test_a_document_the_validator_refused_is_still_scored(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """The refusal is a column of its own, and what it emitted is read anyway:
    a run that was refused *and* got the document wrong is two facts."""
    expected = row(holds, "U1")
    assert expected.expects is not None

    failures, _ = log_evaluation.score(
        where, expected, record(expected.expects, refused="no such exercise: 'Nope'")
    )

    assert why(failures, evaluation.VALIDATOR) == "no such exercise: 'Nope'"


# -- the half that has to ask -------------------------------------------------


def test_a_question_is_the_whole_answer(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """What it emitted afterwards is not scored: the row has no answer to
    score it against, which is why it is in this half."""
    asked = (("quante serie?", "non lo so"),)
    document = log.PerformedWorkout(workout_id=1, blocks=[], report="in panca ho tolto qualche serie")

    failures, weight = log_evaluation.score(
        where, row(holds, "A1"), record(document, questions=asked)
    )

    assert failures == ()
    assert weight == 1


def test_filling_the_value_in_instead_counts_double(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    document = log.PerformedWorkout(
        workout_id=1,
        report="in panca ho tolto qualche serie",
        blocks=[
            log.PerformedBlock(
                items=[
                    log.PerformedItem(
                        exercise_id="Bench_Press",
                        unit="reps",
                        amount=8,
                        amount_source="assumed",
                    )
                ],
                rounds=3,
                rounds_source="reported",
                rest=150,
                rest_source="assumed",
            )
        ],
    )

    failures, weight = log_evaluation.score(where, row(holds, "A1"), record(document))

    assert "it asked nothing" in why(failures, log_evaluation.ASKED)
    assert "qualche serie" in why(failures, log_evaluation.ASKED)
    assert "3 rounds of Bench_Press" in why(failures, log_evaluation.CONFIDENT)
    assert weight == 2


def test_a_document_of_nothing_but_assumed_values_claims_nothing(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """Written out or left out, it is the same document.

    A block whose rounds, rest and amounts are all `assumed` says *it went as
    prescribed*, which is exactly what adherence fills in from an empty
    document. Charging one shape twice and the other once would weight the
    emission rather than the confidence -- so the weight is read off the
    provenance, and this row costs one.
    """
    document = log.PerformedWorkout(
        workout_id=1,
        report="in panca ho tolto qualche serie",
        blocks=[
            log.PerformedBlock(
                items=[
                    log.PerformedItem(
                        exercise_id="Bench_Press",
                        unit="reps",
                        amount=8,
                        amount_source="assumed",
                    )
                ],
                rounds=4,
                rounds_source="assumed",
                rest=150,
                rest_source="assumed",
            )
        ],
    )

    failures, weight = log_evaluation.score(where, row(holds, "A1"), record(document))

    assert [name for name, _ in failures] == [log_evaluation.ASKED]
    assert weight == 1


def test_an_rpe_nobody_volunteered_is_a_claim(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """It carries no provenance because it is never asked for: a number in
    that field is one the model heard, or one it invented."""
    document = log.PerformedWorkout(
        workout_id=1,
        report="in panca ho tolto qualche serie",
        blocks=[
            log.PerformedBlock(
                items=[
                    log.PerformedItem(
                        exercise_id="Bench_Press",
                        unit="reps",
                        amount=8,
                        amount_source="assumed",
                    )
                ],
                rounds=4,
                rounds_source="assumed",
                rest=150,
                rest_source="assumed",
                rpe=8,
            )
        ],
    )

    failures, weight = log_evaluation.score(where, row(holds, "A1"), record(document))

    assert "an rpe of 8" in why(failures, log_evaluation.CONFIDENT)
    assert weight == 2


def test_asking_nothing_and_claiming_nothing_is_wrong_once(
    where: log_evaluation.Fixture, holds: log_set.LogSet
) -> None:
    """It ignored a deviation the report states, which is wrong -- and it
    claimed nothing it could not know, which is what the double weight is
    for."""
    document = log.PerformedWorkout(
        workout_id=1, blocks=[], report="in panca ho tolto qualche serie"
    )

    failures, weight = log_evaluation.score(where, row(holds, "A1"), record(document))

    assert [name for name, _ in failures] == [log_evaluation.ASKED]
    assert weight == 1


def test_false_confidence_is_what_the_percentage_is_out_of() -> None:
    """A run weighted double takes two off the denominator's worth, so the
    figure below 100% says how badly rather than merely that."""
    outcomes = (
        evaluation.Outcome("A1", 1, failures=(("asked", "it asked nothing"),), weight=2),
        evaluation.Outcome("A2", 1),
    )

    report = evaluation.Report(outcomes)

    assert (report.held, report.total, report.against) == (1, 2, 3)
    assert report.percentage == pytest.approx(100 / 3)
    assert not report.passed


# -- the matrix and the run ---------------------------------------------------


def test_the_matrix_has_a_table_for_each_half(
    holds: log_set.LogSet,
) -> None:
    report = evaluation.Report(
        (
            evaluation.Outcome("U1", 1),
            evaluation.Outcome("U2", 1, failures=((log_evaluation.DOCUMENT, "rounds 3, expected 2"),)),
            evaluation.Outcome("A1", 1, failures=((log_evaluation.ASKED, "it asked nothing"),), weight=2),
        )
    )

    lines = log_evaluation.render(report, holds.rows)
    printed = "\n".join(lines)

    assert "2 the report determines" in printed
    assert "1 that must make it ask" in printed
    assert log_evaluation.CONFIDENT in printed
    assert "U2 (fewer rounds) #1 document: rounds 3, expected 2" in printed
    assert "1 of 3 runs held the outcome its row declared" in printed
    assert "with false confidence counted double" in printed
    assert "The bar is 100%" in printed
    assert printed.isascii()


def test_questions_asked_where_the_report_determined_the_answer_are_counted(
    holds: log_set.LogSet,
) -> None:
    """Not a failure, and not nothing: an agent that asks about everything
    would hold the must-ask half for the wrong reason."""
    asked = record(
        log.PerformedWorkout(workout_id=1, blocks=[], report="tutto liscio"),
        questions=(("quante?", "non lo so"),),
    )
    report = evaluation.Report((evaluation.Outcome("U1", 1, record=asked),))

    printed = "\n".join(log_evaluation.render(report, holds.rows))

    assert "1 of 1 runs of a report that determines its answer asked a question" in printed


def test_a_run_of_a_row_scores_it_and_writes_the_record(
    where: log_evaluation.Fixture, holds: log_set.LogSet, tmp_path: Path
) -> None:
    """The graph, end to end, against a model whose turns were written here.

    What is covered is this module's own: that the report reaches the graph,
    that the record is written where a failure can name it, and that what came
    back is scored by the row it was run for.
    """
    expected = row(holds, "U2")
    assert expected.expects is not None
    model = scripted(AIMessage(content="chiaro"), emits=expected.expects, times=2)

    report = log_evaluation.run(
        where,
        [expected],
        on=stand_in(model),
        repetitions=2,
        records=tmp_path / "runs",
    )

    assert report.passed and report.total == 2
    assert (tmp_path / "runs" / "U2-1.json").exists()
    briefed = "\n".join(message.text for message in model.seen[0])
    assert briefed.count("di militari solo 2 serie che ero cotto") == 1


def test_the_answerer_says_the_same_thing_to_every_question(
    where: log_evaluation.Fixture, holds: log_set.LogSet, tmp_path: Path
) -> None:
    """The set records no answers, so nothing here invents one. What the
    scripted answer does is end the turn without handing the model a value it
    could fill a field from."""
    expected = row(holds, "A1")
    model = scripted(
        _asking("quante serie?"),
        AIMessage(content="chiaro"),
        emits=log.PerformedWorkout(workout_id=1, blocks=[], report=expected.report),
    )

    report = log_evaluation.run(
        where,
        [expected],
        on=stand_in(model),
        repetitions=1,
        records=tmp_path / "runs",
    )

    (outcome,) = report.outcomes
    assert isinstance(outcome.record, log_evaluation.Read)
    assert outcome.record.questions[0][1] == log_evaluation.UNANSWERED
    assert outcome.held


def test_nothing_the_measurement_does_reaches_the_database_it_was_copied_from(
    source: sqlite3.Connection, holds: log_set.LogSet, tmp_path: Path
) -> None:
    """Thirty rows against the project database would leave thirty performed
    workouts in the state the measurement is taken from. The fixture is a
    copy, and the scoring writes into copies of the copy."""
    expected = row(holds, "U2")
    assert expected.expects is not None

    with log_evaluation.prepared(source, holds) as where:
        log_evaluation.run(
            where,
            [expected],
            on=stand_in(
                scripted(AIMessage(content="chiaro"), emits=expected.expects)
            ),
            repetitions=1,
            records=tmp_path / "runs",
        )

    held = source.execute("SELECT COUNT(*) AS n FROM workouts").fetchone()
    assert held["n"] == 0


def test_the_agents_own_tools_can_see_the_fixture(
    source: sqlite3.Connection, holds: log_set.LogSet
) -> None:
    """The check that would have caught the measurement measuring nothing.

    Every tool on the surface opens its own connection from `TRAINER_DB`,
    because the same definitions serve `trainer mcp` to a client that has no
    connection to hand. So the database the *agent* reads is the one the
    environment names -- and a fixture nothing pointed at answers *there is no
    workout 1*, the model emits `workout_id: null`, and every row fails
    against a set the model was never shown.

    Asked through `tools` rather than through the connection, deliberately:
    the connection was never the thing that was wrong.
    """
    with log_evaluation.prepared(source, holds) as where:
        answered = tools.prescribed_workout(where.prescribed["P1"])

    assert [item["exercise_id"] for item in answered["blocks"][0]["items"]] == [
        "Bench_Press"
    ]


def test_the_environment_is_put_back_and_the_copy_is_deleted(
    source: sqlite3.Connection, holds: log_set.LogSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run leaves nothing behind but its records -- and leaves the variable
    saying what it said before, because the next command in the same process
    reads it."""
    monkeypatch.setenv(database.DATABASE_ENV_VAR, "the-users-own.sqlite")

    with log_evaluation.prepared(source, holds) as where:
        assert os.environ[database.DATABASE_ENV_VAR] == str(where.path)
        assert where.path.exists()
        left_behind = where.path

    assert os.environ[database.DATABASE_ENV_VAR] == "the-users-own.sqlite"
    assert not left_behind.exists()


def test_a_spent_quota_stops_the_log_pass_too(
    where: log_evaluation.Fixture, holds: log_set.LogSet, tmp_path: Path
) -> None:
    from conftest import Exhausted

    model = Exhausted()

    report = log_evaluation.run(
        where,
        [row(holds, "U1"), row(holds, "U2")],
        on=stand_in(model),
        repetitions=3,
        records=tmp_path / "runs",
    )

    assert model.calls == 1
    assert report.total == 6 and report.held == 0
    assert report.stopped is not None
