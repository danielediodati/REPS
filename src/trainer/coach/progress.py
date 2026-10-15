"""What a run is doing, in the one line the chat shows while it works."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage

from trainer import plan as plans
from trainer.coach import logger as coach_logger
from trainer.coach import planner
from trainer.coach.language import ITALIAN, Language, ProgressLines, texts

PLAN = "plan"
LOG = "log"
ONBOARD = "onboard"
"""Which run is being watched. The two graphs share four node names and mean
different things by three of them: `emit` writes a plan on one and a performed
workout on the other, and a draft that says *scrivo il piano* while a report is
being read is a lie about what the machine is doing. An interview shows no
lines: its steps are questions, and they reach the chat as messages."""

ASKING = coach_logger.ask_user.__name__
"""The logger's question to the user, which is no phase of the run."""

GROUPS, SHARES, BUDGET, MINUTES = "muscle_groups", "proportions", "budget_min", "minutes"
"""The tool arguments a mesocycle's workout is recognised by."""

LIMIT = 3500
"""Characters a draft is cut to, under Telegram's 4096."""


class Progress:
    """The phases one run has passed through, read off its `updates` chunks; the draft shows the last."""

    def __init__(self, of: str = PLAN, language: Language = ITALIAN) -> None:
        self.of = of
        self.language = language
        self._said = texts(language).progress
        self.lines: list[str] = []
        self._slots: tuple[plans.Request, ...] = ()
        self._workout: int | None = None
        self._budget: int | None = None
        self._refused = False

    def reading(self, update: Mapping[str, Any]) -> bool:
        """One chunk, read into the current phase. True when the line changed."""
        before = self.text()
        if self.of == ONBOARD:
            return False
        for node, delta in update.items():
            if isinstance(delta, Mapping):
                self._node(node, delta)
        return self.text() != before

    def text(self) -> str:
        """The current line, cut to what Telegram carries."""
        return self.lines[-1][:LIMIT] if self.lines else ""

    def _now(self, line: str) -> None:
        if not self.lines or self.lines[-1] != line:
            self.lines.append(line)

    def _node(self, node: str, delta: Mapping[str, Any]) -> None:
        if node in ("planner", "logger"):
            self._turned(delta)
        elif node == "tools":
            spent = delta.get("spent", 0)
            if delta.get("finished") or (self._budget is not None and spent >= self._budget):
                # No turn follows a spent budget: the next node is `emit`.
                self._now(self._writing())
        elif node == "emit":
            # A retried emission has rejections and is still writing.
            if self.of == PLAN and not delta.get("rejections"):
                self._now(self._said.checking)
        elif node == "validate":
            self._validated(delta) if self.of == PLAN else self._read(delta)
        elif node == "propose" and "request" in delta:
            # The plan was turned down and the node handed back a fresh run.
            self._refused = False
            self._workout = None
            self._requested(delta["request"])
            self._now(self._said.again)
        # `confirm` says nothing: the exclusion it proposes is put to the user
        # as a question in the chat, and a draft repeating it is the same
        # sentence twice.

    def _turned(self, delta: Mapping[str, Any]) -> None:
        """A model turn: looking something up, or done and on to writing."""
        if "budget" in delta:
            self._budget = delta["budget"]
        if "request" in delta:
            self._requested(delta["request"])
        messages: Sequence[AnyMessage] = delta.get("messages", ())
        reply = messages[-1] if messages else None
        if not isinstance(reply, AIMessage):
            # A provider refusing the turn: the run asks again, still in its phase.
            return
        if not reply.tool_calls:
            self._now(self._writing())
        elif all(call["name"] == ASKING for call in reply.tool_calls):
            # A question, which reaches the chat as a message of its own.
            return
        elif self.of == LOG:
            self._now(self._said.reading_report)
        else:
            self._now(self._looking(reply.tool_calls))

    def _requested(self, request: Any) -> None:
        if isinstance(request, plans.MesocycleRequest) and request.slots != self._slots:
            self._slots = request.slots
            self._workout = None

    def _looking(self, calls: Sequence[Mapping[str, Any]]) -> str:
        for call in calls:
            self._workout = _workout(self._slots, call.get("args") or {}, self._workout)
        if self._workout is None:
            return self._said.looking
        return self._said.looking_workout.format(
            workout=self._workout + 1, count=len(self._slots)
        )

    def _writing(self) -> str:
        if self.of == LOG:
            return self._said.writing_report
        return self._said.rewriting if self._refused else self._said.writing

    def _validated(self, delta: Mapping[str, Any]) -> None:
        said = self._said
        violations: Sequence[plans.Violation] = delta.get("violations", ())
        if not violations:
            plan = delta.get("plan")
            if isinstance(plan, plans.Mesocycle):
                workouts = said.workouts.format(count=len(plan.workouts))
                self._now(said.valid.format(blocks=workouts))
                return
            blocks = len(plan.blocks) if plan is not None else 0
            self._now(said.valid.format(blocks=_counted(blocks, said)))
            return
        attempts = delta.get("attempts", 0)
        if attempts >= planner.ATTEMPTS:
            self._now(said.exhausted.format(attempts=attempts))
            return
        self._refused = True
        self._workout = None
        self._now(said.refused.format(rules=", ".join(broken.rule for broken in violations)))

    def _read(self, delta: Mapping[str, Any]) -> None:
        """What the logger's validator made of the document it was handed."""
        refused = delta.get("refused")
        said = self._said
        self._now(said.read if refused is None else said.not_read.format(why=refused))


def _counted(blocks: int, said: ProgressLines) -> str:
    return said.one_block if blocks == 1 else said.blocks.format(count=blocks)


def _workout(
    slots: Sequence[plans.Request], arguments: Mapping[str, Any], current: int | None
) -> int | None:
    """Which workout of the cycle a call is about, by the groups and minutes it names; `current` when it names none."""
    named = arguments.get(GROUPS)
    if not isinstance(named, list):
        proportions = arguments.get(SHARES)
        named = list(proportions) if isinstance(proportions, Mapping) else None
    if not named:
        return current
    groups = {str(group) for group in named}
    matching = [at for at, slot in enumerate(slots) if set(slot.groups) == groups]
    minutes = arguments.get(BUDGET, arguments.get(MINUTES))
    timed = [at for at in matching if slots[at].budget_min == minutes]
    candidates = timed or matching
    if not candidates:
        return current
    # The brief asks for the workouts in order, so of two alike the later one is next.
    return next((at for at in candidates if current is None or at >= current), candidates[0])
