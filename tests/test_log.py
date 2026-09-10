"""The performed workout as a document: the shape, the little it is refused
for, the flags it carries instead, adherence, and the print.

No model anywhere in this file, which is the point of the ticket it covers:
the door the logging agent will come out through is built and exercised before
there is an agent to come out of it.

The one thing to keep in mind while reading it: **almost nothing here is a
refusal**. A report is a fact, and the tests that look like they should refuse
something -- pressing under an exclusion, swapping an exercise, training a
workout nobody planned -- assert that the row was written and that a flag says
so.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from conftest import enrich, make_exercise
from trainer import log
from trainer.engine import catalog, database, duration, exclusions, migrations, state, workouts

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Standing_Military_Press", name="Standing Military Press", equipment="barbell"
    ),
    make_exercise(
        id="Dumbbell_Bench_Press",
        name="Dumbbell Bench Press",
        equipment="dumbbell",
        primary_muscles=("chest",),
    ),
    make_exercise(
        id="Plank", name="Plank", equipment="body only", primary_muscles=("abdominals",)
    ),
    make_exercise(id="Ankle_Circles", name="Ankle Circles", category="stretching"),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Dumbbell_Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 1),
    "Plank": ("isolation", "shoulder", "no", "low", 0),
}

TODAY = "2026-09-09"


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


def prescribe(connection: sqlite3.Connection) -> int:
    """One squat block and one superset, the workout every test below reports
    against."""
    return workouts.record_prescribed(
        connection,
        (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(duration.BlockItem(exercise_id="Barbell_Squat", reps=8),),
                    rounds=4,
                    rest=150,
                ),
                reason="the heaviest lift while fresh",
            ),
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(
                        duration.BlockItem(
                            exercise_id="Standing_Military_Press", reps=10
                        ),
                        duration.BlockItem(exercise_id="Plank", seconds=45),
                    ),
                    rounds=3,
                    rest=90,
                ),
                reason="press and brace, nothing competing for the same joint",
            ),
        ),
        on="2026-09-08",
    )


def lifted(connection: sqlite3.Connection, exercise_id: str, load_kg: float) -> int:
    """One workout, already performed, with a load on the bar.

    Written through the engine's own writer rather than in SQL: what
    `last_performed_load` reads back has to be what a report actually puts
    there, and a fixture that inserted its own rows could agree with a view
    that no report ever fills.
    """
    return workouts.record_performed(
        connection,
        (
            workouts.PerformedBlock(
                items=(
                    workouts.PerformedItem(
                        exercise_id=exercise_id,
                        unit="reps",
                        amount=5,
                        amount_source="reported",
                        load_kg=load_kg,
                        load_kg_source="reported",
                    ),
                ),
                rounds=3,
                rounds_source="reported",
                rest=120,
                rest_source="reported",
            ),
        ),
        on="2026-09-01",
        report="lifted it",
    )


def document(*blocks: dict[str, Any], **fields: Any) -> str:
    base: dict[str, Any] = {"blocks": list(blocks), "report": "went fine"}
    base.update(fields)
    return json.dumps(base)


def block(*items: dict[str, Any], **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "items": list(items),
        "rounds": 3,
        "rounds_source": "reported",
        "rest": 90,
        "rest_source": "reported",
    }
    base.update(fields)
    return base


def item(exercise_id: str, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "exercise_id": exercise_id,
        "unit": "reps",
        "amount": 8,
        "amount_source": "reported",
    }
    base.update(fields)
    return base


def says(flagged: tuple[log.Flag, ...], about: str | None) -> list[str]:
    return [flag.says for flag in flagged if flag.about == about]


def flags_for(
    connection: sqlite3.Connection, parsed: log.PerformedWorkout
) -> tuple[log.Flag, ...]:
    """Validate, resolve, flag -- the order `trainer log` runs them in.

    The flags are read off the **resolved** blocks and never off the document,
    because the resolved blocks are what gets written. A test that flagged the
    document would pass while the commonest report there is went unexamined.
    """
    log.validate(connection, parsed, TODAY)
    return log.flags(connection, parsed, log.to_performed(connection, parsed), TODAY)


# -- the shape ----------------------------------------------------------------


def test_a_report_arrives_whole() -> None:
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount=5, load_kg=100, load_kg_source="reported"), rpe=8.5),
            workout_id=7,
            report="squat felt heavy",
        )
    )

    assert parsed.workout_id == 7
    assert parsed.report == "squat felt heavy"
    assert parsed.blocks[0].rpe == 8.5
    assert parsed.blocks[0].items[0].load_kg == 100
    assert parsed.proposed_exclusion is None


def test_a_report_may_mention_no_block_at_all() -> None:
    """*Did it as prescribed* is the commonest report there is, and it is the
    whole reason logging is by deviation. A plan with no blocks is not a
    workout; a report with no blocks is one."""
    parsed = log.parse(document(workout_id=7, report="all as planned"))

    assert parsed.blocks == []


def test_something_that_is_not_json_says_so() -> None:
    with pytest.raises(log.LogError, match="not JSON"):
        log.parse("did the squats, skipped the rest")


def test_a_report_with_no_words_in_it_is_not_a_report() -> None:
    """`report` is the user's own words, verbatim, and it is the only prose
    the schema keeps. An empty one is a workout nobody said anything about."""
    with pytest.raises(log.LogError, match="report"):
        log.parse(json.dumps({"blocks": [], "report": ""}))


def test_a_provenance_outside_the_three_is_refused() -> None:
    with pytest.raises(log.LogError, match="amount_source"):
        log.parse(document(block(item("Barbell_Squat", amount_source="guessed"))))


def test_a_unit_that_is_neither_reps_nor_seconds_is_refused() -> None:
    with pytest.raises(log.LogError, match="unit"):
        log.parse(document(block(item("Barbell_Squat", unit="metres"))))


def test_an_amount_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(log.LogError, match="amount"):
        log.parse(document(block(item("Barbell_Squat", amount="a lot"))))


def test_a_load_without_its_provenance_is_refused() -> None:
    """A provenance describing nothing is not a provenance, and a load whose
    provenance nobody wrote is a number that came from nowhere."""
    with pytest.raises(log.LogError, match="together or not at all"):
        log.parse(document(block(item("Barbell_Squat", load_kg=80))))


def test_a_misspelled_field_is_refused_rather_than_ignored() -> None:
    """The same reason `plan.PlanItem` forbids extras: a field quietly
    dropped is a report the author believes they wrote and did not."""
    with pytest.raises(log.LogError, match="reps_source"):
        log.parse(document(block(item("Barbell_Squat", reps_source="reported"))))


# -- the four refusals --------------------------------------------------------


def test_a_report_of_nothing_at_all_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """Empty blocks are *"did it as prescribed"*, which needs a prescription
    to be as. With neither, the render would print a workout with an empty
    `performed:` section under it and only the write would notice."""
    parsed = log.parse(document(report="did nothing much"))

    with pytest.raises(log.LogRejected, match="names no prescribed workout"):
        log.validate(connection, parsed, TODAY)


def test_a_value_cannot_be_assumed_with_no_prescription_behind_it(
    connection: sqlite3.Connection,
) -> None:
    """`assumed` means *as prescribed*, and there was no prescription. Left
    through, `WHERE amount_source = 'assumed'` -- the list of numbers the user
    never gave -- would hold one nobody can trace back to a plan."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount_source="assumed"), rest_source="assumed"),
            report="palestra di un amico",
        )
    )

    with pytest.raises(log.LogRejected) as refused:
        log.validate(connection, parsed, TODAY)
    assert "Barbell_Squat's amount" in str(refused.value)
    assert "rest" in str(refused.value)


def test_an_assumed_value_is_fine_when_there_is_a_prescription(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount_source="assumed")),
            workout_id=identifier,
        )
    )

    log.validate(connection, parsed, TODAY)


def test_an_assumed_amount_the_prescription_does_not_say_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """`assumed` means *as prescribed*, so it has to say what was prescribed.

    A real emission: asked to report *"only 3 sets of military because the
    shoulder was pulling"* against a prescription of 10 reps, a model wrote
    `amount: 8, amount_source: "assumed"`. Every other rule passes it -- the
    id exists, the number is a number, there is a workout to deviate from --
    and the row it writes says *the user never gave this number, it came from
    the plan* about a number that came from nowhere.
    """
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(
                item("Standing_Military_Press", amount=8, amount_source="assumed"),
                rounds=3,
            ),
            workout_id=identifier,
        )
    )

    with pytest.raises(log.LogRejected) as refused:
        log.validate(connection, parsed, TODAY)

    assert "8 reps of Standing_Military_Press" in str(refused.value)
    assert "prescribed as 10 reps" in str(refused.value)


def test_an_assumed_amount_that_matches_the_prescription_is_fine(
    connection: sqlite3.Connection,
) -> None:
    """The engine's own fill is exactly this, and refusing it would refuse
    every report that mentions one exercise of a block and not its sibling."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Standing_Military_Press", amount=10, amount_source="assumed")),
            workout_id=identifier,
        )
    )

    log.validate(connection, parsed, TODAY)


def test_assumed_rounds_the_prescription_does_not_say_are_refused(
    connection: sqlite3.Connection,
) -> None:
    """Volume is rounds performed, so this is the number that would be wrong
    on both axes -- and the column would say the user never gave it."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat"), rounds=7, rounds_source="assumed"),
            workout_id=identifier,
        )
    )

    with pytest.raises(log.LogRejected) as refused:
        log.validate(connection, parsed, TODAY)

    assert "7 rounds, prescribed as 4" in str(refused.value)


def test_a_substituted_block_may_call_what_the_user_did_not_say_assumed(
    connection: sqlite3.Connection,
) -> None:
    """The refusal is for a **contradiction**, never for silence.

    *"I did the dumbbell bench instead, three sets"* leaves the rest nobody
    asked about, and `rest` and `rest_source` are required fields. There is no
    prescribed counterpart to check the number against -- which prescribed
    exercise a substitute stands in for is a judgement the engine deliberately
    does not make -- so `reported` would be a lie about what the user said and
    `assumed` keeps its useful half: *the user did not give this number*.
    Refused, this report would be unwritable, and a substitution is the case
    the whole logging path exists for.
    """
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(
                item("Dumbbell_Bench_Press", amount=10, amount_source="assumed"),
                rest=90,
                rest_source="assumed",
            ),
            workout_id=identifier,
        )
    )

    log.validate(connection, parsed, TODAY)


def test_an_assumed_load_is_refused_because_a_plan_prescribes_none(
    connection: sqlite3.Connection,
) -> None:
    """`_assumed_items` sets no load, because there is nothing to set it from.
    A document claiming one is claiming the plan said what the bar weighed."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", load_kg=60, load_kg_source="assumed")),
            workout_id=identifier,
        )
    )

    with pytest.raises(log.LogRejected) as refused:
        log.validate(connection, parsed, TODAY)

    assert "prescribes no load" in str(refused.value)


def test_the_assumed_check_reads_the_block_the_report_is_actually_about(
    connection: sqlite3.Connection,
) -> None:
    """Matched by exercise, never by position -- the same matching the writer
    fills gaps from. Read by position, this plank would be checked against the
    squat block and refused for a number that is exactly what was prescribed.
    """
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(
                item("Plank", unit="seconds", amount=45, amount_source="assumed"),
                rounds=3,
                rest=90,
            ),
            workout_id=identifier,
        )
    )

    log.validate(connection, parsed, TODAY)


def test_an_exercise_the_catalog_does_not_have_is_refused(
    connection: sqlite3.Connection,
) -> None:
    parsed = log.parse(document(block(item("Kettlebell_Juggling"))))

    with pytest.raises(log.LogRejected, match="Kettlebell_Juggling"):
        log.validate(connection, parsed, TODAY)


def test_a_workout_nobody_prescribed_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """Not a fact about training -- a typo in the document. Reported as one,
    the render would print it as training nobody planned and only the write
    would notice."""
    parsed = log.parse(document(block(item("Barbell_Squat")), workout_id=404))

    with pytest.raises(log.LogRejected, match="no workout 404"):
        log.validate(connection, parsed, TODAY)


def test_a_workout_already_reported_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """One training session is one workout. Reported twice it would count
    twice on both volume axes."""
    identifier = prescribe(connection)
    parsed = log.parse(document(block(item("Barbell_Squat")), workout_id=identifier))
    workouts.record_performed(
        connection,
        log.to_performed(connection, parsed),
        on=TODAY,
        report="done",
        workout_id=identifier,
    )

    with pytest.raises(log.LogRejected, match="already reported"):
        log.validate(connection, parsed, TODAY)


def test_a_proposed_exclusion_that_is_neither_granularity_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """`classify` decides, against the catalog's own vocabulary, and its
    refusal names both granularities and says an exclusion is never an
    exercise id."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat")),
            proposed_exclusion={
                "value": "Standing_Military_Press",
                "retest_date": "2026-10-01",
                "why": "the shoulder was pulling",
            },
        )
    )

    with pytest.raises(log.LogRejected) as refused:
        log.validate(connection, parsed, TODAY)
    assert "movement pattern" in str(refused.value)
    assert "joint" in str(refused.value)
    assert "never an exercise id" in str(refused.value)


def test_a_proposed_exclusion_at_either_granularity_is_accepted(
    connection: sqlite3.Connection,
) -> None:
    for value in ("vertical push", "shoulder"):
        parsed = log.parse(
            document(
                block(item("Barbell_Squat")),
                proposed_exclusion={
                    "value": value,
                    "retest_date": "2026-10-01",
                    "why": "the shoulder was pulling",
                },
            )
        )

        log.validate(connection, parsed, TODAY)


# -- the flags ----------------------------------------------------------------


def test_an_exercise_under_an_active_exclusion_is_flagged_never_refused(
    connection: sqlite3.Connection,
) -> None:
    """The row this ticket exists to protect. You had an exclusion on
    `vertical push` and you pressed anyway: that is the most valuable row in
    the database, and refusing it would keep the state clean by not knowing."""
    exclusions.add(connection, exclusions.Exclusion("pattern", "vertical push"), "2026-12-01")
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Standing_Military_Press", amount=10)),
            workout_id=identifier,
            report="pressed anyway, shoulder held up",
        )
    )

    flags = flags_for(connection, parsed)

    assert says(flags, "Standing_Military_Press") == [
        "is under an exclusion on pattern 'vertical push', and was performed anyway"
    ]
    written = workouts.record_performed(
        connection,
        log.to_performed(connection, parsed),
        on=TODAY,
        report=parsed.report,
        workout_id=identifier,
    )
    assert any(
        performed.exercise_id == "Standing_Military_Press"
        for block_ in workouts.performed(connection, written)
        for performed in block_.items
    )


def test_a_joint_exclusion_reaches_the_same_row(connection: sqlite3.Connection) -> None:
    """`exclusions.covering` is one definition of what an exclusion reaches,
    shared with `admissible.rejection`, so the boundary that keeps a movement
    out of a plan is the boundary that notices it in a report."""
    exclusions.add(connection, exclusions.Exclusion("joint", "shoulder"), "2026-12-01")
    parsed = log.parse(document(block(item("Standing_Military_Press"))))

    flags = flags_for(connection, parsed)

    assert says(flags, "Standing_Military_Press") == [
        "is under an exclusion on joint 'shoulder', and was performed anyway"
    ]


def test_an_expired_exclusion_flags_nothing(connection: sqlite3.Connection) -> None:
    """A wall with a way back. Once the re-test date arrives the row stops
    excluding, and a workout done after it is an ordinary workout."""
    exclusions.add(connection, exclusions.Exclusion("pattern", "vertical push"), "2026-08-01")
    parsed = log.parse(document(block(item("Standing_Military_Press"))))

    assert says(flags_for(connection, parsed), "Standing_Military_Press") == []


def test_an_exercise_that_was_not_prescribed_is_flagged(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Dumbbell_Bench_Press", amount=10)),
            workout_id=identifier,
            report="swapped the presses, the shoulder was pulling",
        )
    )

    flags = flags_for(connection, parsed)

    assert says(flags, "Dumbbell_Bench_Press") == ["was not in the prescribed workout"]


def test_a_prescribed_exercise_is_not_flagged_as_a_substitution(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    parsed = log.parse(
        document(block(item("Barbell_Squat")), workout_id=identifier)
    )

    assert flags_for(connection, parsed) == ()


def test_a_workout_nobody_planned_is_flagged_once_not_per_exercise(
    connection: sqlite3.Connection,
) -> None:
    """A reader who does not know there was no prescription is reading a
    workout with no deviations and concluding the user did as they were told.
    Said once, about the workout -- per exercise it would bury itself."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat"), item("Dumbbell_Bench_Press")),
            report="went to a different gym",
        )
    )

    flags = flags_for(connection, parsed)

    assert len(flags) == 1
    assert flags[0].about is None
    assert "nothing it deviates from" in flags[0].says


def test_a_load_that_moved_further_than_the_history_explains_is_flagged(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule is `LOAD_JUMP`; the history is `state.last_performed_load`,
    which is asked rather than queried here so there is one definition of what
    the last load was."""
    monkeypatch.setattr(
        state, "last_performed_load", lambda connection, exercise_id: state.Answer("", 100.0)
    )
    parsed = log.parse(
        document(block(item("Barbell_Squat", load_kg=140, load_kg_source="reported")))
    )

    flags = flags_for(connection, parsed)

    assert says(flags, "Barbell_Squat") == [
        "moved from 100 kg to 140 kg, further than the recorded history explains"
    ]


def test_a_load_inside_the_rule_is_not_flagged(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding 2.5 kg to a 100 kg lift is what progression looks like, and a
    flag on it would fire on every workout that went well."""
    monkeypatch.setattr(
        state, "last_performed_load", lambda connection, exercise_id: state.Answer("", 100.0)
    )
    parsed = log.parse(
        document(block(item("Barbell_Squat", load_kg=102.5, load_kg_source="reported")))
    )

    assert says(flags_for(connection, parsed), "Barbell_Squat") == []


def test_a_load_with_no_history_behind_it_is_not_flagged(
    connection: sqlite3.Connection,
) -> None:
    """An unknown history flags nothing: the first time a load is recorded
    there is nothing for it to have jumped from, and inventing a baseline would
    make every first entry suspicious.

    This asserted the same thing when `state.last_performed_load` could not
    answer at all, and it asserts it now against a database where the answer is
    real and this exercise simply has no load in it -- which is what the
    original was standing in for.
    """
    lifted(connection, "Standing_Military_Press", 40.0)
    parsed = log.parse(
        document(block(item("Barbell_Squat", load_kg=400, load_kg_source="reported")))
    )

    assert says(flags_for(connection, parsed), "Barbell_Squat") == []


def test_a_load_is_flagged_against_a_load_that_was_really_recorded(
    connection: sqlite3.Connection,
) -> None:
    """No `monkeypatch`. The flag was dormant for two sessions because
    `last_performed_load` had nowhere to read from; migration 0007 gave it one,
    and this is the whole path -- a workout performed at 100 kg, and the next
    report saying 140."""
    lifted(connection, "Barbell_Squat", 100.0)
    parsed = log.parse(
        document(block(item("Barbell_Squat", load_kg=140, load_kg_source="reported")))
    )

    assert says(flags_for(connection, parsed), "Barbell_Squat") == [
        "moved from 100 kg to 140 kg, further than the recorded history explains"
    ]


def test_progression_against_a_real_recorded_load_is_not_flagged(
    connection: sqlite3.Connection,
) -> None:
    """The other half of the same path: a flag that fired on every good workout
    would be a flag nobody reads."""
    lifted(connection, "Barbell_Squat", 100.0)
    parsed = log.parse(
        document(block(item("Barbell_Squat", load_kg=102.5, load_kg_source="reported")))
    )

    assert says(flags_for(connection, parsed), "Barbell_Squat") == []


# -- adherence ----------------------------------------------------------------


def test_an_unmentioned_item_comes_back_assumed(
    connection: sqlite3.Connection,
) -> None:
    """What a report does not mention was performed as prescribed, and every
    number it filled in says so."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount=5), rounds=3),
            workout_id=identifier,
            report="only three sets of squats",
        )
    )

    blocks = log.to_performed(connection, parsed)

    assert len(blocks) == 2
    assert blocks[0].rounds == 3 and blocks[0].rounds_source == "reported"
    assert blocks[1].rounds == 3 and blocks[1].rounds_source == "assumed"
    assert [(entry.exercise_id, entry.amount_source) for entry in blocks[1].items] == [
        ("Standing_Military_Press", "assumed"),
        ("Plank", "assumed"),
    ]


def test_a_mentioned_block_keeps_its_unmentioned_sibling(
    connection: sqlite3.Connection,
) -> None:
    """A superset the user talked half of. The other half is filled into the
    same block rather than lost -- it is an *item* that was not mentioned, and
    the block it belongs to is one the report is about."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Standing_Military_Press", amount=8), rounds=2),
            workout_id=identifier,
        )
    )

    blocks = log.to_performed(connection, parsed)

    press = next(entry for entry in blocks if len(entry.items) == 2)
    assert [(entry.exercise_id, entry.amount, entry.amount_source) for entry in press.items] == [
        ("Standing_Military_Press", 8, "reported"),
        ("Plank", 45, "assumed"),
    ]
    assert press.rounds == 2


def test_a_report_that_mentions_nothing_is_the_whole_workout_assumed(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    parsed = log.parse(document(workout_id=identifier, report="all as planned"))

    blocks = log.to_performed(connection, parsed)

    assert [entry.rounds for entry in blocks] == [4, 3]
    assert {
        source
        for entry in blocks
        for source in (entry.rounds_source, entry.rest_source)
    } == {"assumed"}


def test_nothing_is_counted_twice_when_the_user_regrouped_the_workout(
    connection: sqlite3.Connection,
) -> None:
    """Two reported blocks naming exercises of one prescribed superset. The
    fill has to notice that both are accounted for: repeated, the same rounds
    would count twice on both volume axes."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Standing_Military_Press", amount=10)),
            block(item("Plank", unit="seconds", amount=60)),
            workout_id=identifier,
            report="did the press and the plank separately",
        )
    )

    blocks = log.to_performed(connection, parsed)

    named = [entry.exercise_id for block_ in blocks for entry in block_.items]
    assert named.count("Standing_Military_Press") == 1
    assert named.count("Plank") == 1
    assert named.count("Barbell_Squat") == 1


def test_a_substitution_records_both_and_flags_the_one_nobody_prescribed(
    connection: sqlite3.Connection,
) -> None:
    """Which prescribed exercise a substitute stands in for is a judgement,
    and ROADMAP.md gives the judgements to the agent. The engine records what
    it was told and what it defaulted, marks which is which, and says one of
    them was never prescribed."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Dumbbell_Bench_Press", amount=10)),
            workout_id=identifier,
            report="swapped the presses",
        )
    )

    blocks = log.to_performed(connection, parsed)
    flags = flags_for(connection, parsed)

    recorded = {
        entry.exercise_id: entry.amount_source
        for block_ in blocks
        for entry in block_.items
    }
    assert recorded["Dumbbell_Bench_Press"] == "reported"
    assert recorded["Standing_Military_Press"] == "assumed"
    assert says(flags, "Dumbbell_Bench_Press") == ["was not in the prescribed workout"]


def test_a_workout_nobody_planned_assumes_nothing(
    connection: sqlite3.Connection,
) -> None:
    """There was nothing to assume against, so every value in it is the
    user's."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount_source="asked")),
            report="went to a different gym",
        )
    )

    blocks = log.to_performed(connection, parsed)

    assert {entry.amount_source for block_ in blocks for entry in block_.items} == {"asked"}
    assert {entry.rounds_source for entry in blocks} == {"reported"}


def test_timed_work_is_filled_in_as_timed_work(
    connection: sqlite3.Connection,
) -> None:
    """The plank is prescribed in seconds, and the assumed row has to say so
    -- filled as reps it would be *45 reps of plank*, which means nothing."""
    identifier = prescribe(connection)
    parsed = log.parse(document(workout_id=identifier, report="all as planned"))

    blocks = log.to_performed(connection, parsed)

    plank = next(
        entry
        for block_ in blocks
        for entry in block_.items
        if entry.exercise_id == "Plank"
    )
    assert (plank.unit, plank.amount) == ("seconds", 45)


def test_adherence_never_invents_a_load(connection: sqlite3.Connection) -> None:
    """A plan does not prescribe load, so there is nothing to assume."""
    identifier = prescribe(connection)
    parsed = log.parse(document(workout_id=identifier, report="all as planned"))

    blocks = log.to_performed(connection, parsed)

    assert all(
        entry.load_kg is None and entry.load_kg_source is None
        for block_ in blocks
        for entry in block_.items
    )


# -- the proposed exclusion ---------------------------------------------------


def test_the_granularity_is_read_from_the_catalog_not_from_the_document(
    connection: sqlite3.Connection,
) -> None:
    """The document names a value and a date; `classify` says which of the two
    granularities it is. A granularity on the wire would be a second answer to
    a question the engine already answers."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat")),
            proposed_exclusion={
                "value": "shoulder",
                "retest_date": "2026-10-01",
                "why": "it was pulling under the bar",
            },
        )
    )

    exclusion, retest_date = log.proposed(connection, parsed)

    assert exclusion == exclusions.Exclusion("joint", "shoulder")
    assert retest_date == "2026-10-01"


def test_a_report_proposing_nothing_proposes_nothing(
    connection: sqlite3.Connection,
) -> None:
    parsed = log.parse(document(block(item("Barbell_Squat"))))

    assert log.proposed(connection, parsed) == (None, None)


# -- the renderer -------------------------------------------------------------


def rendered(connection: sqlite3.Connection, parsed: log.PerformedWorkout) -> str:
    blocks = log.to_performed(connection, parsed)
    log.validate(connection, parsed, TODAY)
    return "\n".join(
        log.render(
            connection, parsed, blocks, log.flags(connection, parsed, blocks, TODAY)
        )
    )


def test_the_render_sets_prescribed_against_performed(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount=5), rounds=3),
            workout_id=identifier,
            report="only three sets, the knee was noisy",
        )
    )

    output = rendered(connection, parsed)

    assert f"prescribed (workout {identifier}):" in output
    assert "block 1 -- 4 rounds, 150s rest" in output
    assert "performed:" in output
    assert "block 1 -- 3 rounds, 90s rest" in output
    assert "said: only three sets, the knee was noisy" in output


def test_the_render_marks_what_was_assumed_and_leaves_the_rest_alone(
    connection: sqlite3.Connection,
) -> None:
    """A workout every line of which ends in `(reported)` is a workout nobody
    reads to the end of. What has to stand out is the value the system
    supplied on the user's behalf."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount=5), rounds=3),
            workout_id=identifier,
            report="only three sets",
        )
    )

    output = rendered(connection, parsed)

    assert "5 reps" in output and "5 reps (reported)" not in output
    assert "10 reps (assumed)" in output
    assert "3 rounds (assumed)" in output


def test_the_render_puts_a_flag_under_the_line_it_is_about(
    connection: sqlite3.Connection,
) -> None:
    exclusions.add(connection, exclusions.Exclusion("pattern", "vertical push"), "2026-12-01")
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Standing_Military_Press", amount=10)),
            workout_id=identifier,
            report="pressed anyway",
        )
    )

    lines = rendered(connection, parsed).splitlines()
    performed = lines.index("performed:")
    at = next(
        index
        for index, line in enumerate(lines)
        if index > performed and "Standing Military Press" in line
    )

    assert "! is under an exclusion on pattern 'vertical push'" in lines[at + 1]


def test_the_render_says_when_there_was_no_prescription(
    connection: sqlite3.Connection,
) -> None:
    parsed = log.parse(
        document(block(item("Barbell_Squat")), report="trained at a hotel")
    )

    output = rendered(connection, parsed)

    assert "prescribed: nothing -- this workout was not planned" in output
    assert "! this reports no prescribed workout" in output


def test_the_render_states_the_exclusion_the_report_proposes(
    connection: sqlite3.Connection,
) -> None:
    parsed = log.parse(
        document(
            block(item("Barbell_Squat")),
            proposed_exclusion={
                "value": "vertical push",
                "retest_date": "2026-10-01",
                "why": "the shoulder was pulling",
            },
        )
    )

    output = rendered(connection, parsed)

    assert (
        "proposes excluding pattern 'vertical push' until 2026-10-01: "
        "the shoulder was pulling" in output
    )


def test_the_render_shows_a_load_and_an_rpe(connection: sqlite3.Connection) -> None:
    parsed = log.parse(
        document(
            block(
                item("Barbell_Squat", amount=5, load_kg=102.5, load_kg_source="reported"),
                rpe=8.0,
            )
        )
    )

    output = rendered(connection, parsed)

    assert "5 reps @ 102.5 kg" in output
    assert "RPE 8" in output


def test_the_render_is_ascii(connection: sqlite3.Connection) -> None:
    """An em dash reaches the Windows console as a replacement character."""
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount=5, load_kg=100, load_kg_source="asked")),
            workout_id=identifier,
            report="ok",
        )
    )

    assert rendered(connection, parsed).isascii()


# -- what the flags are read off ----------------------------------------------
#
# All four of these are one bug: the flags were computed against the document
# rather than against what `to_performed` resolved. Everything adherence fills
# in is a performed exercise, and the report that fills in the most is the one
# that says the least.


def test_the_shortest_report_there_is_still_flags_an_exclusion(
    connection: sqlite3.Connection,
) -> None:
    """`{"workout_id": N, "report": "went fine"}` writes every prescribed
    exercise as performed. Flagged off the document, it would write a press
    under an active exclusion and say nothing at all -- the row this module
    exists to shout about, silent in the commonest report there is."""
    exclusions.add(connection, exclusions.Exclusion("pattern", "vertical push"), "2026-12-01")
    identifier = prescribe(connection)
    parsed = log.parse(document(workout_id=identifier, report="tutto come previsto"))

    flags = flags_for(connection, parsed)

    assert says(flags, "Standing_Military_Press") == [
        "is under an exclusion on pattern 'vertical push', and was performed anyway"
    ]


def test_an_assumed_sibling_is_flagged_like_any_other_performed_exercise(
    connection: sqlite3.Connection,
) -> None:
    """The plank loads the shoulder and was never mentioned. It is still
    written, so it is still checked."""
    exclusions.add(connection, exclusions.Exclusion("joint", "shoulder"), "2026-12-01")
    identifier = prescribe(connection)
    parsed = log.parse(
        document(
            block(item("Barbell_Squat", amount=5)),
            workout_id=identifier,
            report="squat pesante",
        )
    )

    flags = flags_for(connection, parsed)

    assert says(flags, "Plank") == [
        "is under an exclusion on joint 'shoulder', and was performed anyway"
    ]


def test_an_assumed_exercise_is_never_flagged_as_a_substitution(
    connection: sqlite3.Connection,
) -> None:
    """Everything adherence fills in came out of the prescription, so nothing
    it fills in can be something nobody prescribed."""
    identifier = prescribe(connection)
    parsed = log.parse(document(workout_id=identifier, report="tutto come previsto"))

    assert flags_for(connection, parsed) == ()


def test_a_flag_is_raised_once_however_often_the_exercise_appears(
    connection: sqlite3.Connection,
) -> None:
    """The bar was picked up twice. The same sentence twice is how the line
    that matters most gets skipped."""
    exclusions.add(connection, exclusions.Exclusion("pattern", "vertical push"), "2026-12-01")
    exclusions.add(connection, exclusions.Exclusion("joint", "shoulder"), "2026-12-01")
    parsed = log.parse(
        document(
            block(item("Standing_Military_Press", amount=10)),
            block(item("Standing_Military_Press", amount=6)),
            report="due volte, la seconda leggera",
        )
    )

    flags = flags_for(connection, parsed)
    printed = rendered(connection, parsed)

    assert len(says(flags, "Standing_Military_Press")) == 2
    assert printed.count("is under an exclusion on pattern 'vertical push'") == 1
    assert printed.count("is under an exclusion on joint 'shoulder'") == 1


# -- the re-test date ---------------------------------------------------------


def test_a_retest_date_that_is_not_a_date_is_a_shape_error() -> None:
    """`exclusions.active` compares the column with `>`, which is
    chronological only because `YYYY-MM-DD` sorts that way. *"next week"*
    sorts after every date there will ever be, so the exclusion would never
    expire and nothing would ever say so."""
    with pytest.raises(log.LogError, match="retest_date"):
        log.parse(
            document(
                block(item("Barbell_Squat")),
                proposed_exclusion={
                    "value": "vertical push",
                    "retest_date": "next week",
                    "why": "la spalla",
                },
            )
        )


def test_a_retest_date_in_a_format_that_sorts_wrong_is_refused() -> None:
    """`20261001` is a real date that `date.fromisoformat` accepts and that
    sorts nowhere near the dates beside it in the column."""
    with pytest.raises(log.LogError, match="retest_date"):
        log.parse(
            document(
                block(item("Barbell_Squat")),
                proposed_exclusion={
                    "value": "vertical push",
                    "retest_date": "20261001",
                    "why": "la spalla",
                },
            )
        )


def test_a_retest_date_that_has_already_passed_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """It would be written, the render would print a confident sentence about
    a movement being excluded, and `exclusions.active` would never return it."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat")),
            proposed_exclusion={
                "value": "vertical push",
                "retest_date": "2020-01-01",
                "why": "la spalla",
            },
        )
    )

    with pytest.raises(log.LogRejected, match="expires before it starts"):
        log.validate(connection, parsed, TODAY)


def test_a_retest_date_of_today_is_refused_too(
    connection: sqlite3.Connection,
) -> None:
    """`exclusions.active` keeps a row while `retest_date > today`, so a date
    of today excludes nothing from the moment it is written."""
    parsed = log.parse(
        document(
            block(item("Barbell_Squat")),
            proposed_exclusion={
                "value": "vertical push",
                "retest_date": TODAY,
                "why": "la spalla",
            },
        )
    )

    with pytest.raises(log.LogRejected, match="not after"):
        log.validate(connection, parsed, TODAY)
