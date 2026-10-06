"""One ask and its runs, holding at most one plan: the life both the bot and the CLI drive."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from trainer import plan as plans
from trainer import tools
from trainer.coach import planner
from trainer.coach import record as records
from trainer.coach import supervisor as supervisor_graph
from trainer.engine import mesocycles

Progress = Callable[[dict[str, Any]], None]
"""Called with each update the planner streams, for a door that shows the run as it goes."""


@dataclass(frozen=True)
class Proposed:
    """A plan offered and waiting, answerable only by its id."""

    plan: plans.WorkoutPlan | plans.Mesocycle
    request: plans.Request | plans.MesocycleRequest
    id: str
    unasked: bool


@dataclass(frozen=True)
class Accepted:
    """The plan kept: a workout written, or a mesocycle kept."""

    plan: plans.WorkoutPlan | plans.Mesocycle
    workout: int | None
    mesocycle: int | None
    record: dict[str, Any]


@dataclass(frozen=True)
class Refused:
    """The validator refused every attempt, and nothing was offered."""

    violations: tuple[plans.Violation, ...]
    record: dict[str, Any]


@dataclass(frozen=True)
class Superseded:
    """The answer was to a proposal no longer in hand, and nothing was written."""


Outcome = Proposed | Accepted | Refused | Superseded


def outcome(final: Mapping[str, Any], budget: int = tools.CALL_BUDGET) -> Outcome:
    """Where a planner run stopped, as the result a door renders."""
    waiting = final.get("__interrupt__")
    if waiting:
        return Proposed(
            final["plan"], final["request"], waiting[0].id, bool(final.get("unasked"))
        )
    if final.get("workout") is not None or final.get("mesocycle") is not None:
        return Accepted(
            final["plan"],
            final.get("workout"),
            final.get("mesocycle"),
            records.of(final, budget),
        )
    return Refused(tuple(final.get("violations", ())), records.of(final, budget))


def next_request() -> plans.MesocycleRequest | None:
    """The next mesocycle's request, when the last cycle has just ended."""
    with tools.reported(), tools.opened() as connection:
        ended = mesocycles.finished(connection)
        if ended is None or ended.past:
            return None
        return plans.next_requested(connection, date.today().isoformat())


class Negotiation:
    """Plan proposals on one planner graph: opened, answered, prepared and read back."""

    def __init__(
        self,
        planning: planner.Planner,
        archive: Path | None = None,
        budget: int = tools.CALL_BUDGET,
        supervisor: supervisor_graph.Supervisor | None = None,
        preparing: set[str] | None = None,
    ) -> None:
        self._planner = planning
        self._archive = archive
        self._budget = budget
        self._supervisor = supervisor
        self._preparing = preparing if preparing is not None else set()
        self._claiming = threading.Lock()

    def open(
        self,
        on: RunnableConfig,
        request: plans.Request | plans.MesocycleRequest,
        carrying: Mapping[str, Any] | None = None,
        progress: Progress | None = None,
        unasked: bool = False,
    ) -> Outcome:
        """A new ask on this thread, superseding any proposal pending on it."""
        given = dict(planner.starting(request, unasked=unasked)) | dict(carrying or {})
        return self._ran(given, on, progress)

    def answer(
        self,
        on: RunnableConfig,
        proposal: str,
        answer: planner.Answer,
        progress: Progress | None = None,
    ) -> Outcome:
        """The proposal `proposal` kept or turned down; superseded when it is not the one pending."""
        held = self.pending(on)
        if held is None or held.id != proposal:
            return Superseded()
        return self._ran(Command(resume=answer), on, progress)

    def pending(self, on: RunnableConfig) -> Proposed | None:
        """The proposal this thread is waiting on, or nothing."""
        held = self._planner.get_state(on)
        if not held.interrupts:
            return None
        return Proposed(
            held.values["plan"],
            held.values["request"],
            held.interrupts[0].id,
            bool(held.values.get("unasked")),
        )

    def preparing(self, on: RunnableConfig) -> bool:
        """Whether the next mesocycle is being prepared on this thread right now."""
        return _thread(on) in self._preparing

    def prepare(self, on: RunnableConfig, directing: RunnableConfig) -> Outcome | None:
        """The next mesocycle, directed then planned unasked; nothing if one is offered, being prepared, or not due."""
        thread = _thread(on)
        with self._claiming:
            if thread in self._preparing or self._offers_a_mesocycle(on):
                return None
            request = next_request()
            if request is None:
                return None
            self._preparing.add(thread)
        try:
            assert self._supervisor is not None, "preparing needs the supervisor"
            directed = supervisor_graph.directed(
                self._supervisor, request, directing, self._archive
            )
            return self.open(on, directed, unasked=True)
        finally:
            self._preparing.discard(thread)

    def _offers_a_mesocycle(self, on: RunnableConfig) -> bool:
        # A pending change or adaptation is not the next mesocycle: what it
        # was for has just ended.
        held = self.pending(on)
        return (
            held is not None
            and isinstance(held.request, plans.MesocycleRequest)
            and held.request.changing is None
        )

    def _ran(self, given: Any, on: RunnableConfig, progress: Progress | None) -> Outcome:
        final: dict[str, Any] = {}
        try:
            for mode, chunk in cast(
                Iterator[tuple[str, dict[str, Any]]],
                self._planner.stream(given, on, stream_mode=["updates", "values"]),
            ):
                if mode == "values":
                    final = chunk
                elif progress is not None:
                    progress(chunk)
        except Exception:
            records.failed(self._planner, on, self._budget, self._archive)
            raise
        return outcome(final, self._budget)


def _thread(on: RunnableConfig) -> str:
    return str(on.get("configurable", {}).get("thread_id", ""))
