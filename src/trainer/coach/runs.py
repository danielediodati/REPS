"""The runs the checkpointer kept: which conversations are in it, and what one of them did."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple

from trainer.coach import record


@dataclass(frozen=True)
class Conversation:
    """One thread as its last checkpoint leaves it: enough to recognise it and pick it."""

    thread: str
    moved: str
    outcome: str
    on: record.Run


def conversations(saver: BaseCheckpointSaver[Any]) -> list[Conversation]:
    """Every thread in the checkpointer, at the last checkpoint it reached, most recent first.

    Sorted here rather than trusted to the saver: `list` orders by checkpoint
    id, and the question being asked is which conversation moved last.
    """
    latest: dict[str, Conversation] = {}
    for kept in saver.list(None):
        thread = str(kept.config["configurable"]["thread_id"])
        if thread not in latest:
            latest[thread] = _conversation(thread, kept)
    return sorted(latest.values(), key=lambda held: held.moved, reverse=True)


def read(
    saver: BaseCheckpointSaver[Any], thread: str
) -> tuple[Conversation, Mapping[str, Any]] | None:
    """One thread at its last checkpoint, with the state the record is derived from.

    The last checkpoint and not the last *finished* run: a run cut mid-flight
    is the case this exists for, and what it reached is what it reached.
    """
    kept = saver.get_tuple({"configurable": {"thread_id": thread}})
    if kept is None:
        return None
    return _conversation(thread, kept), kept.checkpoint["channel_values"]


def line(conversation: Conversation, width: int = 0) -> str:
    """One conversation, on one line of ASCII, for the terminal.

    `width` is the widest thread id it is being listed beside; zero means it
    is on its own, and then there is nothing to line the columns up with.
    """
    outcome = conversation.outcome
    if width:
        outcome = outcome.ljust(len(record.UNFINISHED))
    return (
        f"{conversation.thread.ljust(width)}  {moment(conversation.moved)}  "
        f"{outcome}  {conversation.on.model} on {conversation.on.provider}"
    )


def moment(stamp: str) -> str:
    """A checkpoint's timestamp in the reader's own time zone, to the minute.

    Local, because what the listing is for is recognising a run you remember
    having: the clock you compared it against is the one on this machine.
    """
    try:
        written = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    return written.astimezone().strftime("%Y-%m-%d %H:%M")


def _conversation(thread: str, kept: CheckpointTuple) -> Conversation:
    return Conversation(
        thread=thread,
        moved=str(kept.checkpoint["ts"]),
        outcome=record.outcome(kept.checkpoint["channel_values"]),
        on=record.ran(kept.metadata or {}),
    )
