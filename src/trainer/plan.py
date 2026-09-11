"""A plan as a document: its wire shape, the rules it must pass, and how it prints."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trainer.engine import admissible, catalog, duration
from trainer.engine.exclusions import Exclusion


class PlanError(RuntimeError):
    """What arrived is not a plan: bad JSON, a missing field, a block the
    vocabulary cannot express. A statement about the document."""


class PlanRejected(RuntimeError):
    """What arrived is a plan, and a rule refuses it. A statement about the
    workout: an exercise that is not admissible today, a plan that does not
    fit the time, an exercise written twice."""


# -- the shape ----------------------------------------------------------------


class Prescription(BaseModel):
    """How much of an exercise: an amount, and what it counts.

    One field and a unit rather than an optional `reps` beside an optional
    `seconds`. The engine's `BlockItem` has always refused both-or-neither --
    *"3 rounds of 10 reps of walking"* means nothing -- but *exactly one of
    these two is set* is a rule no schema can state, so a model held to that
    schema is being asked to guess. Written this way the wrong state cannot be
    expressed, which is worth more than any number of sentences telling a
    model not to write it. It also survives strict structured output, where
    every property must be present and *absent* stops being available as a
    way to say "not this one".
    """

    model_config = ConfigDict(extra="forbid")

    unit: Literal["reps", "seconds"]
    amount: int


class PlanItem(BaseModel):
    """One exercise inside a block, and how it is prescribed.

    `extra="forbid"` here and below: a misspelled field that is quietly
    ignored is a prescription the author believes they wrote and did not, and
    what comes back is a different workout that validates. The same reason
    `config._KEYS` refuses an unrecognised key rather than skipping it.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: str = Field(
        description=(
            "The exercise's id, character for character as `admissible_set` "
            "returned it."
        ),
    )
    prescription: Prescription


class PlanBlock(BaseModel):
    """One or more exercises, the rounds, and the rest after each round.

    `reason` is required, and it is the field that makes this shape the
    agent's rather than the engine's: TRAINER.md has the agent give its
    reasons for what it prescribes, and a plan with nowhere to put them turns
    those reasons into prose beside the plan -- which is the thing structured
    output exists to stop.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[PlanItem] = Field(min_length=1)
    rounds: int = Field(
        description=(
            "How many times the block is performed from the top. One exercise "
            "is straight sets, two is a superset, more is a circuit."
        ),
    )
    rest: int = Field(
        description=(
            "Seconds rested after each round -- 90 means a minute and a half. "
            "Seconds, never milliseconds and never minutes."
        ),
    )
    reason: str = Field(min_length=1)
    """`rounds` and `rest` carry their units in the schema because a bare
    integer does not.

    An observed run wrote `rest: 60000` -- a minute, in milliseconds -- which
    costed out at 3,007 minutes against a fifteen-minute budget. The plan was
    correctly refused and the run was lost, over a unit nobody had told the
    model. The engine's `Block` has said *seconds after each round* since it
    was written; what it had never done is say it anywhere the model reads.
    """


class Acknowledgement(BaseModel):
    """One exercise the user said no to, and why it is in the workout anyway."""

    model_config = ConfigDict(extra="forbid")

    exercise_id: str
    why: str = Field(min_length=1)


class WorkoutPlan(BaseModel):
    """The whole plan: blocks in the order they are performed, and whatever in
    them the user had already said no to.

    What the plan was made *against* -- the equipment, the time, the
    exclusions -- is the request, and it is deliberately not carried here: a
    plan that declared its own budget could declare one it fits.
    """

    model_config = ConfigDict(extra="forbid")

    blocks: list[PlanBlock] = Field(min_length=1)
    despite: list[Acknowledgement] = Field(
        default_factory=list,
        description=(
            "Empty, unless the workout includes something the user said they "
            "would rather not do. One entry for each of those, saying why it "
            "is there anyway, so they can say no again."
        ),
    )
    """A preference is not an exclusion.

    An exclusion is safety and the engine removes it from the space; a
    preference is knowledge of the person, and TRAINER.md's fourth invariant
    is *nothing the user has refused -- and if it proposes it again, it says
    so and asks*. This list is what makes *says so* checkable: prescribing one
    without a row here is refused, and a row is a question the user answers by
    refusing the plan.

    **A list on the plan, not a field on every item**, which is where it
    started. Strict structured output puts every property on every object, so
    a per-item `despite` asked the model to decide *null, or a sentence* on
    every exercise in the workout -- and an observed run filled all eight of
    them, inventing refusals the user had never made. Asked once, about the
    plan, the empty answer is an empty list, which is a thing a model writes
    without being talked into it.
    """


@dataclass(frozen=True)
class Request:
    """What the plan was asked for, and what it is checked against.

    One object, assembled before the model is called, out of what the project
    already knows: which workout of the declared rotation this is, the groups
    it trains and how its minutes divide over them, today's equipment, the
    exclusions in force, what the user said they would rather not do, and --
    on a second pass -- the plan they just turned down.

    It is one object rather than a handful of arguments so that the validator
    checks against *the request that was made*. Assembled at each call site,
    the two would drift, and a plan would be checked against a request nobody
    asked for.
    """

    equipment: tuple[str, ...]
    budget_min: int
    exclusions: tuple[Exclusion, ...] = ()
    groups: tuple[str, ...] = ()
    """The muscle groups this workout trains. Empty is the whole space, which
    is what a caller who has not said which workout this is has asked for."""

    allocation: tuple[tuple[str, int], ...] = ()
    """Minutes per group, divided **before** the plan is built rather than cut
    after it (ADR-0001). Offered rather than imposed, the way the rest bands
    are: the agent has `allocate` and may divide the time differently, and
    nothing here checks that it did not."""

    preferences: tuple[str, ...] = ()
    """Exercise ids the user would rather not do; a plan names one only with a `despite` row."""

    refused: WorkoutPlan | None = None
    """A plan the user just turned down, on a second pass. The new one has to
    differ from it; how is the agent's business."""

    because: str = ""
    """What the user said when they turned it down; it reaches the model and no rule checks it."""


def parse(text: str) -> WorkoutPlan:
    """A plan out of JSON, or a shape error naming the field it choked on.

    Never a traceback: the author of a bad plan is a person editing a file
    today and a model emitting one tomorrow, and neither can act on a pydantic
    stack trace.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlanError(f"that is not JSON: {error}") from error

    try:
        return WorkoutPlan.model_validate(raw)
    except ValidationError as error:
        raise PlanError(_shape(error)) from error


def _shape(error: ValidationError) -> str:
    lines = ["that is not a plan:"]
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "the document"
        lines.append(f"  {where}: {problem['msg']}")
    return "\n".join(lines)


def to_blocks(plan: WorkoutPlan) -> tuple[duration.Block, ...]:
    """The wire shape, in the vocabulary the engine costs.

    Every refusal below is the engine dataclass's own -- reps and seconds both
    given or neither, a round count under one, a negative rest. Re-checking
    them here would be two definitions of what a block is, and the second one
    would be the one that drifts. The position is added because the engine's
    message is about an item and the author is looking at a file.
    """
    blocks: list[duration.Block] = []
    for position, block in enumerate(plan.blocks, start=1):
        try:
            blocks.append(
                duration.Block(
                    items=tuple(
                        duration.BlockItem(
                            exercise_id=item.exercise_id,
                            reps=_amount(item, "reps"),
                            seconds=_amount(item, "seconds"),
                        )
                        for item in block.items
                    ),
                    rounds=block.rounds,
                    rest=block.rest,
                )
            )
        except ValueError as error:
            raise PlanError(f"block {position}: {error}") from error
    return tuple(blocks)


# -- the validator ------------------------------------------------------------


def validate(
    connection: sqlite3.Connection,
    blocks: duration.Plan,
    request: Request,
    plan: WorkoutPlan,
) -> None:
    """The rules, in the order that makes the message useful.

    Duplicates first, because the two rules after it both cost the plan and
    `plan_seconds` refuses a duplicate on its own -- reached that way it would
    arrive as a costing failure rather than as the rule it is. Then
    admissibility, so an id the catalog does not have is named as an id rather
    than as an exercise that could not be costed. The clock last, because it
    is the only one of the three that is about the plan as a whole.

    The last two are about the request rather than the catalog, and they come
    after it for that reason: an id nobody has is not a preference violation,
    it is a typo, and saying so in the wrong order sends the reader looking in
    the wrong place.

    Nothing is trimmed. ADR-0001.
    """
    _no_exercise_twice(blocks)
    _every_id_admissible(connection, blocks, request)
    _inside_the_budget(connection, blocks, request)
    _preferences_acknowledged(plan, request)
    _not_the_plan_that_was_refused(plan, request)


def _no_exercise_twice(blocks: duration.Plan) -> None:
    try:
        duration.check_plan(blocks)
    except duration.DurationError as error:
        raise PlanRejected(str(error)) from error


def _every_id_admissible(
    connection: sqlite3.Connection, blocks: duration.Plan, request: Request
) -> None:
    """The set decides; `admissible.rejection` only explains.

    Asking each id whether it is admissible would make this a second reading
    of the same `WHERE`, and the day the two disagree the plan is checked
    against whichever one is wrong. So membership comes from `admissible_set`
    itself, and a reason is fetched only for the ids already known to be out.
    """
    inside = {
        exercise.id
        for exercise in admissible.admissible_set(
            connection,
            request.exclusions,
            request.equipment,
            request.budget_min,
            request.groups,
        )
    }
    offenders = [
        item.exercise_id
        for block in blocks
        for item in block.items
        if item.exercise_id not in inside
    ]
    if not offenders:
        return

    lines = ["the plan names exercises that are not admissible today:"]
    for exercise_id in offenders:
        why = admissible.rejection(
            connection,
            exercise_id,
            request.exclusions,
            request.equipment,
            request.budget_min,
            request.groups,
        )
        lines.append(f"  {exercise_id}: {why or 'not in the admissible set'}")
    raise PlanRejected("\n".join(lines))


def _preferences_acknowledged(plan: WorkoutPlan, request: Request) -> None:
    """Nothing the user refused -- unless the agent says why.

    TRAINER.md's fourth invariant is *nothing the user has refused; and if it
    proposes it again, it says so and asks*. Both halves are here: proposing
    one silently is refused, and proposing one with a sentence attached is
    allowed, printed prominently, and left for the user to turn down.

    Silence is the failure, not the choice. An agent that has read the history
    and thinks the user should revisit something is doing its job; one that
    slips it in among five other blocks is not.
    """
    invented = [
        said.exercise_id
        for said in plan.despite
        if said.exercise_id not in request.preferences
    ]
    if invented:
        # A refusal the user never made, which the renderer would otherwise
        # print back to them as their own words.
        raise PlanRejected(
            "the plan says the user refused exercises they did not:\n"
            + "\n".join(f"  {exercise_id}" for exercise_id in invented)
            + "\n`despite` names exercises they actually said no to, and is "
            "empty otherwise."
        )

    if not request.preferences:
        return

    spoken = {said.exercise_id for said in plan.despite}
    unspoken = [
        item.exercise_id
        for block in plan.blocks
        for item in block.items
        if item.exercise_id in request.preferences and item.exercise_id not in spoken
    ]
    if unspoken:
        raise PlanRejected(
            "the plan prescribes exercises the user said they would rather not "
            "do, without saying why:\n"
            + "\n".join(f"  {exercise_id}" for exercise_id in unspoken)
            + "\nA preference is not an exclusion -- propose it again if there "
            "is a reason, and put the reason in the item's `despite`."
        )


def _not_the_plan_that_was_refused(plan: WorkoutPlan, request: Request) -> None:
    """Asked again, it has to answer differently.

    The weakest possible reading of *proposes again* -- not the same document
    -- and deliberately so: what makes the second plan better is the agent's
    business, and a rule about *how* different it must be would be this file
    deciding method. What it refuses is the one answer that is certainly not a
    second proposal.
    """
    if request.refused is None:
        return
    if plan == request.refused:
        raise PlanRejected(
            "this is the plan that was just refused, unchanged. Propose a "
            "different one: the user said no, and saying it again is not an "
            "answer"
        )


def _inside_the_budget(
    connection: sqlite3.Connection, blocks: duration.Plan, request: Request
) -> None:
    spent = duration.plan_duration(connection, blocks)
    if spent > request.budget_min:
        raise PlanRejected(
            f"the plan runs {spent} min against a budget of {request.budget_min} "
            f"min, {spent - request.budget_min} min over. It is not cut to fit: "
            "allocate the time first and build a shorter plan"
        )


# -- the renderer -------------------------------------------------------------
#
# ASCII, because an em dash reaches the Windows console as a replacement
# character. The documents keep their typography; output does not.


def render(
    connection: sqlite3.Connection,
    plan: WorkoutPlan,
    blocks: duration.Plan,
    budget_min: int,
) -> list[str]:
    """The workout, as a person reads it.

    Block costs are exact, in `M:SS`, and the total is whole minutes rounded
    up: the two units differ on purpose. Rounding each block up would make the
    parts sum past a total the engine computed once from the exact seconds,
    and a reader who checks the arithmetic would find it wrong.
    """
    blocks = tuple(blocks)
    names = {
        item.exercise_id: _name(connection, item.exercise_id)
        for block in plan.blocks
        for item in block.items
    }
    # Widened to the longest name in this plan rather than fixed: the catalog
    # holds names past fifty characters, and a fixed column either wraps those
    # or pushes every prescription to the right of a page of blanks. The
    # catalog listing aligns its own columns the same way.
    column = max(len(name) for name in names.values()) + 2
    acknowledged = {said.exercise_id: said.why for said in plan.despite}

    lines: list[str] = []
    for position, (shape, costed) in enumerate(
        # `strict`, because these are two representations of one plan and
        # nothing in the types says so. Handed a mismatched pair, `zip` would
        # render the shorter of the two and print a partial workout as if it
        # were whole -- the failure this ticket forbids, arriving through the
        # renderer instead of through the validator.
        zip(plan.blocks, blocks, strict=True),
        start=1,
    ):
        seconds = duration.plan_seconds(connection, [costed])
        lines.append(
            f"block {position} -- {costed.rounds} rounds, {costed.rest}s rest "
            f"-- {seconds // 60}:{seconds % 60:02d}"
        )
        for item in shape.items:
            lines.append(f"  {names[item.exercise_id]:<{column}}{_prescription(item)}")
            said = acknowledged.get(item.exercise_id)
            if said is not None:
                # On its own line and marked, not folded into the block's
                # reason: this is the agent proposing something the user said
                # no to, and it has to be the thing they notice.
                lines.append(f"    ! you said no to this: {said}")
        lines.append(f"  why: {shape.reason}")
        lines.append("")

    lines.append(f"total {duration.plan_duration(connection, blocks)} min of {budget_min}")
    return lines


def _name(connection: sqlite3.Connection, exercise_id: str) -> str:
    """The catalog's own name for an id the plan already passed validation on.

    Unreachable through `trainer plan`, which validates first and rejects an
    unknown id there. It states the id anyway rather than falling back to
    printing it, because the alternative is not a rendered line: `plan_seconds`
    below refuses the same id a moment later, and the failure would arrive as
    a costing error about a plan whose real problem is that it names an
    exercise nobody has.
    """
    found = catalog.exercise(connection, exercise_id)
    if found is None:
        raise PlanError(f"no such exercise: {exercise_id!r}")
    return found.name


def _prescription(item: PlanItem) -> str:
    return f"{item.prescription.amount} {item.prescription.unit}"


def _amount(item: PlanItem, unit: str) -> int | None:
    """The count, for the unit it is counted in, and `None` for the other.

    `BlockItem` keeps two fields because costing reads them differently -- reps
    become seconds at a tempo, seconds are already seconds -- and it is the one
    definition of what a block holds. This is the only place the two shapes
    meet.
    """
    return item.prescription.amount if item.prescription.unit == unit else None
