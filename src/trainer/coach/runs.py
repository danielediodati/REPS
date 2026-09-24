"""The negotiations the home holds, and the one run the checkpointer is still carrying.

Documents, not state: the reader is what you reach for when the provider is
what is wrong, so nothing here builds a graph, names a model or opens a
provider (ADR-0007, item 9).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple

from trainer.coach import record

logger = logging.getLogger(__name__)

INTERRUPT = "__interrupt__"
"""The channel a pending question is written to, as LangGraph names it.

Read off the checkpoint's own writes rather than asked of the graph:
`graph.get_state` would have this reader build a planner, and the one moment
you want it is when the model cannot be reached.
"""

WAITING = "waiting"
"""The live run has asked something and nobody has answered."""

CUT = "cut"
"""The live run stopped where it stood: no ending written, and no question pending."""

NOTHING = "-"
"""A negotiation with no closed run and no live one. Only an empty thread reads this way."""


@dataclass(frozen=True)
class Run:
    """One closed run, as its document keeps it."""

    negotiation: str
    run: str
    follows: str | None
    began: str
    ended: str
    ending: str
    document: Mapping[str, Any]
    unasked: bool = False


@dataclass(frozen=True)
class Live:
    """The run the checkpointer is still holding, and where the reader found it.

    `waiting` and `cut` are the two axes' second half (ADR-0007, item 7): they
    are not endings and are never written, because an absence is not an event.
    """

    thread: str
    negotiation: str
    run: str
    moved: str
    waiting: bool
    state: Mapping[str, Any]
    unasked: bool = False


@dataclass(frozen=True)
class Negotiation:
    """One ask and everything it took to answer it: its runs, and the live one if it has one."""

    negotiation: str
    runs: tuple[Run, ...]
    live: Live | None = None

    @property
    def unasked(self) -> bool:
        """Whether the machine opened it rather than the user."""
        return any(run.unasked for run in self.runs) or (
            self.live is not None and self.live.unasked
        )

    @property
    def moved(self) -> str:
        """When this negotiation last did anything."""
        stamps = [run.ended or run.began for run in self.runs]
        if self.live is not None:
            stamps.append(self.live.moved)
        return max(stamps, key=instant) if stamps else ""

    @property
    def outcome(self) -> str:
        """What it came to: an ending it wrote, or where the reader found the live run.

        The live run wins when it has one, because a negotiation that offered
        a plan at nine and is still waiting at midnight is waiting -- the
        refusal it wrote at nine is how it got there, not where it is.
        """
        if self.open:
            assert self.live is not None
            return WAITING if self.live.waiting else CUT
        return self.runs[-1].ending if self.runs else NOTHING

    @property
    def open(self) -> bool:
        """Whether the live run is one this negotiation never closed."""
        return self.live is not None and self.live.run not in {
            run.run for run in self.runs
        }

    @property
    def since(self) -> str:
        """When the run the reader found unfinished started waiting."""
        return self.live.moved if self.live is not None else self.moved


def kept(archive: Path) -> list[Run]:
    """Every closed run the home holds, oldest first.

    A file that is not a record is skipped rather than refused: the archive is
    a directory on the user's disk, and one unreadable document must not take
    the history with it.
    """
    found: list[Run] = []
    for document in sorted(archive.glob("*/*.json")):
        try:
            held = json.loads(document.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("%s is not a run record", document)
            continue
        if not isinstance(held, dict):
            logger.warning("%s is not a run record", document)
            continue
        found.append(
            Run(
                negotiation=str(held.get("negotiation", document.parent.name)),
                run=str(held.get("run", document.stem)),
                follows=held.get("follows"),
                began=str(held.get("began", "")),
                ended=str(held.get("ended", "")),
                ending=str(held.get("ending", "")),
                document=held,
                unasked=bool(held.get("unasked", False)),
            )
        )
    return sorted(found, key=lambda run: (instant(run.began), run.run))


def live(saver: BaseCheckpointSaver[Any]) -> list[Live]:
    """The last checkpoint of every thread: one live run each, most recently moved first."""
    latest: dict[str, Live] = {}
    for held in saver.list(None):
        thread = str(held.config["configurable"]["thread_id"])
        if thread not in latest:
            latest[thread] = _live(thread, held)
    return sorted(latest.values(), key=lambda run: instant(run.moved), reverse=True)


def negotiations(closed: Sequence[Run], unfinished: Sequence[Live]) -> list[Negotiation]:
    """Every negotiation the two sources know about, most recently moved first.

    A live run whose negotiation nobody wrote a document for is still a
    negotiation: that is what a thread cut on its first run looks like, and it
    is the one the session 8 demo produces.
    """
    grouped: dict[str, list[Run]] = {}
    for run in closed:
        grouped.setdefault(run.negotiation, []).append(run)
    standing: dict[str, Live] = {}
    for one in unfinished:
        standing[one.negotiation or one.thread] = one
    held = [
        Negotiation(named, tuple(runs), standing.pop(named, None))
        for named, runs in grouped.items()
    ]
    held.extend(
        Negotiation(named, (), one) for named, one in standing.items()
    )
    return sorted(held, key=lambda one: instant(one.moved), reverse=True)


def named(held: Sequence[Negotiation], name: str) -> Negotiation | None:
    """The negotiation that goes by this name, or the one holding the run that does."""
    for one in held:
        if one.negotiation == name:
            return one
    for one in held:
        if any(run.run == name for run in one.runs):
            return one
        if one.live is not None and one.live.run == name:
            return one
    return None


def run_named(held: Negotiation, name: str) -> Run | None:
    """One run of a negotiation, by its own name."""
    return next((run for run in held.runs if run.run == name), None)


UNASKED = "opened by the machine"


def line(held: Negotiation, width: int = 0, now: datetime | None = None) -> str:
    """One negotiation, on one line of ASCII, for the terminal.

    `width` is the widest negotiation name it is being listed beside; zero
    means it is on its own, and then there is nothing to line the columns up
    with.
    """
    outcome = held.outcome
    if held.open and held.live is not None and held.live.waiting:
        since = instant(held.since)
        waited = (now or datetime.now(timezone.utc)) - since
        outcome = f"{WAITING} since {moment(held.since)} ({lasted(waited)})"
    runs = len(held.runs) + (1 if held.open else 0)
    counted = f"{runs} run" if runs == 1 else f"{runs} runs"
    if width:
        counted = counted.ljust(len("00 runs"))
    shown = f"{held.negotiation.ljust(width)}  {moment(held.moved)}  {counted}  {outcome}"
    return f"{shown}  {UNASKED}" if held.unasked else shown


def lasted(span: timedelta) -> str:
    """How long, to the two largest units that say it: 2d 3h, 5h 10m, 12m."""
    minutes = max(0, int(span.total_seconds() // 60))
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def instant(stamp: str) -> datetime:
    """A timestamp as the moment it names, for ordering.

    Two clocks meet here: a run document is stamped in this machine's own time
    zone and a checkpoint in UTC, so comparing the strings would sort a run by
    its offset. One nobody can read sorts first rather than raising -- an
    unreadable stamp is a listing that is out of order, not a history that
    cannot be read.
    """
    try:
        written = datetime.fromisoformat(stamp)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return written if written.tzinfo else written.replace(tzinfo=timezone.utc)


def moment(stamp: str) -> str:
    """A timestamp in the reader's own time zone, to the minute.

    Local, because what the listing is for is recognising a negotiation you
    remember having: the clock you compared it against is the one on this
    machine.
    """
    try:
        written = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    return written.astimezone().strftime("%Y-%m-%d %H:%M")


def _live(thread: str, held: CheckpointTuple) -> Live:
    values = held.checkpoint["channel_values"]
    return Live(
        thread=thread,
        negotiation=str(values.get("negotiation", "")),
        run=str(values.get("run", "")),
        moved=str(held.checkpoint["ts"]),
        waiting=any(channel == INTERRUPT for _, channel, _ in held.pending_writes or ()),
        state=values,
        unasked=bool(values.get("unasked", False)),
    )


def of(held: Live, budget: int) -> dict[str, Any]:
    """The live run's record, derived the way a closed one's was written.

    The one place the reader looks at state rather than at a document, and it
    reads it the same way: `record.of` takes a mapping, and a checkpoint's
    channel values are one.
    """
    return record.of(held.state, budget)
