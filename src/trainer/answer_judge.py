"""Faithfulness read by a model the way RAGAS reads it, relevance asked of it outright, both scored in code."""

from __future__ import annotations

import json
import math
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage

from trainer import corpus

CALIBRATION = Path(__file__).resolve().parents[2] / "docs" / "answering" / "judge-calibration.toml"

REAL, UNSUPPORTED, OFF_QUESTION = "real", "unsupported", "off_question"
KINDS = (REAL, UNSUPPORTED, OFF_QUESTION)

CANDIDATES = ("openai/gpt-oss-120b", "qwen/qwen3-32b", "anthropic/claude-haiku-4.5")
"""Cheapest first, never the answering model's family (ADR-0018)."""

CAUGHT_BAR, AGREED_BAR = 13, 27
"""Of the 15 planted, how many the judge must catch; of the 30 real, on how many it must agree."""

_STATEMENTS = """Break the answer below into short, self-contained factual statements, one claim each, \
in the answer's language. Leave out courtesy, offers of help and restatements of the question.

Question: {question}
Answer: {answer}

Reply with JSON only: {{"statements": ["...", "..."]}}"""

_VERDICTS = """Here is a context and a list of statements. For each statement say whether the context \
supports it: 1 if the context states it or it follows directly from what the context states \
(in any language), 0 otherwise.

Context:
{context}

Statements:
{statements}

Reply with JSON only: {{"verdicts": [{{"statement": "...", "verdict": 0 or 1}}, ...]}}, one per statement, in order."""

_RELEVANT = """Does the answer below answer the question that was asked? 1 if it addresses that \
question, even partly but on point; 0 if it answers a different question, even a closely related one \
on the same topic, dodges, or only gives loosely related information.

Question: {question}
Answer: {answer}

Reply with JSON only: {{"reason": "<one short sentence>", "relevant": 0 or 1}}"""


class JudgeError(RuntimeError):
    """The judge's reply could not be read, with what it said."""


@dataclass(frozen=True)
class Reply:
    """One answer to judge: the question, the reply, and the passages it cited."""

    id: str
    question: str
    answer: str
    passages: tuple[str, ...]
    """The cited chunks' ids."""


@dataclass(frozen=True)
class Verdict:
    """What the judge read of one reply, and what reading it cost."""

    faithfulness: float
    relevance: float
    statements: tuple[tuple[str, bool], ...]
    reason: str
    """Why the judge read the answer as relevant or not."""

    dollars: float


class Judge:
    """A chat model reading an answer's statements against its passages, and whether it answers."""

    def __init__(self, chat: BaseChatModel) -> None:
        self.chat = chat
        self.dollars = 0.0

    def judge(self, reply: Reply, texts: dict[str, str]) -> Verdict:
        """Faithfulness as the share of statements the cited passages support; relevance as 1 or 0."""
        spent = self.dollars
        statements = [str(s) for s in self._ask(_STATEMENTS.format(question=reply.question, answer=reply.answer))["statements"]]
        supported: list[bool] = []
        if statements:
            context = "\n\n".join(texts[one] for one in reply.passages)
            listed = "\n".join(f"{n}. {s}" for n, s in enumerate(statements, 1))
            verdicts = self._ask(_VERDICTS.format(context=context, statements=listed))["verdicts"]
            supported = [bool(int(v.get("verdict", 0))) for v in verdicts][: len(statements)]
            supported += [False] * (len(statements) - len(supported))
        faithfulness = sum(supported) / len(supported) if supported else 0.0
        asked = self._ask(_RELEVANT.format(question=reply.question, answer=reply.answer))
        return Verdict(
            faithfulness,
            float(bool(int(asked.get("relevant", 0)))),
            tuple(zip(statements, supported)),
            str(asked.get("reason", "")),
            self.dollars - spent,
        )

    def _ask(self, prompt: str) -> dict[str, Any]:
        """The judge's JSON reply to one prompt, asked again once if it is not JSON."""
        said = ""
        for _attempt in range(2):
            message: BaseMessage = self.chat.invoke([HumanMessage(prompt)])
            self.dollars += float(message.response_metadata.get("cost") or 0.0)
            said = message.text if isinstance(message.text, str) else str(message.content)
            found = re.search(r"\{.*\}", said, re.S)
            if found:
                try:
                    read = json.loads(found.group(0))
                except json.JSONDecodeError:
                    continue
                if isinstance(read, dict):
                    return read
        raise JudgeError(f"the judge did not reply with JSON: {said[:200]!r}")


@dataclass(frozen=True)
class Calibrated:
    """One reply of the calibration set: its kind and, for a real one, the reader's labels."""

    reply: Reply
    kind: str
    faithful: bool
    relevant: bool


@dataclass(frozen=True)
class Calibration:
    """The frozen replies a judge clears its bar on, versioned with the answer set."""

    version: int
    answer_set: int
    replies: tuple[Calibrated, ...] = field(default_factory=tuple)


def load(path: Path = CALIBRATION) -> Calibration:
    """The calibration set as written."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    replies = tuple(
        Calibrated(
            Reply(one["id"], one["question"], one["answer"], tuple(one["passages"])),
            one["kind"],
            bool(one["faithful"]),
            bool(one["relevant"]),
        )
        for one in raw["replies"]
    )
    for one in replies:
        if one.kind not in KINDS:
            raise ValueError(f"{one.reply.id}: kind {one.kind!r} is not one of {', '.join(KINDS)}")
    return Calibration(int(raw["version"]), int(raw["answer_set"]), replies)


def passages() -> dict[str, str]:
    """Each corpus chunk's text under its title and section, by id, as the judge reads it."""
    return {c.id: f"{c.title} / {c.section}\n{c.text}" for c in corpus.read_chunks()}


@dataclass(frozen=True)
class Thresholds:
    """The scores at or above which a reply reads as faithful, and as relevant."""

    faithful: float
    relevant: float


def fitted(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """The threshold agreeing with the most labels; the highest such, so a tie is read strictly.

    With every label *yes*, the lowest any of them scored: anything lower reads *no*.
    """
    candidates = sorted({0.0, *scores, math.inf})
    return max(candidates, key=lambda t: (sum((s >= t) == y for s, y in zip(scores, labels)), t))


@dataclass(frozen=True)
class Reading:
    """A judge's verdicts on the calibration set, against its bar."""

    thresholds: Thresholds
    agreed: int
    real: int
    caught: int
    planted: int
    dollars: float
    disagreements: tuple[str, ...]

    @property
    def clears(self) -> bool:
        return self.agreed >= AGREED_BAR and self.caught >= CAUGHT_BAR


def read(calibration: Calibration, verdicts: dict[str, Verdict]) -> Reading:
    """Thresholds fitted on the real replies, then agreement on them and planted errors caught."""
    real = [one for one in calibration.replies if one.kind == REAL]
    planted = [one for one in calibration.replies if one.kind != REAL]
    thresholds = Thresholds(
        fitted([verdicts[o.reply.id].faithfulness for o in real], [o.faithful for o in real]),
        fitted([verdicts[o.reply.id].relevance for o in real], [o.relevant for o in real]),
    )

    def says(one: Calibrated) -> tuple[bool, bool]:
        v = verdicts[one.reply.id]
        return v.faithfulness >= thresholds.faithful, v.relevance >= thresholds.relevant

    disagreements = [
        f"{o.reply.id}: judge faithful {says(o)[0]}, relevant {says(o)[1]}; reader {o.faithful}, {o.relevant}"
        for o in real
        if says(o) != (o.faithful, o.relevant)
    ]
    caught = 0
    for one in planted:
        faithful, relevant = says(one)
        if (one.kind == UNSUPPORTED and not faithful) or (one.kind == OFF_QUESTION and not relevant):
            caught += 1
        else:
            disagreements.append(f"{one.reply.id}: planted {one.kind} not caught")
    return Reading(
        thresholds,
        len(real) - sum(1 for d in disagreements if "planted" not in d),
        len(real),
        caught,
        len(planted),
        sum(v.dollars for v in verdicts.values()),
        tuple(disagreements),
    )
