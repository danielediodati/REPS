"""The engine's read-only tool surface, defined once and served by the agents and `trainer mcp`."""

from __future__ import annotations

import inspect
import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date
from typing import Any, get_type_hints

from pydantic import BaseModel, TypeAdapter

from trainer.engine import (
    admissible,
    budget,
    catalog,
    config,
    constraints,
    database,
    duration,
    graph,
    mesocycles,
    methodology,
    migrations,
    muscle_groups,
    state,
    workouts,
)
from trainer.engine.exclusions import Exclusion, ExclusionError

INSTRUCTIONS = """\
The REPS engine: a deterministic library over an exercise catalog and the
training state. It answers questions and never decides how to train.

`admissible_set` is the space -- an exercise outside what it returns cannot be
prescribed. `remaining_budget` and `allocate` are arithmetic over the time
available; neither cuts a plan that does not fit. `compare_variants` says what
two exercises are like and whether the curated graph calls them the same
movement, or one of them easier. `search_exercises` goes from a phrase to the
exercises that could be it, and answers nothing rather than guessing.

`pattern_history`, `last_performed_load`, `adherence_history`, `volume_deficit`
and `unreported_workouts` read what has actually been trained. They answer
*"I don't know"* where nothing has been recorded, which is an answer and not a
failure: a movement nobody has trained is a fact to plan around.
`prescribed_workout` is what one workout asked for, which is the thing a report
is a deviation from.

None of these writes anything. The engine records a workout; a tool never does.
"""


class ToolFailure(RuntimeError):
    """A tool call that cannot be answered, stated in words for the caller.

    One exception type for the whole surface, so a door translates once
    instead of enumerating the engine's error classes a second time.
    """


_ENGINE_ERRORS = (
    admissible.AdmissibleError,
    budget.BudgetError,
    catalog.CatalogError,
    config.ConfigError,
    constraints.ConstraintError,
    duration.DurationError,
    ExclusionError,
    graph.GraphError,
    mesocycles.MesocycleError,
    methodology.MethodologyError,
    migrations.MigrationError,
    muscle_groups.MuscleGroupError,
    state.StateError,
    workouts.WorkoutError,
)
"""Every failure the library states in words. Each is re-raised as a
`ToolFailure` so it reaches the caller as a result marked failed, rather than
as a traceback that takes the door down with it -- the same job
`cli.reported()` does for the terminal.

`ConfigError` is among them because a window is counted in cycles and only
the declarations say how long one is. Its own wording is kept -- it names the
bot as the fix -- rather than being restated as a state the engine invented."""


@contextmanager

def opened() -> Iterator[sqlite3.Connection]:
    """The connection every tool reads through, with its preconditions named.

    A missing database, a database behind this checkout's migrations and an
    empty catalog are states rather than caller errors, and each has a command
    that fixes it. Left to fail on their own the first two arrive as `no such
    table: exercises` and the third as an answer -- an empty admissible set, or
    an id the catalog does not have -- which names neither the state nor the
    way out of it.
    """
    path = database.database_path()
    if not path.exists():
        raise ToolFailure(
            f"there is no database at {path}; run `trainer db init` and "
            "`trainer db import` first"
        )
    with closing(database.connect(path)) as connection:
        current = migrations.applied_version(connection)
        latest = migrations.latest_version(migrations.discover())
        if current < latest:
            raise ToolFailure(
                f"the database is at schema version {current} and this "
                f"checkout is at {latest}; run `trainer db init`"
            )
        if catalog.count(connection) == 0:
            raise ToolFailure("the catalog is empty; run `trainer db import` first")
        yield connection


@contextmanager

def reported() -> Iterator[None]:
    """Turn a stated library failure into a tool failure.

    The catalog being unenriched arrives through here rather than from
    `opened()`: it is the engine that decides which fields a given call reads,
    and a precondition checked by whoever opens the connection would refuse
    `pattern_history`, which reads no enrichment at all.
    """
    try:
        yield
    except _ENGINE_ERRORS as error:
        raise ToolFailure(str(error)) from error
    except sqlite3.Error as error:
        raise ToolFailure(f"the database could not be used: {error}") from error


# -- shaping for the wire -----------------------------------------------------
#
# Dataclasses out, dicts in. The engine's types are frozen dataclasses holding
# tuples, which JSON has no word for, so each is turned into the plainest thing
# that carries the same fields. Nothing is computed, renamed or dropped on the
# way through: a client reading this is reading the engine's own answer.


def _exercise(found: catalog.Exercise) -> dict[str, Any]:
    return asdict(found) | {
        "primary_muscles": list(found.primary_muscles),
        "secondary_muscles": list(found.secondary_muscles),
        "instructions": list(found.instructions),
        "images": list(found.images),
    }


def _enrichment(found: catalog.Enrichment) -> dict[str, Any]:
    return asdict(found) | {"loaded_joints": list(found.loaded_joints)}


def _answer(answer: state.Answer[Any]) -> dict[str, Any]:
    """An `Answer`, with its "I don't know" kept legible.

    `known` travels as its own field rather than being left implicit in a null
    value: an agent reading this mid-loop has to be able to tell *nobody has
    trained this yet* from a field that happens to be empty, and that
    distinction is the whole reason these two functions exist this early.
    """
    value = answer.value
    return {
        "about": answer.about,
        "known": answer.known,
        "value": asdict(value) if is_dataclass(value) and not isinstance(value, type) else value,
    }


def _block(raw: Mapping[str, Any]) -> duration.Block:
    """One block, out of what a JSON client can express.

    Every error here is the dataclass's own -- `Block` and `BlockItem` validate
    themselves in `__post_init__`, and re-checking their fields on the way in
    would be this module growing the logic it exists not to have.
    """
    try:
        items = tuple(
            duration.BlockItem(
                exercise_id=str(item["exercise_id"]),
                reps=item.get("reps"),
                seconds=item.get("seconds"),
            )
            for item in raw["items"]
        )
        return duration.Block(items=items, rounds=raw["rounds"], rest=raw["rest"])
    except (KeyError, TypeError, ValueError) as error:
        raise ToolFailure(f"that is not a block: {error}") from error


# -- the tools ----------------------------------------------------------------


def admissible_set(
    equipment: list[str],
    budget_min: int,
    muscle_groups: list[str] | None = None,
    exclusions: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """The exercises today's equipment, the time available and the muscle
    groups being trained leave standing -- the space a plan is chosen inside.

    The exclusions in force today are applied whether or not you name any:
    `exclusions` adds to them for this one call. Each is `{"granularity":
    "pattern" | "joint", "value": ...}`, and an exclusion never names an
    exercise id.

    `equipment` names the catalog's own values (`barbell`, `body only`) and
    must hold at least one. `budget_min` over the declared cap is refused
    rather than answered, because a workout that
    long is one the declaration says never happens. `muscle_groups` names what
    this workout trains, as the brief gives it: groups (`arms`) or muscles
    (`biceps`). Give them, because the whole space is several times larger
    than any one workout needs and every exercise you are handed you are also
    paying to re-read on every later turn.
    """
    given = [
        Exclusion(
            granularity=str(item.get("granularity", "")),
            value=str(item.get("value", "")),
        )
        for item in exclusions or []
    ]
    with reported(), opened() as connection:
        today = constraints.constraining_today(
            connection,
            date.today().isoformat(),
            budget_min=budget_min,
            groups=muscle_groups or (),
            given=given,
        )
        found = admissible.admissible_set(
            connection, today.exclusions, equipment, today.budget_min, today.groups
        )
    return [_exercise(exercise) for exercise in found]


def remaining_budget(partial_plan: list[dict[str, Any]], budget_min: int) -> int:
    """How many minutes are left once `partial_plan` is committed.

    A plan is a list of blocks, each `{"items": [{"exercise_id": ..., "reps":
    ...} | {"exercise_id": ..., "seconds": ...}], "rounds": N, "rest": SECONDS}`.
    Negative when the plan is already over. A plan is accepted when this
    lands within 5 minutes either side of zero: 45 minutes asked accepts
    anything from 5 left to 5 over. Nothing is trimmed or padded to fit.
    """
    plan = [_block(raw) for raw in partial_plan]
    with reported(), opened() as connection:
        return budget.remaining_budget(connection, plan, budget_min)


def allocate(minutes: int, proportions: dict[str, float]) -> dict[str, int]:
    """Divide a workout's minutes among the muscle groups it trains.

    `proportions` maps a group or muscle of this workout to its share of the whole, **as a
    decimal number**: `{"chest": 0.49, "arms": 0.51}`. Never as a fraction. An
    observed run wrote `{"chest": 22/45, "arms": 23/45}` -- the minutes this
    brief had just handed it, over the budget -- and JSON has no arithmetic,
    so the provider refused the call before it reached this tool and the whole
    run was lost with it. The two units meeting here is what invites it: the
    brief speaks minutes and this asks for shares.

    They have to sum to 1, and are refused rather than normalised, because
    scaling a typo produces a different plan that runs the full time and
    trains something else. The names are the ones the brief gives for
    this workout.
    """
    with reported():
        return budget.allocate(minutes, proportions)


def pattern_history(pattern: str, cycles: int) -> dict[str, Any]:
    """What the state has recorded for one movement pattern, over `cycles`.

    The window is a **cycle** -- one complete rotation through the workouts
    being trained -- never a week. Nothing writes this state until workouts are
    logged, so today the answer comes back with `known: false`, which is an
    answer: nobody has trained this pattern yet.
    """
    with reported(), opened() as connection:
        return _answer(state.pattern_history(connection, pattern, cycles))


def last_performed_load(exercise_id: str) -> dict[str, Any]:
    """The load this exercise was last performed with, if it ever was.

    `known: false` means no load has been recorded for a valid exercise. An id
    the catalog does not have is a tool failure instead, so a typo never reads
    as *"you have never done this"*.
    """
    with reported(), opened() as connection:
        return _answer(state.last_performed_load(connection, exercise_id))


def search_exercises(text: str, limit: int = 20) -> dict[str, Any]:
    """The exercises a plain-language phrase could be naming.

    Every word has to appear somewhere in the row, and the words may land in
    different fields: `"dumbbell bench"` is dumbbells **and** benching,
    `"cable chest"` is the cable exercises that train the chest. The fields
    searched are the catalog's own -- name, equipment, category, primary
    muscles, movement pattern.

    A phrase that matches nothing comes back with `total: 0` and no exercises.
    There is no nearest match and no dropped word: an id you did not ask for
    reads exactly like the one you did, and it is the id that gets prescribed.

    `total` is how many there were before `limit`, so a listing that stops
    short still says how much it stopped short of.
    """
    with reported(), opened() as connection:
        found = catalog.candidates(connection, text, limit=limit)
    return {
        "total": found.total,
        "exercises": [_exercise(exercise) for exercise in found.exercises],
    }


def adherence_history(cycles: int) -> dict[str, Any]:
    """What became of the workouts of the last `cycles` cycles.

    Three counts and no percentage: `performed` is what was done, `unreported`
    is prescribed workouts a later one overtook with no report ever filed, and
    `unplanned` is training nobody prescribed -- which is training all the
    same. An unreported workout is **never** counted as adherence: assuming a
    silent workout happened inflates the record at exactly the moment training
    stopped.

    `known: false` means the window holds nothing at all, which is *"nobody has
    trained yet"* and not zero-percent adherence.
    """
    with reported(), opened() as connection:
        return _answer(state.adherence_history(connection, cycles))


def volume_deficit(cycles: int) -> list[dict[str, Any]]:
    """Planned against performed volume, on both axes.

    Largest deficit first **within each axis**, pattern rows and then muscle
    rows: a round counts once per pattern and once per primary muscle, so the
    two are not on one scale and ranking them against each other would be
    arithmetic on different units. Read the list to the end -- the largest
    muscle-axis deficit is below every pattern row, however small.

    Volume is **rounds performed**. Every round counts whole to the exercise's
    movement pattern and whole to each of its primary muscles; nothing is
    divided, and a block of two exercises for four rounds is four rounds of
    each.

    Both axes in one answer, because neither catches the other's failure: a leg
    day of calf raises shows up per pattern, an arm day of nothing but curls
    only per muscle, since biceps, triceps and forearms are all `isolation`.

    A negative deficit is training nobody planned. The number absorbs four
    different mechanisms -- a substitution, a cut for time, a workout stopped
    early, a workout skipped -- and does not claim to know which it was.

    A workout still to do is **not** in here. A prescription that has been
    neither performed nor overtaken by a later workout has not been missed, and
    counting it would have you making up volume that is already scheduled.
    """
    with reported(), opened() as connection:
        found = state.volume_deficit(connection, cycles)
    return [
        {
            "axis": short.axis,
            "key": short.key,
            "cycles": short.cycles,
            "planned": short.planned,
            "performed": short.performed,
            "deficit": short.deficit,
        }
        for short in found
    ]


def unreported_workouts() -> list[dict[str, Any]]:
    """The prescribed workouts a later one has overtaken with no report.

    A statement of fact, oldest first: *"there is a prescribed workout from
    twelve days ago with no report"*. It decides nothing -- whether to ask the
    user about it is yours to judge, and reading this closes nothing and
    assumes nothing happened.

    Empty is the normal state. A plan emitted this morning is not in here; it
    is a workout still to do.
    """
    today = date.today().isoformat()
    with reported(), opened() as connection:
        found = state.unreported(connection, today)
    return [asdict(waiting) for waiting in found]


def prescribed_workout(workout_id: int) -> dict[str, Any]:
    """What one workout asked for: the blocks in the order they were to be
    done, the exercises in them by id **and** by name, and the reason each
    block was there.

    This is the thing a report is a deviation from, so it is also the closed
    set an exercise the user names should be resolved against first: ten
    exercises with their catalog names beside their ids, rather than eight
    hundred. Reach for `search_exercises` only when nothing here can be what
    they meant -- which is exactly the case where something was substituted.

    `state` is `prescribed` or `performed`. A workout already reported is
    still readable, and reading it changes nothing; what it cannot take is a
    second report.

    A workout id nobody has is a failure naming it, never an empty plan --
    which would read as *the workout was prescribed and asked for nothing*.
    """
    with reported(), opened() as connection:
        found = workouts.workout(connection, workout_id)
        if found is None:
            raise ToolFailure(
                f"there is no workout {workout_id}; `unreported_workouts` "
                "lists the prescribed workouts still waiting for a report"
            )
        blocks = workouts.prescribed(connection, workout_id)
        return {
            "workout_id": found.id,
            "state": found.state,
            "prescribed_on": found.prescribed_on,
            "blocks": [
                {
                    "rounds": block.block.rounds,
                    "rest": block.block.rest,
                    "reason": block.reason,
                    "items": [
                        _prescribed_item(connection, item) for item in block.block.items
                    ],
                }
                for block in blocks
            ],
        }


def _prescribed_item(
    connection: sqlite3.Connection, item: duration.BlockItem
) -> dict[str, Any]:
    """One prescribed exercise, with the catalog's own name beside its id.

    The name is here because this tool exists to be matched against prose:
    *"the bench"* is resolved by reading `Dumbbell Bench Press`, and an id is
    not a thing anybody says out loud. The id beside it is what gets written,
    and it is the one that has to be copied character for character.
    """
    found = catalog.exercise(connection, item.exercise_id)
    return {
        "exercise_id": item.exercise_id,
        "name": found.name if found is not None else None,
        "unit": "reps" if item.reps is not None else "seconds",
        "amount": item.reps if item.reps is not None else item.seconds,
    }


def compare_variants(id_a: str, id_b: str) -> dict[str, Any]:
    """Two exercises side by side, and what the curated graph says about them.

    Each side carries its movement pattern, the joints it loads, the stability
    it demands and what it costs to set up. `same_movement` is true when both
    belong to one variant group -- *the Arnold and the military press are the
    same pattern, to the engine they are interchangeable*. `easier` names the
    id that is a regression of the other, or is null when neither is.

    An id the catalog does not have is a failure naming that id, never a
    comparison of two blanks that reads as *these two have nothing in common*.
    """
    with reported(), opened() as connection:
        found = graph.compare(connection, id_a, id_b)
    return {
        "a": _enrichment(found.a),
        "b": _enrichment(found.b),
        "same_movement": found.same_movement,
        "easier": found.easier,
        "summary": found.summary,
    }


TOOLS: tuple[Callable[..., Any], ...] = (
    admissible_set,
    remaining_budget,
    allocate,
    pattern_history,
    last_performed_load,
    search_exercises,
    adherence_history,
    volume_deficit,
    unreported_workouts,
    prescribed_workout,
    compare_variants,
)
"""The surface, enumerated once.

Every door registers exactly this. A test asserting the same names a second
time would be a second place to forget them, so what the doors are checked
against is this tuple rather than a copy of it.

Not every graph is offered all of them -- the logger reads what was trained
and never plans, so it has no use for `allocate`. Which subset a given graph
sees is that graph's to decide; what may exist at all is decided here.
"""


# -- how a model calls them ---------------------------------------------------
#
# The surface above is a set of Python functions. What follows is everything
# between a model and one of them: the definition it is offered as, the
# arguments it comes back with checked against the types that definition was
# derived from, and the answer trimmed to what this door reads. It lives here
# rather than beside any one graph because both subgraphs and `trainer mcp`
# reach the same functions, and a second copy of the derivation would be the
# one that drifts.


CALL_BUDGET = 12
"""Tool calls one run may make before its graph stops offering tools; `--call-budget` overrides it."""


class SurfaceError(RuntimeError):
    """A door asked for a tool that does not exist. About the code, never about the user."""


@dataclass(frozen=True)
class Call:
    """One tool call the model asked for."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Result:
    """What one tool answered, on its way back to the model."""

    call_id: str
    name: str
    content: str
    failed: bool = False


def schema(tool: Callable[..., Any]) -> dict[str, Any]:
    """One tool definition, derived from the function rather than restated.

    `mcp_server.py` gets its schemas from the SDK reading the same signatures;
    this is the same derivation for the other door. Hand-written schemas here
    would be a second definition -- and the one
    that drifts, because nothing would fail when it did.

    Provider-neutral: name, description, parameters. The envelope a given API
    wants around that is the adapter's business.
    """
    hints = get_type_hints(tool)
    properties: dict[str, Any] = {}
    required: list[str] = []
    definitions: dict[str, Any] = {}
    for name, parameter in inspect.signature(tool).parameters.items():
        built = TypeAdapter(hints[name]).json_schema()
        # A `$ref` resolves from the root of the schema document, and the root
        # here is `parameters`. Left where pydantic puts them -- inside the
        # property -- the definitions an enum or a model-typed parameter needs
        # sit one level too deep and every reference to them dangles. No
        # parameter is typed that way today; the day one is, the provider
        # rejects the definition with nothing in this file to explain it.
        definitions.update(built.pop("$defs", {}))
        properties[name] = built
        if parameter.default is inspect.Parameter.empty:
            required.append(name)

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    if definitions:
        parameters["$defs"] = definitions
    return {
        "name": tool.__name__,
        "description": inspect.getdoc(tool) or "",
        "parameters": parameters,
    }


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A pydantic model's schema as strict mode accepts it: every property required, no extras."""
    built = model.model_json_schema()

    def require_everything(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node.setdefault("additionalProperties", False)
            for value in node.values():
                require_everything(value)
        elif isinstance(node, list):
            for item in node:
                require_everything(item)

    require_everything(built)
    return built


def registered(asked_by: str, names: Sequence[str]) -> tuple[Callable[..., Any], ...]:
    """The tool functions one agent asks for, out of the shared surface.

    A name that `TOOLS` does not have is a `SurfaceError` rather than a
    silently shorter surface: these lists are the one place a tool can be
    misspelled, and a logger quietly missing the tool it resolves
    substitutions with would look like a model that chose not to search.

    Each graph names its own list beside the nodes that offer it -- this is
    the guard on all of them, and it is the half that must not be copied.
    """
    defined = {tool.__name__: tool for tool in TOOLS}
    missing = [name for name in names if name not in defined]
    if missing:
        raise SurfaceError(
            f"the {asked_by} asks for {', '.join(missing)}, and the "
            f"tools defined are {', '.join(defined)}"
        )
    return tuple(defined[name] for name in names)


def execute(
    call: Call, offered: Sequence[Callable[..., Any]], keeps: Sequence[str]
) -> Result:
    """Run one call: what the model got wrong comes back as a failed result, anything else propagates."""
    import pydantic

    def failed(sentence: str) -> Result:
        return Result(call_id=call.id, name=call.name, content=sentence, failed=True)

    found = next((tool for tool in offered if tool.__name__ == call.name), None)
    if found is None:
        # The model asked for a tool nobody offered *it* -- which includes a
        # tool that exists on the other door. Its mistake, not ours, so it goes
        # back as a result it can recover from.
        named = ", ".join(tool.__name__ for tool in offered)
        return failed(f"there is no tool called {call.name!r}; the tools are {named}")

    try:
        arguments = _fitted(found, call.arguments)
    except pydantic.ValidationError as error:
        return failed(f"{call.name} was given arguments that do not fit: {error}")
    except KeyError as error:
        return failed(f"{call.name} takes no argument called {error}")

    try:
        answer = found(**arguments)
    except ToolFailure as error:
        return failed(str(error))
    except TypeError as error:
        # An argument left out, or given twice. The shapes are checked above,
        # so what is left is the call itself not fitting the signature.
        return failed(f"{call.name} cannot be called that way: {error}")
    return Result(call_id=call.id, name=call.name, content=_serialised(answer, keeps))


def _fitted(tool: Callable[..., Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    """The model's arguments, against the types the schema was derived from.

    Reached by exactly the mistake a model makes: `exclusions` given as a list
    of strings rather than of `{granularity, value}` objects satisfies the
    signature and reaches the tool body, where it comes apart as an
    `AttributeError` on a string -- a traceback, no record, and a paid-for run
    thrown away over something the model could have corrected next turn.

    Checked against `get_type_hints`, which is what `schema()` derives the
    definitions from, so what is enforced here and what the model was told are
    the same declaration read twice rather than two declarations.
    """
    hints = get_type_hints(tool)
    fitted: dict[str, Any] = {}
    for name, value in arguments.items():
        if name not in hints:
            raise KeyError(name)
        fitted[name] = TypeAdapter(hints[name]).validate_python(value)
    return fitted


EXERCISE_FIELDS = frozenset(declared.name for declared in fields(catalog.Exercise))
"""Every field of a catalog record, read from the dataclass rather than listed a second time."""


def _serialised(answer: Any, keeps: Sequence[str]) -> str:
    """The engine's answer, in the dialect the tool definitions promised.

    JSON rather than `repr`: the docstrings the model reads describe
    `known: false` and `{"granularity": "pattern"}`, and Python would hand
    back `'known': False`. A model translating between two dialects mid-loop
    is one more thing that can go wrong for no reason at all.
    """
    return json.dumps(_trimmed(answer, keeps), default=str)


def _trimmed(answer: Any, keeps: Sequence[str]) -> Any:
    """Every exercise record, cut to the fields this door reads; every envelope around one, left whole.

    A catalog field the caller does not keep -- `name` above all, which a
    model shown both strings copied into `exercise_id` -- reaches it under no
    key at all. A key that is not a catalog field is nobody's to drop.
    """
    return _cut(answer, tuple(keeps), EXERCISE_FIELDS - set(keeps))


def _cut(answer: Any, keeps: tuple[str, ...], hidden: frozenset[str]) -> Any:
    if isinstance(answer, list):
        return [_cut(item, keeps, hidden) for item in answer]
    if isinstance(answer, dict):
        if _an_exercise(answer):
            return {key: value for key, value in answer.items() if key in keeps}
        return {
            key: _cut(value, keeps, hidden)
            for key, value in answer.items()
            if key not in hidden
        }
    return answer


def _an_exercise(answer: Mapping[str, Any]) -> bool:
    """A catalog record, and not an envelope that happens to share a field name with one."""
    return "id" in answer and set(answer) <= EXERCISE_FIELDS
