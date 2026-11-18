"""The answer suite's eval set: questions, what each expects, and the passages that answer it, labelled by their words."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from trainer import corpus, eval_set
from trainer.corpus import Chunk

ANSWER_SET_ENV_VAR = "TRAINER_ANSWER_SET"
DEFAULT_PARTS = ("docs", "answering", "eval-set.toml")

COVERED = "covered"
NEAR = "near"
OFF_TOPIC = "off_topic"
PAIN = "pain"
TECHNIQUE_PAIN = "technique_pain"
PREVENTION = "prevention"
CITING = (COVERED, TECHNIQUE_PAIN, PREVENTION)
UNCITED = (NEAR, OFF_TOPIC, PAIN)

LANGUAGES = ("it", "en")
BARS = ("recall", "verbatim", "faithful", "relevant", "not_covered", "wrongly_not_covered", "triage")


class AnswerSetError(eval_set.SetError):
    """A set that cannot be run as written, saying where."""


@dataclass(frozen=True)
class Label:
    """A passage that answers a row: the page, its revision and section, and words quoted from it."""

    title: str
    revision: str
    section: str
    quote: str


@dataclass(frozen=True)
class Case:
    """One question in the owner's words, the kind of reply it expects, and the passages that answer it."""

    name: str
    kind: str
    language: str
    question: str
    passages: tuple[Label, ...] = ()


@dataclass(frozen=True)
class AnswerSet:
    version: int
    corpus: int
    bars: Mapping[str, int]
    cases: tuple[Case, ...] = field(default_factory=tuple)


def path() -> Path:
    """Where the set is read from: `TRAINER_ANSWER_SET`, or the committed one."""
    return eval_set.path(ANSWER_SET_ENV_VAR, DEFAULT_PARTS)


def load(where: Path | None = None) -> AnswerSet:
    """The set, off disk; refused naming the file when it is not there."""
    return eval_set.load(where, ANSWER_SET_ENV_VAR, DEFAULT_PARTS, "answer eval set", parse, AnswerSetError)


def parse(text: str) -> AnswerSet:
    """A set out of its TOML, every row checked against what the suite can score."""
    raw = eval_set.toml(text, AnswerSetError)
    for key in ("version", "corpus"):
        if not isinstance(raw.get(key), int):
            raise AnswerSetError(f"the set names no {key}")
    bars = raw.get("bars")
    if not isinstance(bars, dict):
        bars = {}
    missing = [bar for bar in BARS if bar not in bars]
    if missing:
        raise AnswerSetError(f"the set's [bars] lack {', '.join(missing)}")
    cases = tuple(_case(entry) for entry in raw.get("cases", ()))
    eval_set.unique([case.name for case in cases], AnswerSetError)
    return AnswerSet(
        version=raw["version"],
        corpus=raw["corpus"],
        bars={bar: int(bars[bar]) for bar in BARS},
        cases=cases,
    )


def found(label: Label, chunks: Iterable[Chunk]) -> bool:
    """Whether the corpus holds the label's quote in its page, revision and section, whitespace and quote marks aside."""
    return any(
        (chunk.title, chunk.revision, chunk.section) == (label.title, label.revision, label.section)
        and corpus.quoted(label.quote, chunk.text) is not None
        for chunk in chunks
    )


def lost(held: AnswerSet, chunks: Sequence[Chunk]) -> list[str]:
    """The rows that cite and of whose labels the corpus holds none."""
    return [
        case.name
        for case in held.cases
        if case.passages and not any(found(label, chunks) for label in case.passages)
    ]


def settle(corpus: int, chunks: Sequence[Chunk], where: Path | None = None) -> AnswerSet:
    """Bump the set's version and name `corpus`, its rows as they stand; refused while a row has lost its quote."""
    where = where or path()
    held = load(where)
    missing = lost(held, chunks)
    if missing:
        raise AnswerSetError(
            f"corpus version {corpus} holds none of the labelled quotes of {', '.join(missing)}; "
            f"relabel or drop each in {where}, then settle again"
        )
    settled = replace(held, version=held.version + 1, corpus=corpus)
    text = where.read_bytes().decode("utf-8")
    for key, value in (("version", settled.version), ("corpus", settled.corpus)):
        text = re.sub(rf"^{key} = \d+", f"{key} = {value}", text, count=1, flags=re.MULTILINE)
    where.write_bytes(text.encode("utf-8"))
    return settled


def _case(raw: Mapping[str, Any]) -> Case:
    name = str(raw.get("name", ""))
    kind = raw.get("kind")
    if kind not in CITING + UNCITED:
        raise AnswerSetError(f"case {name}: kind {kind!r} is none of {', '.join(CITING + UNCITED)}")
    language = raw.get("language")
    if language not in LANGUAGES:
        raise AnswerSetError(f"case {name}: language {language!r} is none of {', '.join(LANGUAGES)}")
    try:
        passages = tuple(
            Label(str(entry["title"]), str(entry["revision"]), str(entry["section"]), str(entry["quote"]))
            for entry in raw.get("passages", ())
        )
    except (KeyError, TypeError) as broken:
        raise AnswerSetError(f"case {name}: a passage lacks {broken}") from broken
    if kind in CITING and not passages:
        raise AnswerSetError(f"case {name}: a {kind} row labels no passage")
    if kind in UNCITED and passages:
        raise AnswerSetError(f"case {name}: a {kind} row expects no source, yet labels a passage")
    return Case(name=name, kind=kind, language=language, question=str(raw.get("question", "")), passages=passages)
