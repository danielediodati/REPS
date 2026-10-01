"""The accepted mesocycle: written once when it is accepted, read between workouts (ADR-0008)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine import duration, state, workouts

ASK_FOR_ONE = "plan one with `trainer plan --mesocycle`"
"""The fix every state below names."""


class MesocycleError(RuntimeError):
    """There is no workout to read off a mesocycle today, with the fix."""


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
    accepted_after: int | None = None,
) -> int:
    """Keep an accepted mesocycle, end the one it replaces, and return its id.

    Each slot is checked as a plan (`duration.check_plan`) before anything is
    written. Nothing is prescribed: that happens when a slot is served. The
    ended one's serving that nobody has performed yet is withdrawn with it.
    `accepted_after` is given by a change, which keeps the count it rewrites.
    """
    for blocks in slots:
        if not blocks:
            raise workouts.WorkoutError("a workout is at least one block")
        duration.check_plan([prescribed.block for prescribed in blocks])

    connection.execute("BEGIN IMMEDIATE")
    try:
        performed = _performed(connection)
        ending = connection.execute(
            "SELECT id FROM mesocycles WHERE ended_on IS NULL"
        ).fetchone()
        if ending is not None:
            _withdraw(connection, int(ending["id"]), performed)
        connection.execute(
            "UPDATE mesocycles SET ended_on = ? WHERE ended_on IS NULL", (on,)
        )
        cursor = connection.execute(
            "INSERT INTO mesocycles (accepted_on, accepted_after, cycles, why) "
            "VALUES (?, ?, ?, ?)",
            (on, performed if accepted_after is None else accepted_after, cycles, why),
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


def _performed(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM workouts WHERE state = 'performed'"
        ).fetchone()[0]
    )


def _withdraw(connection: sqlite3.Connection, mesocycle_id: int, served_after: int) -> None:
    """The serving at this count taken back, if nobody has performed it: it was never trained."""
    connection.execute(
        "DELETE FROM workouts WHERE state = 'prescribed' AND id IN "
        "(SELECT workout_id FROM served WHERE mesocycle_id = ? AND served_after = ?)",
        (mesocycle_id, served_after),
    )


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


@dataclass(frozen=True)
class Today:
    """The mesocycle's slot the rotation is at, and where that is in its cycles."""

    mesocycle: int
    slot: int
    slots: int
    cycle: int
    cycles: int
    blocks: tuple[workouts.PrescribedBlock, ...]
    performed: int
    """Workouts performed so far: what a serving of today is keyed by."""


def today(connection: sqlite3.Connection) -> Today:
    """Today's workout off the active mesocycle, or the state that stops it."""
    kept = active(connection)
    if kept is None:
        raise MesocycleError(f"no mesocycle has been accepted; {ASK_FOR_ONE}")
    where = state.rotation(connection)
    if where.cycle_length != len(kept.slots):
        raise MesocycleError(
            f"the declared split has {where.cycle_length} workouts and the "
            f"mesocycle has {len(kept.slots)}; {ASK_FOR_ONE}"
        )
    since = where.performed - kept.accepted_after
    if since >= kept.cycles * len(kept.slots):
        raise MesocycleError(
            f"the mesocycle accepted on {kept.accepted_on} has finished its "
            f"{kept.cycles} cycles; {ASK_FOR_ONE}"
        )
    return Today(
        mesocycle=kept.id,
        slot=where.position,
        slots=len(kept.slots),
        cycle=since // len(kept.slots) + 1,
        cycles=kept.cycles,
        blocks=kept.slots[where.position - 1],
        performed=where.performed,
    )


@dataclass(frozen=True)
class Trained:
    """One workout performed while a mesocycle ran: its slot, its day, and what was done."""

    slot: int
    performed_on: str
    blocks: tuple[workouts.PerformedBlock, ...]


@dataclass(frozen=True)
class Finished:
    """The active mesocycle once its cycles are all performed, and what was performed in them."""

    mesocycle: Mesocycle
    trained: tuple[Trained, ...]
    past: int
    """Workouts performed after its last cycle ended; zero on the report that ended it."""


def finished(connection: sqlite3.Connection) -> Finished | None:
    """The active mesocycle if it has run all its cycles, or `None`."""
    kept = active(connection)
    if kept is None:
        return None
    total = kept.cycles * len(kept.slots)
    filled = state.performed_slots(connection, len(kept.slots))
    since = len(filled) - kept.accepted_after
    if since < total:
        return None
    rows = connection.execute(
        "SELECT id, performed_on FROM workouts WHERE state = 'performed' "
        "ORDER BY performed_on, id LIMIT ? OFFSET ?",
        (total, kept.accepted_after),
    ).fetchall()
    return Finished(
        mesocycle=kept,
        trained=tuple(
            Trained(
                slot=filled[kept.accepted_after + index],
                performed_on=str(row["performed_on"]),
                blocks=workouts.performed(connection, int(row["id"])),
            )
            for index, row in enumerate(rows)
        ),
        past=since - total,
    )


def record_served(connection: sqlite3.Connection, on: str) -> tuple[Today, int]:
    """Today's workout, prescribed the first time it is served, and its workout id.

    Served again, it is the prescription on record, which an adaptation may
    have made different from the slot.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        found = today(connection)
        performed = found.performed
        row = connection.execute(
            "SELECT workout_id FROM served WHERE mesocycle_id = ? AND served_after = ?",
            (found.mesocycle, performed),
        ).fetchone()
        if row is not None:
            workout_id = int(row["workout_id"])
            found = Today(
                mesocycle=found.mesocycle,
                slot=found.slot,
                slots=found.slots,
                cycle=found.cycle,
                cycles=found.cycles,
                blocks=workouts.prescribed(connection, workout_id),
                performed=found.performed,
            )
        else:
            workout_id = workouts.write_prescribed(connection, found.blocks, on)
            connection.execute(
                "INSERT INTO served (workout_id, mesocycle_id, slot, served_after) "
                "VALUES (?, ?, ?, ?)",
                (workout_id, found.mesocycle, found.slot, performed),
            )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return found, workout_id


def record_adapted(
    connection: sqlite3.Connection,
    blocks: Sequence[workouts.PrescribedBlock],
    *,
    on: str,
    mesocycle: int,
    served_after: int,
) -> int:
    """Prescribe an adapted workout as today's serving of the mesocycle, and return its id.

    The mesocycle is not touched (ADR-0008 item 6). A serving of the same day
    that nobody performed is withdrawn; a day the rotation has moved past, or
    a mesocycle since replaced, is a state.
    """
    if not blocks:
        raise workouts.WorkoutError("a workout is at least one block")
    duration.check_plan([prescribed.block for prescribed in blocks])

    connection.execute("BEGIN IMMEDIATE")
    try:
        found = today(connection)
        if (found.mesocycle, found.performed) != (mesocycle, served_after):
            raise MesocycleError(
                "the day this workout was adapted for has moved on: a workout was "
                "reported or another mesocycle accepted since; ask for today's again"
            )
        _withdraw(connection, mesocycle, served_after)
        workout_id = workouts.write_prescribed(connection, blocks, on)
        connection.execute(
            "INSERT INTO served (workout_id, mesocycle_id, slot, served_after) "
            "VALUES (?, ?, ?, ?)",
            (workout_id, mesocycle, found.slot, served_after),
        )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return workout_id
