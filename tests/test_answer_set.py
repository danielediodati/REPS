"""The answer set: parsed from its TOML, its passages found in the corpus by their words."""

from __future__ import annotations

from pathlib import Path

import pytest

from trainer import answer_set, corpus

SET = """\
version = 1
corpus = 3

[bars]
recall = 80
verbatim = 100
faithful = 90
relevant = 85
not_covered = 90
wrongly_not_covered = 10
triage = 90

[[cases]]
name = "squat-depth"
kind = "covered"
language = "it"
question = "quanto devo scendere?"
passages = [
  { title = "Squat (exercise)", revision = "11", section = "Depth", quote = "below parallel" },
  { title = "Squat", revision = "22", section = "", quote = "sotto il parallelo" },
]

[[cases]]
name = "pallof"
kind = "near"
language = "en"
question = "how do I do a Pallof press?"
"""


def chunk(title: str, revision: str, section: str, text: str) -> corpus.Chunk:
    return corpus.Chunk(
        id=f"{title}/{section}",
        source="wikipedia",
        language="en",
        title=title,
        section=section,
        revision=revision,
        link="https://example.org",
        licence="CC BY-SA 4.0",
        author="Wikipedia contributors",
        text=text,
    )


def test_a_set_carries_its_version_corpus_bars_and_labelled_passages() -> None:
    held = answer_set.parse(SET)

    assert (held.version, held.corpus) == (1, 3)
    assert held.bars["recall"] == 80 and held.bars["wrongly_not_covered"] == 10
    depth, pallof = held.cases
    assert depth.passages[1] == answer_set.Label("Squat", "22", "", "sotto il parallelo")
    assert pallof.kind == answer_set.NEAR and pallof.passages == ()


@pytest.mark.parametrize("bar", answer_set.BARS)
def test_a_set_missing_a_bar_is_refused_naming_it(bar: str) -> None:
    with pytest.raises(answer_set.AnswerSetError, match=bar):
        answer_set.parse(SET.replace(f"\n{bar} = ", "\nunused = ", 1))


@pytest.mark.parametrize("key", ["version", "corpus"])
def test_a_set_that_names_no_version_or_corpus_is_refused(key: str) -> None:
    with pytest.raises(answer_set.AnswerSetError, match=key):
        answer_set.parse(SET.replace(f"{key} = ", "unused = ", 1))


def test_a_kind_nothing_scores_is_refused_naming_the_case() -> None:
    with pytest.raises(answer_set.AnswerSetError, match="pallof"):
        answer_set.parse(SET.replace('kind = "near"', 'kind = "maybe"'))


def test_a_row_expected_to_cite_without_a_passage_is_refused() -> None:
    bare = SET.replace('kind = "near"', 'kind = "prevention"')

    with pytest.raises(answer_set.AnswerSetError, match="pallof"):
        answer_set.parse(bare)


def test_a_row_outside_the_corpus_that_labels_a_passage_is_refused() -> None:
    labelled = SET.replace('kind = "covered"', 'kind = "off_topic"')

    with pytest.raises(answer_set.AnswerSetError, match="squat-depth"):
        answer_set.parse(labelled)


def test_a_language_other_than_italian_or_english_is_refused() -> None:
    with pytest.raises(answer_set.AnswerSetError, match="squat-depth"):
        answer_set.parse(SET.replace('language = "it"', 'language = "fr"'))


def test_a_name_used_twice_is_refused() -> None:
    with pytest.raises(answer_set.AnswerSetError, match="pallof"):
        answer_set.parse(SET.replace('"squat-depth"', '"pallof"'))


def test_a_missing_set_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(answer_set.AnswerSetError, match="nowhere.toml"):
        answer_set.load(tmp_path / "nowhere.toml")


def test_a_row_keeps_its_passage_while_one_label_is_found_whitespace_aside() -> None:
    held = answer_set.parse(SET)
    chunks = [chunk("Squat (exercise)", "11", "Depth", "Go just\nbelow   parallel, then up.")]

    assert answer_set.lost(held, chunks) == []


def test_a_row_none_of_whose_labels_is_found_is_lost() -> None:
    held = answer_set.parse(SET)
    elsewhere = [
        chunk("Squat (exercise)", "12", "Depth", "below parallel"),
        chunk("Squat", "22", "Profondità", "sotto il parallelo"),
    ]

    assert answer_set.lost(held, elsewhere) == ["squat-depth"]


def test_every_label_of_the_committed_set_is_found_in_the_committed_corpus() -> None:
    held = answer_set.load()
    chunks = corpus.read_chunks()

    unfound = [
        f"{case.name}: {label.title} § {label.section}"
        for case in held.cases
        for label in case.passages
        if not answer_set.found(label, chunks)
    ]
    assert unfound == []


def test_the_committed_set_names_the_corpus_it_ships_with() -> None:
    assert answer_set.load().corpus == corpus.read_manifest().version
