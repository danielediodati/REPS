"""The runner every eval suite goes through, driven by a suite that calls no model."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from trainer import eval_runner
from trainer.coach import models
from trainer.engine import database

AFTER = " after"
"""Appended to a case's name for the outcome of the graph run after it."""


@dataclass(frozen=True)
class Case:
    name: str


Script = Callable[[str, int], eval_runner.Scored]
"""What one attempt at a case does: score a run, or raise as a provider would."""


def held(_name: str, _attempt: int) -> eval_runner.Scored:
    return eval_runner.Scored(eval_runner.Recorded({"calls": [1], "tokens": {"input": 10, "output": 1}}, 0.0))


class Fake(eval_runner.Suite[Case, eval_runner.Copy]):
    """Cases `a`, `b` and `c`, each followed by a second graph whose outcome is `<name> after`."""

    def __init__(self, script: Script = held, after: Script = held) -> None:
        super().__init__([Case("a"), Case("b"), Case("c")])
        self.script = script
        self.after = after

    def fixture(self, connection: sqlite3.Connection) -> AbstractContextManager[eval_runner.Copy]:
        return eval_runner.copied(connection)

    def chats(self, chosen: Sequence[Case]) -> Mapping[str, models.Chat]:
        return {"model": models.Chat(cast(Any, None), "scripted", "a-stand-in")}

    def runs(
        self, where: eval_runner.Copy, chats: Mapping[str, models.Chat], *, records: Path, budget: int
    ) -> eval_runner.Once[Case]:
        def once(case: Case, attempt: int) -> tuple[eval_runner.Outcome, ...]:
            own = eval_runner.attempted(
                case.name, attempt, records, f"{case.name}-{attempt}", lambda: self.script(case.name, attempt)
            )
            then = eval_runner.attempted(
                case.name + AFTER,
                attempt,
                records,
                f"{case.name}-{attempt}-after",
                lambda: self.after(case.name, attempt),
                typed=True,
            )
            return (own, then)

        return once

    def halves(self) -> tuple[eval_runner.Half, ...]:
        return (
            eval_runner.Half("own", frozenset("abc"), 100),
            eval_runner.Half("after", frozenset(name + AFTER for name in "abc"), 50),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[Case]) -> list[str]:
        return eval_runner.totals(report, "held")


@pytest.fixture()
def source(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(tmp_path / "source.sqlite")) as opened:
        yield opened


def measured(suite: Fake, where: sqlite3.Connection, records: Path, repetitions: int = 1) -> eval_runner.Report:
    _lines, report = eval_runner.run(suite, where, repetitions=repetitions, records=records)
    return report


def test_a_spent_quota_stops_the_pass_and_every_run_left_is_not_made(
    source: sqlite3.Connection, tmp_path: Path
) -> None:
    def script(name: str, attempt: int) -> eval_runner.Scored:
        if (name, attempt) == ("b", 2):
            raise models.QuotaSpent("the day's quota is spent")
        return held(name, attempt)

    report = measured(Fake(script), source, tmp_path / "records", repetitions=2)

    made = [(o.case, o.attempt) for o in report.outcomes if not o.skipped]
    skipped = [(o.case, o.attempt) for o in report.outcomes if o.skipped]
    assert made == [("a", 1), ("a", 2), ("b", 1), ("a after", 1), ("a after", 2), ("b after", 1)]
    assert skipped == [("b", 2), ("c", 1), ("c", 2)]
    assert report.stopped == "the day's quota is spent"
    assert not report.passed


def test_a_run_that_errors_is_a_run_not_made_and_the_pass_goes_on(
    source: sqlite3.Connection, tmp_path: Path
) -> None:
    def script(name: str, attempt: int) -> eval_runner.Scored:
        if name == "a":
            raise models.ProviderFailed("the host went away", emitted=['{"half'])
        return held(name, attempt)

    def after(name: str, attempt: int) -> eval_runner.Scored:
        raise RuntimeError("no plan")

    report = measured(Fake(script, after), source, tmp_path / "records")

    by_case = {o.case: o for o in report.outcomes}
    assert by_case["a"].error == "the host went away" and not by_case["a"].held
    assert by_case["a after"].error == "RuntimeError: no plan", "said with its type when asked to"
    assert by_case["b"].held and by_case["c"].held
    lost = json.loads((tmp_path / "records" / "a-1-lost.json").read_text(encoding="utf-8"))
    assert lost == {"error": "the host went away", "emitted": ['{"half']}
    assert report.stopped is None


def test_a_second_graphs_outcomes_follow_the_cases_and_are_held_to_their_own_bar(
    source: sqlite3.Connection, tmp_path: Path
) -> None:
    def after(name: str, attempt: int) -> eval_runner.Scored:
        failures = (("followed", "no"),) if name == "a" else ()
        return eval_runner.Scored(held(name, attempt).run, failures)

    report = measured(Fake(after=after), source, tmp_path / "records")

    assert [o.case for o in report.outcomes] == ["a", "b", "c", "a after", "b after", "c after"]
    own, then = report.halves
    assert report.of(own).held == 3 and report.of(then).held == 2
    assert report.passed, "two of three is above the second graph's bar of 50%"
    assert report.calls == 6, "both graphs' runs are on the bill"
    assert sorted(path.name for path in (tmp_path / "records").iterdir())[:2] == ["a-1-after.json", "a-1.json"]


def test_trainer_db_is_put_back_and_the_copy_deleted_after_a_failure(
    source: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(database.DATABASE_ENV_VAR, "the-users-own.sqlite")
    seen: list[Path] = []

    class Broken(Fake):
        def runs(
            self, where: eval_runner.Copy, chats: Mapping[str, models.Chat], *, records: Path, budget: int
        ) -> eval_runner.Once[Case]:
            seen.append(where.path)
            assert os.environ[database.DATABASE_ENV_VAR] == str(where.path)
            raise RuntimeError("a bug in the suite")

    with pytest.raises(RuntimeError, match="a bug in the suite"):
        measured(Broken(), source, tmp_path / "records")

    assert os.environ[database.DATABASE_ENV_VAR] == "the-users-own.sqlite"
    (copy,) = seen
    assert not copy.exists()
