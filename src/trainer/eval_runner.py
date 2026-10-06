"""One runner for every eval suite: the fixture, the runs, the quota stop, the records and the bars.

A suite says what is particular to it: its cases, what its fixture holds, how
one run is made and scored, its bars and its columns. Everything around that
is here, once.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from trainer import tools
from trainer.coach import checkpoints, conclusions, memory, models
from trainer.coach import record as run_record
from trainer.engine import database, home

T = TypeVar("T")

REPETITIONS = 3
"""How many times each case runs, unless told otherwise: one run of a model measures nothing."""

VALIDATOR = "validator"
"""A column of a matrix: the validator refused for a reason no check names, which is worth seeing."""

NOT_RUN = "not run"
"""A column of every matrix: runs that never reached the provider, counted against the metric."""

RECORDS_ENV_VAR = "TRAINER_EVAL_RUNS"
"""Overrides where the records are written, the way `TRAINER_DB` does for the database."""

DEFAULT_RECORDS_NAME = "eval-runs"

USER = "eval"
"""Whose conclusions a run keeps, in its own store."""


def records_path() -> Path:
    """Where each run's record is written: a failure names the file."""
    override = os.environ.get(RECORDS_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return home.inside(DEFAULT_RECORDS_NAME)


class Refused(Exception):
    """A pass that cannot start, said as the state to fix."""


# -- what a run leaves ----------------------------------------------------------


class Costed(Protocol):
    """What the cost lines read off a run, whichever graph made it."""

    @property
    def calls(self) -> list[Any]: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    @property
    def dollars(self) -> float | None: ...

    @property
    def seconds(self) -> float: ...


@dataclass(frozen=True)
class Recorded:
    """One run of a graph: its run record, and the wall time somebody waited for it."""

    record: Mapping[str, Any]
    seconds: float

    @property
    def written(self) -> str:
        """The run as it is written down."""
        return run_record.document(self.record)

    @property
    def calls(self) -> list[Any]:
        return list(self.record["calls"])

    @property
    def input_tokens(self) -> int:
        return int(self.record["tokens"]["input"])

    @property
    def output_tokens(self) -> int:
        return int(self.record["tokens"]["output"])

    @property
    def dollars(self) -> float | None:
        dollars = self.record.get("dollars")
        return None if dollars is None else float(dollars)


@dataclass(frozen=True)
class Talked(Recorded):
    """A run written down with what was said in it."""

    conversation: tuple[tuple[str, str], ...] = ()

    @property
    def written(self) -> str:
        return json.dumps(
            {"conversation": [list(line) for line in self.conversation], "run": self.record},
            indent=2,
            ensure_ascii=False,
            default=str,
        )


@dataclass(frozen=True)
class Outcome:
    """One run of a case, and what held.

    `error` is a run that never finished: it holds nothing and counts against
    the metric in the *not run* column, not against any check.
    """

    case: str
    attempt: int
    failures: tuple[tuple[str, str], ...] = ()
    record: Costed | None = None
    written: Path | None = None
    error: str | None = None
    also: tuple[Costed, ...] = ()
    """Runs made to set this one up and not measured: they count towards the cost only."""

    weight: int = 1
    """How much a failure counts against the metric: two for false confidence, one otherwise."""

    skipped: bool = False
    """Never attempted: the pass stopped before it (`Report.stopped` says why)."""

    @property
    def held(self) -> bool:
        return self.error is None and not self.failures

    @property
    def records(self) -> tuple[Costed, ...]:
        return (*self.also, *((self.record,) if self.record else ()))


@dataclass(frozen=True)
class Half:
    """Rows scored together against a bar their set declares."""

    name: str
    cases: frozenset[str]
    bar: int


@dataclass(frozen=True)
class Report:
    outcomes: tuple[Outcome, ...] = field(default_factory=tuple)
    stopped: str | None = None
    """The state that ended the pass early, when one did."""
    halves: tuple[Half, ...] = ()
    """Declared bars, each over its own rows; none means every run must hold."""

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def held(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.held)

    @property
    def against(self) -> int:
        """What the percentage is out of: runs, plus one for every failure weighted double."""
        return sum(outcome.weight if not outcome.held else 1 for outcome in self.outcomes)

    @property
    def percentage(self) -> float:
        return 100.0 * self.held / self.against if self.against else 0.0

    @property
    def passed(self) -> bool:
        """Every declared bar, or 100% without one; and at least one run."""
        if not self.halves:
            return self.total > 0 and self.held == self.total
        return self.total > 0 and all(
            100 * self.of(half).held >= half.bar * self.of(half).against for half in self.halves
        )

    def of(self, half: Half) -> Report:
        """The runs of one half, as a report of their own."""
        return Report(tuple(outcome for outcome in self.outcomes if outcome.case in half.cases))

    @property
    def calls(self) -> int:
        return sum(len(r.calls) for r in self.runs)

    @property
    def input_tokens(self) -> int:
        """Every run that was paid for, measured or not."""
        return sum(r.input_tokens for r in self.runs)

    @property
    def output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.runs)

    @property
    def runs(self) -> tuple[Costed, ...]:
        """Every run that was paid for, measured or not."""
        return tuple(r for o in self.outcomes for r in o.records)

    @property
    def dollars(self) -> float | None:
        """What the priced runs cost, or `None` when the provider priced none."""
        priced = [r.dollars for r in self.runs if r.dollars is not None]
        return sum(priced) if priced else None


# -- one run --------------------------------------------------------------------


def checkpointer() -> InMemorySaver:
    """Where a run waits for an answer: in memory, because nothing resumes it once it is scored."""
    return InMemorySaver(serde=checkpoints.Declared())


def thread(kind: str, *, remembers: bool = False) -> RunnableConfig:
    """A thread of its own for one run; with `remembers`, keeping conclusions under the suite's user."""
    configurable: dict[str, Any] = {"thread_id": f"{kind}:{uuid4()}"}
    if remembers:
        configurable[conclusions.USER] = USER
    return {"configurable": configurable}


def timed(run: Callable[[], T]) -> tuple[T, float]:
    """What the run returned, and the seconds it took on the wall clock."""
    started = time.monotonic()
    made = run()
    return made, time.monotonic() - started


@dataclass(frozen=True)
class Scored:
    """One run as a suite scores it: the run, what it failed, and what a failure weighs."""

    run: Recorded
    failures: tuple[tuple[str, str], ...] = ()
    weight: int = 1


def attempted(
    case: str,
    attempt: int,
    records: Path,
    named: str,
    run: Callable[[], Scored],
    *,
    typed: bool = False,
) -> Outcome:
    """One run made, written to `records` as `named`, and scored; a run the provider failed is a run not made.

    A spent quota is raised on, so the pass stops there. Any other error is
    the run's own, said with its type when `typed`.
    """
    try:
        scored = run()
    except Exception as error:
        if (quota := models.spent(error)) is not None:
            raise quota from error
        if isinstance(error, models.ProviderFailed) and error.emitted:
            lost = {"error": str(error), "emitted": list(error.emitted)}
            write(records, f"{named}-lost", json.dumps(lost, indent=2))
        said = f"{type(error).__name__}: {error}" if typed else str(error)
        return Outcome(case, attempt, error=said)
    written = write(records, named, scored.run.written)
    return Outcome(case, attempt, scored.failures, scored.run, written, weight=scored.weight)


def write(records: Path, name: str, document: str) -> Path:
    """One record to disk, its directory made only now, so a pass that never ran leaves nothing behind."""
    records.mkdir(parents=True, exist_ok=True)
    written = records / f"{name}.json"
    written.write_text(document, encoding="utf-8")
    return written


# -- the fixture ----------------------------------------------------------------


@contextmanager
def pointed_at(path: Path | None = None) -> Iterator[Path]:
    """`TRAINER_DB` naming `path`, or the database in use, while the block runs; put back after.

    The tools open their own connection from it, so a fixture nothing points at
    is invisible to the model.
    """
    named = (path if path is not None else database.database_path()).resolve()
    previous = os.environ.get(database.DATABASE_ENV_VAR)
    os.environ[database.DATABASE_ENV_VAR] = str(named)
    try:
        yield named
    finally:
        if previous is None:
            os.environ.pop(database.DATABASE_ENV_VAR, None)
        else:
            os.environ[database.DATABASE_ENV_VAR] = previous


@dataclass(frozen=True)
class Copy:
    """A throwaway copy of the database, and the directory it lives in."""

    connection: sqlite3.Connection
    path: Path
    directory: Path


@contextmanager
def copied(source: sqlite3.Connection, *, emptied: Sequence[str] = ()) -> Iterator[Copy]:
    """A copy of `source` with `emptied` tables emptied, named in `TRAINER_DB` while it is open, deleted after."""
    directory = Path(tempfile.mkdtemp(prefix="reps-eval-"))
    path = directory / "eval.sqlite"
    connection = database.connect(path)
    try:
        source.backup(connection)
        for table in emptied:
            connection.execute(f"DELETE FROM {table}")
        with pointed_at(path) as named:
            yield Copy(connection, named, directory)
    finally:
        # Closed before the directory goes: on Windows an open SQLite file cannot be deleted.
        connection.close()
        shutil.rmtree(directory, ignore_errors=True)


# -- a suite --------------------------------------------------------------------


class Named(Protocol):
    @property
    def name(self) -> str: ...


C = TypeVar("C", bound=Named)
W = TypeVar("W")

Once = Callable[[C, int], Sequence[Outcome]]
"""One attempt at a case: its outcome first, then those of any graph run after it."""


class Suite(Generic[C, W]):
    """What one suite says of itself; the runner does the rest."""

    what = "case"
    """What a case is called, in the message naming them when one is mistyped."""

    def __init__(self, cases: Sequence[C]) -> None:
        self.cases = tuple(cases)

    def problems(self, connection: sqlite3.Connection) -> Sequence[str]:
        """What disagrees with this database before the fixture is built."""
        return ()

    def fixture(self, connection: sqlite3.Connection) -> AbstractContextManager[W]:
        """The database the pass runs against, named in `TRAINER_DB` while it is open."""
        raise NotImplementedError

    def checked(self, where: W) -> Sequence[str]:
        """What disagrees with the fixture, before anything is paid for."""
        return ()

    def nodes(self, chosen: Sequence[C]) -> Sequence[models.Node]:
        """The nodes these cases run, whose models the roster gives."""
        raise NotImplementedError

    def runs(
        self, where: W, chats: models.Roster, *, records: Path, budget: int
    ) -> Once[C]:
        """How one attempt at a case is made and scored."""
        raise NotImplementedError

    def derived(self, outcome: Outcome) -> Sequence[Outcome]:
        """Outcomes read off one of the case's own, a run the pass never made included."""
        return ()

    def halves(self) -> tuple[Half, ...]:
        """The bars the set declares; none means every run must hold."""
        return ()

    def render(self, report: Report, chosen: Sequence[C]) -> list[str]:
        """The matrices, the failures and the totals. ASCII."""
        raise NotImplementedError


def run(
    suite: Suite[C, W],
    connection: sqlite3.Connection,
    *,
    only: Sequence[str] = (),
    repetitions: int = REPETITIONS,
    records: Path | None = None,
    budget: int = tools.CALL_BUDGET,
) -> tuple[list[str], Report]:
    """The whole pass: checked, built, run against the models, and measured against its bars.

    Everything that can be wrong without a model is refused before one is
    asked whether it is there, and that before anything is paid for.
    """
    _refuse(suite.problems(connection))
    chosen = picked(suite.cases, only, suite.what)
    with suite.fixture(connection) as where:
        _refuse(suite.checked(where))
        chats = models.roster(suite.nodes(chosen))
        models.ready_all(chats)
        with _sampling(chats) as sampled:
            report = measure(suite, where, chosen, chats, repetitions=repetitions, records=records, budget=budget)
    return [*suite.render(report, chosen), *sampled()], report


def measure(
    suite: Suite[C, W],
    where: W,
    chosen: Sequence[C],
    chats: models.Roster,
    *,
    repetitions: int = REPETITIONS,
    records: Path | None = None,
    budget: int = tools.CALL_BUDGET,
) -> Report:
    """Every chosen case, every repetition, against `where`, measured against the suite's bars."""
    once = suite.runs(where, chats, records=records if records is not None else records_path(), budget=budget)
    report = measured(
        [case.name for case in chosen],
        repetitions,
        lambda at, attempt: once(chosen[at], attempt),
        suite.derived,
    )
    return barred(suite, report)


def barred(suite: Suite[Any, Any], report: Report) -> Report:
    """The report measured against the bars the suite declares."""
    return replace(report, halves=suite.halves())


def measured(
    cases: Sequence[str],
    repetitions: int,
    once: Callable[[int, int], Sequence[Outcome]],
    derived: Callable[[Outcome], Sequence[Outcome]] = lambda _own: (),
) -> Report:
    """Every case, every repetition, until the provider's day runs out.

    `once` takes the case's position and the attempt. Each case's own outcome
    comes first in the report, then those of graphs run after it and those
    `derived` reads off it. The runs a spent quota leaves are counted as not
    made, and `derived` still reads them, so they count against every bar.
    """
    outcomes: list[Outcome] = []
    after: list[Outcome] = []
    for at, _case in enumerate(cases):
        for attempt in range(1, repetitions + 1):
            try:
                own, *rest = once(at, attempt)
            except models.QuotaSpent as spent:
                left = [
                    Outcome(name, again, error=str(spent), skipped=True)
                    for position, name in enumerate(cases)
                    for again in range(1, repetitions + 1)
                    if (position, again) >= (at, attempt)
                ]
                outcomes.extend(left)
                after.extend(one for skipped in left for one in derived(skipped))
                return Report((*outcomes, *after), stopped=str(spent))
            outcomes.append(own)
            after.extend(rest)
            after.extend(derived(own))
    return Report((*outcomes, *after))


def picked(available: Sequence[C], only: Sequence[str], what: str) -> tuple[C, ...]:
    """The cases `only` names, once each, or every case when it names none."""
    if not only:
        return tuple(available)
    known = {case.name: case for case in available}
    for name in only:
        if name not in known:
            raise Refused(f"no {what} called {name!r}; they are {', '.join(known)}")
    # Named twice is named once: left in, it runs twice against a paid provider.
    return tuple(known[name] for name in dict.fromkeys(only))


@contextmanager
def _sampling(chats: models.Roster) -> Iterator[Callable[[], list[str]]]:
    """Memory sampled while the pass runs, on the first model's host; its line, or none off Ollama."""
    first = next(iter(chats.values()), None)
    if first is None:
        yield list
        return
    with memory.sampling(first) as sampler:
        yield sampler.lines


def _refuse(problems: Sequence[str]) -> None:
    if problems:
        raise Refused("\n".join(problems))


# -- the matrix ---------------------------------------------------------------


def matrix(report: Report, cases: Sequence[str], columns: Sequence[str]) -> list[str]:
    """One row per case, one column per check, `N failed` in the cells.

    Shared with the log suite, which has different cases and different columns
    and the same question to answer: *of the runs of this case, how many broke
    this check*. The distribution is the point -- a cell saying `1 failed` out
    of three runs is a different fact from one saying `3 failed`, and a
    pass/fail cell would print them the same.
    """
    width = max((len(case) for case in cases), default=0) + 2
    # Each column as wide as it needs to be, and no narrower than the number
    # under it: `false confidence` is 16 characters, and a fixed 14 would put
    # every cell in its row half a column to the right of its heading.
    widths = {name: max(14, len(name) + 2) for name in columns}

    lines = ["".ljust(width) + "  ".join(f"{n:^{widths[n]}}" for n in columns)]
    for case in cases:
        runs = [outcome for outcome in report.outcomes if outcome.case == case]
        measured = [outcome for outcome in runs if outcome.error is None]
        cells = []
        for name in columns:
            if name == NOT_RUN:
                missed = sum(1 for outcome in runs if outcome.error is not None)
                said = str(missed) if missed else "-"
            elif not measured:
                said = "-"
            else:
                broke = sum(
                    1 for o in measured if any(n == name for n, _ in o.failures)
                )
                said = "ok" if not broke else f"{broke} failed"
            cells.append(f"{said:^{widths[name]}}")
        lines.append(case.ljust(width) + "  ".join(cells))
    return lines


def failures(report: Report, about: Mapping[str, str] | None = None) -> list[str]:
    """Every failure, one to a line, with the record that says why.

    `about` says what a case *is*, for a suite whose names do not: `U11` is a
    row number and `no-equipment` is a description, so the log suite passes
    its headings and the six situations do not need to.
    """
    said = about or {}
    lines = []
    for outcome in report.outcomes:
        named = outcome.case
        if outcome.case in said:
            named = f"{outcome.case} ({said[outcome.case]})"
        if outcome.error is not None and not outcome.skipped:
            lines.append(f"{named} #{outcome.attempt}: {outcome.error}")
        for name, why in outcome.failures:
            where = outcome.written or "(not written)"
            lines.append(f"{named} #{outcome.attempt} {name}: {why}")
            lines.append(f"    {where}")
    return lines


def _money(report: Report) -> str:
    """Dollars in all and a run, as the provider priced them, and seconds a run. ASCII."""
    runs = report.runs
    seconds = f"{sum(r.seconds for r in runs) / len(runs):.1f}s a run"
    if report.dollars is None:
        return f"dollars not reported by the provider, {seconds}"
    priced = sum(1 for r in runs if r.dollars is not None)
    spent = (
        f"${report.dollars:.4f} in all"
        if priced == len(runs)
        else f"${report.dollars:.4f} over {priced} of {len(runs)} runs "
        f"({len(runs) - priced} not reported)"
    )
    return f"{spent}, ${report.dollars / priced:.4f} a run, {seconds}"


def totals(report: Report, held: str) -> list[str]:
    """The number, what it cost, and the bar it is measured against.

    `held` is what holding meant -- every invariant, or the outcome the row
    declared. The bar is the same either way and it is not a knob: a labelled
    row is an expected outcome somebody wrote down before the run, so a row
    that fails is either the agent being wrong or the row being wrong, and
    both are things to go and read.
    """
    lines = []
    # Floored, never rounded. At 249 of 250 a rounded figure prints 100% on
    # the line above "the bar is 100%" and then exits non-zero -- the one
    # number this command exists to produce, contradicting itself.
    counted = (
        ""
        if report.against == report.total
        else f", out of {report.against} with false confidence counted double"
    )
    lines.append(
        f"{report.held} of {report.total} runs {held} "
        f"-- {math.floor(report.percentage)}%{counted}"
    )
    for half in report.halves:
        part = report.of(half)
        if part.total:
            doubled = (
                "" if part.against == part.total else f" ({part.against} counted)"
            )
            lines.append(
                f"  {half.name}: {part.held} of {part.total}{doubled} -- "
                f"{math.floor(part.percentage)}%, the bar is {half.bar}%"
            )
    lines.append(
        f"cost: {report.calls} tool calls, {report.input_tokens} tokens in, "
        f"{report.output_tokens} out"
    )
    if report.runs:
        lines.append(f"      {_money(report)}")
    if report.stopped is not None:
        skipped = sum(1 for outcome in report.outcomes if outcome.skipped)
        lines.append("")
        lines.append(f"Stopped with {skipped} runs not made: {report.stopped}.")
    elif report.halves and not report.passed:
        lines.append("")
        lines.append("Below the bar the set declares.")
    elif not report.passed:
        lines.append("")
        lines.append("The bar is 100%. Anything below it is a bug, not a knob.")
    return lines
