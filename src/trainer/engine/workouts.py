"""The write path for a prescribed workout, and reading one back.

A plan that is only rendered is a plan nobody can deviate from. This is where
one becomes a row -- `prescribed`, with its blocks and its exercises -- so that
session 5's report has something to be a difference *against*.

**Only `trainer plan` calls this, and it calls it from the CLI command.** Not
from `plan.py`, not from `agent.py`: `trainer eval` runs eighteen agent loops
against the project database, and a plan that persisted from inside the agent
would write eighteen phantom prescribed workouts into the very state the
measurement is taken from -- where the unreported-workout tool would then read
them as a rotation the user skipped. ROADMAP.md § Session 5: writes are never
tools. The agent emits; the engine writes.

**The wire shape stops at the door.** What arrives here is `duration.Block`,
the vocabulary the engine already costs plans in, plus the one field a block
carries that costing has no use for: the reason it was prescribed. Nothing in
this module knows what JSON is, and `test_engine_boundary.py` is what keeps it
that way.

**One transaction or nothing.** A workout row with no blocks under it is not a
smaller workout, it is a lie about what was prescribed, and the deviation
computed against it later would be the whole session.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine import duration

# The phases (`prescribed`, `performed`) and the provenances (`reported`,
# `assumed`, `asked`) live in migration 0006's CHECK constraints, which is
# what enforces them, and nowhere else. They are deliberately not restated
# here as constants: this module writes one phase and no provenance at all, so
# a tuple naming the rest would have no reader to keep it honest and would
# drift from the schema the first time either vocabulary moved. Whatever fills
# a provenance -- session 5's issue 02 -- is where it earns a name in Python.


class WorkoutError(RuntimeError):
    """What arrived cannot be recorded as a workout -- no blocks at all -- or
    what is stored cannot be read back as one.

    Not the only refusal this module makes: a plan that breaks an invariant of
    what a plan is comes back as `duration.DurationError`, raised by
    `check_plan` and left as itself rather than re-wrapped. The engine has one
    definition of that rule and one exception type for it, and a caller
    catching only this one still has to expect the other.
    """


@dataclass(frozen=True)
class PrescribedBlock:
    """One block as it was prescribed: what the engine costs, and why.

    Two fields rather than a wider `Block`, because `reason` is not something
    the costing formula reads and `duration.Block` is the type that gets
    costed. The wire shape has said since session 4 that a plan with nowhere
    to put its reasons turns them into prose beside the plan; persisting the
    plan and dropping them would do the same thing a week later.
    """

    block: duration.Block
    reason: str


@dataclass(frozen=True)
class Workout:
    """One workout row, in whichever of its two states it is in.

    `state` is a reading of the dates rather than a second fact: migration
    0006's CHECK makes `performed` and `performed_on IS NOT NULL` the same
    statement, so nothing can be performed on no day or dated without having
    happened.
    """

    id: int
    state: str
    prescribed_on: str | None
    performed_on: str | None
    report: str | None


def record_prescribed(
    connection: sqlite3.Connection,
    blocks: Sequence[PrescribedBlock],
    on: str,
) -> int:
    """Write one prescribed workout and return its id.

    `on` is an ISO-8601 date (`YYYY-MM-DD`), supplied by the caller for the
    reason `exclusions.active` takes `today`: the engine does not read the
    clock, so a test can place a workout in any week it needs one in.

    Each call is a new workout. Asked for a plan twice in a day, the user was
    prescribed two workouts, and the second one is not a correction of the
    first -- an upsert here would silently make two prescriptions into one and
    lose a deviation nobody could then account for.
    """
    if not blocks:
        raise WorkoutError("a workout is at least one block")

    # The plan's own invariant, checked here rather than trusted: an exercise
    # appears at most once across a workout (`check_plan` carries why). The
    # validator has already run for a plan arriving from `trainer plan`, but
    # this function's contract is *a plan*, and a writer that took a shape the
    # engine calls impossible would put it beyond the reach of everything that
    # reads it afterwards.
    duration.check_plan([prescribed.block for prescribed in blocks])

    connection.execute("BEGIN IMMEDIATE")
    try:
        cursor = connection.execute(
            "INSERT INTO workouts (state, prescribed_on) VALUES ('prescribed', ?)",
            (on,),
        )
        workout_id = _inserted(cursor)
        for position, prescribed in enumerate(blocks, start=1):
            _write_block(connection, workout_id, position, prescribed)
        # Inside the try, because a COMMIT can fail too -- a concurrent writer
        # holding the lock, a full disk. Left outside it, that failure would
        # escape with the transaction still open, and the next call on this
        # connection would die on BEGIN with a message about transactions
        # rather than about the disk.
        connection.execute("COMMIT")
    except Exception:
        # The same shape as `migrations.migrate`: SQLite rolls back by itself
        # for some failures, and rolling back again would raise an error that
        # replaced the one explaining what actually went wrong.
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return workout_id


def _write_block(
    connection: sqlite3.Connection,
    workout_id: int,
    position: int,
    prescribed: PrescribedBlock,
) -> None:
    cursor = connection.execute(
        "INSERT INTO workout_blocks "
        "(workout_id, phase, position, rounds, rest, reason) "
        "VALUES (?, 'prescribed', ?, ?, ?, ?)",
        (workout_id, position, prescribed.block.rounds, prescribed.block.rest, prescribed.reason),
    )
    block_id = _inserted(cursor)
    for item_position, item in enumerate(prescribed.block.items, start=1):
        unit, amount = _prescription(item)
        connection.execute(
            "INSERT INTO workout_exercises "
            "(block_id, phase, position, exercise_id, unit, amount) "
            "VALUES (?, 'prescribed', ?, ?, ?, ?)",
            (block_id, item_position, item.exercise_id, unit, amount),
        )


def _inserted(cursor: sqlite3.Cursor) -> int:
    """The id the row just written was given.

    An assert rather than an `or 0` fallback: `lastrowid` is typed optional
    because a cursor that ran a SELECT has none, and defaulting to zero here
    would file every child row under a workout that does not exist -- caught
    by the foreign key, but reported as a plan naming something nobody has.
    """
    assert cursor.lastrowid is not None  # an INSERT always has one
    return cursor.lastrowid


def _prescription(item: duration.BlockItem) -> tuple[str, int]:
    """The amount, and the unit it counts.

    `BlockItem` keeps `reps` and `seconds` as separate fields because costing
    reads them differently, and refuses both-or-neither in `__post_init__`, so
    there is no third case to handle here.
    """
    if item.reps is not None:
        return "reps", item.reps
    assert item.seconds is not None  # __post_init__ leaves no third case
    return "seconds", item.seconds


def workout(connection: sqlite3.Connection, workout_id: int) -> Workout | None:
    """One workout by id, or `None` when there is no such row.

    `None` rather than a raise: asking about a workout that is not there is a
    question with an answer, and every caller of this so far is checking
    whether something got written.
    """
    row = connection.execute(
        "SELECT id, state, prescribed_on, performed_on, report FROM workouts WHERE id = ?",
        (workout_id,),
    ).fetchone()
    if row is None:
        return None
    return Workout(
        id=int(row["id"]),
        state=row["state"],
        prescribed_on=row["prescribed_on"],
        performed_on=row["performed_on"],
        report=row["report"],
    )


def prescribed(
    connection: sqlite3.Connection, workout_id: int
) -> tuple[PrescribedBlock, ...]:
    """What was prescribed for this workout, in the order it was to be done.

    Empty for a workout nobody planned -- a performed workout with no
    prescribed phase is a real thing and not a missing row. Ordered by
    `position`, which is unique per workout and phase, so the sequence read
    back is the sequence written; ADR-0002 is why a plan is a sequence at all.

    A block holding no exercises is refused rather than skipped. `LEFT JOIN`
    is what makes it visible at all: joined the other way it would simply not
    come back, and the plan read out would be silently shorter than the plan
    stored -- a deviation computed against it would be wrong in the one
    direction nobody checks. No writer can produce that row today; the read is
    what would have to notice if one ever did.
    """
    rows = connection.execute(
        "SELECT b.id AS block_id, b.position AS block_position, "
        "b.rounds, b.rest, b.reason, e.exercise_id, e.unit, e.amount "
        "FROM workout_blocks AS b "
        "LEFT JOIN workout_exercises AS e ON e.block_id = b.id "
        "WHERE b.workout_id = ? AND b.phase = 'prescribed' "
        "ORDER BY b.position, e.position",
        (workout_id,),
    ).fetchall()

    blocks: list[PrescribedBlock] = []
    items: list[duration.BlockItem] = []
    current: sqlite3.Row | None = None
    for row in rows:
        if row["exercise_id"] is None:
            raise WorkoutError(
                f"workout {workout_id} has a prescribed block at position "
                f"{row['block_position']} with no exercises in it"
            )
        if current is not None and row["block_id"] != current["block_id"]:
            blocks.append(_assembled(current, items))
            items = []
        current = row
        items.append(
            duration.BlockItem(
                exercise_id=row["exercise_id"],
                reps=row["amount"] if row["unit"] == "reps" else None,
                seconds=row["amount"] if row["unit"] == "seconds" else None,
            )
        )
    if current is not None:
        blocks.append(_assembled(current, items))
    return tuple(blocks)


def _assembled(row: sqlite3.Row, items: Sequence[duration.BlockItem]) -> PrescribedBlock:
    return PrescribedBlock(
        block=duration.Block(items=tuple(items), rounds=row["rounds"], rest=row["rest"]),
        reason=row["reason"],
    )
