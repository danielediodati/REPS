"""The onboarding suite: scripted users driven by code against a scripted model, and every check it decides."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from conftest import enrich
from test_planner import CATALOG, PATTERNS, Scripted
from trainer import evaluation, onboarding_evaluation, onboarding_set
from trainer.coach import conclusions, entrance, models, onboarding
from trainer.engine import catalog, database, migrations

SET = """\
today = "2026-10-01"

[bars]
on_time = 80
remembered = 80
routed = 80

[[cases]]
name = "terse"
kind = "interview"
describes = "two answers"
opens = "ciao"
replies = [
  { fields = ["goal", "equipment"], says = "massa, con un bilanciere. odio correre" },
  { fields = ["cycle_length", "split", "duration_cap_min"], says = "due, gambe e spalle, 45 minuti" },
]
afterwards = ["il ginocchio si lamenta"]
otherwise = "no"
remembers = ["odio correre"]

[[cases]]
name = "away"
kind = "interview"
describes = "comes back the next day"
opens = "ciao"
replies = [
  { fields = ["goal", "equipment"], says = "massa, con un bilanciere" },
  { fields = ["cycle_length", "split", "duration_cap_min"], says = "due, gambe e spalle, 45 minuti" },
]
pause_after = 1
back = "eccomi, dove eravamo?"
otherwise = "no"

[[cases]]
name = "bought"
kind = "change"
describes = "equipment bought"
opens = "ho preso dei manubri"
before = { cycle_length = 2, duration_cap_min = 45, split = [["legs"], ["shoulders"]], equipment = ["barbell"], goal = "hypertrophy" }
changes = ["equipment"]
open = ["keep", "rewrite"]
otherwise = "si"

[[cases]]
name = "gym"
kind = "route"
describes = "equipment from now on"
opens = "mi sono iscritto in palestra"
routed = "change_declaration"
"""

GOAL_AND_GEAR = {"goal": "hypertrophy", "equipment": ["barbell"]}
THE_REST = {"cycle_length": 2, "split": [["legs"], ["shoulders"]], "duration_cap_min": 45}


@pytest.fixture()
def source(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, PATTERNS)
        yield opened


@pytest.fixture()
def holds() -> onboarding_set.OnboardSet:
    return onboarding_set.parse(SET)


@pytest.fixture()
def where(
    source: sqlite3.Connection, holds: onboarding_set.OnboardSet
) -> Iterator[onboarding_evaluation.Fixture]:
    with onboarding_evaluation.prepared(source, holds) as prepared:
        yield prepared


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


def chat(*turns: AIMessage) -> models.Chat:
    return models.Chat(Scripted(turns=list(turns)), "scripted", "a-stand-in")


def ran(
    where: onboarding_evaluation.Fixture,
    case: onboarding_set.Case,
    tmp_path: Path,
    *turns: AIMessage,
) -> evaluation.Report:
    on = chat(*turns)
    return onboarding_evaluation.run(
        where, [case], talks=on, front=on, repetitions=1, records=tmp_path / "records"
    )


def case_of(holds: onboarding_set.OnboardSet, name: str) -> onboarding_set.Case:
    return next(case for case in holds.cases if case.name == name)


def failed(report: evaluation.Report, case: str) -> list[str]:
    (outcome,) = [o for o in report.outcomes if o.case == case]
    assert outcome.error is None, outcome.error
    return [name for name, _ in outcome.failures]


def test_the_fixture_is_the_one_trainer_db_names_and_holds_nothing_declared(
    where: onboarding_evaluation.Fixture,
) -> None:
    import os

    assert os.environ[database.DATABASE_ENV_VAR] == str(where.path)
    assert where.connection.execute("SELECT COUNT(*) FROM declarations").fetchone()[0] == 0


def test_a_persona_answered_by_its_replies_holds_every_check_and_its_memory(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "terse"),
        tmp_path,
        says("Per cosa ti alleni, e con cosa?"),
        calls(
            (onboarding.DECLARE, GOAL_AND_GEAR),
            (conclusions.REMEMBER, {"conclusion": "non ama correre", "quote": "odio correre"}),
        ),
        says("Quanti allenamenti, cosa e quanto tempo?"),
        calls((onboarding.DECLARE, THE_REST)),
        says("Qualche movimento ti dà fastidio?"),
        says("Altro?"),
        calls((onboarding.FINISH, {})),
    )

    assert failed(report, "terse") == []
    assert failed(report, "terse remembers") == []
    (outcome,) = [o for o in report.outcomes if o.case == "terse"]
    assert isinstance(outcome.record, onboarding_evaluation.Talked)
    assert ("user", "il ginocchio si lamenta") in outcome.record.conversation
    assert ("user", "no") in outcome.record.conversation
    assert outcome.written is not None and outcome.written.exists()


def test_a_reply_the_model_did_not_declare_is_given_again_and_counted_as_declared_late(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "terse"),
        tmp_path,
        says("Per cosa ti alleni, e con cosa?"),
        says("E quanti allenamenti, e quanto tempo?"),
        says("Scusa, per cosa ti alleni?"),
        calls((onboarding.DECLARE, GOAL_AND_GEAR | THE_REST), (onboarding.FINISH, {})),
    )

    assert failed(report, "terse") == []
    assert failed(report, "terse on time") == [onboarding_evaluation.LATE]
    assert failed(report, "terse remembers") == [onboarding_evaluation.REMEMBERED]


def test_a_persona_gives_what_it_has_not_said_before_repeating_an_undeclared_reply(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    """A model that sits on an answer and asks about the next field gets the next answer, not the old one."""
    report = ran(
        where,
        case_of(holds, "terse"),
        tmp_path,
        says("Per cosa ti alleni, e con cosa?"),
        says("E quanti allenamenti, e quanto tempo?"),
        calls((onboarding.DECLARE, GOAL_AND_GEAR | THE_REST), (onboarding.FINISH, {})),
    )

    assert failed(report, "terse") == []
    (outcome,) = [o for o in report.outcomes if o.case == "terse"]
    assert isinstance(outcome.record, onboarding_evaluation.Talked)
    said = [line for who, line in outcome.record.conversation if who == "user"]
    assert said[1:] == [reply.says for reply in case_of(holds, "terse").replies]


def test_an_interview_that_never_finishes_fails_filled(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "terse"),
        tmp_path,
        *[says(f"E poi? ({n})") for n in range(onboarding_evaluation.MAX_ANSWERS + 2)],
    )

    assert onboarding_evaluation.FILLED in failed(report, "terse")


def test_a_paused_persona_comes_back_to_a_graph_built_again(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "away"),
        tmp_path,
        says("Per cosa ti alleni, e con cosa?"),
        calls((onboarding.DECLARE, GOAL_AND_GEAR)),
        says("Quanti allenamenti?"),
        says("Ciao di nuovo! Quanti allenamenti, cosa e quanto tempo?"),
        calls((onboarding.DECLARE, THE_REST), (onboarding.FINISH, {})),
    )

    assert failed(report, "away") == []
    (outcome,) = [o for o in report.outcomes if o.case == "away"]
    assert isinstance(outcome.record, onboarding_evaluation.Talked)
    assert ("user", "eccomi, dove eravamo?") in outcome.record.conversation


def test_a_change_holds_when_it_picks_an_open_path_and_changes_only_its_field(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "bought"),
        tmp_path,
        calls((onboarding.DECLARE, {"equipment": ["barbell", "dumbbell"]}), (onboarding.FINISH, {})),
        calls((onboarding.CHOOSE, {"path": "keep", "why": "Va bene così."})),
    )

    assert failed(report, "bought") == []


def test_a_change_that_touches_another_field_fails_only_changed(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "bought"),
        tmp_path,
        calls(
            (onboarding.DECLARE, {"equipment": ["barbell", "dumbbell"], "duration_cap_min": 60}),
            (onboarding.FINISH, {}),
        ),
        calls((onboarding.CHOOSE, {"path": "rewrite", "why": "Riscrivo."})),
    )

    assert failed(report, "bought") == [onboarding_evaluation.ONLY]


def test_a_message_handed_where_its_row_says_holds_and_elsewhere_fails_routed(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    gym = case_of(holds, "gym")

    right = ran(where, gym, tmp_path, calls((entrance.CHANGE_DECLARATION, {"said": gym.opens})), says("Aggiorno."))
    wrong = ran(where, gym, tmp_path, calls((entrance.ADAPT_THIS_WORKOUT, {"said": gym.opens})), says("Adatto oggi."))

    assert failed(right, "gym") == []
    assert failed(wrong, "gym") == [onboarding_evaluation.ROUTED]


def test_a_quota_spent_on_the_interviews_counts_every_route_as_a_run_not_made(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    class Spent(Scripted):
        def _generate(self, *args: Any, **kwargs: Any) -> Any:
            raise models.QuotaSpent("the day's quota is spent")

    on = models.Chat(Spent(), "scripted", "a-stand-in")

    report = onboarding_evaluation.run(
        where,
        [case_of(holds, "bought"), case_of(holds, "gym")],
        talks=on,
        front=on,
        repetitions=2,
        records=tmp_path / "records",
    )

    routed = [o for o in report.outcomes if o.case == "gym"]
    assert report.stopped is not None
    assert len(routed) == 2 and all(o.skipped for o in routed)


def test_a_memory_below_its_bar_fails_the_pass_while_the_held_half_holds(
    holds: onboarding_set.OnboardSet,
) -> None:
    report = evaluation.Report(
        (
            evaluation.Outcome("terse", 1),
            evaluation.Outcome("terse remembers", 1, ((onboarding_evaluation.REMEMBERED, "no"),)),
        )
    )

    barred = onboarding_evaluation.barred(report, holds)

    held, _, remembered, _ = barred.halves
    assert barred.of(held).held == 1
    assert not barred.passed


def test_the_rendered_pass_is_ascii_with_a_matrix_per_kind(
    where: onboarding_evaluation.Fixture, holds: onboarding_set.OnboardSet, tmp_path: Path
) -> None:
    report = ran(
        where,
        case_of(holds, "bought"),
        tmp_path,
        calls((onboarding.DECLARE, {"equipment": ["barbell", "dumbbell"]}), (onboarding.FINISH, {})),
        calls((onboarding.CHOOSE, {"path": "keep", "why": "Va bene."})),
    )

    lines = onboarding_evaluation.render(onboarding_evaluation.barred(report, holds), [case_of(holds, "bought")])

    text = "\n".join(lines)
    assert "changes" in text and onboarding_evaluation.ONLY in text
    assert "per onboarding:" in text
    assert text.isascii()


def test_a_change_whose_before_the_catalog_cannot_hold_is_a_problem_before_any_run(
    source: sqlite3.Connection,
) -> None:
    broken = onboarding_set.parse(SET.replace('equipment = ["barbell"]', 'equipment = ["anvil"]'))

    assert any("anvil" in said for said in onboarding_evaluation.problems(source, broken))
