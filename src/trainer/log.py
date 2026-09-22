"""A performed workout is a document: the shape it arrives in, the little it
can be refused for, the flags it carries instead, and how it is printed.

The door session 5's agent comes out through -- the mirror of session 4's
`plan.py`. `trainer log` reads what a model made of what you said and
`trainer log --from FILE` reads a report somebody wrote by hand; both are
validated, written in one transaction and rendered by what is in this file. No
model and no network anywhere in here.

**The symmetry with `plan.py` breaks at the validator, and that break is the
point of this ticket.** That one refuses a plan outside the admissible set,
because the plan has not happened yet and can still be prevented. This one
cannot refuse **a fact**. You had an exclusion on `vertical push` and you
pressed anyway: that row is the most valuable one in the database -- it is
what feeds the hypotheses and the medical escalation -- and rejecting
it would mean keeping a clean state by lying about what happened. A performed
workout is **recorded and flagged**, never rejected.

So the two are separate functions. `validate` raises, and only for things that
are not a matter of opinion: an id the catalog does not have, a unit or an
amount the schema cannot express, a provenance outside the three values, a
provenance that could not be true -- `assumed` with no prescription behind it,
or `assumed` saying something the prescription does not -- and a proposed
exclusion naming neither a pattern nor a joint or naming no way back. Every one
of those is a statement about the *document* -- a typo, a mistyped field -- and
none of them is a statement about what the user did. `flags` returns, never
raises, and is the whole of what can be said about the training.

**Adherence is a property of the document, not of the database**, which is why
`to_performed` lives here and not in `engine/`. Logging is by deviation: what
a report does not mention was done as prescribed, so the gaps in the document
are filled from the prescribed workout with a provenance of `assumed`. The
engine's writer takes complete blocks and has no idea that anything was left
out; only the shape that arrives by wire has gaps in it.

**Beside `trainer.cli`, never inside `engine/`**, for the reason `plan.py` is:
pydantic is a wire concern, and `test_engine_boundary.py` keeps the engine free
of every client's vocabulary.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from trainer.engine import catalog, exclusions, state, workouts
from trainer.engine.exclusions import Exclusion

Provenance = Literal["reported", "assumed", "asked"]
"""The three ways a value in a performed workout got here, and the one place
Python names them.

CONTEXT.md defines them; migration 0006's CHECK enforces them. This is the
wire's copy, and it is a `Literal` rather than a tuple so that a fourth value
is refused by the schema, in the shape error, before anything reaches a
database that would refuse it as a constraint violation nobody can read.
"""

LOAD_JUMP = 0.2
"""How far a load may move from the last one recorded for that exercise before
the row is flagged -- a fifth, either way.

A written rule rather than a stored judgement, for the reason `load_trend` gets
one: a rule is checkable and an opinion is not. A fifth is far outside anything
progression produces -- adding 2.5 kg to a 100 kg lift is 2.5% -- and comfortably
inside the mistakes it exists to catch: pounds typed as kilos is 45% off, and a
10 written for a 100 is 900%.

It flags. It never refuses. A user who put twenty kilos on the bar in a week
did that, and the row saying so is the interesting one.
"""


class LogError(RuntimeError):
    """What arrived is not a performed workout: bad JSON, a missing field, a
    provenance outside the three. A statement about the document."""


class LogRejected(RuntimeError):
    """What arrived is a performed workout, and something in it cannot be
    resolved: an exercise id the catalog does not have, a value marked
    `assumed` that the prescription does not say, a proposed exclusion naming
    neither a pattern nor a joint, a workout that was already reported.

    Never a statement about what the user did. Everything about *that* is a
    `Flag`.
    """


# -- the shape ----------------------------------------------------------------


class PerformedItem(BaseModel):
    """One exercise as it was performed, and how every number on it is known.

    `unit` and `amount` are one field and a unit for the reason
    `plan.Prescription` is: *"3 rounds of 10 reps of walking"* means nothing,
    and a shape that cannot express it needs no rule saying so. The two are
    flat here rather than nested in a `Prescription` because each value on a
    performed row carries its own `_source`, and a value separated from its
    provenance by a level of nesting is a provenance about something else.

    `load_kg` and `load_kg_source` stand or fall together: a provenance
    describing nothing is not a provenance, which is migration 0006's own
    rule, restated here so it arrives as a sentence about the document rather
    than as a CHECK constraint. `unit`, `amount` and `amount_source` do the
    same: null all three when the user did not say how much, and adherence
    writes the prescribed amount.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(
        description="The exercise's id, character for character as the catalog has it."
    )
    unit: Literal["reps", "seconds"] | None = None
    amount: int | None = Field(
        default=None,
        ge=1,
        description="Reps or seconds of one round, and null when the user did not say.",
    )
    amount_source: Provenance | None = None
    load_kg: float | None = Field(
        default=None,
        ge=0,
        description="Kilograms, and null for anything performed without a load.",
    )
    load_kg_source: Provenance | None = None

    @model_validator(mode="after")
    def _each_number_with_its_source(self) -> PerformedItem:
        if (self.load_kg is None) != (self.load_kg_source is None):
            raise ValueError(
                "a load and its provenance are written together or not at all"
            )
        if len({self.unit is None, self.amount is None, self.amount_source is None}) > 1:
            raise ValueError(
                "a unit, an amount and its provenance are written together or not at all"
            )
        return self


class PerformedBlock(BaseModel):
    """One block as it was performed: what was in it, how many rounds of it,
    the rest that was actually taken, and how hard it felt if the user said.

    No `reason`, which is the one field `plan.PlanBlock` requires. Nobody
    justifies what has already happened; the justification was given when the
    workout was prescribed and it is still on the prescribed row.

    `rpe` carries no `_source` and is never asked for. If the user says it, it
    is recorded; if they do not, it stays empty -- so `assumed` and `asked`
    cannot arise for it and a provenance column would have one legal value.

    `rounds` and `rest` are null, with their sources, when the user did not
    say them: adherence writes the prescribed ones.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[PerformedItem] = Field(min_length=1)
    rounds: int | None = Field(
        default=None,
        ge=1,
        description="How many times the block was performed, and null when the user did not say.",
    )
    rounds_source: Provenance | None = None
    rest: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Seconds rested after each round -- 90 means a minute and a half. "
            "Seconds, never milliseconds and never minutes. Null when the user "
            "did not say."
        ),
    )
    rest_source: Provenance | None = None
    rpe: float | None = Field(
        default=None,
        ge=1,
        le=10,
        description=(
            "How hard it felt, 1-10, and null unless the user volunteered it. "
            "It is never asked for."
        ),
    )

    @model_validator(mode="after")
    def _each_number_with_its_source(self) -> PerformedBlock:
        for name, value, source in (
            ("rounds", self.rounds, self.rounds_source),
            ("rest", self.rest, self.rest_source),
        ):
            if (value is None) != (source is None):
                raise ValueError(
                    f"{name} and its provenance are written together or not at all"
                )
        return self


class ProposedExclusion(BaseModel):
    """A movement the report says should stop being prescribed, and the day to
    try it again.

    **No granularity field.** `exclusions.classify` decides whether a value is
    a movement pattern or a loaded joint, against the catalog's own vocabulary
    rather than by inference -- ROADMAP.md § Session 5 is explicit about that,
    and it is the same rule that keeps the twelve patterns out of Python. A
    granularity on the wire would be a second answer to a question the engine
    already answers, and the day the two disagreed the exclusion would be
    filed under whichever of them was wrong.

    `retest_date` is required. TRAINER.md's position is that a wall with no
    way back is the one failure this state cannot afford, and an optional date
    is a wall with no way back that nobody had to decide to build.
    """

    model_config = ConfigDict(extra="forbid")

    value: str = Field(
        min_length=1,
        description=(
            "A movement pattern (`vertical push`) or a loaded joint "
            "(`shoulder`) -- never an exercise id, and never a preference."
        ),
    )
    retest_date: str = Field(
        description="ISO-8601 (`YYYY-MM-DD`): the day this is tried again."
    )
    """Checked to be that shape, not merely documented as it.

    The column stores a string and `exclusions.active` compares it with `>`,
    which is chronological only because this format sorts that way. A
    `retest_date` of *"next week"* sorts after every date there will ever be,
    so the exclusion never expires -- and nothing anywhere would ever say so.
    That is a wall with no way back, arriving through the first code path that
    ever creates an exclusion from a document, and *"next week"* is a phrase a
    model is perfectly capable of emitting.

    Whether the date is in the *future* is not decided here: this schema does
    not know what day it is, and a document that validates differently
    depending on when it is read is a document nobody can test. `validate`
    holds `today` and refuses it there.
    """

    why: str = Field(
        min_length=1,
        description="What the user said that this is a reading of, in one sentence.",
    )

    @field_validator("retest_date")
    @classmethod
    def _a_date_that_sorts_as_one(cls, value: str) -> str:
        # `strptime` rather than `date.fromisoformat`, which also accepts
        # `20261001` -- a real date that sorts nowhere near the dates beside it
        # in the column.
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"{value!r} is not a date; a re-test date is written YYYY-MM-DD"
            ) from None
        return value


class PerformedWorkout(BaseModel):
    """The whole report: which workout it is about, what was actually done,
    the user's own words, and the one thing it may propose.

    `workout_id` is the prescribed workout this reports against, or null.
    Null is a real answer and not a missing value: training nobody planned is
    still training, and it is recorded like any other -- flagged, because a
    report with nothing to be a deviation *from* is a different kind of row
    from one that has a prescription behind it.

    `blocks` may be **empty**, which is the one place this shape is looser
    than `plan.WorkoutPlan`. A plan with no blocks is not a workout; a report
    with no blocks is *"did it as prescribed"*, which is the commonest report
    there is and the whole reason logging is by deviation. Adherence fills it
    in. With no `workout_id` there is nothing to fill it from, and the writer
    refuses a workout with no blocks in it.

    `report` is the user's own words, verbatim, and the only prose this
    document keeps. Not a summary: it is what a hypothesis is formed from,
    and a paraphrase is the agent's reading of the user
    rather than the user.
    """

    model_config = ConfigDict(extra="forbid")

    workout_id: int | None = Field(
        default=None,
        description=(
            "The prescribed workout this reports against, or null when the "
            "user trained something nobody planned."
        ),
    )
    blocks: list[PerformedBlock] = Field(
        default_factory=list,
        description=(
            "What was actually done. Only what differs from the prescription "
            "has to be here: anything left out is filled in as prescribed, "
            "with a provenance of `assumed`."
        ),
    )
    report: str = Field(
        min_length=1,
        description="The user's own words about the workout, verbatim.",
    )
    proposed_exclusion: ProposedExclusion | None = Field(
        default=None,
        description=(
            "Empty, unless something in the report says a movement should "
            "stop being prescribed for a while. A preference is never one of "
            "these."
        ),
    )


@dataclass(frozen=True)
class Flag:
    """Something worth knowing about a row that was written anyway.

    `about` is the exercise it concerns, or `None` when it is about the
    workout as a whole. It travels beside the id rather than inside the
    sentence so the renderer can put the flag under the line it is about,
    which is where a reader is looking when they need it.
    """

    about: str | None
    says: str


def parse(text: str) -> PerformedWorkout:
    """A performed workout out of JSON, or a shape error naming the field it
    choked on.

    Never a traceback, for `plan.parse`'s reason: the author of a bad document
    is a person editing a file today and a model emitting one tomorrow, and
    neither can act on a pydantic stack trace.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise LogError(f"that is not JSON: {error}") from error

    try:
        return PerformedWorkout.model_validate(raw)
    except ValidationError as error:
        raise LogError(_shape(error)) from error


def _shape(error: ValidationError) -> str:
    lines = ["that is not a performed workout:"]
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "the document"
        lines.append(f"  {where}: {problem['msg']}")
    return "\n".join(lines)


# -- the validator ------------------------------------------------------------


def validate(
    connection: sqlite3.Connection, performed: PerformedWorkout, today: str
) -> None:
    """The refusals, and only the refusals.

    Every one of them is a statement about the *document* -- a typo, a
    provenance that cannot be true, an exclusion naming nothing. Nothing here
    is about what the user did; that is `flags`, and it raises on none of it.

    They run in this order because each is a precondition for reading the next
    thing: a document with nothing in it has no ids to check, an id the
    catalog does not have cannot be checked against an exclusion, and a
    workout that is not there cannot be a prescription to deviate from.
    """
    _something_was_performed(performed)
    _nothing_assumed_without_a_prescription(performed)
    _every_id_in_the_catalog(connection, performed)
    _the_workout_it_reports_against(connection, performed)
    _nothing_left_out_that_nothing_prescribes(connection, performed)
    _nothing_assumed_the_prescription_does_not_say(connection, performed)
    _the_exclusion_it_proposes(connection, performed, today)


def flags(
    connection: sqlite3.Connection,
    performed: PerformedWorkout,
    blocks: tuple[workouts.PerformedBlock, ...],
    today: str,
) -> tuple[Flag, ...]:
    """Everything worth knowing about a workout that is going to be written
    anyway.

    **It reads `blocks`, not the document, and that distinction is the whole
    of this function's correctness.** `blocks` is what `to_performed` resolved
    -- what the report said *plus* everything adherence filled in -- and it is
    what will be written. Read off the document instead, the commonest report
    there is (`{"workout_id": N, "report": "went fine"}`, no blocks at all)
    would write every prescribed exercise as performed and flag none of them:
    a press under an active exclusion, recorded and silent, which is exactly
    the row this module exists to shout about.

    `performed` is still needed for the two things only the document knows:
    whether there was a prescription behind it at all, and which workout it
    was.

    Deduplicated, in the order the checks run. The same exclusion can reach an
    exercise the user did twice, and the flag that matters most in this output
    is the one that would be buried by repeating it.
    """
    found = (
        *_no_prescription(performed),
        *_substitutions(connection, performed, blocks),
        *_under_an_exclusion(connection, blocks, today),
        *_loads_that_jumped(connection, blocks),
    )
    return tuple(dict.fromkeys(found))


def _something_was_performed(performed: PerformedWorkout) -> None:
    """A report with no blocks and no prescription behind it is a report of
    nothing.

    Empty blocks are legitimate on their own -- *"did it as prescribed"* is
    the commonest report there is -- but only when there is a prescription for
    adherence to fill them from. With neither, the writer would refuse it a
    moment later, *after* the render had already printed a workout with an
    empty `performed:` section under it.
    """
    if performed.workout_id is None and not performed.blocks:
        raise LogRejected(
            "this report says nothing was done and names no prescribed workout "
            "to have done it as. Name the workout it is about, or say what was "
            "performed"
        )


def _nothing_assumed_without_a_prescription(performed: PerformedWorkout) -> None:
    """`assumed` means *as prescribed*, so it cannot appear where nothing was.

    A statement about the document rather than about the training: the
    provenance names where a value came from, and with no prescription behind
    the workout there is no adherence default it could have come from. Left
    through, the row would say a number was defaulted from a plan that does
    not exist -- and `WHERE amount_source = 'assumed'`, which is supposed to
    list the numbers the user never gave, would return one nobody can trace.
    """
    if performed.workout_id is not None:
        return

    found: set[str] = set()
    for position, block in enumerate(performed.blocks, start=1):
        if block.rounds_source == "assumed":
            found.add(f"block {position}: rounds")
        if block.rest_source == "assumed":
            found.add(f"block {position}: rest")
        for item in block.items:
            if item.amount_source == "assumed":
                found.add(f"block {position}: {item.exercise_id}'s amount")
            if item.load_kg_source == "assumed":
                found.add(f"block {position}: {item.exercise_id}'s load")
    if not found:
        return
    offenders = sorted(found)
    raise LogRejected(
        "this report names no prescribed workout, so nothing in it can be "
        "`assumed` -- there is no prescription to have assumed it from:\n"
        + "\n".join(f"  {where}" for where in offenders)
        + "\nEverything here is `reported` or `asked`."
    )


def _every_id_in_the_catalog(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> None:
    """An id nobody has is a typo, not a workout.

    The one refusal that is genuinely about the exercises named, and it is
    about the *document* rather than about the training: nothing was performed
    under an id that does not exist, so there is no fact here to preserve.
    Written through, the foreign key would refuse it a moment later as a
    constraint violation naming a column.
    """
    unknown = [
        item.exercise_id
        for block in performed.blocks
        for item in block.items
        if catalog.exercise(connection, item.exercise_id) is None
    ]
    if unknown:
        raise LogRejected(
            "the report names exercises the catalog does not have:\n"
            + "\n".join(f"  {exercise_id}" for exercise_id in unknown)
            + "\nIds come from the catalog (`trainer catalog --name ...`)."
        )


def _the_workout_it_reports_against(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> None:
    """`workouts.reportable` states both refusals; this only asks it early.

    Early, because the renderer reads the prescription and `workouts.prescribed`
    answers `()` for a workout that is not there -- which would print a report
    about workout 404 as though it were training nobody planned, and only then
    fail at the write.
    """
    if performed.workout_id is None:
        return
    try:
        workouts.reportable(connection, performed.workout_id)
    except workouts.WorkoutError as error:
        raise LogRejected(str(error)) from error


def _left_out(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> list[str]:
    """Every null in the document that no prescribed number stands behind."""
    prescribed = (
        () if performed.workout_id is None
        else workouts.prescribed(connection, performed.workout_id)
    )
    found: list[str] = []
    for position, (block, index) in enumerate(
        _paired(prescribed, performed.blocks), start=1
    ):
        planned = (
            set() if index is None
            else {item.exercise_id for item in prescribed[index].block.items}
        )
        if block.rounds is None and index is None:
            found.append(f"block {position}: rounds")
        if block.rest is None and index is None:
            found.append(f"block {position}: rest")
        found.extend(
            f"block {position}: {item.exercise_id}'s amount"
            for item in block.items
            if item.amount is None and item.exercise_id not in planned
        )
    return found


def _nothing_left_out_that_nothing_prescribes(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> None:
    """A null is filled from the prescription, so it needs one behind it.

    A substitute, a block nobody prescribed, a workout nobody planned: there
    is no number to fill in. Whether to ask the user or to write a reading of
    the report marked `assumed` is the agent's call, and the refusal offers
    both.
    """
    found = _left_out(connection, performed)
    if found:
        raise LogRejected(
            "nothing prescribes these, so they cannot be left out:\n"
            + "\n".join(f"  {where}" for where in found)
            + (
                "\nAsk the user for them."
                if performed.workout_id is None
                else "\nAsk the user for them, or write the number you read in "
                "the report, marked `assumed`."
            )
        )


def _nothing_assumed_the_prescription_does_not_say(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> None:
    """`assumed` means *as prescribed*, so where there is a prescription to
    check it against, it has to say what the prescription says.

    The sibling of `_nothing_assumed_without_a_prescription`, and the same
    kind of statement: a provenance that could not be true. That one catches a
    document with no prescription behind it at all; this one catches a
    document that has one and marks a number `assumed` that **contradicts**
    it.

    **Found by running the agent.** Asked to report *"only 3 sets of military
    because the shoulder was pulling"* against a prescription of 10 reps, a
    model emitted `amount: 8, amount_source: "assumed"`. Every rule up to here
    passed it: the id exists, the number is a number, there is a workout to
    deviate from. What it wrote is a row saying *the user never gave this
    number, it came from the plan* -- about a number that came from nowhere,
    in the one column whose whole job is to separate the two.

    **Contradiction, and not merely silence.** A substituted exercise has no
    prescribed line at all, and the block it sits in has no prescribed
    counterpart: `rounds`, `rounds_source`, `rest` and `rest_source` are
    required fields, so a report of *"I did dumbbell bench instead, three
    sets"* has to say **something** about the rest nobody asked about, and
    `reported` would be a lie about what the user said. Where the prescription
    is silent this rule is silent too, and `assumed` keeps its useful half --
    *the user did not give this number*. What is refused is only what can be
    shown false.

    A load is the exception, and it is refused everywhere: a plan prescribes
    no load anywhere, so there is nothing for one ever to have been assumed
    from. `_assumed_items` sets none, and a document claiming one is claiming
    the plan said what the bar weighed.

    The block a reported one is about is decided by `_paired`, which is what
    `to_performed` fills the gaps from, so the answer here and the answer at
    the write are one matching read twice.
    """
    if performed.workout_id is None:
        return

    prescribed = workouts.prescribed(connection, performed.workout_id)
    planned = {
        item.exercise_id: item for block in prescribed for item in block.block.items
    }
    found: list[str] = []
    for position, (block, index) in enumerate(
        _paired(prescribed, performed.blocks), start=1
    ):
        where = f"block {position}"
        source = None if index is None else prescribed[index]
        if source is not None:
            if block.rounds_source == "assumed" and block.rounds != source.block.rounds:
                found.append(
                    f"{where}: {block.rounds} rounds, prescribed as "
                    f"{source.block.rounds}"
                )
            if block.rest_source == "assumed" and block.rest != source.block.rest:
                found.append(
                    f"{where}: {block.rest}s rest, prescribed as {source.block.rest}"
                )
        for item in block.items:
            if item.load_kg_source == "assumed":
                found.append(
                    f"{where}: {item.exercise_id}'s load, and a plan "
                    "prescribes no load to have assumed it from"
                )
            was = planned.get(item.exercise_id)
            if item.amount_source != "assumed" or was is None:
                continue
            unit = "reps" if was.reps is not None else "seconds"
            amount = was.reps if was.reps is not None else was.seconds
            if (unit, amount) != (item.unit, item.amount):
                found.append(
                    f"{where}: {item.amount} {item.unit} of {item.exercise_id}, "
                    f"prescribed as {amount} {unit}"
                )
    if not found:
        return
    raise LogRejected(
        "this report marks values `assumed`, which means *as prescribed*, "
        "that the prescription contradicts:\n"
        + "\n".join(f"  {where}" for where in found)
        + "\nA value the user did not give is left out and adherence fills "
        "it in; one they did give is `reported`."
    )


def _the_exclusion_it_proposes(
    connection: sqlite3.Connection, performed: PerformedWorkout, today: str
) -> None:
    """`classify` decides the granularity, and refusing is one of its answers.

    The message is `classify`'s own, which already names both granularities
    and says an exclusion is never an exercise id -- the two things whoever
    wrote the value needs to be told.

    Then the date, which the schema has already checked is a date. A re-test
    date that has passed is a wall with no way back, arriving by the one route
    that is easy to miss: nothing later re-reads it, `exclusions.active`
    simply never returns the row, and the render prints a confident sentence
    about a movement that is not in fact excluded. TRAINER.md says a wall with
    no way back is the one failure this state cannot afford; a wall that was
    never a wall is the same failure with the sign flipped.
    """
    if performed.proposed_exclusion is None:
        return
    try:
        exclusions.classify(connection, performed.proposed_exclusion.value)
    except exclusions.ExclusionError as error:
        raise LogRejected(str(error)) from error

    if performed.proposed_exclusion.retest_date <= today:
        # Lexicographic, which for `YYYY-MM-DD` is chronological -- the same
        # comparison `exclusions.active` makes, and the schema is what
        # guarantees the format it relies on.
        raise LogRejected(
            f"the proposed exclusion is to be re-tested on "
            f"{performed.proposed_exclusion.retest_date}, which is not after "
            f"{today}. An exclusion that expires before it starts excludes "
            "nothing; give it a date to come back on"
        )


def _no_prescription(performed: PerformedWorkout) -> tuple[Flag, ...]:
    """A workout nobody planned. Recorded like any other, and said out loud.

    It is flagged rather than passed over because every value in it is
    `reported` or `asked` and none of them can be `assumed`: there was no
    prescription to assume against. A reader who does not know that is reading
    a workout with no deviations and concluding the user did exactly as they
    were told.
    """
    if performed.workout_id is not None:
        return ()
    return (
        Flag(
            None,
            "this reports no prescribed workout, so there is nothing it "
            "deviates from",
        ),
    )


def _substitutions(
    connection: sqlite3.Connection,
    performed: PerformedWorkout,
    blocks: tuple[workouts.PerformedBlock, ...],
) -> tuple[Flag, ...]:
    """An exercise that was not in the prescribed workout.

    Almost always a substitution -- the presses swapped for something the
    shoulder tolerated -- and occasionally something added on the end. The
    engine does not try to tell those apart: which prescribed exercise a
    substitute stands in for is a judgement, and ROADMAP.md leaves the
    judgements to the agent. What is stated here is the fact that the workout
    contains something nobody prescribed.
    """
    if performed.workout_id is None:
        # Everything in it is unprescribed, which `_no_prescription` has
        # already said once. Saying it again per exercise would bury the one
        # flag that matters under a list of every line in the workout.
        return ()

    prescribed = {
        item.exercise_id
        for block in workouts.prescribed(connection, performed.workout_id)
        for item in block.block.items
    }
    return tuple(
        Flag(item.exercise_id, "was not in the prescribed workout")
        for block in blocks
        for item in block.items
        if item.exercise_id not in prescribed
    )


def _under_an_exclusion(
    connection: sqlite3.Connection,
    blocks: tuple[workouts.PerformedBlock, ...],
    today: str,
) -> tuple[Flag, ...]:
    """Performed anyway, under an exclusion that was in force.

    **The row this whole ticket exists to protect.** It is written, it is
    flagged, and it is never refused: an exclusion the user trained straight
    through is what a hypothesis is formed about and what a medical
    escalation would be read off. Refused, the state stays clean by not
    knowing.

    `exclusions.covering` is the one definition of what an exclusion reaches,
    shared with `admissible.rejection`, so the boundary that keeps a movement
    out of a plan is the same boundary that notices it in a report.
    """
    standing = exclusions.active(connection, today)
    if not standing:
        return ()

    return tuple(
        Flag(
            item.exercise_id,
            f"is under an exclusion on {covering.granularity} "
            f"{covering.value!r}, and was performed anyway",
        )
        for block in blocks
        for item in block.items
        for covering in exclusions.covering(connection, standing, item.exercise_id)
    )


def _loads_that_jumped(
    connection: sqlite3.Connection, blocks: tuple[workouts.PerformedBlock, ...]
) -> tuple[Flag, ...]:
    """A load that moved further than the recorded history explains.

    `LOAD_JUMP` is the rule; `state.last_performed_load` is the history, and
    it is asked rather than queried here so that there is one definition of
    *the load this exercise was last performed with*. That function answers
    *"I don't know"* for an exercise with nothing recorded -- which today is
    every exercise, because its `LOAD_SOURCE` still points at the columns the
    load had before migration 0006 moved it onto `workout_exercises`. Session
    5's issue 03 is what repoints it, and this flag starts firing on that
    commit without a line changing here.

    An unknown history flags nothing. The first time you record a load there
    is nothing for it to have jumped from, and inventing a baseline to compare
    against would make every first entry suspicious.
    """
    found: list[Flag] = []
    for block in blocks:
        for item in block.items:
            if item.load_kg is None:
                continue
            previous = state.last_performed_load(connection, item.exercise_id).value
            if previous is None or previous == 0:
                continue
            if abs(item.load_kg - previous) / previous > LOAD_JUMP:
                found.append(
                    Flag(
                        item.exercise_id,
                        f"moved from {previous:g} kg to {item.load_kg:g} kg, "
                        f"further than the recorded history explains",
                    )
                )
    return tuple(found)


# -- adherence ----------------------------------------------------------------


def to_performed(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> tuple[workouts.PerformedBlock, ...]:
    """The document, plus everything it did not mention, in the vocabulary the
    engine writes.

    **Adherence, and it is a rule about the document.** What a report does not
    mention was performed as prescribed -- CONTEXT.md, and it holds inside one
    report and nowhere else. So a prescribed exercise the document never names
    comes through with the prescription's own numbers and a provenance of
    `assumed`, which is what makes *"assume adherence and flag the
    uncertainty"* a column rather than a slogan: `WHERE amount_source =
    'assumed'` is the list of numbers the user never actually said.

    **Matched by exercise, never by position** -- `_paired` is that matching,
    and the validator reads it too. A prescribed block is *reported* when the
    document names any of its exercises, its unmentioned siblings are filled
    into the same block, and a prescribed block the document never touches
    comes through whole and entirely assumed.

    A substitution therefore leaves the prescribed exercise assumed as well as
    recording the substitute, and both are flagged -- the substitute as
    something nobody prescribed. That is deliberate: which of the two the user
    meant is a judgement, and ROADMAP.md § Session 5 gives the judgements to
    the agent. The engine states what it was told and what it defaulted, and
    every one of those numbers says which it is.
    """
    if performed.workout_id is None:
        return tuple(_reported(block, None) for block in performed.blocks)

    prescribed = workouts.prescribed(connection, performed.workout_id)
    accounted = {
        item.exercise_id for block in performed.blocks for item in block.items
    }

    blocks: list[workouts.PerformedBlock] = []
    matched: set[int] = set()
    for reported, index in _paired(prescribed, performed.blocks):
        filled: tuple[workouts.PerformedItem, ...] = ()
        if index is not None:
            matched.add(index)
            filled = _assumed_items(prescribed[index], accounted)
            accounted.update(item.exercise_id for item in filled)
        blocks.append(
            _reported(reported, None if index is None else prescribed[index], filled)
        )

    # Whatever the report never touched, in the order it was prescribed. A
    # block whose exercises turned up inside some *other* reported block is
    # not repeated here: `accounted` is what says so, and repeating it would
    # count the same rounds twice on both volume axes.
    for index, block in enumerate(prescribed):
        if index in matched:
            continue
        items = _assumed_items(block, accounted)
        if not items:
            continue
        accounted.update(item.exercise_id for item in items)
        blocks.append(
            workouts.PerformedBlock(
                items=items,
                rounds=block.block.rounds,
                rounds_source="assumed",
                rest=block.block.rest,
                rest_source="assumed",
            )
        )
    return tuple(blocks)


def _paired(
    prescribed: Sequence[workouts.PrescribedBlock],
    reported: Sequence[PerformedBlock],
) -> list[tuple[PerformedBlock, int | None]]:
    """Which prescribed block each reported one is talking about, by position.

    **Matched by exercise, never by position.** A report is prose about the
    parts that differed, so the blocks in it are the ones the user talked
    about and their order is the order they talked about them -- neither is a
    map onto the prescribed positions. Matched by position, a user who
    mentions the third block and nothing else has their words filed under the
    first one.

    `None` is a reported block naming nothing that was prescribed, which is a
    substitution or something done on the end. Nothing in it can be `assumed`
    and nothing is filled into it.

    One definition, two readers: `to_performed` fills the gaps from what this
    returns, and `validate` checks an `assumed` value against it. Written
    twice, the day they disagreed a number would be refused against one block
    and written from another.
    """
    matched: set[int] = set()
    pairs: list[tuple[PerformedBlock, int | None]] = []
    for block in reported:
        named = {item.exercise_id for item in block.items}
        index = next(
            (
                position
                for position, candidate in enumerate(prescribed)
                if position not in matched
                and any(item.exercise_id in named for item in candidate.block.items)
            ),
            None,
        )
        if index is not None:
            matched.add(index)
        pairs.append((block, index))
    return pairs


def _reported(
    block: PerformedBlock,
    source: workouts.PrescribedBlock | None,
    filled: tuple[workouts.PerformedItem, ...] = (),
) -> workouts.PerformedBlock:
    """One block the user talked about, with its unmentioned siblings after it.

    A number the document left null is the prescribed one from `source`, the
    block `_paired` matched it to, marked `assumed`. `validate` has refused a
    null with nothing behind it, so reaching one here is a caller that skipped
    it.

    The filled items go last rather than in the prescribed order: the reported
    ones are what the user said they did, and reading them first is reading
    the report.
    """
    planned = (
        {} if source is None
        else {item.exercise_id: item for item in _assumed_items(source, set())}
    )

    def said(value: int | None, provenance: str | None, prescribed: int | None) -> tuple[int, str]:
        if value is not None and provenance is not None:
            return value, provenance
        if prescribed is None:
            raise LogRejected("a value left out has no prescription to be filled from")
        return prescribed, "assumed"

    def item_of(item: PerformedItem) -> workouts.PerformedItem:
        if item.unit is not None and item.amount is not None and item.amount_source is not None:
            return workouts.PerformedItem(
                exercise_id=item.exercise_id,
                unit=item.unit,
                amount=item.amount,
                amount_source=item.amount_source,
                load_kg=item.load_kg,
                load_kg_source=item.load_kg_source,
            )
        was = planned.get(item.exercise_id)
        if was is None:
            raise LogRejected(
                f"{item.exercise_id}'s amount was left out and nothing prescribes it"
            )
        return workouts.PerformedItem(
            exercise_id=item.exercise_id,
            unit=was.unit,
            amount=was.amount,
            amount_source="assumed",
            load_kg=item.load_kg,
            load_kg_source=item.load_kg_source,
        )

    rounds, rounds_source = said(
        block.rounds, block.rounds_source, None if source is None else source.block.rounds
    )
    rest, rest_source = said(
        block.rest, block.rest_source, None if source is None else source.block.rest
    )
    return workouts.PerformedBlock(
        items=(*(item_of(item) for item in block.items), *filled),
        rounds=rounds,
        rounds_source=rounds_source,
        rest=rest,
        rest_source=rest_source,
        rpe=block.rpe,
    )


def _assumed_items(
    block: workouts.PrescribedBlock, accounted: set[str]
) -> tuple[workouts.PerformedItem, ...]:
    """The prescribed items nothing has accounted for yet, as performed.

    No load: a plan does not prescribe one, so there is nothing to assume.
    """
    return tuple(
        workouts.PerformedItem(
            exercise_id=item.exercise_id,
            unit="reps" if item.reps is not None else "seconds",
            amount=item.reps if item.reps is not None else item.seconds or 0,
            amount_source="assumed",
        )
        for item in block.block.items
        if item.exercise_id not in accounted
    )


def proposed(
    connection: sqlite3.Connection, performed: PerformedWorkout
) -> tuple[Exclusion, str] | tuple[None, None]:
    """The exclusion this report proposes, classified, with its re-test date.

    Classified here rather than at the writer, because `classify` reads the
    catalog and the writer takes an `Exclusion` that has already been through
    it. `validate` has run the same call and refused the value that does not
    resolve, so this one cannot fail -- it is asked twice because the answer,
    unlike the refusal, is needed at the write.
    """
    if performed.proposed_exclusion is None:
        return None, None
    return (
        exclusions.classify(connection, performed.proposed_exclusion.value),
        performed.proposed_exclusion.retest_date,
    )


# -- the renderer -------------------------------------------------------------
#
# ASCII, because an em dash reaches the Windows console as a replacement
# character. The documents keep their typography; output does not.


def render(
    connection: sqlite3.Connection,
    performed: PerformedWorkout,
    blocks: tuple[workouts.PerformedBlock, ...],
    flagged: tuple[Flag, ...],
) -> list[str]:
    """What was prescribed set against what was performed, with the deviations
    named and the provenance of anything that was assumed rather than said.

    The prescription is printed first and whole, because a deviation is only
    legible against the thing it deviates from. Then the performed workout,
    with `(assumed)` on every value the user did not actually give -- so a
    reader can see at a glance which numbers are theirs -- and the flags under
    the lines they are about.

    A flag about an exercise is printed **once**, under the first line about
    that exercise. An exercise can appear in two blocks -- the bar was picked
    up again later -- and a flag repeated under each occurrence is the same
    sentence twice, which is how the line that matters most in this output
    gets skipped.
    """
    lines: list[str] = []
    prescribed = (
        workouts.prescribed(connection, performed.workout_id)
        if performed.workout_id is not None
        else ()
    )
    names = _names(connection, performed, blocks, prescribed)
    column = max((len(name) for name in names.values()), default=0) + 2

    if performed.workout_id is None:
        lines.append("prescribed: nothing -- this workout was not planned")
    else:
        lines.append(f"prescribed (workout {performed.workout_id}):")
        for position, block in enumerate(prescribed, start=1):
            lines.append(
                f"  block {position} -- {block.block.rounds} rounds, "
                f"{block.block.rest}s rest"
            )
            for planned in block.block.items:
                amount = planned.reps if planned.reps is not None else planned.seconds
                unit = "reps" if planned.reps is not None else "seconds"
                lines.append(
                    f"    {names[planned.exercise_id]:<{column}}{amount} {unit}"
                )
    lines.append("")

    lines.append("performed:")
    about = _by_exercise(flagged)
    for position, done in enumerate(blocks, start=1):
        lines.append(
            f"  block {position} -- {done.rounds} rounds{_said(done.rounds_source)}, "
            f"{done.rest}s rest{_said(done.rest_source)}"
            + (f", RPE {done.rpe:g}" if done.rpe is not None else "")
        )
        for item in done.items:
            lines.append(f"    {names[item.exercise_id]:<{column}}{_performance(item)}")
            for flag in about.pop(item.exercise_id, ()):
                lines.append(f"      ! {flag.says}")
    lines.append("")

    for flag in flagged:
        if flag.about is None:
            lines.append(f"! {flag.says}")
    lines.append(f"said: {performed.report}")
    if performed.proposed_exclusion is not None:
        granularity, _ = proposed(connection, performed)
        assert granularity is not None  # `proposed` pairs both or neither
        lines.append(
            f"proposes excluding {granularity.granularity} "
            f"{granularity.value!r} until "
            f"{performed.proposed_exclusion.retest_date}: "
            f"{performed.proposed_exclusion.why}"
        )
    return lines


def _names(
    connection: sqlite3.Connection,
    performed: PerformedWorkout,
    blocks: tuple[workouts.PerformedBlock, ...],
    prescribed: tuple[workouts.PrescribedBlock, ...],
) -> dict[str, str]:
    """The catalog's own name for every id either phase mentions.

    Every id here has already passed validation, so an id the catalog does not
    have is a bug rather than a bad document -- but it is stated as one anyway
    rather than falling back to printing the id, which would render a workout
    naming an exercise nobody has as though it were fine.
    """
    ids = {item.exercise_id for block in blocks for item in block.items}
    ids.update(
        item.exercise_id for block in prescribed for item in block.block.items
    )
    names: dict[str, str] = {}
    for exercise_id in ids:
        found = catalog.exercise(connection, exercise_id)
        if found is None:
            raise LogError(f"no such exercise: {exercise_id!r}")
        names[exercise_id] = found.name
    return names


def _by_exercise(flagged: tuple[Flag, ...]) -> dict[str, tuple[Flag, ...]]:
    """The flags about each exercise, in the order they were raised.

    The caller **consumes** this map as it prints, which is what makes each
    flag appear once. It is built fresh per render for that reason.
    """
    grouped: dict[str, list[Flag]] = {}
    for flag in flagged:
        if flag.about is not None:
            grouped.setdefault(flag.about, []).append(flag)
    return {exercise_id: tuple(found) for exercise_id, found in grouped.items()}


def _said(source: str) -> str:
    """Nothing for a number the user gave, and a word for one nobody did.

    Marked rather than annotated everywhere: `reported` is the ordinary case
    and a workout every line of which ends in `(reported)` is a workout nobody
    reads to the end of. What has to stand out is the value the system
    supplied on the user's behalf.
    """
    return "" if source == "reported" else f" ({source})"


def _performance(item: workouts.PerformedItem) -> str:
    load = "" if item.load_kg is None else f" @ {item.load_kg:g} kg"
    return (
        f"{item.amount} {item.unit}{_said(item.amount_source)}{load}"
        + ("" if item.load_kg_source is None else _said(item.load_kg_source))
    )
