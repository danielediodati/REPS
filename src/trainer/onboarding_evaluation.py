"""The onboarding and memory suite: scripted users through the interview, and messages through the entrance."""

from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from trainer import evaluation, onboarding_set, tools
from trainer.coach import checkpoints, conclusions, entrance, logger, models, onboarding
from trainer.coach import record as run_record
from trainer.engine import catalog, config, database

FILLED = "filled"
AGAIN = "asked again"
QUOTED = "quoted"
PATH = "path open"
ONLY = "only changed"
REMEMBERED = "remembered"
ROUTED = "routed"

USER = "eval"
"""Whose conclusions a run keeps, in its own store."""

MAX_ANSWERS = 20
"""Answers a persona gives before the run is counted as never ending."""

REMEMBERS = " remembers"
"""Appended to an interview's name for the case that holds its memory to the bar."""


@dataclass(frozen=True)
class Fixture:
    """The copy the suite runs against, and the checkpointer file a paused persona resumes from."""

    connection: sqlite3.Connection
    path: Path
    checkpoints: Path
    today: str


@contextmanager
def prepared(source: sqlite3.Connection, holds: onboarding_set.OnboardSet) -> Iterator[Fixture]:
    """A copy of `source` with nothing declared or excluded, named in `TRAINER_DB` while it is open."""
    directory = Path(tempfile.mkdtemp(prefix="reps-onboard-eval-"))
    previous = os.environ.get(database.DATABASE_ENV_VAR)
    connection = database.connect(directory / "eval.sqlite")
    try:
        source.backup(connection)
        connection.execute("DELETE FROM declarations")
        connection.execute("DELETE FROM exclusions")
        os.environ[database.DATABASE_ENV_VAR] = str(directory / "eval.sqlite")
        yield Fixture(
            connection, directory / "eval.sqlite", directory / "checkpoints.sqlite", holds.today
        )
    finally:
        connection.close()
        if previous is None:
            os.environ.pop(database.DATABASE_ENV_VAR, None)
        else:
            os.environ[database.DATABASE_ENV_VAR] = previous
        shutil.rmtree(directory, ignore_errors=True)


def problems(connection: sqlite3.Connection, holds: onboarding_set.OnboardSet) -> tuple[str, ...]:
    """What in the set disagrees with this catalog, before anything is paid for."""
    found: list[str] = []
    equipment = set(catalog.values(connection, "equipment"))
    for case in holds.cases:
        if case.kind != onboarding_set.CHANGE:
            continue
        try:
            before = onboarding.settled(dict(case.before))
        except config.ConfigError as error:
            found.append(f"{case.name}: `before` is not a declaration: {error}")
            continue
        unknown = [name for name in before.equipment if name not in equipment]
        if unknown:
            found.append(f"{case.name}: the catalog has no equipment called {', '.join(unknown)}")
    return tuple(found)


@dataclass(frozen=True)
class Talked:
    """One run of a graph as this suite scores it: its record, what was said, and what it forgot."""

    record: Mapping[str, Any]
    conversation: tuple[tuple[str, str], ...]
    seconds: float
    forgotten: tuple[str, ...] = ()

    @property
    def written(self) -> str:
        return json.dumps(
            {"conversation": [list(line) for line in self.conversation], "run": self.record},
            indent=2,
            ensure_ascii=False,
            default=str,
        )

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


def run(
    where: Fixture,
    chosen: Sequence[onboarding_set.Case],
    *,
    talks: models.Chat | None,
    front: models.Chat | None,
    repetitions: int = evaluation.REPETITIONS,
    records: Path | None = None,
    budget: int = tools.CALL_BUDGET,
) -> evaluation.Report:
    """Every case, every repetition: interviews and changes on `talks`, routes on `front`."""
    into = records if records is not None else evaluation.records_path()
    held = [case for case in chosen if case.kind != onboarding_set.ROUTE]
    routes = [case for case in chosen if case.kind == onboarding_set.ROUTE]
    outcomes: list[evaluation.Outcome] = []
    stopped: str | None = None
    if held:
        assert talks is not None
        on = talks
        report = evaluation.measured(
            [case.name for case in held],
            repetitions,
            lambda at, attempt: _scored(
                held[at], attempt, into, lambda: _interviewed(where, held[at], on, budget)
            ),
        )
        outcomes.extend(report.outcomes)
        outcomes.extend(_memory(report.outcomes, held))
        stopped = report.stopped
    if routes and stopped is None:
        assert front is not None
        door = front
        report = evaluation.measured(
            [case.name for case in routes],
            repetitions,
            lambda at, attempt: _scored(
                routes[at], attempt, into, lambda: _routed(where, routes[at], door, budget)
            ),
        )
        outcomes.extend(report.outcomes)
        stopped = report.stopped
    return evaluation.Report(tuple(outcomes), stopped=stopped)


def _scored(
    case: onboarding_set.Case,
    attempt: int,
    records: Path,
    once: Callable[[], tuple[Talked, tuple[tuple[str, str], ...]]],
) -> evaluation.Outcome:
    """One run, its record written, and the checks it failed; a provider failure is a run not made."""
    try:
        talked, failures = once()
    except Exception as error:
        if (quota := models.spent(error)) is not None:
            raise quota from error
        return evaluation.Outcome(case.name, attempt, error=str(error))
    written = evaluation.write(records, f"{case.name}-{attempt}", talked.written)
    return evaluation.Outcome(case.name, attempt, failures, talked, written)


def _memory(
    outcomes: Sequence[evaluation.Outcome], held: Sequence[onboarding_set.Case]
) -> list[evaluation.Outcome]:
    """Each interview's run again, as the case that holds what it remembered to the bar."""
    remembering = {case.name for case in held if case.remembers}
    derived = []
    for outcome in outcomes:
        if outcome.case not in remembering:
            continue
        forgotten = outcome.record.forgotten if isinstance(outcome.record, Talked) else ()
        derived.append(
            evaluation.Outcome(
                outcome.case + REMEMBERS,
                outcome.attempt,
                tuple((REMEMBERED, f"nothing kept from {line!r}") for line in forgotten),
                written=outcome.written,
                error=outcome.error,
                skipped=outcome.skipped,
            )
        )
    return derived


def _interviewed(
    where: Fixture, case: onboarding_set.Case, on: models.Chat, budget: int
) -> tuple[Talked, tuple[tuple[str, str], ...]]:
    """One persona through the interview, answering by code, and the checks held at 100%."""
    started = time.monotonic()
    store = InMemoryStore()
    thread: RunnableConfig = {
        "configurable": {"thread_id": f"onboard:{uuid4()}", conclusions.USER: USER}
    }
    words = onboarding.vocabulary(where.connection)
    before: dict[str, Any] = {}
    if case.kind == onboarding_set.CHANGE:
        config.record(where.connection, onboarding.settled(dict(case.before)), where.today)
        before = onboarding.declarations(where.connection)
        given: Any = onboarding.changing(case.opens, where.today, words, before)
    else:
        given = onboarding.starting(case.opens, where.today, words)
    paths = case.open

    def opening(_before: Mapping[str, Any], _after: config.TrainingConfig) -> tuple[str, ...]:
        return paths

    conversation: list[tuple[str, str]] = [("user", case.opens)]
    persona = _Persona(case, before)
    answers = 0
    with checkpoints.saver(where.checkpoints) as saver:

        def built() -> onboarding.Onboarding:
            return onboarding.build(
                on, budget=budget, checkpointer=saver, store=store, opening=opening
            )

        graph = built()
        while True:
            final = graph.invoke(given, thread)
            waiting = final.get("__interrupt__")
            if not waiting or answers >= MAX_ANSWERS:
                break
            question = waiting[0].value
            conversation.append(("agent", str(question.get("ask", ""))))
            if question.get("kind") == logger.EXCLUSION:
                answer: Any = case.confirms
            elif case.pause_after is not None and answers == case.pause_after:
                # A day away: the process that held the graph is gone.
                graph = built()
                answer = case.back
            else:
                answer = persona.answer(final.get("declared", {}))
            answers += 1
            conversation.append(("user", str(answer)))
            given = Command(resume=answer)
    kept = conclusions.live(store, USER)
    talked = Talked(
        record=run_record.of(final, budget),
        conversation=tuple(conversation),
        seconds=time.monotonic() - started,
        forgotten=tuple(line for line in case.remembers if not _kept(line, kept)),
    )
    return talked, _held(case, final, before, persona.again, kept, answers)


@dataclass
class _Persona:
    """A scripted user answering by code: which replies it has given, and which twice."""

    case: onboarding_set.Case
    before: Mapping[str, Any]
    replied: set[int] = field(default_factory=set)
    spoken: int = 0
    again: list[str] = field(default_factory=list)

    def answer(self, declared: Mapping[str, Any]) -> str:
        """The first reply whose fields are not all settled; then `afterwards` in order; then `otherwise`."""
        for index, reply in enumerate(self.case.replies):
            if all(self._settled(one, declared) for one in reply.fields):
                continue
            if index in self.replied:
                self.again.extend(reply.fields)
            self.replied.add(index)
            return reply.says
        if self.spoken < len(self.case.afterwards):
            self.spoken += 1
            return self.case.afterwards[self.spoken - 1]
        return self.case.otherwise

    def _settled(self, name: str, declared: Mapping[str, Any]) -> bool:
        """Declared, and on a change declared differently from before."""
        if name not in declared:
            return False
        return name not in self.before or json.dumps(declared[name]) != json.dumps(
            self.before[name]
        )


def _kept(line: str, kept: Sequence[conclusions.Conclusion]) -> bool:
    """Whether a conclusion quotes the persona's sentence, or a part of it."""
    return any(
        conclusions.admitted(one.quote, [line]) or conclusions.admitted(line, [one.quote])
        for one in kept
    )


def _held(
    case: onboarding_set.Case,
    final: Mapping[str, Any],
    before: Mapping[str, Any],
    again: Sequence[str],
    kept: Sequence[conclusions.Conclusion],
    answers: int,
) -> tuple[tuple[str, str], ...]:
    """Every check code holds at 100% on one interview or change."""
    failures: list[tuple[str, str]] = []
    declared = dict(final.get("declared", {}))
    refused = onboarding.refusal(declared)
    if not final.get("finished"):
        failures.append((FILLED, f"never finished: {answers} answers given"))
    elif refused is not None:
        failures.append((FILLED, refused))
    if again:
        failures.append((AGAIN, f"answered again: {', '.join(dict.fromkeys(again))}"))
    said = list(final.get("said", []))
    unsaid = [one.quote for one in kept if not conclusions.admitted(one.quote, said)]
    if unsaid:
        failures.append((QUOTED, f"kept without being said: {unsaid!r}"))
    if case.kind != onboarding_set.CHANGE or not final.get("finished") or refused is not None:
        return tuple(failures)
    chosen = str(final.get("chosen", ""))
    if chosen not in (case.open or ("",)):
        failures.append((PATH, f"chose {chosen or 'nothing'!r}; open: {', '.join(case.open) or 'none'}"))
    differ = onboarding.changed(before, onboarding.settled(declared))
    beyond = [name for name in differ if name not in case.changes]
    if beyond:
        failures.append((ONLY, f"also changed {', '.join(beyond)}"))
    return tuple(failures)


def _routed(
    where: Fixture, case: onboarding_set.Case, on: models.Chat, budget: int
) -> tuple[Talked, tuple[tuple[str, str], ...]]:
    """One message through the entrance, every handoff allowed to start, and where it went."""
    started = time.monotonic()
    store: BaseStore = InMemoryStore()
    graph = entrance.build(
        on,
        budget=budget,
        checkpointer=InMemorySaver(serde=checkpoints.Declared()),
        today=lambda: entrance.NO_MESOCYCLE,
        checking=lambda _name, _asked: None,
        store=store,
    )
    thread: RunnableConfig = {
        "configurable": {"thread_id": f"route:{uuid4()}", conclusions.USER: USER}
    }
    final = graph.invoke(entrance.heard(case.opens), thread)
    handoff = str(final.get("handoff", ""))
    answer = str(final.get("answer", ""))
    talked = Talked(
        record=run_record.of(final, budget),
        conversation=(("user", case.opens), ("agent", answer)),
        seconds=time.monotonic() - started,
    )
    if handoff == case.routed:
        return talked, ()
    return talked, ((ROUTED, f"handed to {handoff or 'nothing'}: {answer!r}"),)


def barred(report: evaluation.Report, holds: onboarding_set.OnboardSet) -> evaluation.Report:
    """The pass against its three bars: 100% held by code, and the two judgements the set declares."""
    return replace(
        report,
        halves=(
            evaluation.Half("held", frozenset(case.name for case in holds.held), 100),
            evaluation.Half(
                "remembered",
                frozenset(case.name + REMEMBERS for case in holds.held if case.remembers),
                holds.bar_remembered,
            ),
            evaluation.Half(
                "routed", frozenset(case.name for case in holds.routes), holds.bar_routed
            ),
        ),
    )


def render(report: evaluation.Report, chosen: Sequence[onboarding_set.Case]) -> list[str]:
    """One matrix per kind of case, the failures, what an onboarding cost, and the bars. ASCII."""
    kinds = (
        (onboarding_set.INTERVIEW, "interviews", [FILLED, AGAIN, QUOTED]),
        (onboarding_set.CHANGE, "changes", [FILLED, AGAIN, QUOTED, PATH, ONLY]),
    )
    lines: list[str] = []
    for kind, heading, columns in kinds:
        names = [case.name for case in chosen if case.kind == kind]
        if names:
            lines += [heading, *evaluation.matrix(report, names, [*columns, evaluation.NOT_RUN]), ""]
    remembering = [case.name + REMEMBERS for case in chosen if case.remembers]
    if remembering:
        lines += ["memory", *evaluation.matrix(report, remembering, [REMEMBERED, evaluation.NOT_RUN]), ""]
    routes = [case.name for case in chosen if case.kind == onboarding_set.ROUTE]
    if routes:
        lines += ["routing", *evaluation.matrix(report, routes, [ROUTED, evaluation.NOT_RUN]), ""]
    about = {case.name: case.describes for case in chosen}
    about |= {case.name + REMEMBERS: case.describes for case in chosen}
    lines += [*evaluation.failures(report, about), ""]
    lines += _per_onboarding(report, chosen)
    lines += evaluation.totals(report, "held what their case declares")
    return lines


def _per_onboarding(
    report: evaluation.Report, chosen: Sequence[onboarding_set.Case]
) -> list[str]:
    """Dollars and seconds an interview or change took, the figures ADR-0011 compares."""
    held = {case.name for case in chosen if case.kind != onboarding_set.ROUTE}
    runs = [o.record for o in report.outcomes if o.case in held and isinstance(o.record, Talked)]
    if not runs:
        return []
    seconds = sorted(one.seconds for one in runs)
    priced = [one.dollars for one in runs if one.dollars is not None]
    spent = f"${sum(priced) / len(priced):.4f}" if priced else "dollars not reported"
    return [
        f"per onboarding: {spent}, {math.floor(seconds[0])}-{math.ceil(seconds[-1])}s "
        f"over {len(runs)} runs",
        "",
    ]
