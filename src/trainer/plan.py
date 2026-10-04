"""A plan as a document: its wire shape, the rules it must pass, and how it prints."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from trainer.engine import admissible, budget, catalog, config, constraints, duration
from trainer.engine import exclusions as exclusion_state
from trainer.engine import mesocycles, state, workouts
from trainer.engine.exclusions import Exclusion


class PlanError(RuntimeError):
    """What arrived is not a plan: bad JSON, a missing field, a block the
    vocabulary cannot express. A statement about the document."""


class PlanRejected(RuntimeError):
    """The violations, raised: what a caller does with them when there is
    nobody to hand them back to. A statement about the workout -- an exercise
    that is not admissible today, a plan that does not fit the time, an
    exercise written twice -- never about the document."""



@dataclass(frozen=True)
class Violation:
    """One rule this plan breaks, named so that a reader can say which."""

    rule: str
    says: str


SHAPE = "shape"
"""What refuses a document that is not a plan at all. `validate` never returns it: no rule can be read off such a document, and it is refused before any of them runs."""

DUPLICATES = "duplicates"
ADMISSIBLE = "admissible"
BUDGET = "budget"
PREFERENCES = "preferences"
REFUSED = "refused"
UNTRAINED = "untrained"
SLOTS = "slots"
CYCLES = "cycles"
COUNTS_AS = "counts as"

TOLERANCE_MIN = 5
"""How far either side of the minutes asked for a plan may land: 45 accepts 40 to 50."""


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


class AdaptedPlan(WorkoutPlan):
    """A workout adapted for today: the plan, which of the cycle's workouts it stands for, and what to tell the user."""

    counts_as: int = Field(
        description=(
            "The number of the cycle's workout, among those still to do, that "
            "this one takes the place of."
        ),
    )
    note: str = Field(
        description=(
            "Empty, unless something they asked for could not be done, as an "
            "exercise under an exclusion: then one sentence saying so, with "
            "its re-test date."
        ),
    )


class Mesocycle(BaseModel):
    """A workout for each slot of the cycle, how many cycles it is repeated for, and why (ADR-0008)."""

    model_config = ConfigDict(extra="forbid")

    workouts: list[WorkoutPlan] = Field(
        min_length=1,
        description="One workout per slot of the cycle, in the split's order.",
    )
    cycles: int = Field(ge=1, description="How many times the whole cycle is repeated.")
    why: str = Field(
        min_length=1, description="Why this many cycles, in one sentence."
    )

    @field_validator("why")
    @classmethod
    def _said(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("why is blank; say why this many cycles")
        return value


@dataclass(frozen=True)
class Refusal:
    """A plan the user turned down, and what they said turning it down.

    It belongs to the negotiation rather than to the run that was refused, and
    travels into every later run of it (ADR-0007). The newest one is kept
    whole; the ones before it keep their exercise ids and their words, because
    the ids are all a later plan needs in order not to repeat one.
    """

    because: str
    exercise_ids: tuple[str, ...]
    plan: WorkoutPlan | None = None


def exercise_ids(plan: WorkoutPlan) -> tuple[str, ...]:
    """Every exercise the plan names, in the order it prescribes them."""
    return tuple(item.exercise_id for block in plan.blocks for item in block.items)


def turned_down(
    refusals: Sequence[Refusal], plan: WorkoutPlan, because: str
) -> tuple[Refusal, ...]:
    """The negotiation's refusals with this one on the end, the earlier ones narrowed to their ids."""
    return (
        *(dataclasses.replace(refusal, plan=None) for refusal in refusals),
        Refusal(because=because, exercise_ids=exercise_ids(plan), plan=plan),
    )


@dataclass(frozen=True)
class Adapting:
    """The mesocycle an adaptation starts from, and what the user said of this workout (ADR-0008 item 6).

    Nothing here binds the plan: the user's words do, within the exclusions.
    """

    mesocycle: int
    served_after: int
    """Workouts performed when it was asked: the day it is today's workout for."""

    slot: int
    """The cycle's workout the rotation has due today."""

    cycle: tuple[WorkoutPlan, ...]
    """Every workout of the mesocycle, in the cycle's order."""

    split: tuple[str, ...]
    """The groups each of the cycle's workouts trains, in the same order."""

    still: tuple[int, ...]
    """The cycle's workouts not yet performed: the ones this one may count as."""

    usual_minutes: int
    usual_equipment: tuple[str, ...]
    said: str = ""
    named: tuple[str, ...] = ()
    """What a door named outright, as the terminal's `--minutes`: binding, unlike the words."""

    retests: tuple[str, ...] = ()
    """Each exclusion in force with its re-test date, as the user is told it."""

    def __post_init__(self) -> None:
        # A checkpoint reads tuples back as lists.
        for name in ("cycle", "split", "still", "usual_equipment", "named", "retests"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    @property
    def workout(self) -> WorkoutPlan:
        return self.cycle[self.slot - 1]


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
    after it (ADR-0001). Offered rather than imposed, the way the methodology's ranges
    are: the agent has `allocate` and may divide the time differently, and
    nothing here checks that it did not."""

    preferences: tuple[str, ...] = ()
    """Exercise ids the user would rather not do; a plan names one only with a `despite` row."""

    refusals: tuple[Refusal, ...] = ()
    """Every plan this negotiation has already turned down, oldest first. The
    new one has to differ from each of them; how is the agent's business."""

    adapting: Adapting | None = None
    """Set when this is an adaptation: accepted, it is today's serving and the mesocycle stays."""

    goal: str | None = None
    """The methodology column the plan is made for; `None` when nothing is declared."""


@dataclass(frozen=True)
class MesocycleRefusal:
    """A mesocycle the user turned down: the newest whole, earlier ones as their ids per slot."""

    because: str
    exercise_ids: tuple[tuple[str, ...], ...]
    mesocycle: Mesocycle | None = None


@dataclass(frozen=True)
class Changing:
    """The active mesocycle a change rewrites, where its count stands, and what the user wants changed."""

    mesocycle: int
    accepted_after: int
    """Kept by the new one, so its cycles go on counting from the same place."""

    cycle: int
    current: Mesocycle
    said: str


@dataclass(frozen=True)
class Continuing:
    """The mesocycle whose cycles have all been performed, and the next one's direction."""

    mesocycle: int
    ended: Mesocycle
    direction: mesocycles.Direction | None = None
    """Written by the supervisor before the planner runs (ADR-0014), and kept with the mesocycle accepted."""


@dataclass(frozen=True)
class MesocycleRequest:
    """One `Request` per slot of the cycle, in the split's order, and what the negotiation turned down."""

    slots: tuple[Request, ...]
    refusals: tuple[MesocycleRefusal, ...] = ()
    changing: Changing | None = None
    continuing: Continuing | None = None


def mesocycle_turned_down(
    refusals: Sequence[MesocycleRefusal], mesocycle: Mesocycle, because: str
) -> tuple[MesocycleRefusal, ...]:
    """The negotiation's refusals with this one on the end, the earlier ones narrowed to their ids."""
    return (
        *(dataclasses.replace(refusal, mesocycle=None) for refusal in refusals),
        MesocycleRefusal(
            because=because,
            exercise_ids=tuple(exercise_ids(workout) for workout in mesocycle.workouts),
            mesocycle=mesocycle,
        ),
    )


@dataclass(frozen=True)
class Asked:
    """What a door was told, before anything was derived from it.

    The terminal's flags and the chat's words both arrive as this, and
    `requested` turns it into a `Request`. Every field is optional because
    every field has somewhere to come from when nobody names it: the declarations
    hold the equipment and the cap, and the performed workouts say where
    the rotation is. The chat names almost none of them, which is the point --
    *"what am I doing today?"* is an empty `Asked`.
    """

    equipment: tuple[str, ...] = ()
    minutes: int | None = None
    workout: int | None = None
    """Which workout of the declared cycle to plan, overriding the rotation."""

    groups: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    """Movement patterns or loaded joints to keep out of this one plan, in the
    catalog's own vocabulary. Not persisted, and never an exercise id."""

    avoid: tuple[str, ...] = ()
    """Exercise ids the user would rather not do."""


@dataclass(frozen=True)
class Assembled:
    """The request, and the rotation position it was derived from if it was."""

    request: Request
    rotation: state.Rotation | None


def requested(
    connection: sqlite3.Connection,
    today: str,
    asked: Asked = Asked(),
    declared: config.TrainingConfig | None = None,
) -> Assembled:
    """Today's request, out of what a door was told and what the project knows.

    The one place a `Request` is built, called by the terminal and by the chat.
    `Request`'s own docstring carries why it is one object; this is why it is
    one *function*: assembled at each door, the two drift and a plan comes back
    checked against a request nobody made.

    What can be derived is never asked for. Equipment falls back to what is
    declared, the minutes to the declared cap, and the groups to the workout
    the performed workouts put the rotation at. With nothing declared there is
    nothing to fall back to, and that is reported as the state it is --
    `config.NoTrainingConfig`, naming the bot -- rather than as a complaint
    about a flag nobody typed.
    """
    # First, and before anything is read off the catalog. Every part of a
    # request is classified against the enriched vocabulary sooner or later --
    # `classify` reads the movement patterns, `admissible_set` refuses outright
    # -- and against an unenriched catalog the honest answer is *nobody has
    # enriched it yet*, not a correct value reported as a typo. The chat is why
    # it is here rather than at each door: `trainer plan` checked this itself
    # since ticket 3.2, and the bot had no equivalent, so a machine that had
    # imported but not enriched was promised minutes of planning and then given
    # a run that fell over inside a tool call.
    if not catalog.values(connection, "movement_pattern"):
        raise admissible.AdmissibleError(admissible.UNENRICHED_MESSAGE)

    if declared is None:
        declared = config.declared(connection)
    if asked.workout is not None and asked.groups:
        raise PlanRejected(
            "a named workout takes its groups from the declared split, so "
            "naming groups as well asks for two different workouts; give one "
            "or the other"
        )

    equipment = _equipment(connection, asked.equipment, declared)
    minutes = _minutes(asked.minutes, declared)
    turn = constraints.rotated(
        connection, declared, _named(asked.workout, declared, asked.groups)
    )

    todays = constraints.constraining_today(
        connection,
        today,
        budget_min=minutes,
        groups=turn.groups,
        given=[exclusion_state.classify(connection, value) for value in asked.exclude],
    )
    return Assembled(
        request=Request(
            equipment=equipment,
            budget_min=todays.budget_min,
            exclusions=todays.exclusions,
            groups=todays.groups,
            allocation=_divided(todays.budget_min, todays.groups),
            preferences=_preferred(connection, asked.avoid),
            goal=None if declared is None else declared.goal,
        ),
        rotation=turn.where,
    )


def mesocycle_requested(
    connection: sqlite3.Connection,
    today: str,
    asked: Asked = Asked(),
    declared: config.TrainingConfig | None = None,
) -> MesocycleRequest:
    """One request per slot, each the one that slot would get asked on its own; `declared` defaults to the file's.

    A mesocycle needs the split, so with nothing declared that is the state
    reported.
    """
    if declared is None:
        declared = config.load(connection)
    return MesocycleRequest(
        slots=tuple(
            requested(
                connection,
                today,
                dataclasses.replace(asked, workout=slot, groups=()),
                declared,
            ).request
            for slot in range(1, declared.cycle_length + 1)
        )
    )


def adaptation_requested(
    connection: sqlite3.Connection,
    today: str,
    asked: Asked = Asked(),
    said: str = "",
) -> Request:
    """This workout's request: the whole catalog under today's exclusions, with the mesocycle as a starting point.

    What was named on `asked` narrows it -- equipment, minutes, exclusions --
    and nothing else does: the mesocycle's groups, the declared equipment and
    the usual time are the planner's to read, not limits.
    """
    if asked.groups or asked.workout is not None:
        raise PlanRejected(
            "an adaptation chooses which of the cycle's workouts it stands for "
            "itself; name groups or a workout to plan one outright"
        )
    found = mesocycles.today(connection)
    kept = mesocycles.active(connection)
    assert kept is not None, "`today` found a mesocycle"
    declared = config.load(connection)
    equipment = (
        _equipment(connection, asked.equipment, declared)
        if asked.equipment
        else tuple(catalog.values(connection, "equipment"))
    )
    minutes = declared.duration_cap_min if asked.minutes is None else asked.minutes
    todays = constraints.constraining_today(
        connection,
        today,
        budget_min=minutes,
        given=[exclusion_state.classify(connection, value) for value in asked.exclude],
    )
    return Request(
        equipment=equipment,
        budget_min=minutes,
        exclusions=todays.exclusions,
        preferences=_preferred(connection, asked.avoid),
        goal=declared.goal,
        adapting=Adapting(
            mesocycle=found.mesocycle,
            served_after=found.performed,
            slot=found.slot,
            cycle=tuple(from_prescribed(slot) for slot in kept.slots),
            split=tuple(
                ", ".join(declared.groups_for(slot)) for slot in range(1, found.slots + 1)
            ),
            still=tuple(slot for slot in range(1, found.slots + 1) if slot not in found.done),
            usual_minutes=declared.duration_cap_min,
            usual_equipment=declared.equipment,
            said=said,
            named=(
                *([] if asked.minutes is None else [f"{asked.minutes} minutes"]),
                *([] if not asked.equipment else [f"only {', '.join(equipment)}"]),
                *(f"no {value}" for value in asked.exclude),
                *(f"rather not {one}" for one in asked.avoid),
            ),
            retests=tuple(
                f"{one.granularity} {one.value} until "
                f"{exclusion_state.retest_date(connection, one, today)}"
                for one in todays.exclusions
            ),
        ),
    )


def change_requested(
    connection: sqlite3.Connection, today: str, said: str, asked: Asked = Asked()
) -> MesocycleRequest:
    """A mesocycle's request carrying the active one it rewrites for the cycles left."""
    found = mesocycles.today(connection)
    active = mesocycles.active(connection)
    assert active is not None, "`today` found a mesocycle"
    return dataclasses.replace(
        mesocycle_requested(connection, today, asked),
        changing=Changing(
            mesocycle=active.id,
            accepted_after=active.accepted_after,
            cycle=found.cycle,
            current=Mesocycle(
                workouts=[from_prescribed(slot) for slot in active.slots],
                cycles=active.cycles,
                why=active.why,
            ),
            said=said,
        ),
    )


def next_requested(connection: sqlite3.Connection, today: str) -> MesocycleRequest:
    """A mesocycle's request carrying the one that has run all its cycles."""
    ended = mesocycles.finished(connection)
    if ended is None:
        raise mesocycles.MesocycleError(
            "the active mesocycle has not finished its cycles, or none was accepted"
        )
    return dataclasses.replace(
        mesocycle_requested(connection, today),
        continuing=Continuing(
            mesocycle=ended.mesocycle.id,
            ended=Mesocycle(
                workouts=[from_prescribed(slot) for slot in ended.mesocycle.slots],
                cycles=ended.mesocycle.cycles,
                why=ended.mesocycle.why,
            ),
        ),
    )


def _equipment(
    connection: sqlite3.Connection,
    asked: tuple[str, ...],
    declared: config.TrainingConfig | None,
) -> tuple[str, ...]:
    """Today's equipment: what was named, or what the user declared having.

    Named wins, because the declaration is what you own and today is where you
    are -- a hotel room with nothing in it is the case that distinction exists
    for.

    Checked against the catalog **here**, where the catalog is open, and not
    left to the admissible set further in. A declared value the catalog lacks would
    otherwise surface from inside the graph run, where the chat can only say
    *something went wrong* -- and a declaration nobody can plan against is a
    state with a fix, in the vocabulary the data actually holds.
    """
    chosen = tuple(dict.fromkeys(asked)) if asked else None
    if chosen is None:
        if declared is None:
            raise config.NoTrainingConfig()
        chosen = declared.equipment
    for value in chosen:
        catalog.check_value(connection, "equipment", value)
    return chosen


def _minutes(asked: int | None, declared: config.TrainingConfig | None) -> int:
    """Today's budget: what was asked for, or the cap that was declared; asking for more than the cap is refused."""
    if declared is None:
        if asked is None:
            raise config.NoTrainingConfig()
        return asked
    if asked is None:
        return declared.duration_cap_min
    return constraints.within_the_cap(asked, declared)


def _named(
    workout: int | None,
    declared: config.TrainingConfig | None,
    given: tuple[str, ...],
) -> tuple[str, ...]:
    """The groups a door named: off the declared split by position, or by hand.

    A named workout is the override. Where the rotation is gets derived from
    the performed workouts, so naming a workout is for saying *no, plan the
    leg day again* -- not for telling the engine something it can count.

    Repeats are dropped rather than refused. Asking for legs twice is a slip
    with one obvious reading, and left in it makes the even division sum to
    half a workout: arithmetic nobody wrote, blamed on whoever said it twice.
    """
    if workout is None:
        return tuple(dict.fromkeys(given))
    if declared is None:
        raise config.NoTrainingConfig()
    try:
        return declared.groups_for(workout)
    except IndexError as error:
        raise PlanRejected(str(error)) from error


def _divided(minutes: int, groups: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    """The minutes over the groups, evenly.

    Offered rather than imposed, the way the methodology's ranges are (ADR-0001): the
    agent has `allocate` and may divide the time on any proportions it can
    argue for. Even shares because this layer has no grounds for any other
    split -- *60-40 on two groups* is what one workout might look like, not a
    law, and it means nothing the moment a workout trains three.
    """
    if not groups:
        return ()
    share = 1 / len(groups)
    allocated = budget.allocate(minutes, {group: share for group in groups})
    return tuple((group, allocated[group]) for group in groups)


def _preferred(connection: sqlite3.Connection, avoid: tuple[str, ...]) -> tuple[str, ...]:
    """The exercises the user would rather not do, checked against the catalog.

    A mistyped id is the worst possible outcome here: the preference is
    silently unenforced, the plan comes back with the thing in it, and the typo
    also travels to the model as something it must not prescribe. Read from the
    data, the way every other vocabulary in this project is.
    """
    for exercise_id in avoid:
        if catalog.exercise(connection, exercise_id) is None:
            raise PlanRejected(
                f"no such exercise: {exercise_id!r}. A preference names an "
                "exercise by id, the way a plan does"
            )
    return tuple(dict.fromkeys(avoid))


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


def parse_adapted(text: str) -> AdaptedPlan:
    """An adapted workout out of JSON, or a shape error naming the field it choked on."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlanError(f"that is not JSON: {error}") from error
    try:
        return AdaptedPlan.model_validate(raw)
    except ValidationError as error:
        raise PlanError(_shape(error)) from error


def parse_mesocycle(text: str) -> Mesocycle:
    """A mesocycle out of JSON, or a shape error naming the field it choked on."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlanError(f"that is not JSON: {error}") from error
    try:
        return Mesocycle.model_validate(raw)
    except ValidationError as error:
        raise PlanError(_shape(error).replace("a plan", "a mesocycle", 1)) from error


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
) -> tuple[Violation, ...]:
    """Every rule this plan breaks, in the order that makes the message useful.

    Duplicates first, then admissibility, so an id the catalog does not have
    is named as an id rather than as an exercise that could not be costed.
    The clock is skipped when either of those failed: `plan_seconds` cannot
    cost a plan naming one exercise twice, and *it cannot be costed* is the
    wrong sentence for a mistake already named. The last two are about the
    request rather than the catalog, and come after for that reason.

    Nothing is trimmed. ADR-0001.
    """
    found = [
        broken
        for broken in (
            _no_exercise_twice(blocks),
            _every_id_admissible(connection, blocks, request),
        )
        if broken is not None
    ]
    if not found and request.adapting is None:
        # An adaptation answers to what the user said, which no rule reads:
        # its time and its groups are the planner's to choose.
        found.extend(
            broken
            for broken in (
                _inside_the_budget(connection, blocks, request),
                every_group_trained(connection, plan, request),
            )
            if broken is not None
        )
    found.extend(
        broken
        for broken in (
            _preferences_acknowledged(plan, request),
            _not_a_plan_already_refused(plan, request),
            _counts_as_one_still_to_do(plan, request),
        )
        if broken is not None
    )
    return tuple(found)


def validate_mesocycle(
    connection: sqlite3.Connection, mesocycle: Mesocycle, request: MesocycleRequest
) -> tuple[Violation, ...]:
    """Every rule the mesocycle breaks: each workout against its own slot, then the whole.

    A workout is checked as the plan for its slot would be (`validate`), and
    its violations say which slot. Across the mesocycle only the count of
    workouts and a refusal already made; how many cycles and why is the
    agent's, and the shape already refuses none and a blank reason (ADR-0001).
    """
    wanted, given = len(request.slots), len(mesocycle.workouts)
    if given != wanted:
        return (
            Violation(
                SLOTS,
                f"the mesocycle has {given} workout{'s' if given != 1 else ''} and "
                f"the cycle has {wanted} slots: one workout per slot, in the "
                "split's order",
            ),
        )
    found: list[Violation] = []
    changing = request.changing
    if changing is not None and mesocycle.cycles < changing.cycle:
        found.append(
            Violation(
                CYCLES,
                f"cycles is {mesocycle.cycles} and the mesocycle is in cycle "
                f"{changing.cycle}: a change keeps the count, so cycles is the "
                f"total and at least {changing.cycle}",
            )
        )
    for slot, (workout, asked) in enumerate(zip(mesocycle.workouts, request.slots), start=1):
        try:
            broken = validate(connection, to_blocks(workout), asked, workout)
        except PlanError as error:
            broken = (Violation(SHAPE, str(error)),)
        found.extend(
            Violation(violation.rule, f"workout {slot}: {violation.says}")
            for violation in broken
        )
    for refused in request.refusals:
        same = (
            mesocycle == refused.mesocycle
            if refused.mesocycle is not None
            else tuple(exercise_ids(workout) for workout in mesocycle.workouts)
            == refused.exercise_ids
        )
        if same:
            found.append(
                Violation(
                    REFUSED,
                    "this is a mesocycle the user has already turned down. "
                    "Propose a different one: they said no, and saying it "
                    "again is not an answer",
                )
            )
            break
    return tuple(found)


def refusal(violations: Sequence[Violation]) -> str:
    """The violations as one message, in the order the rules decided them."""
    return "\n".join(violation.says for violation in violations)


def _no_exercise_twice(blocks: duration.Plan) -> Violation | None:
    try:
        duration.check_plan(blocks)
    except duration.DurationError as error:
        return Violation(DUPLICATES, str(error))
    return None


def _every_id_admissible(
    connection: sqlite3.Connection, blocks: duration.Plan, request: Request
) -> Violation | None:
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
        return None

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
    return Violation(ADMISSIBLE, "\n".join(lines))


def every_group_trained(
    connection: sqlite3.Connection, plan: WorkoutPlan, request: Request
) -> Violation | None:
    """Every group asked for has an exercise whose primary muscles are in it, unless today's admissible set has none."""
    prescribed = set(exercise_ids(plan))
    available = admissible.admissible_set(
        connection,
        request.exclusions,
        request.equipment,
        request.budget_min,
        request.groups,
    )
    untouched = []
    for group in request.groups:
        muscles = set(admissible.muscles_of([group]))
        trainable = [e for e in available if set(e.primary_muscles) & muscles]
        if trainable and not any(e.id in prescribed for e in trainable):
            untouched.append(group)
    if not untouched:
        return None
    return Violation(
        UNTRAINED,
        f"it trains nothing for {', '.join(untouched)}, which today's admissible "
        "set can train: give each group asked for at least one exercise whose "
        "primary muscles are in it",
    )


def _preferences_acknowledged(plan: WorkoutPlan, request: Request) -> Violation | None:
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
        return Violation(
            PREFERENCES,
            "the plan says the user refused exercises they did not:\n"
            + "\n".join(f"  {exercise_id}" for exercise_id in invented)
            + "\n`despite` names exercises they actually said no to, and is "
            "empty otherwise.",
        )

    if not request.preferences:
        return None

    spoken = {said.exercise_id for said in plan.despite}
    unspoken = [
        item.exercise_id
        for block in plan.blocks
        for item in block.items
        if item.exercise_id in request.preferences and item.exercise_id not in spoken
    ]
    if unspoken:
        return Violation(
            PREFERENCES,
            "the plan prescribes exercises the user said they would rather not "
            "do, without saying why:\n"
            + "\n".join(f"  {exercise_id}" for exercise_id in unspoken)
            + "\nA preference is not an exclusion -- propose it again if there "
            "is a reason, and add a row to the plan's `despite` for it: "
            '{"exercise_id": "...", "why": "..."}. The field is `why`; '
            "`reason` belongs to a block and is not accepted here.",
        )
    return None


def _not_a_plan_already_refused(plan: WorkoutPlan, request: Request) -> Violation | None:
    """Asked again, it has to answer differently -- from every plan the negotiation turned down.

    The weakest possible reading of *proposes again* -- not the same document
    -- and deliberately so: what makes the second plan better is the agent's
    business, and a rule about *how* different it must be would be this file
    deciding method. What it refuses is the one answer that is certainly not a
    second proposal.

    A refusal the negotiation has narrowed to its exercise ids is compared on
    those, which is the weakest reading still available once the document is
    gone -- and coarser than the newest one's: a plan naming the same
    exercises in the same order is refused however different the rest of it
    is. That is what an evening of memory costs, against the one step this
    rule used to have.
    """
    for refusal in request.refusals:
        if refusal.plan is not None:
            if plan != refusal.plan:
                continue
        elif exercise_ids(plan) != refusal.exercise_ids:
            continue
        return Violation(
            REFUSED,
            "this is a plan the user has already turned down. Propose a "
            "different one: they said no, and saying it again is not an "
            "answer",
        )
    return None


def _counts_as_one_still_to_do(plan: WorkoutPlan, request: Request) -> Violation | None:
    if request.adapting is None:
        return None
    still = request.adapting.still
    if not isinstance(plan, AdaptedPlan):
        return Violation(
            COUNTS_AS, "an adapted workout says which of the cycle's workouts it counts as"
        )
    if plan.counts_as in still:
        return None
    return Violation(
        COUNTS_AS,
        f"it counts as workout {plan.counts_as}, which is not one still to do "
        f"this cycle: those are {', '.join(str(one) for one in still)}",
    )


def window(budget_min: int) -> tuple[int, int]:
    """The fewest and the most minutes a plan built to `budget_min` may run."""
    return max(budget_min - TOLERANCE_MIN, 0), budget_min + TOLERANCE_MIN


def _inside_the_budget(
    connection: sqlite3.Connection, blocks: duration.Plan, request: Request
) -> Violation | None:
    spent = duration.plan_duration(connection, blocks)
    asked = request.budget_min
    floor, ceiling = window(asked)
    if spent > ceiling:
        return Violation(
            BUDGET,
            f"the plan runs {spent} min against a budget of {asked} min, "
            f"{spent - ceiling} min over the {ceiling} it may run. It is not cut "
            "to fit: allocate the time first and build a shorter plan",
        )
    if spent < floor:
        return Violation(
            BUDGET,
            f"the plan runs {spent} min of the {asked} min asked for, "
            f"{floor - spent} min under the {floor} it has to reach. A plan is "
            f"built to the time, within {TOLERANCE_MIN} min either side: plan "
            "the time that was given",
        )
    return None


# -- the renderer -------------------------------------------------------------
#
# ASCII, because an em dash reaches the Windows console as a replacement
# character. The documents keep their typography; output does not.


@dataclass(frozen=True)
class ShownItem:
    """One prescribed exercise, under the catalog's own name, with whatever the user had said about it."""

    name: str
    prescription: str
    said: str | None = None
    last: state.Answer[float] | None = None
    """The load it was last performed with, beside a served workout; `None` beside a proposal."""


@dataclass(frozen=True)
class ShownBlock:
    """One block, costed: what it asks for and what it takes."""

    position: int
    rounds: int
    rest: int
    seconds: int
    reason: str
    items: tuple[ShownItem, ...]


@dataclass(frozen=True)
class Shown:
    """A plan with the catalog's names and the engine's costs filled in.

    What every rendering of a plan is built from. The terminal folds it into
    aligned ASCII and the chat into markup Telegram accepts, and neither of
    them names an exercise or costs a block a second time -- two renderings
    that each ask the engine would be two chances to disagree about what the
    workout is.
    """

    blocks: tuple[ShownBlock, ...]
    total_min: int
    budget_min: int
    note: str = ""
    """What an adapted workout tells the user it could not do; empty otherwise."""


def shown(
    connection: sqlite3.Connection,
    plan: WorkoutPlan,
    blocks: duration.Plan,
    budget_min: int,
    loads: bool = False,
) -> Shown:
    """The plan a reader is shown: names off the catalog, seconds off the engine.

    Block costs are exact seconds and the total is whole minutes rounded up:
    the two units differ on purpose. Rounding each block up would make the
    parts sum past a total the engine computed once from the exact seconds,
    and a reader who checks the arithmetic would find it wrong.
    """
    blocks = tuple(blocks)
    # Every name first, before anything is costed: both refuse an id the
    # catalog does not have, and `_name` is the one that says so as a plan
    # naming an exercise nobody has rather than as arithmetic that fell over.
    names = {
        item.exercise_id: _name(connection, item.exercise_id)
        for block in plan.blocks
        for item in block.items
    }
    acknowledged = {said.exercise_id: said.why for said in plan.despite}
    return Shown(
        blocks=tuple(
            ShownBlock(
                position=position,
                rounds=costed.rounds,
                rest=costed.rest,
                seconds=duration.plan_seconds(connection, [costed]),
                reason=shape.reason,
                items=tuple(
                    ShownItem(
                        name=names[item.exercise_id],
                        prescription=_prescription(item),
                        said=acknowledged.get(item.exercise_id),
                        last=(
                            state.last_performed_load(connection, item.exercise_id)
                            if loads
                            else None
                        ),
                    )
                    for item in shape.items
                ),
            )
            for position, (shape, costed) in enumerate(
                # `strict`, because these are two representations of one plan
                # and nothing in the types says so. Handed a mismatched pair,
                # `zip` would render the shorter of the two and show a partial
                # workout as if it were whole -- the failure the validator
                # exists to catch, arriving through the renderer instead.
                zip(plan.blocks, blocks, strict=True),
                start=1,
            )
        ),
        total_min=duration.plan_duration(connection, blocks),
        budget_min=budget_min,
        note=plan.note if isinstance(plan, AdaptedPlan) else "",
    )


def render(
    connection: sqlite3.Connection,
    plan: WorkoutPlan,
    blocks: duration.Plan,
    budget_min: int,
    loads: bool = False,
) -> list[str]:
    """The workout, as the terminal prints it."""
    reading = shown(connection, plan, blocks, budget_min, loads)
    # Widened to the longest name in this plan rather than fixed: the catalog
    # holds names past fifty characters, and a fixed column either wraps those
    # or pushes every prescription to the right of a page of blanks. The
    # catalog listing aligns its own columns the same way.
    column = max(len(item.name) for block in reading.blocks for item in block.items) + 2

    lines: list[str] = []
    for block in reading.blocks:
        lines.append(
            f"block {block.position} -- {block.rounds} rounds, {block.rest}s rest "
            f"-- {block.seconds // 60}:{block.seconds % 60:02d}"
        )
        for item in block.items:
            lines.append(f"  {item.name:<{column}}{item.prescription}{_last(item.last)}")
            if item.said is not None:
                # On its own line and marked, not folded into the block's
                # reason: this is the agent proposing something the user said
                # no to, and it has to be the thing they notice.
                lines.append(f"    ! you said no to this: {item.said}")
        lines.append(f"  why: {block.reason}")
        lines.append("")

    lines.append(f"total {reading.total_min} min of {reading.budget_min}")
    if reading.note:
        lines.append(f"note: {reading.note}")
    return lines


def _last(last: state.Answer[float] | None) -> str:
    if last is None:
        return ""
    if last.value is None:
        return "   last load: not recorded"
    return f"   last {last.value:g} kg"


def from_prescribed(blocks: Sequence[workouts.PrescribedBlock]) -> WorkoutPlan:
    """A kept workout in the wire shape, so it renders the way a proposed one does."""
    return WorkoutPlan(
        blocks=[
            PlanBlock(
                items=[
                    PlanItem(
                        exercise_id=item.exercise_id,
                        prescription=(
                            Prescription(unit="reps", amount=item.reps)
                            if item.reps is not None
                            else Prescription(unit="seconds", amount=item.seconds or 0)
                        ),
                    )
                    for item in prescribed.block.items
                ],
                rounds=prescribed.block.rounds,
                rest=prescribed.block.rest,
                reason=prescribed.reason,
            )
            for prescribed in blocks
        ]
    )


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
