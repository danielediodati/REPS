"""The onboarding and memory suite: scripted users through the interview, and messages through the entrance."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from trainer import eval_runner, onboarding_set
from trainer.coach import checkpoints, conclusions, entrance, logger, models, onboarding
from trainer.coach import record as run_record
from trainer.engine import catalog, config

FILLED = "filled"
LATE = "declared late"
"""A field the persona had to say again because the model asked on without writing it down."""
QUOTED = "quoted"
PATH = "path open"
ONLY = "only changed"
REMEMBERED = "remembered"
ROUTED = "routed"

MAX_ANSWERS = 20
"""Answers a persona gives before the run is counted as never ending."""

REMEMBERS = " remembers"
ON_TIME = " on time"
"""Appended to a case's name for the judgement it is held to at a bar: memory, and declaring on time."""


@dataclass(frozen=True)
class Fixture:
    """The copy the suite runs against, and the checkpointer file a paused persona resumes from."""

    connection: sqlite3.Connection
    path: Path
    checkpoints: Path
    today: str


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
class Interviewed(eval_runner.Talked):
    """An interview or a change: also what the persona said that was not kept, and what it had to say again."""

    forgotten: tuple[str, ...] = ()
    late: tuple[str, ...] = ()


class Onboard(eval_runner.Suite[onboarding_set.Case, Fixture]):
    """Scripted users through the interview, and messages through the entrance, in a copy with nothing declared."""

    def __init__(self, holds: onboarding_set.OnboardSet) -> None:
        super().__init__(holds.cases)
        self.holds = holds

    def problems(self, connection: sqlite3.Connection) -> Sequence[str]:
        return problems(connection, self.holds)

    @contextmanager
    def fixture(self, connection: sqlite3.Connection) -> Iterator[Fixture]:
        with eval_runner.copied(connection, emptied=("declarations", "exclusions")) as copy:
            yield Fixture(copy.connection, copy.path, copy.directory / "checkpoints.sqlite", self.holds.today)

    def chats(self, chosen: Sequence[onboarding_set.Case]) -> Mapping[str, models.Chat]:
        """The interview's model when an interview or change is chosen, the entrance's when a route is."""
        chats = {}
        if any(case.kind != onboarding_set.ROUTE for case in chosen):
            chats["onboarding"] = models.onboarding()
        if any(case.kind == onboarding_set.ROUTE for case in chosen):
            chats["entrance"] = models.entrance()
        return chats

    def runs(
        self, where: Fixture, chats: Mapping[str, models.Chat], *, records: Path, budget: int
    ) -> eval_runner.Once[onboarding_set.Case]:
        def once(case: onboarding_set.Case, attempt: int) -> tuple[eval_runner.Outcome, ...]:
            named = f"{case.name}-{attempt}"
            if case.kind == onboarding_set.ROUTE:
                return (
                    eval_runner.attempted(
                        case.name, attempt, records, named, lambda: _routed(case, chats["entrance"], budget)
                    ),
                )
            return (
                eval_runner.attempted(
                    case.name, attempt, records, named, lambda: _interviewed(where, case, chats["onboarding"], budget)
                ),
            )

        return once

    def derived(self, outcome: eval_runner.Outcome) -> list[eval_runner.Outcome]:
        """An interview or change again, as the cases held to a bar; a route, nothing."""
        case = next(case for case in self.cases if case.name == outcome.case)
        return [] if case.kind == onboarding_set.ROUTE else _judged(outcome, case)

    def halves(self) -> tuple[eval_runner.Half, ...]:
        """100% held by code, and the judgements the set declares."""
        holds = self.holds
        return (
            eval_runner.Half("held", frozenset(case.name for case in holds.held), 100),
            eval_runner.Half("on time", frozenset(case.name + ON_TIME for case in holds.held), holds.bar_on_time),
            eval_runner.Half(
                "remembered",
                frozenset(case.name + REMEMBERS for case in holds.held if case.remembers),
                holds.bar_remembered,
            ),
            eval_runner.Half("routed", frozenset(case.name for case in holds.routes), holds.bar_routed),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[onboarding_set.Case]) -> list[str]:
        return render(report, chosen)


def _judged(outcome: eval_runner.Outcome, case: onboarding_set.Case) -> list[eval_runner.Outcome]:
    """The run again, as the cases held to a bar: whether it declared on time, and what it remembered."""
    talked = outcome.record if isinstance(outcome.record, Interviewed) else None
    late = talked.late if talked else ()
    judged: list[tuple[str, tuple[tuple[str, str], ...]]] = [
        (ON_TIME, ((LATE, f"said again, still undeclared: {', '.join(late)}"),) if late else ())
    ]
    if case.remembers:
        forgotten = talked.forgotten if talked else ()
        judged.append((REMEMBERS, tuple((REMEMBERED, f"nothing kept from {line!r}") for line in forgotten)))
    return [
        eval_runner.Outcome(
            outcome.case + suffix,
            outcome.attempt,
            failures,
            written=outcome.written,
            error=outcome.error,
            skipped=outcome.skipped,
        )
        for suffix, failures in judged
    ]


def _interviewed(
    where: Fixture, case: onboarding_set.Case, on: models.Chat, budget: int
) -> eval_runner.Scored:
    """One persona through the interview, answering by code, and the checks held at 100%."""
    store = InMemoryStore()
    thread = eval_runner.thread("onboard", remembers=True)
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

    def talked() -> tuple[Mapping[str, Any], int]:
        nonlocal given
        answers = 0
        with checkpoints.saver(where.checkpoints) as saver:

            def built() -> onboarding.Onboarding:
                return onboarding.build(on, budget=budget, checkpointer=saver, store=store, opening=opening)

            graph = built()
            while True:
                final = graph.invoke(given, thread)
                waiting = final.get("__interrupt__")
                if not waiting or answers >= MAX_ANSWERS:
                    return final, answers
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

    (final, answers), seconds = eval_runner.timed(talked)
    kept = conclusions.live(store, eval_runner.USER)
    interviewed = Interviewed(
        record=run_record.of(final, budget),
        seconds=seconds,
        conversation=tuple(conversation),
        forgotten=tuple(line for line in case.remembers if not _kept(line, kept)),
        late=tuple(dict.fromkeys(persona.late)),
    )
    return eval_runner.Scored(interviewed, _held(case, final, before, kept, answers))


@dataclass
class _Persona:
    """A scripted user answering by code: which replies it has given, and which it had to give again."""

    case: onboarding_set.Case
    before: Mapping[str, Any]
    replied: set[int] = field(default_factory=set)
    spoken: int = 0
    late: list[str] = field(default_factory=list)

    def answer(self, declared: Mapping[str, Any]) -> str:
        """The first unsettled reply not yet given, else the first given again; then `afterwards`; then `otherwise`."""
        unsettled = [
            index
            for index, reply in enumerate(self.case.replies)
            if not all(self._settled(one, declared) for one in reply.fields)
        ]
        fresh = [index for index in unsettled if index not in self.replied]
        if fresh:
            self.replied.add(fresh[0])
            return self.case.replies[fresh[0]].says
        if unsettled:
            self.late.extend(self.case.replies[unsettled[0]].fields)
            return self.case.replies[unsettled[0]].says
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


def _routed(case: onboarding_set.Case, on: models.Chat, budget: int) -> eval_runner.Scored:
    """One message through the entrance, every handoff allowed to start, and where it went."""
    store: BaseStore = InMemoryStore()
    graph = entrance.build(
        on,
        budget=budget,
        checkpointer=eval_runner.checkpointer(),
        today=lambda: entrance.NO_MESOCYCLE,
        checking=lambda _name, _asked: None,
        store=store,
    )
    final, seconds = eval_runner.timed(
        lambda: graph.invoke(entrance.heard(case.opens), eval_runner.thread("route", remembers=True))
    )
    handoff = str(final.get("handoff", ""))
    answer = str(final.get("answer", ""))
    talked = eval_runner.Talked(
        record=run_record.of(final, budget),
        seconds=seconds,
        conversation=(("user", case.opens), ("agent", answer)),
    )
    if handoff == case.routed:
        return eval_runner.Scored(talked)
    return eval_runner.Scored(talked, ((ROUTED, f"handed to {handoff or 'nothing'}: {answer!r}"),))


def render(report: eval_runner.Report, chosen: Sequence[onboarding_set.Case]) -> list[str]:
    """One matrix per kind of case, the failures, what an onboarding cost, and the bars. ASCII."""
    kinds = (
        (onboarding_set.INTERVIEW, "interviews", [FILLED, QUOTED]),
        (onboarding_set.CHANGE, "changes", [FILLED, QUOTED, PATH, ONLY]),
    )
    lines: list[str] = []
    for kind, heading, columns in kinds:
        names = [case.name for case in chosen if case.kind == kind]
        if names:
            lines += [heading, *eval_runner.matrix(report, names, [*columns, eval_runner.NOT_RUN]), ""]
    on_time = [case.name + ON_TIME for case in chosen if case.kind != onboarding_set.ROUTE]
    if on_time:
        lines += ["on time", *eval_runner.matrix(report, on_time, [LATE, eval_runner.NOT_RUN]), ""]
    remembering = [case.name + REMEMBERS for case in chosen if case.remembers]
    if remembering:
        lines += ["memory", *eval_runner.matrix(report, remembering, [REMEMBERED, eval_runner.NOT_RUN]), ""]
    routes = [case.name for case in chosen if case.kind == onboarding_set.ROUTE]
    if routes:
        lines += ["routing", *eval_runner.matrix(report, routes, [ROUTED, eval_runner.NOT_RUN]), ""]
    about = {case.name: case.describes for case in chosen}
    about |= {case.name + REMEMBERS: case.describes for case in chosen}
    about |= {case.name + ON_TIME: case.describes for case in chosen}
    lines += [*eval_runner.failures(report, about), ""]
    lines += _per_onboarding(report, chosen)
    lines += eval_runner.totals(report, "held what their case declares")
    return lines


def _per_onboarding(
    report: eval_runner.Report, chosen: Sequence[onboarding_set.Case]
) -> list[str]:
    """Dollars and seconds an interview or change took, the figures ADR-0011 compares."""
    held = {case.name for case in chosen if case.kind != onboarding_set.ROUTE}
    runs = [o.record for o in report.outcomes if o.case in held and isinstance(o.record, Interviewed)]
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
