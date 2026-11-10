"""The answer suite: each question retrieved and asked of the entrance, every layer a model need not judge held by code."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.store.memory import InMemoryStore

from trainer import answer_set, eval_runner, retrieval
from trainer.answer_set import Case
from trainer.coach import entrance, models
from trainer.coach import record as run_record

RECALL = "recall"
ANSWERED = "answered"
NOT_COVERED = "not covered"
TRIAGE = "triage"
VERBATIM = "verbatim"
LABELLED = "labelled"

RECALLED = " recall"
"""Appended to a case's name for whether its question retrieved a labelled passage."""

QUOTED = " quote"
"""Appended to a case's name for whether what it cited is verbatim and labelled."""

TRIAGED = (answer_set.PAIN, answer_set.TECHNIQUE_PAIN, answer_set.PREVENTION)
"""The rows on the boundary with triage: a current pain goes there, general prevention never does."""

OUTSIDE = (answer_set.NEAR, answer_set.OFF_TOPIC)


@dataclass(frozen=True)
class Fixture:
    """The copy the entrance's reads run against, named in `TRAINER_DB` while it is open."""

    path: Path


@dataclass(frozen=True)
class Retrieved:
    """Where the row's first labelled passage came in the top results, if it did, and how long the search took."""

    rank: int | None
    seconds: float


class Answer(eval_runner.Suite[Case, Fixture]):
    """Each question searched in code, then, unless retrieval only, asked of the entrance over the same corpus."""

    what = "question"
    repetitions = 1

    def __init__(self, held: answer_set.AnswerSet, search: retrieval.Search, *, retrieval_only: bool = False) -> None:
        cases = [case for case in held.cases if case.kind == answer_set.COVERED] if retrieval_only else held.cases
        super().__init__(cases)
        self.held = held
        self.search = search
        self.retrieval_only = retrieval_only
        self.retrieved: dict[tuple[str, int], Retrieved] = {}
        self.english = english_pages(search)
        self.revisions = {chunk.id: chunk.revision for chunk in search.chunks}

    def problems(self, connection: sqlite3.Connection) -> Sequence[str]:
        return problems(self.held, self.search)

    @contextmanager
    def fixture(self, connection: sqlite3.Connection) -> Iterator[Fixture]:
        """A copy of the database, and the corpus the pass measures as the one the tools search."""
        with eval_runner.copied(connection) as copy, retrieval.installed(self.search):
            yield Fixture(copy.path)

    def nodes(self, chosen: Sequence[Case]) -> Sequence[models.Node]:
        return () if self.retrieval_only else ("entrance",)

    def runs(self, where: Fixture, chats: models.Roster, *, records: Path, budget: int) -> eval_runner.Once[Case]:
        def once(case: Case, attempt: int) -> Sequence[eval_runner.Outcome]:
            recalled = self.recall(case, attempt)
            if self.retrieval_only:
                return recalled
            return (*_asked(case, attempt, chats["entrance"], budget, records, self.revisions), *recalled)

        return once

    def recall(self, case: Case, attempt: int) -> tuple[eval_runner.Outcome, ...]:
        """The row's question searched as it stands, when it is a covered row; the rank kept for MRR."""
        if case.kind != answer_set.COVERED:
            return ()
        named = case.name + RECALLED
        try:
            found, seconds = eval_runner.timed(lambda: self.search.search(case.question))
        except retrieval.Unavailable as missing:
            return (eval_runner.Outcome(named, attempt, error=str(missing)),)
        rank = next(
            (at for at, one in enumerate(found, 1) if any(answer_set.found(label, [one.chunk]) for label in case.passages)),
            None,
        )
        self.retrieved[(case.name, attempt)] = Retrieved(rank, seconds)
        if rank is not None:
            return (eval_runner.Outcome(named, attempt),)
        nearest = "; ".join(f"{one.chunk.title} / {one.chunk.section}" for one in found) or "nothing"
        return (eval_runner.Outcome(named, attempt, ((RECALL, f"no labelled passage in the top {len(found)}: {nearest}"),)),)

    def ranked(self, cases: Sequence[Case]) -> list[Retrieved]:
        """Every search made for these rows."""
        names = {case.name for case in cases}
        return [one for (name, _attempt), one in self.retrieved.items() if name in names]

    def halves(self) -> tuple[eval_runner.Half, ...]:
        """Recall on the covered rows; unless retrieval only, the quotes, *not covered* and the triage boundary."""
        bars, cases = self.held.bars, self.held.cases

        def of(kinds: Sequence[str], suffix: str = "") -> frozenset[str]:
            return frozenset(case.name + suffix for case in cases if case.kind in kinds)

        recall = eval_runner.Half(RECALL, of((answer_set.COVERED,), RECALLED), bars["recall"])
        if self.retrieval_only:
            return (recall,)
        return (
            recall,
            eval_runner.Half(VERBATIM, frozenset(case.name + QUOTED for case in cases), bars["verbatim"]),
            eval_runner.Half(NOT_COVERED, of(OUTSIDE), bars["not_covered"]),
            # At most this share of covered rows answered *not covered*: held as at least the rest answered.
            eval_runner.Half(
                f"covered answered (at most {bars['wrongly_not_covered']}% not covered)",
                of((answer_set.COVERED,)),
                100 - bars["wrongly_not_covered"],
            ),
            eval_runner.Half(TRIAGE, of(TRIAGED), bars["triage"]),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[Case]) -> list[str]:
        return render(self, report, chosen)


def english_pages(search: retrieval.Search) -> set[tuple[str, str]]:
    """Every (title, revision) the corpus holds in English."""
    return {(chunk.title, chunk.revision) for chunk in search.chunks if chunk.language == "en"}


def on_english(case: Case, english: set[tuple[str, str]]) -> bool:
    """An Italian covered row whose labels all name English pages."""
    return (
        case.kind == answer_set.COVERED
        and case.language == "it"
        and all((label.title, label.revision) in english for label in case.passages)
    )


def problems(held: answer_set.AnswerSet, search: retrieval.Search) -> tuple[str, ...]:
    """The set and the corpus disagreeing, or the corpus not searchable, before anything is paid for."""
    if held.corpus != search.version:
        return (
            f"the answer set was labelled on corpus version {held.corpus} and the corpus is version "
            f"{search.version}; scores are never read across versions, so refresh the set to the corpus first",
        )
    lost = answer_set.lost(held, search.chunks)
    if lost:
        return (f"the corpus holds none of the labelled quotes of {', '.join(lost)}",)
    missing = search.state()
    return (f"the sources are not ready: {missing}",) if missing else ()


def _asked(
    case: Case, attempt: int, on: models.Chat, budget: int, records: Path, revisions: Mapping[str, str]
) -> tuple[eval_runner.Outcome, ...]:
    """The question asked of the entrance and held to its kind; then its quotes, when it cited any."""
    heard: dict[str, Any] = {}

    def ask() -> eval_runner.Scored:
        graph = entrance.build(on, budget=budget, checkpointer=eval_runner.checkpointer(), store=InMemoryStore())
        final, seconds = eval_runner.timed(
            lambda: dict(graph.invoke(entrance.heard(case.question), eval_runner.thread("answer")))
        )
        heard.update(final)
        talked = eval_runner.Talked(
            record=run_record.of(final, budget),
            seconds=seconds,
            conversation=(
                ("user", case.question),
                ("agent", str(final.get("answer", ""))),
                *(("quote", f"{one['title']} / {one['section']}: {one['quote']}") for one in final.get("cited", ())),
            ),
        )
        return eval_runner.Scored(talked, kind_held(case, final))

    asked = eval_runner.attempted(case.name, attempt, records, f"{case.name}-{attempt}", ask)
    if asked.error is not None or not heard.get("cited"):
        return (asked,)
    quoted = eval_runner.Outcome(case.name + QUOTED, attempt, quotes_held(case, heard, revisions), asked.record, asked.written)
    return (asked, quoted)


def kind_held(case: Case, final: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Whether the reply is what the row's kind expects, as one failure or none."""
    sources = str(final.get("sources", ""))
    answer = str(final.get("answer", ""))
    asks = "?" in answer
    went = f"sources {sources or 'not searched'}, {len(final.get('cited', ()))} cited"
    if final.get("handoff"):
        went += f", handed to {final['handoff']}"
    if case.kind == answer_set.COVERED:
        column, wrong = ANSWERED, sources == entrance.NOT_COVERED
    elif case.kind in OUTSIDE:
        column, wrong = NOT_COVERED, sources != entrance.NOT_COVERED
    elif case.kind == answer_set.PAIN:
        column, wrong = TRIAGE, bool(sources) or not asks
    elif case.kind == answer_set.TECHNIQUE_PAIN:
        column, wrong = TRIAGE, sources != entrance.CITED or not asks
    else:
        column, wrong = TRIAGE, sources != entrance.CITED
    if case.kind in TRIAGED and final.get("handoff"):
        wrong = True
    return ((column, f"{went}: {answer!r}"),) if wrong else ()


def quotes_held(case: Case, final: Mapping[str, Any], revisions: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Each quote word for word in a passage that run retrieved, and that passage, by its chunk's revision, one the row labels."""
    found: Mapping[str, Mapping[str, str]] = final.get("found", {})
    labelled = {(label.title, label.revision, label.section) for label in case.passages}
    failures: list[tuple[str, str]] = []
    for one in final.get("cited", ()):
        quote = _spaced(one["quote"])
        held = [
            passage
            for passage in found.values()
            if (passage["title"], passage["section"], passage["link"]) == (one["title"], one["section"], one["link"])
            and quote in _spaced(passage["text"])
        ]
        where = f"{one['title']} / {one['section']}: {one['quote']!r}"
        if not held:
            failures.append((VERBATIM, f"not word for word in a passage retrieved: {where}"))
        elif not any((passage["title"], revisions.get(passage["id"], ""), passage["section"]) in labelled for passage in held):
            failures.append((LABELLED, f"a passage the row does not label: {where}"))
    return tuple(failures)


def _spaced(text: str) -> str:
    return " ".join(text.split())


def render(suite: Answer, report: eval_runner.Report, chosen: Sequence[Case]) -> list[str]:
    """The matrices, the failures, retrieval, the Italian rows on English passages apart, and the bars. ASCII."""
    covered = [case for case in chosen if case.kind == answer_set.COVERED]
    lines = [
        f"answer set version {suite.held.version} on corpus version {suite.search.version}: {suite.search.described}",
        "",
    ]
    if not suite.retrieval_only:
        replies = [ANSWERED, NOT_COVERED, TRIAGE, eval_runner.NOT_RUN]
        lines += ["replies", *eval_runner.matrix(report, [case.name for case in chosen], replies), ""]
        quoted = [case.name + QUOTED for case in chosen if _ran(report, {case.name + QUOTED}).total]
        if quoted:
            lines += ["quotes", *eval_runner.matrix(report, quoted, [VERBATIM, LABELLED]), ""]
    recalled = [case.name + RECALLED for case in covered]
    lines += ["retrieval", *eval_runner.matrix(report, recalled, [RECALL, eval_runner.NOT_RUN]), ""]
    failed = eval_runner.failures(report)
    lines += [*failed, ""] if failed else []
    ranks = suite.ranked(covered)
    seconds = sorted(one.seconds for one in ranks)
    p95 = seconds[math.ceil(0.95 * len(seconds)) - 1] if seconds else 0.0
    lines += [f"MRR: {_mrr(ranks):.2f}", f"p95 retrieval: {p95:.2f}s over {len(seconds)} searches", ""]
    apart = [case for case in covered if on_english(case, suite.english)]
    lines.append(f"italian on english: {len(apart)} row{'' if len(apart) == 1 else 's'}, no bar")
    recall = _ran(report, {case.name + RECALLED for case in apart})
    lines += [f"  recall: {eval_runner.with_interval(recall.held, recall.total)}", f"  MRR: {_mrr(suite.ranked(apart)):.2f}"]
    if not suite.retrieval_only:
        answered = _ran(report, {case.name for case in apart})
        lines.append(f"  covered answered: {eval_runner.with_interval(answered.held, answered.total)}")
    lines.append("")
    lines += eval_runner.totals(report, "held what their row declares", intervals=True)
    return lines


def _ran(report: eval_runner.Report, cases: set[str]) -> eval_runner.Report:
    return eval_runner.Report(tuple(outcome for outcome in report.outcomes if outcome.case in cases))


def _mrr(ranks: Sequence[Retrieved]) -> float:
    """The mean reciprocal rank of the first labelled passage, a miss counting zero."""
    return sum(1 / one.rank for one in ranks if one.rank) / len(ranks) if ranks else 0.0
