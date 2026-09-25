"""The six invariants, decided by code, against recorded runs.

The *running* of `trainer eval` needs a provider and is not here -- the suite
has no sockets and no credentials, on purpose. The *checks* are pure functions
over a run record, so all of them are, which is the whole reason they were
written that way: a measurement whose checks cannot be tested is a measurement
nobody should believe.

The records here are built by `coach.record` out of a state written by hand,
rather than spelled out as dictionaries. A hand-written record would be a
second copy of that shape, and the day the two disagreed these tests would go
on passing against a record the graph no longer produces.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from types import EllipsisType
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage

from conftest import enrich, make_exercise
from trainer import evaluation, tools
from trainer import plan as plans
from trainer.coach import models, planner
from trainer.coach import record as run_record
from trainer.engine import catalog, database, exclusions, methodology, migrations
from trainer.engine.exclusions import Exclusion

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


def one(*items: plans.PlanItem, rounds: int = 8, rest: int = 150) -> plans.PlanBlock:
    return plans.PlanBlock(
        items=list(items), rounds=rounds, rest=rest, reason="because"
    )


def spoke(
    input_tokens: int = 0,
    output_tokens: int = 0,
    calls: tuple[str, ...] = (),
    dollars: float | None = None,
) -> AIMessage:
    """One turn of the model, as the record reads it back."""
    return AIMessage(
        content="",
        response_metadata={} if dollars is None else {"cost": dollars},
        tool_calls=[
            {"name": name, "args": {}, "id": f"call_{name}", "type": "tool_call"}
            for name in calls
        ],
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def ran(
    *blocks: plans.PlanBlock,
    despite: list[plans.Acknowledgement] | None = None,
    refusals: list[tuple[plans.Violation, ...]] | None = None,
    messages: list[AIMessage] | None = None,
    plan: plans.Mesocycle | None | EllipsisType = ...,
    request: plans.Request = LEGS_AND_CORE,
    **overrides: Any,
) -> evaluation.Ran:
    """One run of the graph, in the terms the checks read: a one-workout mesocycle.

    The record is built by `coach.record` out of a state, so what these tests
    assert against is the shape the graph actually produces. `plan` is left
    out to build one from `blocks`, and given as `None` for the run whose
    emission never parsed as a mesocycle at all.
    """
    emitted: plans.Mesocycle | None
    if isinstance(plan, EllipsisType):
        emitted = cycle_of(plans.WorkoutPlan(blocks=list(blocks), despite=despite or []))
    else:
        emitted = plan
    attempts = refusals if refusals is not None else [()]
    state = {
        "plan": emitted,
        "violations": attempts[-1] if attempts else (),
        "refusals": attempts,
        "messages": messages or [],
        "timings": [],
    }
    base: dict[str, Any] = {
        "record": run_record.of(state, tools.CALL_BUDGET),
        "request": plans.MesocycleRequest(slots=(request,)),
        "plan": emitted,
        "spent": 2,
        "seconds": 1.0,
    }
    base.update(overrides)
    return evaluation.Ran(**base)


def cycle_of(*workouts: plans.WorkoutPlan) -> plans.Mesocycle:
    return plans.Mesocycle(workouts=list(workouts), cycles=4, why="settle the loads")


def situation(*slots: plans.Request) -> evaluation.Situation:
    return evaluation.Situation(name="a-situation", describes="one", slots=slots)


def failing(
    connection: sqlite3.Connection, request: plans.Request, run: evaluation.Ran
) -> dict[str, str]:
    return dict(evaluation.check(connection, situation(request), run))


def rendered(report: evaluation.Report) -> str:
    return "\n".join(evaluation.render(report, (situation(LEGS_AND_CORE),)))


# -- the six situations are data ----------------------------------------------


def test_the_six_situations_are_declared(connection: sqlite3.Connection) -> None:
    """A seventh is a row, not a code change."""
    declared = evaluation.situations(connection)

    assert len(declared) == 6
    assert len({s.name for s in declared}) == 6
    for found in declared:
        assert found.describes, f"{found.name} does not say what it is for"


def test_every_situation_plans_for_a_goal_the_methodology_has(
    connection: sqlite3.Connection,
) -> None:
    """A request from a door always carries the declared goal, so the suite measures one that does."""
    for found in evaluation.situations(connection):
        for asked in found.slots:
            assert asked.goal in methodology.goals(), found.name


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

    preferences = half.slots[0].preferences
    assert preferences
    for exercise_id in preferences:
        assert catalog.exercise(connection, exercise_id) is not None


def test_every_situation_asks_for_a_mesocycle_of_the_split(
    connection: sqlite3.Connection,
) -> None:
    """No door asks for a lone workout, so neither does the suite (10.5)."""
    for found in evaluation.situations(connection):
        assert len(found.slots) == len(evaluation.SPLIT), found.name
        assert isinstance(found.request, plans.MesocycleRequest)


def test_a_situations_preferences_are_the_same_in_every_slot(
    connection: sqlite3.Connection,
) -> None:
    """The mesocycle brief reads the user's preferences off the first slot,
    so a preference set only on a later one would be one the model never saw."""
    for found in evaluation.situations(connection):
        assert len({asked.preferences for asked in found.slots}) == 1, found.name


# -- each invariant, on its own -----------------------------------------------


def test_a_plan_that_holds_everything_fails_nothing(
    connection: sqlite3.Connection,
) -> None:
    run = ran(one(item("Bodyweight_Squat")), one(item("Plank")))

    assert failing(connection, LEGS_AND_CORE, run) == {}


def test_a_plan_over_the_time_fails_the_clock(connection: sqlite3.Connection) -> None:
    run = ran(one(item("Bodyweight_Squat"), rounds=99, rest=180))

    broke = failing(connection, LEGS_AND_CORE, run)

    assert "time" in broke
    assert "against a budget of 45" in broke["time"]


def test_an_exercise_outside_the_set_fails_the_constraints(
    connection: sqlite3.Connection,
) -> None:
    run = ran(one(item("Barbell_Curl")), one(item("Plank")))

    broke = failing(connection, LEGS_AND_CORE, run)

    assert "constraints" in broke
    assert "Barbell_Curl" in broke["constraints"]


def test_the_wrong_equipment_fails_on_its_own_axis(
    connection: sqlite3.Connection,
) -> None:
    """Checked apart from the admissible set although the set filters on it:
    a fault in the filter would otherwise pass both."""
    run = ran(one(item("Barbell_Curl")))

    broke = failing(connection, LEGS_AND_CORE, run)

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
    run = ran(one(item("Bodyweight_Squat")), one(item("Plank")))

    broke = failing(connection, request, run)

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
    run = ran(
        one(item("Bodyweight_Squat")),
        one(item("Plank")),
        despite=[said("Bodyweight_Squat", "nothing else loads the knee today")],
    )

    assert "preferences" not in failing(connection, request, run)


def test_an_empty_plan_fails_termination(connection: sqlite3.Connection) -> None:
    """The schema guarantees a plan object; what it does not guarantee is that
    the model put anything in it."""
    run = ran(one(item("Plank")))
    assert run.plan is not None
    run.plan.workouts[0].blocks.clear()

    assert "terminates" in failing(connection, LEGS_AND_CORE, run)


def test_a_run_that_emitted_nothing_that_parses_fails_termination(
    connection: sqlite3.Connection,
) -> None:
    """The graph records `plan: null` when what came back is not a plan at all.
    Read as *no exercises prescribed*, that run would hold every invariant
    about what it prescribed and pass."""
    run = ran(plan=None, refusals=[(plans.Violation(plans.SHAPE, "not a plan"),)])

    broke = failing(connection, LEGS_AND_CORE, run)

    assert "terminates" in broke
    assert "parses" in broke["terminates"]


def test_more_attempts_than_the_graph_allows_fails_termination(
    connection: sqlite3.Connection,
) -> None:
    """The bound is the graph's, and a run past it is a loop that did not stop
    where it was built to."""
    run = ran(one(item("Plank")), refusals=[()] * (planner.ATTEMPTS + 1))

    assert "terminates" in failing(connection, LEGS_AND_CORE, run)


# -- invariant 6, the one that had to be defined ------------------------------


def test_a_group_the_workout_was_asked_for_and_never_trained_degenerates(
    connection: sqlite3.Connection,
) -> None:
    """The muscle axis: *am I touching this at all*. A leg-and-core day with
    no core in it."""
    run = ran(one(item("Bodyweight_Squat")), one(item("Lunge")))

    broke = failing(connection, LEGS_AND_CORE, run)

    assert "not degenerate" in broke
    assert "core" in broke["not degenerate"]


def test_one_movement_pattern_out_of_several_available_degenerates(
    connection: sqlite3.Connection,
) -> None:
    """The pattern axis: *am I balanced*. An arm workout made entirely of
    curls is invisible on the muscle axis, because biceps, triceps and
    forearms are one bucket there (ADR-0001)."""
    legs = plans.Request(equipment=("body only",), budget_min=45, groups=("legs",))
    run = ran(one(item("Bodyweight_Squat")))

    broke = failing(connection, legs, run)

    assert "not degenerate" in broke
    assert "patterns available" in broke["not degenerate"]


def test_two_movement_patterns_is_enough(connection: sqlite3.Connection) -> None:
    legs = plans.Request(equipment=("body only",), budget_min=45, groups=("legs",))
    run = ran(one(item("Bodyweight_Squat")), one(item("Lunge")))

    assert "not degenerate" not in failing(connection, legs, run)


def test_a_group_nothing_could_have_trained_is_not_a_failure(
    connection: sqlite3.Connection,
) -> None:
    """The escape clause, and the reason 100% is a bar the agent can clear: if
    the admissible set offers nothing for a group, a plan that reflects that is
    the only honest answer, and failing it would measure the catalog."""
    with_back = plans.Request(
        equipment=("body only",), budget_min=45, groups=("legs", "core", "back")
    )
    run = ran(one(item("Bodyweight_Squat")), one(item("Lunge")), one(item("Plank")))

    broke = failing(connection, with_back, run)

    assert "not degenerate" not in broke, broke.get("not degenerate")


def test_one_pattern_is_not_a_failure_when_one_is_all_there_was(
    connection: sqlite3.Connection,
) -> None:
    """Same clause on the other axis."""
    core = plans.Request(equipment=("body only",), budget_min=45, groups=("core",))
    run = ran(one(item("Plank")))

    assert "not degenerate" not in failing(connection, core, run)


def test_the_ratio_of_compound_to_isolation_is_not_an_invariant(
    connection: sqlite3.Connection,
) -> None:
    """Against the real catalog the arms group is seventy isolation exercises
    to twelve compound, so any majority-compound rule fails a correct arm day.
    In a measurement whose bar is 100%, an invariant that can be wrong is worse
    than one that is weak."""
    core = plans.Request(equipment=("body only",), budget_min=45, groups=("core",))
    all_isolation = ran(one(item("Plank"), rounds=16))

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
    run = ran(one(item("Barbell_Curl"), rounds=99, rest=180))

    assert len(failing(connection, LEGS_AND_CORE, run)) >= 3


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

    printed = rendered(report)

    assert "a-situation" in printed
    assert "time" in printed
    assert str(written) in printed
    assert "0%" in printed
    assert printed.isascii()


def test_the_report_says_what_the_pass_cost(connection: sqlite3.Connection) -> None:
    """So the price of re-running it after a prompt change is known."""
    run = ran(
        one(item("Plank")),
        messages=[spoke(input_tokens=1200, output_tokens=90, calls=("admissible_set",))],
    )
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, record=run),))

    printed = rendered(report)

    assert "1 tool calls" in printed
    assert "1200 tokens in" in printed
    assert "90 out" in printed


def test_the_pass_says_what_it_cost_in_dollars_and_seconds_a_run(
    connection: sqlite3.Connection,
) -> None:
    runs = [
        ran(one(item("Plank")), messages=[spoke(dollars=0.03)], seconds=10.0),
        ran(one(item("Plank")), messages=[spoke(dollars=0.01)], seconds=30.0),
    ]
    report = evaluation.Report(
        tuple(evaluation.Outcome("a-situation", n, record=r) for n, r in enumerate(runs))
    )

    printed = rendered(report)

    assert report.dollars == pytest.approx(0.04)
    assert "$0.0400 in all, $0.0200 a run, 20.0s a run" in printed


def test_a_pass_no_run_priced_says_not_reported(connection: sqlite3.Connection) -> None:
    run = ran(one(item("Plank")), messages=[spoke()], seconds=5.0)
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, record=run),))

    printed = rendered(report)

    assert report.dollars is None
    assert "dollars not reported by the provider, 5.0s a run" in printed


def test_a_pass_partly_priced_names_the_runs_it_could_not_price(
    connection: sqlite3.Connection,
) -> None:
    runs = [
        ran(one(item("Plank")), messages=[spoke(dollars=0.02)]),
        ran(one(item("Plank")), messages=[spoke()]),
    ]
    report = evaluation.Report(
        tuple(evaluation.Outcome("a-situation", n, record=r) for n, r in enumerate(runs))
    )

    printed = rendered(report)

    assert "$0.0200 over 1 of 2 runs (1 not reported), $0.0200 a run" in printed


# -- what the planner itself cost ---------------------------------------------


def test_the_matrix_says_what_each_run_took(connection: sqlite3.Connection) -> None:
    """*It held every invariant* and *it held them on the third attempt, in
    four minutes* are different answers to whether this model can plan on this
    laptop."""
    run = ran(
        one(item("Plank")),
        refusals=[(plans.Violation(plans.ADMISSIBLE, "no"),), ()],
        seconds=42.0,
        spent=7,
    )
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, record=run),))

    printed = rendered(report)

    assert "attempts" in printed
    assert "seconds" in printed
    assert "42" in printed, printed
    assert "7" in printed, printed


def test_a_run_still_refused_at_the_last_attempt_names_the_rule(
    connection: sqlite3.Connection,
) -> None:
    """*It failed* is a fact the matrix already has. Which rule was still
    standing when the attempts ran out is what says whether the model was
    close."""
    run = ran(
        one(item("Barbell_Curl")),
        refusals=[(plans.Violation(plans.ADMISSIBLE, "it needs a barbell"),)],
    )
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, record=run),))

    assert plans.ADMISSIBLE in rendered(report)


def test_a_run_that_was_never_made_leaves_the_planner_columns_blank(
    connection: sqlite3.Connection,
) -> None:
    """It holds no figures because it produced none, and a zero there would
    read as a run that took no time."""
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, error="no key"),))

    printed = rendered(report)

    assert evaluation.NOT_RUN in printed
    assert printed.isascii()


def test_the_runs_figures_are_each_shown_rather_than_averaged(
    connection: sqlite3.Connection,
) -> None:
    """A situation that needs one attempt twice and three once is a different
    fact from one that always needs two, and a mean prints them the same."""
    once = ran(one(item("Plank")), refusals=[()])
    thrice = ran(one(item("Plank")), refusals=[(), (), ()])
    report = evaluation.Report(
        (
            evaluation.Outcome("a-situation", 1, record=once),
            evaluation.Outcome("a-situation", 2, record=thrice),
        )
    )

    assert "1, 3" in rendered(report)


def test_a_run_that_spent_more_than_its_budget_is_reported_not_failed(
    connection: sqlite3.Connection,
) -> None:
    """A turn's calls are answered as a whole batch, so a turn asking for seven
    at once ends at *16 of 12* -- observed on Groq in ticket 04. The number is
    worth seeing; it is not a run to fail, and the matrix shows what was
    actually spent."""
    over = ran(one(item("Bodyweight_Squat")), one(item("Plank")), spent=16)
    report = evaluation.Report((evaluation.Outcome("a-situation", 1, record=over),))

    assert "terminates" not in failing(connection, LEGS_AND_CORE, over)
    assert "16" in rendered(report)


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
    assert evaluation.NOT_RUN in rendered(report)


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

    printed = rendered(report)

    assert evaluation.VALIDATOR in printed
    assert "1 failed" in printed


def test_the_percentage_never_rounds_up_to_a_pass() -> None:
    """At 249 of 250 a rounded figure prints 100% on the line above *the bar
    is 100%*, and then exits non-zero -- the one number this command exists to
    produce, contradicting itself."""
    outcomes = tuple(held("a", n) for n in range(249)) + (broke("a", 249),)
    report = evaluation.Report(outcomes)

    printed = rendered(report)

    assert report.passed is False
    assert "99%" in printed
    assert "-- 100%" not in printed


def test_the_cost_counts_the_run_that_was_only_made_to_be_turned_down(
    connection: sqlite3.Connection,
) -> None:
    """The refusal situation makes two runs. Only the second is measured; both
    are on the bill, and this number is what a pass is budgeted against."""
    turned_down = ran(
        one(item("Plank")), messages=[spoke(input_tokens=1000, output_tokens=100)]
    )
    measured = ran(
        one(item("Plank")), messages=[spoke(input_tokens=2000, output_tokens=200)]
    )
    report = evaluation.Report(
        (evaluation.Outcome("refused", 1, record=measured, also=(turned_down,)),)
    )

    assert report.input_tokens == 3000
    assert report.output_tokens == 300


# --- the measurement never writes --------------------------------------------


def test_the_measurement_leaves_the_workout_count_unchanged(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """`trainer eval` runs eighteen graph invocations against the project
    database. A plan that persisted from inside the graph would write eighteen
    phantom prescribed workouts into the very state the measurement is taken
    from, where the unreported-workout tool would read them as a skipped
    rotation. ROADMAP.md § Session 5: writes are never tools."""
    from test_planner import Scripted, plan_of

    chosen = evaluation.situations(connection)[:2]
    both = cycle_of(plan_of("Bodyweight_Squat"), plan_of("Bodyweight_Squat"))
    on = models.Chat(Scripted(documents=[both] * 10), "scripted", "a-stand-in")

    report = evaluation.run(
        connection,
        chosen,
        on=on,
        repetitions=1,
        records=tmp_path / "records",
    )

    assert report.total == len(chosen)
    assert connection.execute(
        "SELECT COUNT(*) AS total FROM workouts"
    ).fetchone()["total"] == 0


def test_a_setup_run_with_no_plan_is_not_measured_as_the_situation(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Situation 5 is *the user refuses and it proposes again*, and it needs a
    first plan to refuse. When that run emits nothing that parses, `refused`
    is `None` -- and the brief then says nothing about a refusal at all, not
    even the user's reason, which is nested under it. The second run would be
    an ordinary planning run, and counting it here would put a green row under
    a situation that never happened."""
    from test_planner import Scripted

    (refusal,) = [s for s in evaluation.situations(connection) if s.after_a_refusal]
    on = models.Chat(
        Scripted(raw=["I would start with squats."] * 10), "scripted", "a-stand-in"
    )

    report = evaluation.run(
        connection, (refusal,), on=on, repetitions=1, records=tmp_path / "records"
    )

    (outcome,) = report.outcomes
    assert outcome.held is False
    assert outcome.error is not None
    assert "nothing to refuse" in outcome.error
    assert outcome.also, "the run that was paid for is still counted"


def test_every_run_leaves_the_record_the_failure_names(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """*Invariant 3 failed* is a fact and the record is the only thing that
    says why, so the file has to be there whichever way the run went."""
    from test_planner import Scripted, plan_of

    chosen = evaluation.situations(connection)[:1]
    both = cycle_of(plan_of("Bodyweight_Squat"), plan_of("Bodyweight_Squat"))
    on = models.Chat(Scripted(documents=[both] * 5), "scripted", "a-stand-in")

    report = evaluation.run(
        connection, chosen, on=on, repetitions=1, records=tmp_path / "records"
    )

    (outcome,) = report.outcomes
    assert outcome.written is not None
    assert outcome.written.exists()
    assert "provider" in outcome.written.read_text(encoding="utf-8")


def test_the_database_the_model_reads_is_the_one_the_environment_names(
    database_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLAUDE.md's standing rule. The tools open their own connection from
    `TRAINER_DB`, so a fixture nothing points at is invisible to the agent --
    and the pass measures a model answering *there is no such workout*."""
    monkeypatch.delenv(database.DATABASE_ENV_VAR, raising=False)
    monkeypatch.chdir(database_file.parent)

    with evaluation.pointed_at_the_database() as pointed:
        import os

        assert os.environ[database.DATABASE_ENV_VAR] == str(pointed)
        assert pointed.is_absolute()

    import os

    assert database.DATABASE_ENV_VAR not in os.environ


def test_a_spent_quota_stops_the_pass_and_says_so(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """On 2026-09-21 Groq's free day ran out after 11 of 90 runs. The other 79
    went out anyway, each refused the same way, and the pass ended calling the
    10% it came to a bug -- about a quota."""
    from conftest import Exhausted

    model = Exhausted()
    chosen = evaluation.situations(connection)[:2]

    report = evaluation.run(
        connection,
        chosen,
        on=models.Chat(cast(Any, model), "groq", "qwen/qwen3.8-27b"),
        repetitions=2,
        records=tmp_path / "records",
    )

    assert model.calls == 1
    assert report.total == 4 and report.held == 0
    assert report.stopped is not None and "daily" in report.stopped
    printed = "\n".join(
        evaluation.failures(report) + evaluation.totals(report, "held")
    )
    assert report.stopped in printed
    assert "a bug" not in printed
    assert printed.count(report.stopped) == 1, "said once, not once per run"


# -- a mesocycle is checked workout by workout ---------------------------------


UPPER = plans.Request(equipment=("body only",), budget_min=45, groups=("chest",))


def test_a_failure_names_the_workout_it_is_in(connection: sqlite3.Connection) -> None:
    """Five workouts are five chances to break a rule, and *time failed* does
    not say which one to go and read."""
    good = plans.WorkoutPlan(blocks=[one(item("Bodyweight_Squat")), one(item("Plank"))])
    over = plans.WorkoutPlan(blocks=[one(item("Plank"), rounds=99, rest=180)])
    run = ran(plan=cycle_of(good, over))

    broke = dict(evaluation.check(connection, situation(LEGS_AND_CORE, UPPER), run))

    assert broke["time"].startswith("workout 2: ")


def test_every_workout_is_checked_not_only_the_first(
    connection: sqlite3.Connection,
) -> None:
    good = plans.WorkoutPlan(blocks=[one(item("Bodyweight_Squat")), one(item("Plank"))])
    barbell = plans.WorkoutPlan(blocks=[one(item("Barbell_Curl"))])
    run = ran(plan=cycle_of(good, barbell))

    broke = dict(evaluation.check(connection, situation(LEGS_AND_CORE, UPPER), run))

    assert "workout 2" in broke["equipment"]


def test_a_workout_missing_for_a_slot_fails_termination(
    connection: sqlite3.Connection,
) -> None:
    run = ran(one(item("Bodyweight_Squat")), one(item("Plank")))

    broke = dict(evaluation.check(connection, situation(LEGS_AND_CORE, UPPER), run))

    assert broke == {"terminates": "it emitted 1 workouts for 2 slots"}


def test_the_refused_situation_briefs_the_mesocycle_it_turned_down(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Situation 5 on a mesocycle: the second run is told what was turned down and why."""
    from test_planner import Scripted, plan_of

    (refusal,) = [s for s in evaluation.situations(connection) if s.after_a_refusal]
    first = cycle_of(plan_of("Bodyweight_Squat"), plan_of("Plank"))
    second = cycle_of(plan_of("Lunge"), plan_of("Plank"))
    model = Scripted(documents=[*[first] * 3, *[second] * 3])

    report = evaluation.run(
        connection,
        (refusal,),
        on=models.Chat(model, "scripted", "a-stand-in"),
        repetitions=1,
        records=tmp_path / "records",
    )

    (outcome,) = report.outcomes
    assert len(outcome.also) == 1
    briefed = "\n".join(message.text for message in model.seen[-1])
    assert "turned each one down" in briefed
    assert evaluation.TURNED_DOWN_BECAUSE in briefed


def test_a_standing_exclusion_reaches_every_slot_the_model_plans(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """A door folds today's exclusions into each slot; a suite that did not
    would measure a space no user is ever planned against."""
    from test_planner import Scripted, plan_of

    exclusions.add(connection, Exclusion("pattern", "squat"), "2099-01-01")
    connection.commit()
    chosen = evaluation.situations(connection)[:1]
    both = cycle_of(plan_of("Lunge"), plan_of("Plank"))

    report = evaluation.run(
        connection,
        chosen,
        on=models.Chat(Scripted(documents=[both] * 5), "scripted", "a-stand-in"),
        repetitions=1,
        records=tmp_path / "records",
    )

    (outcome,) = report.outcomes
    assert isinstance(outcome.record, evaluation.Ran)
    for asked in outcome.record.request.slots:
        assert Exclusion("pattern", "squat") in asked.exclusions
