"""The accepted mesocycle: written once when it is accepted, read between workouts (ADR-0008)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace

from trainer.engine import duration, state, workouts

ASK_FOR_ONE = "plan one with `trainer plan --mesocycle`"
"""The fix every state below names."""

VARIES = ("exercises", "reps", "rest")
"""What a direction may change from the last mesocycle (ADR-0014 item 2)."""


class MesocycleError(RuntimeError):
    """There is no workout to read off a mesocycle today, with the fix."""


@dataclass(frozen=True)
class Direction:
    """What a mesocycle is about, written by the supervisor before it was planned (ADR-0014)."""

    theme: str
    changes: str
    why: str
    varies: tuple[str, ...] = ()
    """Which of `VARIES` it changes."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "varies", tuple(self.varies))


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

    direction: Direction | None = None


def record_mesocycle(
    connection: sqlite3.Connection,
    slots: Sequence[Sequence[workouts.PrescribedBlock]],
    *,
    cycles: int,
    why: str,
    on: str,
    accepted_after: int | None = None,
    direction: Direction | None = None,
) -> int:
    """Keep an accepted mesocycle, end the one it replaces, and return its id.

    Each slot is checked as a plan (`duration.check_plan`) before anything is
    written. Nothing is prescribed: that happens when a slot is served. The
    ended one's serving that nobody has performed yet is withdrawn with it.
    `accepted_after` is given by a change, which keeps the count it rewrites;
    `direction` by a mesocycle that follows one which ended.
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
        if direction is not None:
            connection.execute(
                "INSERT INTO directions (mesocycle_id, theme, changes, why, varies) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    mesocycle_id,
                    direction.theme,
                    direction.changes,
                    direction.why,
                    json.dumps(list(direction.varies)),
                ),
            )
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
    return Mesocycle(
        id=int(row["id"]),
        slots=_slots(connection, int(row["id"])),
        cycles=int(row["cycles"]),
        why=str(row["why"]),
        accepted_on=str(row["accepted_on"]),
        accepted_after=int(row["accepted_after"]),
        direction=direction_of(connection, int(row["id"])),
    )


def _slots(
    connection: sqlite3.Connection, mesocycle_id: int
) -> tuple[tuple[workouts.PrescribedBlock, ...], ...]:
    rows = connection.execute(
        "SELECT b.id AS block_id, b.slot, b.rounds, b.rest, b.reason, "
        "e.exercise_id, e.unit, e.amount "
        "FROM mesocycle_blocks AS b JOIN mesocycle_exercises AS e ON e.block_id = b.id "
        "WHERE b.mesocycle_id = ? ORDER BY b.slot, b.position, e.position",
        (mesocycle_id,),
    ).fetchall()
    slots: dict[int, dict[int, list[sqlite3.Row]]] = {}
    for found in rows:
        slots.setdefault(int(found["slot"]), {}).setdefault(int(found["block_id"]), []).append(found)
    return tuple(
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
    )


def direction_of(connection: sqlite3.Connection, mesocycle_id: int) -> Direction | None:
    """The direction a mesocycle was planned from, or `None` when it had none."""
    row = connection.execute(
        "SELECT theme, changes, why, varies FROM directions WHERE mesocycle_id = ?", (mesocycle_id,)
    ).fetchone()
    if row is None:
        return None
    return Direction(
        theme=str(row["theme"]),
        changes=str(row["changes"]),
        why=str(row["why"]),
        varies=tuple(json.loads(row["varies"])),
    )


# -- the history, as the supervisor reads it (ADR-0014 item 3) -----------------


@dataclass(frozen=True)
class Past:
    """One mesocycle ever accepted, as counts: never its reasons, which are the planner's."""

    id: int
    accepted_on: str
    ended_on: str | None
    slots: int
    cycles: int
    workouts: int
    """Workouts its cycles asked for."""

    performed: int
    """Workouts performed while it was the one being followed."""

    changed: bool
    """Ended by a change, which rewrote it for the cycles left."""

    direction: Direction | None


def history(connection: sqlite3.Connection) -> tuple[Past, ...]:
    """Every mesocycle accepted, oldest first."""
    rows = connection.execute(
        "SELECT m.id, m.accepted_on, m.ended_on, m.cycles, m.accepted_after, "
        "(SELECT COUNT(DISTINCT slot) FROM mesocycle_blocks WHERE mesocycle_id = m.id) AS slots "
        "FROM mesocycles AS m ORDER BY m.id"
    ).fetchall()
    found = []
    for index, row in enumerate(rows):
        following = rows[index + 1] if index + 1 < len(rows) else None
        found.append(
            Past(
                id=int(row["id"]),
                accepted_on=str(row["accepted_on"]),
                ended_on=None if row["ended_on"] is None else str(row["ended_on"]),
                slots=int(row["slots"]),
                cycles=int(row["cycles"]),
                workouts=int(row["slots"]) * int(row["cycles"]),
                performed=len(_performed_in(connection, int(row["id"]))),
                changed=following is not None
                and int(following["accepted_after"]) == int(row["accepted_after"]),
                direction=direction_of(connection, int(row["id"])),
            )
        )
    return tuple(found)


def held(
    connection: sqlite3.Connection, mesocycle_id: int
) -> tuple[tuple[workouts.PrescribedBlock, ...], ...]:
    """What one mesocycle prescribed, slot by slot; an id never accepted is an error."""
    if connection.execute("SELECT 1 FROM mesocycles WHERE id = ?", (mesocycle_id,)).fetchone() is None:
        raise MesocycleError(f"no mesocycle {mesocycle_id} was ever accepted; `mesocycle_history` lists them")
    return _slots(connection, mesocycle_id)


def _performed_in(connection: sqlite3.Connection, mesocycle_id: int) -> tuple[int, ...]:
    """The workouts performed while this mesocycle was followed, by the count it was accepted at.

    It runs to its last cycle, or to the count the one after it was accepted
    at; a change keeps the count, so the rewritten one is followed for none.
    """
    row = connection.execute(
        "SELECT m.accepted_after, m.cycles, "
        "(SELECT COUNT(DISTINCT slot) FROM mesocycle_blocks WHERE mesocycle_id = m.id) AS slots, "
        "(SELECT n.accepted_after FROM mesocycles AS n WHERE n.id > m.id ORDER BY n.id LIMIT 1) "
        "AS next_after "
        "FROM mesocycles AS m WHERE m.id = ?",
        (mesocycle_id,),
    ).fetchone()
    start = int(row["accepted_after"])
    span = int(row["cycles"]) * int(row["slots"])
    if row["next_after"] is not None:
        span = min(span, int(row["next_after"]) - start)
    if span <= 0:
        return ()
    rows = connection.execute(
        "SELECT id FROM workouts WHERE state = 'performed' "
        "ORDER BY performed_on, id LIMIT ? OFFSET ?",
        (span, start),
    ).fetchall()
    return tuple(int(found["id"]) for found in rows)


@dataclass(frozen=True)
class Volume:
    """Rounds on one key of one axis: what one cycle of the mesocycle planned, and what was performed in all of it."""

    axis: str
    key: str
    per_cycle: int
    performed: int


def volume(connection: sqlite3.Connection, mesocycle_id: int) -> tuple[Volume, ...]:
    """Planned and performed rounds per movement pattern and per primary muscle, for one mesocycle."""
    held(connection, mesocycle_id)
    planned_by = {
        "pattern": (
            "SELECT x.movement_pattern AS key, SUM(b.rounds) AS rounds "
            "FROM mesocycle_blocks AS b JOIN mesocycle_exercises AS e ON e.block_id = b.id "
            "JOIN exercises AS x ON x.id = e.exercise_id "
            "WHERE b.mesocycle_id = ? AND x.movement_pattern IS NOT NULL GROUP BY key"
        ),
        "muscle": (
            "SELECT muscle.value AS key, SUM(b.rounds) AS rounds "
            "FROM mesocycle_blocks AS b JOIN mesocycle_exercises AS e ON e.block_id = b.id "
            "JOIN exercises AS x ON x.id = e.exercise_id "
            "JOIN json_each(x.primary_muscles) AS muscle "
            "WHERE b.mesocycle_id = ? GROUP BY key"
        ),
    }
    performed_by = {
        "pattern": ("pattern_state", "movement_pattern"),
        "muscle": ("muscle_state", "muscle"),
    }
    ids = _performed_in(connection, mesocycle_id)
    marks = ", ".join("?" for _ in ids)
    found: list[Volume] = []
    for axis, planned_sql in planned_by.items():
        planned = {
            str(row["key"]): int(row["rounds"])
            for row in connection.execute(planned_sql, (mesocycle_id,)).fetchall()
        }
        performed: dict[str, int] = {}
        if ids:
            view, column = performed_by[axis]
            performed = {
                str(row["key"]): int(row["rounds"])
                for row in connection.execute(
                    f"SELECT {column} AS key, SUM(rounds) AS rounds FROM {view} "
                    f"WHERE phase = 'performed' AND workout_id IN ({marks}) GROUP BY key",
                    ids,
                ).fetchall()
            }
        for key in sorted(planned.keys() | performed.keys()):
            found.append(Volume(axis, key, planned.get(key, 0), performed.get(key, 0)))
    return tuple(found)


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

    done: tuple[int, ...] = ()
    """The slots of this cycle already performed."""


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
        done=where.done,
    )


@dataclass(frozen=True)
class Finished:
    """The active mesocycle once its cycles are all performed."""

    mesocycle: Mesocycle
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
    return Finished(mesocycle=kept, past=since - total)


def record_served(connection: sqlite3.Connection, on: str) -> tuple[Today, int]:
    """Today's workout, prescribed the first time it is served, and its workout id.

    Served again, it is the prescription on record and the slot it was served
    as, which an adaptation may have made different from the rotation's.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        found = today(connection)
        performed = found.performed
        row = connection.execute(
            "SELECT workout_id, slot FROM served WHERE mesocycle_id = ? AND served_after = ?",
            (found.mesocycle, performed),
        ).fetchone()
        if row is not None:
            workout_id = int(row["workout_id"])
            found = replace(
                found,
                slot=int(row["slot"]),
                blocks=workouts.prescribed(connection, workout_id),
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
    slot: int | None = None,
) -> int:
    """Prescribe an adapted workout as today's serving of the mesocycle, and return its id.

    `slot` is which of the cycle's workouts it counts as, the rotation's when
    not given. The mesocycle is not touched (ADR-0008 item 6). A serving of
    the same day that nobody performed is withdrawn; a day the rotation has
    moved past, or a mesocycle since replaced, is a state.
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
            (workout_id, mesocycle, found.slot if slot is None else slot, served_after),
        )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return workout_id
