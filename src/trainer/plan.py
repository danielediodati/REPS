"""A plan is a document: the shape it arrives in, the rules it has to pass,
and how it is printed.

The door session 4's agent will come out through, built and testable before
there is an agent. `trainer plan --from FILE` reads a plan somebody wrote by
hand, puts it through the same validator and the same renderer, and either
prints the workout or names the rule that refused it. No model and no network
anywhere in here.

**The shape is the wire shape, not the engine's.** `WorkoutPlan` is what a
model emits and what a JSON file holds; `duration.Block` and
`duration.BlockItem` are what the engine costs. The two are kept apart
deliberately: the engine gains no new type and learns nothing about how a plan
reaches it, and the fields the wire needs -- a block's `reason`, above all --
do not have to be defensible as something the costing formula reads.

**The validator rejects. It never repairs.** Three rules, and a plan that
fails any of them comes back as a rejection naming the rule, with nothing
trimmed and nothing re-asked. ADR-0001: a repaired plan hides from whoever
built it that they got the arithmetic wrong, and from session 4 on that
"whoever" is a model whose next plan would be built on the same mistake.

**Beside `trainer.cli`, never inside `engine/`**, for the reason
`trainer.tools` is: pydantic is a wire concern, and `test_engine_boundary.py`
keeps the engine free of every client's vocabulary.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

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
    reps: int | None = Field(
        default=None,
        description=(
            "How many repetitions, for work counted in reps. Exactly one of "
            "reps and seconds carries a value; the other is null."
        ),
    )
    seconds: int | None = Field(
        default=None,
        description=(
            "How long, for work counted in time -- a carry, a plank, a walk. "
            "Exactly one of reps and seconds carries a value; the other is null."
        ),
    )


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
    rounds: int
    rest: int
    reason: str = Field(min_length=1)


class WorkoutPlan(BaseModel):
    """The whole plan: blocks, in the order they are performed.

    Nothing else. What the plan was made *against* -- the equipment, the time,
    the exclusions -- is the request, and it is deliberately not carried here:
    a plan that declared its own budget could declare one it fits.
    """

    model_config = ConfigDict(extra="forbid")

    blocks: list[PlanBlock] = Field(min_length=1)


@dataclass(frozen=True)
class Request:
    """What the plan was asked for, and what it is checked against.

    Three fields today, all of them things `trainer admissible` already takes.
    Ticket 04 fills in the rest -- which workout of the split, the allocation
    over its groups, the preferences -- and this is the object it grows, so
    that the validator keeps checking against the request that was made rather
    than against arguments a caller assembled at the call site.
    """

    equipment: tuple[str, ...]
    budget_min: int
    exclusions: tuple[Exclusion, ...] = ()


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
                            reps=item.reps,
                            seconds=item.seconds,
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
    connection: sqlite3.Connection, blocks: duration.Plan, request: Request
) -> None:
    """The three rules, in the order that makes the message useful.

    Duplicates first, because the two rules after it both cost the plan and
    `plan_seconds` refuses a duplicate on its own -- reached that way it would
    arrive as a costing failure rather than as the rule it is. Then
    admissibility, so an id the catalog does not have is named as an id rather
    than as an exercise that could not be costed. The clock last, because it
    is the only one of the three that is about the plan as a whole.

    Nothing is trimmed and nothing is re-asked. ADR-0001.
    """
    _no_exercise_twice(blocks)
    _every_id_admissible(connection, blocks, request)
    _inside_the_budget(connection, blocks, request)


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
            connection, request.exclusions, request.equipment, request.budget_min
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
        )
        lines.append(f"  {exercise_id}: {why or 'not in the admissible set'}")
    raise PlanRejected("\n".join(lines))


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
    return f"{item.reps} reps" if item.reps is not None else f"{item.seconds} seconds"
