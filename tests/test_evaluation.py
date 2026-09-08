"""The six invariants, decided by code, against recorded runs.

The *running* of `trainer eval` needs a provider and is not here -- the suite
has no sockets and no credentials, on purpose. The *checks* are pure functions
over a run record, so all of them are, which is the whole reason they were
written that way: a measurement whose checks cannot be tested is a measurement
nobody should believe.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich, make_exercise
from trainer import agent, evaluation
from trainer import plan as plans
from trainer.engine import catalog, database, migrations

CATALOG = (
    make_exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        mechanic="compound",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Lunge",
        name="Lunge",
        equipment="body only",
        mechanic="compound",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Plank",
        name="Plank",
        equipment="body only",
        mechanic="isolation",
        primary_muscles=("abdominals",),
    ),
    make_exercise(
        id="Barbell_Curl",
        name="Barbell Curl",
        equipment="barbell",
        mechanic="isolation",
        primary_muscles=("biceps",),
    ),
)

_PATTERNS = {
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
    "Lunge": ("single-leg", "hip, knee, ankle", "no", "high", 0),
    "Plank": ("isolation", "shoulder", "no", "low", 0),
    "Barbell_Curl": ("isolation", "elbow", "no", "low", 2),
}

LEGS_AND_CORE = plans.Request(
    equipment=("body only",), budget_min=45, groups=("legs", "core")
)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


def item(exercise_id: str) -> plans.PlanItem:
    return plans.PlanItem(
        exercise_id=exercise_id,
        prescription=plans.Prescription(unit="reps", amount=8),
    )


def said(exercise_id: str, why: str) -> plans.Acknowledgement:
    return plans.Acknowledgement(exercise_id=exercise_id, why=why)


def recorded(
    *blocks: plans.PlanBlock,
    despite: list[plans.Acknowledgement] | None = None,
    **overrides: object,
) -> agent.RunRecord:
    """A run record carrying a plan, and nothing a check does not read."""
    base: dict[str, object] = {
        "model": "a-stand-in",
        "budget": 12,
        "spent": 2,
        "emitted_on_exhaustion": False,
        "calls": [],
        "input_tokens": 100,
        "output_tokens": 20,
        "plan": plans.WorkoutPlan(blocks=list(blocks), despite=despite or []),
    }
    base.update(overrides)
    return agent.RunRecord(**base)  # type: ignore[arg-type]


def one(*items: plans.PlanItem, rounds: int = 3, rest: int = 60) -> plans.PlanBlock:
    return plans.PlanBlock(
        items=list(items), rounds=rounds, rest=rest, reason="because"
    )


def situation(request: plans.Request) -> evaluation.Situation:
    return evaluation.Situation(name="a-situation", describes="one", request=request)


def failing(
    connection: sqlite3.Connection, request: plans.Request, record: agent.RunRecord
) -> dict[str, str]:
    return dict(evaluation.check(connection, situation(request), record))


# -- the six situations are data ----------------------------------------------


def test_the_six_situations_are_declared(connection: sqlite3.Connection) -> None:
    """A seventh is a row, not a code change."""
    declared = evaluation.situations(connection)

    assert len(declared) == 6
    assert len({s.name for s in declared}) == 6
    for found in declared:
        assert found.describes, f"{found.name} does not say what it is for"


def test_exactly_one_situation_measures_the_second_plan(
    connection: sqlite3.Connection,
) -> None:
    """TRAINER.md's fifth: the user refuses and it proposes again. The first
    run exists only to have something to turn down."""
    after = [s for s in evaluation.situations(connection) if s.after_a_refusal]

    assert [s.name for s in after] == ["refused"]


def test_the_preference_situations_read_the_catalog(
    connection: sqlite3.Connection,
) -> None:
    """*Half the catalog* is half of whatever the catalog holds, never a
    hand-written list of ids -- this project has been wrong that way once."""
    (half,) = [s for s in evaluation.situations(connection) if s.name == "half-refused"]

    assert half.request.preferences
    for exercise_id in half.request.preferences:
        assert catalog.exercise(connection, exercise_id) is not None


# -- each invariant, on its own -----------------------------------------------


def test_a_plan_that_holds_everything_fails_nothing(
    connection: sqlite3.Connection,
) -> None:
    record = recorded(one(item("Bodyweight_Squat")), one(item("Plank")))

    assert failing(connection, LEGS_AND_CORE, record) == {}


def test_a_plan_over_the_time_fails_the_clock(connection: sqlite3.Connection) -> None:
    record = recorded(one(item("Bodyweight_Squat"), rounds=99, rest=180))

    broke = failing(connection, LEGS_AND_CORE, record)

    assert "time" in broke
    assert "against 45" in broke["time"]


def test_an_exercise_outside_the_set_fails_the_constraints(
    connection: sqlite3.Connection,
) -> None:
    record = recorded(one(item("Barbell_Curl")), one(item("Plank")))

    broke = failing(connection, LEGS_AND_CORE, record)

    assert "constraints" in broke
    assert "Barbell_Curl" in broke["constraints"]


def test_the_wrong_equipment_fails_on_its_own_axis(
    connection: sqlite3.Connection,
) -> None:
    """Checked apart from the admissible set although the set filters on it:
    a fault in the filter would otherwise pass both."""
    record = recorded(one(item("Barbell_Curl")))

    broke = failing(connection, LEGS_AND_CORE, record)

    assert "equipment" in broke
    assert "barbell" in broke["equipment"]


def test_a_preference_prescribed_silently_fails_the_preferences(
    connection: sqlite3.Connection,
) -> None:
    request = plans.Request(
        equipment=("body only",),
        budget_min=45,
        groups=("legs", "core"),
        preferences=("Bodyweight_Squat",),
    )
    record = recorded(one(item("Bodyweight_Squat")), one(item("Plank")))

    broke = failing(connection, request, record)

    assert "preferences" in broke
    assert "without saying why" in broke["preferences"]


def test_a_preference_prescribed_with_a_reason_holds(
    connection: sqlite3.Connection,
) -> None:
    """Both halves of the invariant. Proposing one with the reason attached is
    the behaviour it wants, not the failure."""
    request = plans.Request(
        equipment=("body only",),
        budget_min=45,
        groups=("legs", "core"),
        preferences=("Bodyweight_Squat",),
    )
    record = recorded(
        one(item("Bodyweight_Squat")),
        one(item("Plank")),
        despite=[said("Bodyweight_Squat", "nothing else loads the knee today")],
    )

    assert "preferences" not in failing(connection, request, record)


def test_an_empty_plan_fails_termination(connection: sqlite3.Connection) -> None:
    """The type guarantees a plan object; what it does not guarantee is that
    the model put anything in it."""
    record = recorded(one(item("Plank")))
    record.plan.blocks.clear()

    assert "terminates" in failing(connection, LEGS_AND_CORE, record)


# -- invariant 6, the one that had to be defined ------------------------------


def test_a_group_the_workout_was_asked_for_and_never_trained_degenerates(
    connection: sqlite3.Connection,
) -> None:
    """The muscle axis: *am I touching this at all*. A leg-and-core day with
    no core in it."""
    record = recorded(one(item("Bodyweight_Squat")), one(item("Lunge")))

    broke = failing(connection, LEGS_AND_CORE, record)

    assert "not degenerate" in broke
    assert "core" in broke["not degenerate"]


def test_one_movement_pattern_out_of_several_available_degenerates(
    connection: sqlite3.Connection,
) -> None:
    """The pattern axis: *am I balanced*. An arm workout made entirely of
    curls is invisible on the muscle axis, because biceps, triceps and
    forearms are one bucket there (ADR-0001)."""
    legs = plans.Request(equipment=("body only",), budget_min=45, groups=("legs",))
    record = recorded(one(item("Bodyweight_Squat")))

    broke = failing(connection, legs, record)

    assert "not degenerate" in broke
    assert "patterns available" in broke["not degenerate"]


def test_two_movement_patterns_is_enough(connection: sqlite3.Connection) -> None:
    legs = plans.Request(equipment=("body only",), budget_min=45, groups=("legs",))
    record = recorded(one(item("Bodyweight_Squat")), one(item("Lunge")))

    assert "not degenerate" not in failing(connection, legs, record)


def test_a_group_nothing_could_have_trained_is_not_a_failure(
    connection: sqlite3.Connection,
) -> None:
    """The escape clause, and the reason 100% is a bar the agent can clear: if
    the admissible set offers nothing for a group, a plan that reflects that is
    the only honest answer, and failing it would measure the catalog."""
    with_back = plans.Request(
        equipment=("body only",), budget_min=45, groups=("legs", "core", "back")
    )
    record = recorded(one(item("Bodyweight_Squat")), one(item("Lunge")), one(item("Plank")))

    broke = failing(connection, with_back, record)

    assert "not degenerate" not in broke, broke.get("not degenerate")


def test_one_pattern_is_not_a_failure_when_one_is_all_there_was(
    connection: sqlite3.Connection,
) -> None:
    """Same clause on the other axis."""
    core = plans.Request(equipment=("body only",), budget_min=45, groups=("core",))
    record = recorded(one(item("Plank")))

    assert "not degenerate" not in failing(connection, core, record)


def test_the_ratio_of_compound_to_isolation_is_not_an_invariant(
    connection: sqlite3.Connection,
) -> None:
    """Against the real catalog the arms group is seventy isolation exercises
    to twelve compound, so any majority-compound rule fails a correct arm day.
    In a measurement whose bar is 100%, an invariant that can be wrong is worse
    than one that is weak."""
    core = plans.Request(equipment=("body only",), budget_min=45, groups=("core",))
    all_isolation = recorded(one(item("Plank")))

    assert failing(connection, core, all_isolation) == {}


# -- the report ---------------------------------------------------------------


def held(name: str, attempt: int = 1) -> evaluation.Outcome:
    return evaluation.Outcome(name, attempt)


def broke(name: str, attempt: int = 1) -> evaluation.Outcome:
    return evaluation.Outcome(name, attempt, failures=(("time", "it ran over"),))


def test_the_bar_is_every_run(connection: sqlite3.Connection) -> None:
    """Every run counts. One green run out of two is not half a pass, it is
    not a pass."""
    report = evaluation.Report((held("a"), broke("a", 2)))

    assert report.total == 2
    assert report.held == 1
    assert report.percentage == 50.0
    assert report.passed is False


def test_a_pass_is_every_run_holding() -> None:
    report = evaluation.Report((held("a"), held("a", 2)))

    assert report.percentage == 100.0
    assert report.passed is True


def test_an_empty_pass_is_not_a_pass() -> None:
    """Nothing ran, so nothing held. Reporting 100% would be the easiest way
    to make this command lie."""
    assert evaluation.Report(()).passed is False


def test_a_run_that_never_finished_counts_against_the_metric() -> None:
    """A measurement that quietly skipped the runs it could not make would
    report on the easy ones."""
    report = evaluation.Report((evaluation.Outcome("a", 1, error="no credentials"),))

    assert report.held == 0
    assert report.passed is False


def test_every_invariant_is_reported_not_just_the_first(
    connection: sqlite3.Connection,
) -> None:
    """A run that breaks three properties is a different thing from one that
    breaks one, and stopping at the first hides the difference behind an
    identical line in the matrix."""
    record = recorded(one(item("Barbell_Curl"), rounds=99, rest=180))

    assert len(failing(connection, LEGS_AND_CORE, record)) >= 3


def test_the_matrix_names_the_situation_the_invariant_and_the_record(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    written = tmp_path / "a-situation-1.json"
    report = evaluation.Report(
        (
            evaluation.Outcome(
                "a-situation",
                1,
                failures=(("time", "it runs 60 min against 45"),),
                written=written,
            ),
        ),
    )

    printed = "\n".join(evaluation.render(report, (situation(LEGS_AND_CORE),)))

    assert "a-situation" in printed
    assert "time" in printed
    assert str(written) in printed
    assert "0%" in printed
    assert printed.isascii()


def test_the_report_says_what_the_pass_cost(connection: sqlite3.Connection) -> None:
    """So the price of re-running it after a prompt change is known."""
    record = recorded(
        one(item("Plank")),
        calls=[agent.RecordedCall(name="admissible_set", arguments={})],
        input_tokens=1200,
        output_tokens=90,
    )
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, record=record),))

    printed = "\n".join(evaluation.render(report, (situation(LEGS_AND_CORE),)))

    assert "1 tool calls" in printed
    assert "1200 tokens in" in printed
    assert "90 out" in printed


# -- what the matrix must not hide --------------------------------------------


def test_a_run_that_never_happened_gets_its_own_column_not_the_whole_row(
    connection: sqlite3.Connection,
) -> None:
    """A rate limit on the second of three repetitions says nothing about the
    two that did run. Blanking their verdicts would hide real failures behind
    an unrelated transport error."""
    report = evaluation.Report(
        (
            evaluation.Outcome("a-situation", 1, failures=(("time", "over"),)),
            evaluation.Outcome("a-situation", 2, error="rate limited"),
            evaluation.Outcome("a-situation", 3, failures=(("time", "over"),)),
        )
    )

    matrix = evaluation.render(report, (situation(LEGS_AND_CORE),))[1]

    assert "2 failed" in matrix, matrix
    assert evaluation.NOT_RUN in "\n".join(evaluation.render(report, (situation(LEGS_AND_CORE),)))


def test_a_refusal_the_invariants_do_not_name_still_shows_in_the_matrix(
    connection: sqlite3.Connection,
) -> None:
    """The validator and the invariants disagreeing is the interesting thing.
    A failure with no column would print a row of `ok` above a line saying the
    run did not hold."""
    report = evaluation.Report(
        (
            evaluation.Outcome(
                "a-situation", 1, failures=((evaluation.VALIDATOR, "it refused"),)
            ),
        )
    )

    printed = "\n".join(evaluation.render(report, (situation(LEGS_AND_CORE),)))

    assert evaluation.VALIDATOR in printed
    assert "1 failed" in printed


def test_the_percentage_never_rounds_up_to_a_pass() -> None:
    """At 249 of 250 a rounded figure prints 100% on the line above *the bar
    is 100%*, and then exits non-zero -- the one number this command exists to
    produce, contradicting itself."""
    outcomes = tuple(held("a", n) for n in range(249)) + (broke("a", 249),)
    report = evaluation.Report(outcomes)

    printed = "\n".join(evaluation.render(report, (situation(LEGS_AND_CORE),)))

    assert report.passed is False
    assert "99%" in printed
    assert "-- 100%" not in printed


def test_the_cost_counts_the_run_that_was_only_made_to_be_turned_down(
    connection: sqlite3.Connection,
) -> None:
    """The refusal situation makes two calls' worth of agent loop. Only the
    second is measured; both are on the bill, and this number is what a pass
    is budgeted against."""
    turned_down = recorded(one(item("Plank")), input_tokens=1000, output_tokens=100)
    measured = recorded(one(item("Plank")), input_tokens=2000, output_tokens=200)
    report = evaluation.Report(
        (evaluation.Outcome("refused", 1, record=measured, also=(turned_down,)),)
    )

    assert report.input_tokens == 3000
    assert report.output_tokens == 300


def test_a_loop_that_overshot_without_saying_so_fails_termination(
    connection: sqlite3.Connection,
) -> None:
    """The budget is where tools stop being offered, not a number the loop
    lands on -- a turn's calls run together. What would be a fault is
    overshooting without having crossed the line."""
    record = recorded(
        one(item("Bodyweight_Squat")),
        one(item("Plank")),
        spent=30,
        budget=12,
        emitted_on_exhaustion=False,
    )

    assert "terminates" in failing(connection, LEGS_AND_CORE, record)


def test_overshooting_the_budget_on_the_turn_that_crossed_it_is_not_a_fault(
    connection: sqlite3.Connection,
) -> None:
    record = recorded(
        one(item("Bodyweight_Squat")),
        one(item("Plank")),
        spent=14,
        budget=12,
        emitted_on_exhaustion=True,
    )

    assert "terminates" not in failing(connection, LEGS_AND_CORE, record)
