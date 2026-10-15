"""What a run is doing, in the words the chat shows while it works."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from trainer import plan as plans
from trainer.coach import planner
from trainer.coach.language import ITALIAN, Language, ProgressLines, texts

logger = logging.getLogger(__name__)

ANSWERS = {"remaining_budget": "{answer} min"}
"""The tools whose answer is one number worth showing beside the question."""

PLAN = "plan"
LOG = "log"
ONBOARD = "onboard"
"""Which run is being watched. The two graphs share four node names and mean
different things by three of them: `emit` writes a plan on one and a performed
workout on the other, and a draft that says *scrivo il piano* while a report is
being read is a lie about what the machine is doing. An interview shows no
lines: its steps are questions, and they reach the chat as messages."""

LIMIT = 3500
"""Characters a draft is cut to, under Telegram's 4096, oldest lines first."""


class Progress:
    """The lines a run has produced so far, read off the graph's own updates.

    One object per run. It is fed the `updates` chunks in the order LangGraph
    emits them and never asks the graph anything: what the user watches is the
    run itself, not a second account of it written beside the run.
    """

    def __init__(self, of: str = PLAN, language: Language = ITALIAN) -> None:
        self.of = of
        self.language = language
        self._said = texts(language).progress
        self.lines: list[str] = []
        self._pending: list[Any] = []
        self._emitted = 0

    def reading(self, update: Mapping[str, Any]) -> bool:
        """One chunk, as new lines. True when the draft has something new to show."""
        before = len(self.lines)
        if self.of == ONBOARD:
            return False
        for node, delta in update.items():
            if isinstance(delta, Mapping):
                self._node(node, delta)
        return len(self.lines) > before

    def text(self) -> str:
        """The lines as one message, cut from the front to what Telegram carries."""
        shown = list(self.lines)
        while len(shown) > 1 and sum(len(line) + 1 for line in shown) > LIMIT:
            shown.pop(0)
        # Sliced as well as trimmed: one line is one line however long, and a
        # tool called with half a catalog in an argument would otherwise be a
        # draft Telegram refuses.
        return "\n".join(shown)[-LIMIT:]

    def _node(self, node: str, delta: Mapping[str, Any]) -> None:
        if node in ("planner", "logger"):
            self._pending = list(_calls(delta.get("messages", ())))
        elif node == "tools":
            self._answered(delta.get("messages", ()))
        elif node == "emit":
            self.lines.append(self._writing())
            self._emitted += 1
        elif node == "validate":
            self._validated(delta) if self.of == PLAN else self._read(delta)
        elif node == "propose" and "request" in delta:
            # The plan was turned down and the node handed back a fresh run.
            self.lines.append(self._said.again)
        # `confirm` says nothing: the exclusion it proposes is put to the user
        # as a question in the chat, and a draft repeating it is the same
        # sentence twice.

    def _writing(self) -> str:
        if self.of == LOG:
            return self._said.writing_report
        return self._said.writing if self._emitted == 0 else self._said.rewriting

    def _answered(self, answers: Sequence[Any]) -> None:
        """One line per call, with the answers the tools node paired them with.

        Written here rather than when the model asked, so a tool whose answer
        is a number can show it. The node answers the calls in the order they
        were made, which is what lets the two be zipped.
        """
        for call, answer in zip(self._pending, answers, strict=False):
            self.lines.append(_asked(call, answer, self._said))
        self._pending = []

    def _validated(self, delta: Mapping[str, Any]) -> None:
        said = self._said
        violations: Sequence[plans.Violation] = delta.get("violations", ())
        if not violations:
            plan = delta.get("plan")
            if isinstance(plan, plans.Mesocycle):
                workouts = said.workouts.format(count=len(plan.workouts))
                self.lines.append(said.valid.format(blocks=workouts))
                return
            blocks = len(plan.blocks) if plan is not None else 0
            self.lines.append(said.valid.format(blocks=_counted(blocks, said)))
            return
        attempts = delta.get("attempts", 0)
        if attempts >= planner.ATTEMPTS:
            self.lines.append(said.exhausted.format(attempts=attempts))
            return
        self.lines.append(
            said.refused.format(rules=", ".join(broken.rule for broken in violations))
        )

    def _read(self, delta: Mapping[str, Any]) -> None:
        """What the logger's validator made of the document it was handed."""
        refused = delta.get("refused")
        said = self._said
        self.lines.append(said.read if refused is None else said.not_read.format(why=refused))


def _counted(blocks: int, said: ProgressLines) -> str:
    return said.one_block if blocks == 1 else said.blocks.format(count=blocks)


def _calls(messages: Sequence[AnyMessage]) -> list[Any]:
    """The tool calls a planner turn asked for, or none at all."""
    if not messages:
        return []
    last = messages[-1]
    return list(last.tool_calls) if isinstance(last, AIMessage) else []


def _asked(call: Mapping[str, Any], answer: Any, said: ProgressLines) -> str:
    line = _phrased(str(call.get("name", "")), call.get("args") or {}, said)
    answered = _answer(str(call.get("name", "")), answer, said)
    return f"{line} → {answered}" if answered else line


def _phrased(name: str, arguments: Mapping[str, Any], said: ProgressLines) -> str:
    """The call, in words. The arguments are the model's and may be anything."""
    template = said.calls.get(name)
    if template is None:
        return said.unknown.format(tool=name)
    return template.format_map(_Arguments(arguments))


class _Arguments(dict[str, str]):
    """The model's arguments, readable, and forgiving of the ones it left out."""

    def __init__(self, given: Mapping[str, Any]) -> None:
        super().__init__({key: _readable(value) for key, value in given.items()})

    def __missing__(self, key: str) -> str:
        return "?"


def _readable(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _answer(name: str, answer: Any, said: ProgressLines) -> str:
    """What a tool answered, for the few whose answer is one number."""
    if not isinstance(answer, ToolMessage):
        return ""
    if answer.status == "error":
        return said.failed
    template = ANSWERS.get(name)
    if template is None:
        return ""
    try:
        return template.format(answer=json.loads(answer.text))
    except (ValueError, TypeError):
        logger.info("could not read what %s answered", name)
        return ""
