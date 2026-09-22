"""The accepted mesocycle: written once when it is accepted, read between workouts (ADR-0008)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine import duration, workouts


@dataclass(frozen=True)
class Mesocycle:
    """The active mesocycle: its slots in the split's order, and when its cycles started counting."""

    id: int
    slots: tuple[tuple[workouts.PrescribedBlock, ...], ...]
    cycles: int
    why: str
    accepted_on: str
    accepted_after: int
    """Workouts performed when it was accepted; its cycles count from here."""


def record_mesocycle(
    connection: sqlite3.Connection,
    slots: Sequence[Sequence[workouts.PrescribedBlock]],
    *,
    cycles: int,
    why: str,
    on: str,
) -> int:
    """Keep an accepted mesocycle, end the one it replaces, and return its id.

    Each slot is checked as a plan (`duration.check_plan`) before anything is
    written. Nothing is prescribed: that happens when a slot is served.
    """
    for blocks in slots:
        if not blocks:
            raise workouts.WorkoutError("a workout is at least one block")
        duration.check_plan([prescribed.block for prescribed in blocks])

    connection.execute("BEGIN IMMEDIATE")
    try:
        performed = connection.execute(
            "SELECT COUNT(*) FROM workouts WHERE state = 'performed'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE mesocycles SET ended_on = ? WHERE ended_on IS NULL", (on,)
        )
        cursor = connection.execute(
            "INSERT INTO mesocycles (accepted_on, accepted_after, cycles, why) "
            "VALUES (?, ?, ?, ?)",
            (on, performed, cycles, why),
        )
        assert cursor.lastrowid is not None  # an INSERT always has one
        mesocycle_id = cursor.lastrowid
        for slot, blocks in enumerate(slots, start=1):
            for position, prescribed in enumerate(blocks, start=1):
                _write_block(connection, mesocycle_id, slot, position, prescribed)
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return mesocycle_id


def _write_block(
    connection: sqlite3.Connection,
    mesocycle_id: int,
    slot: int,
    position: int,
    prescribed: workouts.PrescribedBlock,
) -> None:
    cursor = connection.execute(
        "INSERT INTO mesocycle_blocks (mesocycle_id, slot, position, rounds, rest, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            mesocycle_id,
            slot,
            position,
            prescribed.block.rounds,
            prescribed.block.rest,
            prescribed.reason,
        ),
    )
    assert cursor.lastrowid is not None  # an INSERT always has one
    for item_position, item in enumerate(prescribed.block.items, start=1):
        unit, amount = ("reps", item.reps) if item.reps is not None else ("seconds", item.seconds)
        connection.execute(
            "INSERT INTO mesocycle_exercises (block_id, position, exercise_id, unit, amount) "
            "VALUES (?, ?, ?, ?, ?)",
            (cursor.lastrowid, item_position, item.exercise_id, unit, amount),
        )


def active(connection: sqlite3.Connection) -> Mesocycle | None:
    """The mesocycle nothing has replaced, or `None` when none was ever accepted."""
    row = connection.execute(
        "SELECT id, cycles, why, accepted_on, accepted_after "
        "FROM mesocycles WHERE ended_on IS NULL"
    ).fetchone()
    if row is None:
        return None
    rows = connection.execute(
        "SELECT b.id AS block_id, b.slot, b.rounds, b.rest, b.reason, "
        "e.exercise_id, e.unit, e.amount "
        "FROM mesocycle_blocks AS b JOIN mesocycle_exercises AS e ON e.block_id = b.id "
        "WHERE b.mesocycle_id = ? ORDER BY b.slot, b.position, e.position",
        (row["id"],),
    ).fetchall()
    slots: dict[int, dict[int, list[sqlite3.Row]]] = {}
    for found in rows:
        slots.setdefault(int(found["slot"]), {}).setdefault(int(found["block_id"]), []).append(found)
    return Mesocycle(
        id=int(row["id"]),
        slots=tuple(
            tuple(
                workouts.PrescribedBlock(
                    block=duration.Block(
                        items=tuple(
                            duration.BlockItem(
                                exercise_id=str(item["exercise_id"]),
                                reps=int(item["amount"]) if item["unit"] == "reps" else None,
                                seconds=int(item["amount"]) if item["unit"] == "seconds" else None,
                            )
                            for item in items
                        ),
                        rounds=int(items[0]["rounds"]),
                        rest=int(items[0]["rest"]),
                    ),
                    reason=str(items[0]["reason"]),
                )
                for items in blocks.values()
            )
            for _, blocks in sorted(slots.items())
        ),
        cycles=int(row["cycles"]),
        why=str(row["why"]),
        accepted_on=str(row["accepted_on"]),
        accepted_after=int(row["accepted_after"]),
    )
