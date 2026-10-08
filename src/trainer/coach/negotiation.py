"""One ask and its runs, holding at most one plan: the life both the bot and the CLI drive."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Generator, Mapping
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


@dataclass(frozen=True)
class Stopped:
    """The run was stopped between graph steps for a newer ask, and nothing was offered."""

    record: dict[str, Any]


Outcome = Proposed | Accepted | Refused | Superseded | Stopped


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


def passed(request: plans.Request | plans.MesocycleRequest) -> bool:
    """Whether an adaptation's day is over: a workout reported since, or its mesocycle gone."""
    adapting = request.adapting if isinstance(request, plans.Request) else None
    if adapting is None:
        return False
    try:
        with tools.reported(), tools.opened() as connection:
            try:
                found = mesocycles.today(connection)
            except mesocycles.MesocycleError:
                return True
    except tools.ToolFailure:
        # Nothing can be read, so nothing is known to have passed.
        return False
    return (found.mesocycle, found.performed) != (adapting.mesocycle, adapting.served_after)


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
        stopping: dict[str, threading.Event] | None = None,
    ) -> None:
        self._planner = planning
        self._archive = archive
        self._budget = budget
        self._supervisor = supervisor
        self._preparing = preparing if preparing is not None else set()
        self._stopping = stopping if stopping is not None else {}
        self._claiming = threading.Lock()

    def open(
        self,
        on: RunnableConfig,
        request: plans.Request | plans.MesocycleRequest,
        carrying: Mapping[str, Any] | None = None,
        progress: Progress | None = None,
        unasked: bool = False,
    ) -> Outcome:
        """A new ask on this thread, ending any proposal pending on it: stopped when the ask follows it, lapsed when not."""
        given = dict(planner.starting(request, unasked=unasked)) | dict(carrying or {})
        if self.pending(on) is not None:
            follows = self.continuing(on)["follows"]
            replaced = follows is not None and given.get("follows") == follows
            self._ran(
                Command(resume=planner.ended(records.STOPPED if replaced else records.LAPSED)),
                on,
                None,
            )
        return self._ran(given, on, progress)

    def answer(
        self,
        on: RunnableConfig,
        proposal: str,
        answer: planner.Answer,
        progress: Progress | None = None,
    ) -> Outcome:
        """The proposal `proposal` kept or turned down; superseded when it is not the one pending, or has lapsed."""
        held = self.pending(on)
        if held is None or held.id != proposal or self.lapse(on):
            return Superseded()
        return self._ran(Command(resume=answer), on, progress)

    def lapse(self, on: RunnableConfig) -> bool:
        """The pending adaptation ended as lapsed when the day it adapts has passed; whether it was."""
        held = self.pending(on)
        if held is None or not passed(held.request):
            return False
        self._ran(Command(resume=planner.ended(records.LAPSED)), on, None)
        return True

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

    def running(self, on: RunnableConfig) -> bool:
        """Whether a run is in flight on this thread right now."""
        return _thread(on) in self._stopping

    def stop(self, on: RunnableConfig) -> bool:
        """The run in flight on this thread stopped before its next graph step; whether there was one."""
        flag = self._stopping.get(_thread(on))
        if flag is None:
            return False
        flag.set()
        return True

    def continuing(self, on: RunnableConfig) -> dict[str, Any]:
        """What opens the next run in the negotiation of this thread's last run, following it."""
        last = self._planner.get_state(on).values
        return {"negotiation": str(last.get("negotiation", "")), "follows": last.get("run")}

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
        thread = _thread(on)
        flag = self._stopping[thread] = threading.Event()
        stopped = False
        try:
            with contextlib.closing(
                cast(
                    Generator[tuple[str, dict[str, Any]]],
                    self._planner.stream(given, on, stream_mode=["updates", "values"]),
                )
            ) as streaming:
                for mode, chunk in streaming:
                    if mode != "values":
                        if progress is not None:
                            progress(chunk)
                        continue
                    final = chunk
                    # Checked on whole steps only, and never on one that ended
                    # the run or reached a proposal: that run is over, and
                    # stopping it would relabel what it wrote or leave a plan
                    # pending that nobody was shown.
                    over = "__interrupt__" in chunk or bool(chunk.get("ending"))
                    if flag.is_set() and not over:
                        stopped = True
                        break
        except Exception:
            records.failed(self._planner, on, self._budget, self._archive)
            raise
        finally:
            if self._stopping.get(thread) is flag:
                del self._stopping[thread]
        if stopped:
            return Stopped(records.stopped(self._planner, on, self._budget, self._archive))
        return outcome(final, self._budget)


def _thread(on: RunnableConfig) -> str:
    return str(on.get("configurable", {}).get("thread_id", ""))
