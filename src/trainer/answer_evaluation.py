"""The answer suite: each question retrieved and asked of the entrance, every layer a model need not judge held by code."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.store.memory import InMemoryStore

from trainer import answer_judge, answer_set, eval_runner, retrieval
from trainer.answer_set import Case
from trainer.coach import entrance, models
from trainer.coach import record as run_record

RECALL = "recall"
ANSWERED = "answered"
NOT_COVERED = "not covered"
TRIAGE = "triage"
VERBATIM = "verbatim"
LABELLED = "labelled"
FAITHFUL = "faithful"
RELEVANT = "relevant"

RECALLED = " recall"
"""Appended to a case's name for whether its question retrieved a labelled passage."""

QUOTED = " quote"
"""Appended to a case's name for whether what it cited is verbatim and labelled."""

TRIAGED = (answer_set.PAIN, answer_set.TECHNIQUE_PAIN, answer_set.PREVENTION)
"""The rows on the boundary with triage: a current pain goes there, general prevention never does."""

JUDGED_FAITHFUL, JUDGED_RELEVANT = " faithful", " relevant"
"""Appended to a covered case's name for whether the judge read its cited reply faithful, and relevant."""

OUTSIDE = (answer_set.NEAR, answer_set.OFF_TOPIC)


def judge_chat() -> BaseChatModel:
    """The roster's judge, on its own host setting and never the entrance's."""
    return models.openrouter_model(models.JUDGE.model, models.JUDGE.effort, host=models.JUDGE.host)


def judged_by() -> str:
    """The judge's version: its model, its thresholds and the calibration set they were fitted on."""
    t = answer_judge.THRESHOLDS
    return (
        f"judged by {models.JUDGE.model} at faithful {t.faithful:.2f}, relevant {t.relevant:.2f}, "
        f"calibration set {answer_judge.FITTED_ON}"
    )


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

    def __init__(
        self,
        held: answer_set.AnswerSet,
        search: retrieval.Search,
        *,
        retrieval_only: bool = False,
        against: Path | None = None,
    ) -> None:
        cases = [case for case in held.cases if case.kind == answer_set.COVERED] if retrieval_only else held.cases
        super().__init__(cases)
        self.held = held
        self.search = search
        self.retrieval_only = retrieval_only
        self.against = against
        self.retrieved: dict[tuple[str, int], Retrieved] = {}
        self.english = english_pages(search)
        self.revisions = {chunk.id: chunk.revision for chunk in search.chunks}
        self.records: Path | None = None
        self.earlier: Ranks | None = None
        self._judge: answer_judge.Judge | None = None

    @property
    def judge(self) -> answer_judge.Judge:
        """The judge, its chat opened on the first reply it reads."""
        if self._judge is None:
            self._judge = answer_judge.Judge(judge_chat())
        return self._judge

    def problems(self, connection: sqlite3.Connection) -> Sequence[str]:
        found = problems(self.held, self.search)
        if self.against is None:
            return found
        try:
            self.earlier = Ranks.read(self.against)
        except (OSError, ValueError, KeyError, TypeError) as error:
            return (*found, f"no earlier pass to compare with in {self.against} ({error})")
        then = (self.earlier.set_version, self.earlier.corpus_version)
        if then != (self.held.version, self.search.version):
            return (
                *found,
                f"the earlier pass ran set version {then[0]} on corpus version {then[1]}, this one "
                f"set version {self.held.version} on corpus version {self.search.version}; "
                "rows are compared only on the same set and corpus",
            )
        return found

    @contextmanager
    def fixture(self, connection: sqlite3.Connection) -> Iterator[Fixture]:
        """A copy of the database, and the corpus the pass measures as the one the tools search."""
        with eval_runner.copied(connection) as copy, retrieval.installed(self.search):
            yield Fixture(copy.path)

    def nodes(self, chosen: Sequence[Case]) -> Sequence[models.Node]:
        return () if self.retrieval_only else ("entrance",)

    def runs(self, where: Fixture, chats: models.Roster, *, records: Path, budget: int) -> eval_runner.Once[Case]:
        self.records = records

        def once(case: Case, attempt: int) -> Sequence[eval_runner.Outcome]:
            recalled = self.recall(case, attempt)
            if self.retrieval_only:
                return recalled
            judged = self.judged if case.kind == answer_set.COVERED else None
            return (*_asked(case, attempt, chats["entrance"], budget, records, self.revisions, judged), *recalled)

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

    def judged(self, case: Case, attempt: int, final: Mapping[str, Any], records: Path) -> tuple[eval_runner.Outcome, ...]:
        """The cited reply read by the judge against the passages it cited: faithful, and relevant."""
        found: Mapping[str, Mapping[str, str]] = final.get("found", {})
        cited = {(one["title"], one["section"], one["link"]) for one in final.get("cited", ())}
        held = [p for p in found.values() if (p["title"], p["section"], p["link"]) in cited]
        texts = {p["id"]: f"{p['title']} / {p['section']}\n{p['text']}" for p in held}
        reply = answer_judge.Reply(case.name, case.question, str(final.get("answer", "")), tuple(texts))
        faithful, relevant = case.name + JUDGED_FAITHFUL, case.name + JUDGED_RELEVANT
        try:
            verdict = self.judge.judge(reply, texts)
        except Exception as error:
            if (quota := models.spent(error)) is not None:
                raise quota from error
            said = f"the judge failed: {error}"
            return (eval_runner.Outcome(faithful, attempt, error=said), eval_runner.Outcome(relevant, attempt, error=said))
        written = eval_runner.write(
            records, f"{case.name}-{attempt}-judged", json.dumps(asdict(verdict), indent=1, ensure_ascii=False)
        )
        bar = answer_judge.THRESHOLDS
        unsupported = "; ".join(s for s, ok in verdict.statements if not ok) or "no statements"
        cost = eval_runner.Recorded({"calls": [], "tokens": {"input": 0, "output": 0}, "dollars": verdict.dollars}, 0.0)
        not_faithful = ((FAITHFUL, f"{verdict.faithfulness:.2f}, unsupported: {unsupported}"),)
        return (
            eval_runner.Outcome(faithful, attempt, () if verdict.faithfulness >= bar.faithful else not_faithful, cost, written),
            eval_runner.Outcome(
                relevant, attempt, () if verdict.relevance >= bar.relevant else ((RELEVANT, verdict.reason),), written=written
            ),
        )

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
            eval_runner.Half(FAITHFUL, of((answer_set.COVERED,), JUDGED_FAITHFUL), bars["faithful"]),
            eval_runner.Half(RELEVANT, of((answer_set.COVERED,), JUDGED_RELEVANT), bars["relevant"]),
        )

    def render(self, report: eval_runner.Report, chosen: Sequence[Case]) -> list[str]:
        return render(self, report, chosen)


@dataclass(frozen=True)
class Ranks:
    """A retrieval pass row by row: each covered row's rank, None for a miss, and what it ran on."""

    set_version: int
    corpus_version: int
    described: str
    ranks: dict[str, int | None]

    @classmethod
    def read(cls, path: Path) -> Ranks:
        """The pass kept at `path`."""
        kept = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            int(kept["set_version"]), int(kept["corpus_version"]), str(kept["described"]), dict(kept["ranks"])
        )

    def write(self, path: Path) -> Path:
        """Kept at `path`, its folder made."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1, ensure_ascii=False), encoding="utf-8")
        return path


def compared(now: Ranks, earlier: Ranks) -> list[str]:
    """Recall row by row against an earlier pass: what each row did in both, and the difference with its interval."""
    names = [name for name in now.ranks if name in earlier.ranks]
    pairs = [(now.ranks[name] is not None, earlier.ranks[name] is not None) for name in names]
    gained, lost = pairs.count((True, False)), pairs.count((False, True))
    both, neither = pairs.count((True, True)), pairs.count((False, False))
    low, high = eval_runner.paired_interval(both, gained, lost, neither)
    points = 100 * (gained - lost) / len(pairs) if pairs else 0.0
    return [
        f"against {earlier.described}",
        f"  {gained} gained, {lost} lost, {both} held by both, {neither} by neither",
        f"  recall difference: {gained - lost:+d} of {len(pairs)} -- {points:+.0f} points [{low:+.0f}, {high:+.0f}]",
    ]


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
        fix = (
            "relabel or drop the rows that lost their quote, then `trainer corpus settle`"
            if held.corpus < search.version
            else "pass on the corpus the set was labelled on"
        )
        return (
            f"the answer set was labelled on corpus version {held.corpus} and the corpus is version "
            f"{search.version}; scores are never read across versions: {fix}",
        )
    lost = answer_set.lost(held, search.chunks)
    if lost:
        return (f"the corpus holds none of the labelled quotes of {', '.join(lost)}",)
    missing = search.state()
    return (f"the sources are not ready: {missing}",) if missing else ()


def _asked(
    case: Case,
    attempt: int,
    on: models.Chat,
    budget: int,
    records: Path,
    revisions: Mapping[str, str],
    judged: Callable[[Case, int, Mapping[str, Any], Path], tuple[eval_runner.Outcome, ...]] | None = None,
) -> tuple[eval_runner.Outcome, ...]:
    """The question asked of the entrance and held to its kind; then its quotes and the judge's reading, when it cited any."""
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
    return (asked, quoted, *(judged(case, attempt, heard, records) if judged else ()))


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
        lines[-1:] = [judged_by(), ""]
        replies = [ANSWERED, NOT_COVERED, TRIAGE, eval_runner.NOT_RUN]
        lines += ["replies", *eval_runner.matrix(report, [case.name for case in chosen], replies), ""]
        quoted = [case.name + QUOTED for case in chosen if _ran(report, {case.name + QUOTED}).total]
        if quoted:
            lines += ["quotes", *eval_runner.matrix(report, quoted, [VERBATIM, LABELLED]), ""]
        read = [case.name + JUDGED_FAITHFUL for case in chosen if _ran(report, {case.name + JUDGED_FAITHFUL}).total]
        read += [case.name + JUDGED_RELEVANT for case in chosen if _ran(report, {case.name + JUDGED_RELEVANT}).total]
        if read:
            lines += ["judged", *eval_runner.matrix(report, read, [FAITHFUL, RELEVANT, eval_runner.NOT_RUN]), ""]
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
        for column, suffix in ((FAITHFUL, JUDGED_FAITHFUL), (RELEVANT, JUDGED_RELEVANT)):
            judged = _ran(report, {case.name + suffix for case in apart})
            lines.append(f"  {column}: {eval_runner.with_interval(judged.held, judged.total)}")
    lines.append("")
    if suite.retrieval_only:
        lines += _kept(suite, covered)
    lines += eval_runner.totals(report, "held what their row declares", intervals=True)
    return lines


def _kept(suite: Answer, covered: Sequence[Case]) -> list[str]:
    """The pass's ranks kept beside its records, then compared with the earlier pass, if one is named."""
    now = Ranks(
        suite.held.version,
        suite.search.version,
        suite.search.described,
        {case.name: suite.retrieved[(case.name, 1)].rank if (case.name, 1) in suite.retrieved else None for case in covered},
    )
    records = suite.records if suite.records is not None else eval_runner.records_path()
    lines = []
    if suite.earlier is not None:
        lines += [*compared(now, suite.earlier), ""]
    kept = now.write(records / f"retrieval-{suite.search.collection}.json")
    return [*lines, f"rows kept in {kept}", ""]


def _ran(report: eval_runner.Report, cases: set[str]) -> eval_runner.Report:
    return eval_runner.Report(tuple(outcome for outcome in report.outcomes if outcome.case in cases))


def _mrr(ranks: Sequence[Retrieved]) -> float:
    """The mean reciprocal rank of the first labelled passage, a miss counting zero."""
    return sum(1 / one.rank for one in ranks if one.rank) / len(ranks) if ranks else 0.0
