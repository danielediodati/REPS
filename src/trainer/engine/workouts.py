"""The write path for a workout in either of its two states, and reading one
back.

A plan that is only rendered is a plan nobody can deviate from, and a report
that is only read is a workout that never happened. This is where both become
rows -- the same workout, `prescribed` and then `performed`, with its blocks
and its exercises side by side under it, because deviation is the difference
between the two phases and nothing that overwrites one of them can still
compute it.

**Only the CLI commands call these writers, and they call them from the
command.** Not from `plan.py`, not from `log.py`, not from `agent.py`:
`trainer eval` runs eighteen agent loops against the project database, and a
plan that persisted from inside the agent would write eighteen phantom
prescribed workouts into the very state the measurement is taken from -- where
the unreported-workout tool would then read them as a rotation the user
skipped. ROADMAP.md § Session 5: writes are never tools. The agent emits; the
engine writes.

**The wire shape stops at the door.** What arrives here is `duration.Block`,
the vocabulary the engine already costs plans in, plus the one field a block
carries that costing has no use for: the reason it was prescribed. The
performed phase has its own two dataclasses, for the reasons written above
them. Nothing in this module knows what JSON is, and `test_engine_boundary.py`
is what keeps it that way.

**One transaction or nothing.** A workout row with no blocks under it is not a
smaller workout, it is a lie about what was prescribed, and the deviation
computed against it later would be the whole session.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine import duration, exclusions
from trainer.engine.exclusions import Exclusion

# The phases (`prescribed`, `performed`) and the provenances (`reported`,
# `assumed`, `asked`) live in migration 0006's CHECK constraints, which is
# what enforces them, and nowhere else. They are still not restated here as
# constants. This module writes whatever provenance it is handed and checks
# none of them: the vocabulary is decided where a value acquires a provenance,
# which is `log.Provenance` on the wire, and a second copy here would be a
# list with no reader to keep it honest -- it would drift from the schema the
# first time either vocabulary moved, and the CHECK would go on being the
# thing that actually refused the bad value.


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


def awaiting(connection: sqlite3.Connection) -> Workout | None:
    """The prescribed workout a report would be filed against, or `None`.

    The most recently prescribed workout that has not been reported: what
    `trainer log` opens with, because the report a person writes after
    training is a report of the workout they were last given.

    Older prescriptions with no report are **not** this. They are
    `state.unreported`, they are a different mechanism -- nothing closes them
    and nothing assumes they happened -- and offering one here would file
    today's training against a workout from three weeks ago, filling in every
    exercise it did not mention from a plan three weeks dead.

    So the `unreported_workouts` view is what this subtracts, rather than a
    second reading of *has it had its chance*: migration 0007 made that view
    the one definition, `volume_deficit` already reads it, and a rule written
    again here is a rule that would drift from it. A prescribed workout a
    later performed one overtook is out; whatever is left is open.

    `None` is a state and not a failure: training nobody planned is training,
    and it is recorded like any other.
    """
    row = connection.execute(
        "SELECT w.id FROM workouts AS w WHERE w.state = 'prescribed' "
        "AND NOT EXISTS (SELECT 1 FROM unreported_workouts AS u "
        "                WHERE u.workout_id = w.id) "
        "ORDER BY w.prescribed_on DESC, w.id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else workout(connection, int(row["id"]))


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


# -- the performed phase ------------------------------------------------------
#
# Its own dataclasses rather than `duration.Block` with sources bolted on, and
# for two reasons that both come back to what a performed row *is*.
#
# `duration.Block` is the vocabulary the engine **costs** plans in, and a
# provenance is not something the costing formula reads -- the same argument
# `PrescribedBlock` makes for keeping `reason` beside a block rather than in
# it. Bolted on, it would arrive as a tuple of sources parallel to `items`,
# and a pair of sequences that have to stay aligned is the mismatch
# `plan.render`'s `strict=True` exists to catch, moved somewhere nothing
# checks it.
#
# And `check_plan`'s invariant -- an exercise appears at most once -- is a rule
# about a *plan*. A workout in which the bar was picked up twice is a fact, and
# this session's whole position is that a fact is recorded and flagged, never
# refused. Routing performed rows through the plan vocabulary would apply a
# rule about what may be prescribed to something that has already happened.


@dataclass(frozen=True)
class PerformedItem:
    """One exercise as it was performed: how much, how that is known, and
    under what load.

    `amount_source` is required and `load_kg_source` is tied to the load
    rather than to the phase, which is migration 0006's own rule: a provenance
    describing nothing is not a provenance. A pull-up has no load and so says
    nothing about where a load came from.
    """

    exercise_id: str
    unit: str
    amount: int
    amount_source: str
    load_kg: float | None = None
    load_kg_source: str | None = None


@dataclass(frozen=True)
class PerformedBlock:
    """One block as it was performed, with a provenance on each of its numbers
    and whatever the user volunteered about how hard it was.

    No `reason`: nobody justifies what has already happened, and migration
    0006's CHECK says so.
    """

    items: tuple[PerformedItem, ...]
    rounds: int
    rounds_source: str
    rest: int
    rest_source: str
    rpe: float | None = None


def reportable(connection: sqlite3.Connection, workout_id: int) -> Workout:
    """The workout a report may be filed against, or why it may not be.

    Two refusals and one wording, because both callers -- the validator on the
    way in and `record_performed` on the way down -- have to name them the
    same way. A workout nobody has is a typo in the document; a workout
    already reported is one training session recorded twice, which would
    double its volume in every cycle that counts it.

    A raise rather than `workout`'s `None`: that function answers *is this
    there*, and this one answers *may I write here*, where every answer but
    yes is a refusal.
    """
    found = workout(connection, workout_id)
    if found is None:
        raise WorkoutError(
            f"there is no workout {workout_id} to report against. A report "
            "either names a workout that was prescribed or names none at all"
        )
    if found.state == "performed":
        raise WorkoutError(
            f"workout {workout_id} was already reported, on {found.performed_on}. "
            "One training session is one workout: report the one you did today"
        )
    return found


def record_performed(
    connection: sqlite3.Connection,
    blocks: Sequence[PerformedBlock],
    on: str,
    report: str,
    workout_id: int | None = None,
    exclusion: Exclusion | None = None,
    retest_date: str | None = None,
) -> int:
    """Write one performed workout -- and the exclusion it proposed, if it
    proposed one -- and return the workout's id.

    `workout_id` names the prescribed workout this reports against, and that
    workout transitions in place: its prescribed children stay exactly where
    they are, because deviation is the difference between the two phases and
    overwriting one of them destroys it. `None` is training nobody planned,
    which arrives as a new row with no `prescribed_on`.

    **The exclusion is written in the same transaction, or not at all.** It is
    the one thing in a report that changes what may be prescribed tomorrow, so
    a workout recorded without it would go on offering the movement that
    caused it -- while an exclusion written without its workout is a safety
    boundary with no recorded reason for existing.
    """
    if not blocks:
        raise WorkoutError("a workout is at least one block")
    if (exclusion is None) != (retest_date is None):
        raise WorkoutError(
            "a proposed exclusion is a value and a re-test date, never one of "
            "the two: an exclusion with no way back is the one failure "
            "TRAINER.md says this state cannot afford"
        )
    if workout_id is not None:
        # Read before the transaction so the two refusals arrive as
        # themselves, with dates and ids in them. It is **not** what makes
        # them hold: two runs reporting the same workout would both read
        # `prescribed` here and only then serialise on the write. The UPDATE
        # below carries the condition again, inside the transaction, and that
        # is the one that decides.
        reportable(connection, workout_id)

    connection.execute("BEGIN IMMEDIATE")
    try:
        identifier = _transitioned(connection, workout_id, on, report)
        for position, block in enumerate(blocks, start=1):
            _write_performed_block(connection, identifier, position, block)
        if exclusion is not None:
            assert retest_date is not None  # the pair is checked above
            exclusions.add(connection, exclusion, retest_date)
        # Inside the try, for the reason `record_prescribed` gives: a COMMIT
        # that failed outside it would escape with the transaction still open.
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return identifier


def _transitioned(
    connection: sqlite3.Connection, workout_id: int | None, on: str, report: str
) -> int:
    """The row the performed children hang under: the prescribed workout moved
    into its second state, or a new one for training nobody planned.

    **`AND state = 'prescribed'` is the guard, not `reportable`.** That check
    runs before the transaction opens, so two runs reporting the same workout
    both pass it and only then serialise on the write -- and the loser's
    UPDATE would quietly match nothing while its blocks landed as a *second*
    set of performed children under the same workout. Every cycle that counts
    volume would then count that session twice. Written as a condition on the
    UPDATE, the row is re-read under the write lock and the loser is refused.
    """
    if workout_id is None:
        cursor = connection.execute(
            "INSERT INTO workouts (state, performed_on, report) "
            "VALUES ('performed', ?, ?)",
            (on, report),
        )
        return _inserted(cursor)

    cursor = connection.execute(
        "UPDATE workouts SET state = 'performed', performed_on = ?, report = ? "
        "WHERE id = ? AND state = 'prescribed'",
        (on, report, workout_id),
    )
    if cursor.rowcount != 1:
        # `reportable` states the two ways this happens, and it is asked again
        # rather than guessed at: by now the row may have been reported by
        # somebody else, and its message says when.
        reportable(connection, workout_id)
        raise WorkoutError(f"workout {workout_id} could not be moved to performed")
    return workout_id


def _write_performed_block(
    connection: sqlite3.Connection,
    workout_id: int,
    position: int,
    block: PerformedBlock,
) -> None:
    cursor = connection.execute(
        "INSERT INTO workout_blocks "
        "(workout_id, phase, position, rounds, rounds_source, rest, rest_source, rpe) "
        "VALUES (?, 'performed', ?, ?, ?, ?, ?, ?)",
        (
            workout_id,
            position,
            block.rounds,
            block.rounds_source,
            block.rest,
            block.rest_source,
            block.rpe,
        ),
    )
    block_id = _inserted(cursor)
    for item_position, item in enumerate(block.items, start=1):
        connection.execute(
            "INSERT INTO workout_exercises "
            "(block_id, phase, position, exercise_id, unit, amount, amount_source, "
            "load_kg, load_kg_source) "
            "VALUES (?, 'performed', ?, ?, ?, ?, ?, ?, ?)",
            (
                block_id,
                item_position,
                item.exercise_id,
                item.unit,
                item.amount,
                item.amount_source,
                item.load_kg,
                item.load_kg_source,
            ),
        )


def performed(
    connection: sqlite3.Connection, workout_id: int
) -> tuple[PerformedBlock, ...]:
    """What was actually done in this workout, in the order it was reported.

    Empty for a workout nobody has reported yet -- the mirror of `prescribed`,
    and it refuses a childless block for the same reason: read with an inner
    join that block would simply not come back, and the workout read out would
    be shorter than the workout stored.
    """
    rows = connection.execute(
        "SELECT b.id AS block_id, b.position AS block_position, "
        "b.rounds, b.rounds_source, b.rest, b.rest_source, b.rpe, "
        "e.exercise_id, e.unit, e.amount, e.amount_source, e.load_kg, e.load_kg_source "
        "FROM workout_blocks AS b "
        "LEFT JOIN workout_exercises AS e ON e.block_id = b.id "
        "WHERE b.workout_id = ? AND b.phase = 'performed' "
        "ORDER BY b.position, e.position",
        (workout_id,),
    ).fetchall()

    blocks: list[PerformedBlock] = []
    items: list[PerformedItem] = []
    current: sqlite3.Row | None = None
    for row in rows:
        if row["exercise_id"] is None:
            raise WorkoutError(
                f"workout {workout_id} has a performed block at position "
                f"{row['block_position']} with no exercises in it"
            )
        if current is not None and row["block_id"] != current["block_id"]:
            blocks.append(_performed(current, items))
            items = []
        current = row
        items.append(
            PerformedItem(
                exercise_id=row["exercise_id"],
                unit=row["unit"],
                amount=row["amount"],
                amount_source=row["amount_source"],
                load_kg=None if row["load_kg"] is None else float(row["load_kg"]),
                load_kg_source=row["load_kg_source"],
            )
        )
    if current is not None:
        blocks.append(_performed(current, items))
    return tuple(blocks)


def _performed(row: sqlite3.Row, items: Sequence[PerformedItem]) -> PerformedBlock:
    return PerformedBlock(
        items=tuple(items),
        rounds=row["rounds"],
        rounds_source=row["rounds_source"],
        rest=row["rest"],
        rest_source=row["rest_source"],
        rpe=None if row["rpe"] is None else float(row["rpe"]),
    )


def volume(
    connection: sqlite3.Connection, blocks: Sequence[PerformedBlock]
) -> tuple[dict[str, int], dict[str, int]]:
    """What these blocks would add to each of the two axes, before they are
    written -- rounds per movement pattern, and rounds per primary muscle.

    **The same arithmetic `workout_volume` does, on a workout that is not in
    the database yet.** Migration 0007 answers this question over stored rows
    and is the definition; nothing that has not been recorded can be asked of
    a view, and the measurement in `log_evaluation` has to ask it of a
    document the agent emitted without recording anything. `test_workouts.py`
    holds the two against each other over the same workout, which is what
    stops this drifting into a second answer.

    CONTEXT.md's rule, unchanged: a round counts **whole** to the exercise's
    movement pattern and whole to each of its primary muscles, and nothing is
    divided -- a block of two exercises for four rounds is four rounds of
    each. An exercise the enrichment has no pattern for contributes to no
    pattern, rather than to a bucket nobody can act on.
    """
    patterns: dict[str, int] = {}
    muscles: dict[str, int] = {}
    for block in blocks:
        for item in block.items:
            row = connection.execute(
                "SELECT movement_pattern, primary_muscles FROM exercises WHERE id = ?",
                (item.exercise_id,),
            ).fetchone()
            if row is None:
                raise WorkoutError(
                    f"no such exercise: {item.exercise_id!r}; ids come from "
                    "the catalog"
                )
            if row["movement_pattern"] is not None:
                patterns[row["movement_pattern"]] = (
                    patterns.get(row["movement_pattern"], 0) + block.rounds
                )
            for muscle in json.loads(row["primary_muscles"]):
                muscles[muscle] = muscles.get(muscle, 0) + block.rounds
    return patterns, muscles
