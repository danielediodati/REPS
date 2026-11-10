"""The answer suite through `trainer eval --suite answer`: on a scripted entrance and the in-memory corpus."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from langchain_core.messages import AIMessage

from test_cli import enriched, runner, stocked  # noqa: F401
from test_planner import Scripted
from trainer import corpus, eval_runner, retrieval
from trainer.cli import main
from trainer.coach import entrance, models


def chunk(language: str, title: str, revision: str, section: str, text: str) -> corpus.Chunk:
    return corpus.Chunk(
        id=f"{language}/{title}/{section}",
        source="wikipedia",
        language=language,
        title=title,
        section=section,
        revision=revision,
        link=f"https://{language}.example.org/{title}?oldid={revision}",
        licence="CC BY-SA 4.0",
        author="contributors",
        text=text,
    )


SQUAT_FORM = chunk("en", "Squat (exercise)", "11", "Form", "Squat with the heels down and the trunk braced as the hips descend.")
SQUAT_DEPTH = chunk("it", "Squat", "22", "Esecuzione", "Scendi con la schiena dritta e i talloni a terra fino al parallelo.")
PLANK = chunk("it", "Plank", "33", "", "Tieni il tronco rigido su avambracci e punte dei piedi.")
CHUNKS = [SQUAT_FORM, SQUAT_DEPTH, PLANK]

BARS = """\
[bars]
recall = 80
verbatim = 100
faithful = 90
relevant = 85
not_covered = 90
wrongly_not_covered = 10
triage = 90
"""

ROWS = """\
[[cases]]
name = "heels"
kind = "covered"
language = "it"
question = "squat heels down, trunk braced?"
passages = [{ title = "Squat (exercise)", revision = "11", section = "Form", quote = "the heels down" }]

[[cases]]
name = "depth"
kind = "covered"
language = "it"
question = "fino a dove scendo con la schiena dritta?"
passages = [{ title = "Squat", revision = "22", section = "Esecuzione", quote = "fino al parallelo" }]

[[cases]]
name = "pallof"
kind = "near"
language = "en"
question = "how do I do a Pallof press?"

[[cases]]
name = "knee"
kind = "pain"
language = "it"
question = "mi fa male il ginocchio da ieri"
"""


def answer_set(path: Path, *, corpus_version: int = 1) -> Path:
    written = path / "answer-set.toml"
    written.write_text(f"version = 4\ncorpus = {corpus_version}\n\n{BARS}\n{ROWS}", encoding="utf-8")
    return written


@pytest.fixture()
def sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[retrieval.Search]:
    """The in-memory corpus, built and installed, the set beside it, and a clock that stands still."""
    monkeypatch.setenv("TRAINER_ANSWER_SET", str(answer_set(tmp_path)))
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    search = retrieval.in_memory(CHUNKS, version=1)
    search.build()
    with retrieval.installed(search):
        yield search


def no_model(node: str) -> models.Chat:
    raise AssertionError(f"a retrieval-only pass asked for {node}'s model")


def scripted(monkeypatch: pytest.MonkeyPatch, *turns: AIMessage) -> None:
    model = Scripted(turns=list(turns))
    monkeypatch.setattr(models, "chat_for", lambda node: models.Chat(model, "scripted", "a-stand-in"))


def calling(name: str, n: int, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{n}", "type": "tool_call"}])


def passed(runner: CliRunner, tmp_path: Path, *more: str) -> Any:  # noqa: F811
    return runner.invoke(main, ["eval", "--suite", "answer", "--records", str(tmp_path / "records"), *more])


def test_a_retrieval_only_pass_runs_no_model_and_reports_recall_mrr_and_latency(
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    sources: retrieval.Search,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models, "chat_for", no_model)

    result = passed(runner, tmp_path, "--retrieval-only")

    assert result.exit_code == 0, result.output
    assert "recall: 2 of 2 -- 100% [34%, 100%], the bar is 80%" in result.output
    assert "MRR: 1.00" in result.output
    assert "p95 retrieval: 0.00s over 2 searches" in result.output
    assert "pallof" not in result.output and "knee" not in result.output


def test_the_italian_rows_on_english_passages_are_reported_apart_with_no_bar(
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    sources: retrieval.Search,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models, "chat_for", no_model)

    result = passed(runner, tmp_path, "--retrieval-only")

    apart = result.output.split("italian on english")[1]
    assert apart.splitlines()[0] == ": 1 row, no bar"
    assert "recall: 1 of 1 -- 100% [21%, 100%]" in apart


def test_a_pass_against_another_corpus_is_refused_naming_both_versions(
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    sources: retrieval.Search,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAINER_ANSWER_SET", str(answer_set(tmp_path, corpus_version=2)))
    monkeypatch.setattr(models, "chat_for", no_model)

    result = passed(runner, tmp_path, "--retrieval-only")

    assert result.exit_code == 1
    assert "labelled on corpus version 2" in result.output and "the corpus is version 1" in result.output
    assert not (tmp_path / "records").exists()


def test_retrieval_only_belongs_to_the_answer_suite(runner: CliRunner, enriched: Path) -> None:  # noqa: F811
    result = runner.invoke(main, ["eval", "--suite", "log", "--retrieval-only"])

    assert result.exit_code == 2
    assert "--retrieval-only" in result.output


def test_a_full_pass_holds_each_row_to_its_kind_once_and_reports_each_bar(
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    sources: retrieval.Search,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted(
        monkeypatch,
        # heels: cited from a passage the row does not label
        calling(entrance.SEARCH_SOURCES, 1, question="talloni nello squat"),
        calling(entrance.CITE, 2, passage=SQUAT_DEPTH.id, quote="i talloni a terra"),
        AIMessage(content="Talloni a terra."),
        # depth: answered not covered by mistake
        calling(entrance.SEARCH_SOURCES, 3, question="profondita squat"),
        AIMessage(content="Non e nei miei testi.\nCopro tecnica e prevenzione."),
        # pallof: not covered, as it should be
        calling(entrance.SEARCH_SOURCES, 4, question="Pallof press"),
        AIMessage(content="Not in my texts.\nThey cover technique and prevention."),
        # knee: triage, a question and no search
        AIMessage(content="Dove ti fa male, e facendo cosa?"),
    )

    result = passed(runner, tmp_path)

    assert result.exit_code == 1, result.output
    assert "heels quote #1 labelled: " in result.output
    assert "depth #1 answered: " in result.output
    assert "verbatim: 0 of 1 -- 0% [0%, 79%], the bar is 100%" in result.output
    assert "not covered: 1 of 1 -- 100% [21%, 100%], the bar is 90%" in result.output
    assert "covered answered (at most 10% not covered): 1 of 2 -- 50% [9%, 91%], the bar is 90%" in result.output
    assert "triage: 1 of 1 -- 100% [21%, 100%], the bar is 90%" in result.output
    assert sorted(path.name for path in (tmp_path / "records").iterdir()) == [
        "depth-1.json", "heels-1.json", "knee-1.json", "pallof-1.json"
    ]


@pytest.mark.parametrize(
    ("held", "total", "low", "high"),
    [(8, 10, 49.0, 94.3), (0, 4, 0.0, 49.0), (60, 60, 94.0, 100.0)],
)
def test_the_interval_is_wilsons_at_95_percent(held: int, total: int, low: float, high: float) -> None:
    found = eval_runner.interval(held, total)

    assert found == pytest.approx((low, high), abs=0.1)


@pytest.mark.parametrize(
    ("both", "only_new", "only_old", "neither", "low", "high"),
    # Newcombe (1998), Statist. Med. 17:2635, table III, method 10.
    [
        (36, 12, 2, 0, 5.69, 34.04),
        (18, 12, 2, 18, 5.62, 32.90),
        (35, 14, 0, 1, 14.61, 41.75),
        (1, 97, 1, 1, 87.36, 98.50),
        (54, 0, 0, 0, -6.64, 6.64),
    ],
)
def test_the_paired_difference_interval_is_newcombes_hybrid_score(
    both: int, only_new: int, only_old: int, neither: int, low: float, high: float
) -> None:
    found = eval_runner.paired_interval(both, only_new, only_old, neither)

    assert found == pytest.approx((low, high), abs=0.01)


class Blind(retrieval.Search):
    """The same corpus, every search finding only the plank."""

    def search(self, question: str, top: int = retrieval.TOP) -> list[retrieval.Passage]:
        return [retrieval.Passage(PLANK, 1.0)]


def test_a_retrieval_only_pass_is_compared_row_by_row_with_an_earlier_one(
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    sources: retrieval.Search,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models, "chat_for", no_model)
    with retrieval.installed(Blind(sources.embedder, sources.store, sources.version, sources.chunks)):
        before = passed(runner, tmp_path, "--retrieval-only")
    kept = before.output.split("rows kept in ")[1].splitlines()[0].strip()
    earlier = tmp_path / "earlier.json"
    Path(kept).replace(earlier)

    result = passed(runner, tmp_path, "--retrieval-only", "--against", str(earlier))

    assert result.exit_code == 0, result.output
    assert "against words on in memory" in result.output
    assert "2 gained, 0 lost, 0 held by both, 0 by neither" in result.output
    assert f"recall difference: +2 of 2 -- {_points(0, 2, 0, 0)}" in result.output


def _points(both: int, only_new: int, only_old: int, neither: int) -> str:
    low, high = eval_runner.paired_interval(both, only_new, only_old, neither)
    return f"+100 points [{low:+.0f}, {high:+.0f}]"


def test_a_comparison_with_a_pass_on_another_set_is_refused_naming_both(
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    sources: retrieval.Search,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models, "chat_for", no_model)
    first = passed(runner, tmp_path, "--retrieval-only")
    kept = Path(first.output.split("rows kept in ")[1].splitlines()[0].strip())
    held = tmp_path / "answer-set.toml"
    held.write_text(held.read_text(encoding="utf-8").replace("version = 4", "version = 5"), encoding="utf-8")

    result = passed(runner, tmp_path, "--retrieval-only", "--against", str(kept))

    assert result.exit_code == 1
    assert "set version 4" in result.output and "set version 5" in result.output


def test_a_comparison_belongs_to_a_retrieval_only_pass(runner: CliRunner, enriched: Path, tmp_path: Path) -> None:  # noqa: F811
    result = runner.invoke(main, ["eval", "--suite", "answer", "--against", str(tmp_path / "x.json")])

    assert result.exit_code == 2
    assert "--against" in result.output
