"""What a run is doing, in the words the chat shows while it works."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from trainer import plan as plans
from trainer.coach import planner

logger = logging.getLogger(__name__)

CALLS = {
    "admissible_set": "guardo cosa puoi fare oggi con {equipment} e {budget_min} minuti",
    "remaining_budget": "controllo quanto tempo resta",
    "allocate": "divido {minutes} minuti fra i gruppi",
    "pattern_history": "guardo lo storico di {pattern}",
    "last_performed_load": "cerco l'ultimo carico su {exercise_id}",
    "search_exercises": "cerco «{text}» in catalogo",
    "adherence_history": "guardo quanto hai seguito i piani",
    "volume_deficit": "confronto il volume pianificato con quello fatto",
    "unreported_workouts": "controllo se è rimasto un allenamento senza report",
    "compare_variants": "confronto {id_a} e {id_b}",
    "prescribed_workout": "rileggo l'allenamento {workout_id}",
    "ask_user": "ti chiedo una cosa",
}
"""One line per tool a streamed run can call, in the user's language.

Keyed by the tool lists of the graphs that are streamed, and a test fails the
build when one of them is missing a line. The words the model chose are shown
as they arrive -- an equipment name is the catalog's own and is not translated
here, which is the same rule that keeps a hand-copied equipment list out of
the code.
"""

UNKNOWN = "uso {tool}"
"""A tool with no line of its own. Never reached while the test above is green."""

ANSWERS = {"remaining_budget": "{answer} min"}
"""The tools whose answer is one number worth showing beside the question."""

FAILED = "non ha funzionato"

WRITING = "scrivo il piano"
REWRITING = "riscrivo il piano"
REFUSED = "il validatore ha rifiutato: {rules}"
EXHAUSTED = "dopo {attempts} tentativi non ho un piano che stia nei vincoli"
VALID = "piano valido, {blocks}"
ONE_BLOCK = "1 blocco"
BLOCKS = "{count} blocchi"
AGAIN = "va bene, ne penso un altro"

WRITING_REPORT = "metto giù quello che hai fatto"
READ = "report letto"
NOT_READ = "il report non è passato: {why}"

PLAN = "plan"
LOG = "log"
"""Which run is being watched. The two graphs share four node names and mean
different things by three of them: `emit` writes a plan on one and a performed
workout on the other, and a draft that says *scrivo il piano* while a report is
being read is a lie about what the machine is doing."""

LIMIT = 3500
"""Characters a draft is cut to, under Telegram's 4096, oldest lines first."""


class Progress:
    """The lines a run has produced so far, read off the graph's own updates.

    One object per run. It is fed the `updates` chunks in the order LangGraph
    emits them and never asks the graph anything: what the user watches is the
    run itself, not a second account of it written beside the run.
    """

    def __init__(self, of: str = PLAN) -> None:
        self.of = of
        self.lines: list[str] = []
        self._pending: list[Any] = []
        self._emitted = 0

    def reading(self, update: Mapping[str, Any]) -> bool:
        """One chunk, as new lines. True when the draft has something new to show."""
        before = len(self.lines)
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
            self.lines.append(AGAIN)
        # `confirm` says nothing: the exclusion it proposes is put to the user
        # as a question in the chat, and a draft repeating it is the same
        # sentence twice.

    def _writing(self) -> str:
        if self.of == LOG:
            return WRITING_REPORT
        return WRITING if self._emitted == 0 else REWRITING

    def _answered(self, answers: Sequence[Any]) -> None:
        """One line per call, with the answers the tools node paired them with.

        Written here rather than when the model asked, so a tool whose answer
        is a number can show it. The node answers the calls in the order they
        were made, which is what lets the two be zipped.
        """
        for call, answer in zip(self._pending, answers, strict=False):
            self.lines.append(_asked(call, answer))
        self._pending = []

    def _validated(self, delta: Mapping[str, Any]) -> None:
        violations: Sequence[plans.Violation] = delta.get("violations", ())
        if not violations:
            plan = delta.get("plan")
            blocks = len(plan.blocks) if plan is not None else 0
            self.lines.append(VALID.format(blocks=_counted(blocks)))
            return
        attempts = delta.get("attempts", 0)
        if attempts >= planner.ATTEMPTS:
            self.lines.append(EXHAUSTED.format(attempts=attempts))
            return
        self.lines.append(
            REFUSED.format(rules=", ".join(broken.rule for broken in violations))
        )

    def _read(self, delta: Mapping[str, Any]) -> None:
        """What the logger's validator made of the document it was handed."""
        refused = delta.get("refused")
        self.lines.append(READ if refused is None else NOT_READ.format(why=refused))


def _counted(blocks: int) -> str:
    return ONE_BLOCK if blocks == 1 else BLOCKS.format(count=blocks)


def _calls(messages: Sequence[AnyMessage]) -> list[Any]:
    """The tool calls a planner turn asked for, or none at all."""
    if not messages:
        return []
    last = messages[-1]
    return list(last.tool_calls) if isinstance(last, AIMessage) else []


def _asked(call: Mapping[str, Any], answer: Any) -> str:
    line = _phrased(str(call.get("name", "")), call.get("args") or {})
    said = _said(str(call.get("name", "")), answer)
    return f"{line} → {said}" if said else line


def _phrased(name: str, arguments: Mapping[str, Any]) -> str:
    """The call, in words. The arguments are the model's and may be anything."""
    template = CALLS.get(name)
    if template is None:
        return UNKNOWN.format(tool=name)
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


def _said(name: str, answer: Any) -> str:
    """What a tool answered, for the few whose answer is one number."""
    if not isinstance(answer, ToolMessage):
        return ""
    if answer.status == "error":
        return FAILED
    template = ANSWERS.get(name)
    if template is None:
        return ""
    try:
        return template.format(answer=json.loads(answer.text))
    except (ValueError, TypeError):
        logger.info("could not read what %s answered", name)
        return ""
