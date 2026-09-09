"""The tool surface: one set of definitions, registered behind two doors.

TRAINER.md's `admissible_set`, `remaining_budget`, `allocate`,
`pattern_history`, `adherence_history`, `last_performed_load` and
`compare_variants`, plus the three this project found it needed --
`search_exercises`, `volume_deficit`, `unreported_workouts` -- each of which
unpacks its arguments, opens the connection, calls the library function and
shapes the result for a caller that speaks JSON. No validation of its own, no
decision, no new logic: `tests/test_engine_boundary.py` exists precisely so
that the CLI, this surface and a direct call stay doors onto the same code
rather than copies of it.

**One definition, two registrations.** `trainer mcp` serves these to a generic
client and session 4's agent loops over the same objects. The alternative --
a set of MCP tools and a set of agent tools that happen to wrap the same
library -- diverges at the first tool added to one door and not the other, and
the divergence is invisible until the agent asks for something the inspector
cannot show. `TOOLS` is the single enumeration; a door registers what is in it
and nothing else.

**What each door still owns.** Its transport, and its own error type. This
module states a failure as a `ToolFailure` in the words the caller should
read; `mcp_server` turns that into the SDK's `ToolError`, and the agent will
turn it into a tool result the model can act on. What neither door owns is
*which* failures exist or how they are worded.

**Beside `trainer.cli`, never inside `engine/`.** The engine is the pure
library the boundary test keeps free of any knowledge of a client, and `mcp`
is in its forbidden list next to `click` for the same reason: a convention
that is not enforced is a convention forgotten in a month.

**What is not here.** `active_conclusions` is in TRAINER.md's tool surface and
has nothing to wrap yet -- it needs `conclusions`, in session 8. Wrapping a
function that does not exist is not this module's job. `adherence_history` was
here in that sentence too until session 5 gave it rows to read.

**Nothing here writes.** Every tool on this surface is a question, and that is
a rule and not an observation: if the model can call the write, the model
decides when the database changes -- the single door disappears, the validator
becomes optional, and an interrupted run leaves half a workout behind. The
agent emits and the engine writes (ROADMAP.md § Session 5).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from trainer.engine import (
    admissible,
    budget,
    catalog,
    config,
    database,
    duration,
    graph,
    migrations,
    muscle_groups,
    state,
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
    duration.DurationError,
    ExclusionError,
    graph.GraphError,
    migrations.MigrationError,
    muscle_groups.MuscleGroupError,
    state.StateError,
)
"""Every failure the library states in words. Each is re-raised as a
`ToolFailure` so it reaches the caller as a result marked failed, rather than
as a traceback that takes the door down with it -- the same job
`cli.reported()` does for the terminal.

`ConfigError` is among them because a window is counted in cycles and only
`training.toml` says how long one is. Its own wording is kept -- it names the
file and the example to copy -- rather than being restated as a state the
engine invented."""


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
    """The exercises today's equipment, the time available, the muscle groups
    being trained and the exclusions given leave standing -- the space a plan
    is chosen inside.

    `equipment` names the catalog's own values (`barbell`, `body only`) and
    must hold at least one. `muscle_groups` names the groups this workout
    trains, from `chest`, `back`, `shoulders`, `arms`, `legs`, `core`: give
    them, because the whole space is several times larger than any one
    workout needs and every exercise you are handed you are also paying to
    re-read on every later turn. Each exclusion is `{"granularity": "pattern"
    | "joint", "value": ...}`; an exclusion never names an exercise id.
    """
    given = [
        Exclusion(
            granularity=str(item.get("granularity", "")),
            value=str(item.get("value", "")),
        )
        for item in exclusions or []
    ]
    with reported(), opened() as connection:
        found = admissible.admissible_set(
            connection, given, equipment, budget_min, muscle_groups or ()
        )
    return [_exercise(exercise) for exercise in found]


def remaining_budget(partial_plan: list[dict[str, Any]], budget_min: int) -> int:
    """How many minutes are left once `partial_plan` is committed.

    A plan is a list of blocks, each `{"items": [{"exercise_id": ..., "reps":
    ...} | {"exercise_id": ..., "seconds": ...}], "rounds": N, "rest": SECONDS}`.
    Negative when the plan is already over, on purpose: how far over is what
    the caller has to act on, and this engine never trims a plan to fit.
    """
    plan = [_block(raw) for raw in partial_plan]
    with reported(), opened() as connection:
        return budget.remaining_budget(connection, plan, budget_min)


def allocate(minutes: int, proportions: dict[str, float]) -> dict[str, int]:
    """Divide a workout's minutes among the muscle groups it trains.

    `proportions` maps a muscle group to its share and has to sum to 1: they
    are refused rather than normalised, because scaling a typo produces a
    different plan that runs the full time and trains something else. The
    group names are the six in the committed mapping.
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
    compare_variants,
)
"""The surface, enumerated once.

Every door registers exactly this. A test asserting the same names a second
time would be a second place to forget them, so what the doors are checked
against is this tuple rather than a copy of it.

Not every agent is offered all of them -- session 5's logging agent reads what
was trained and never plans, so it has no use for `allocate`. Which subset a
given agent sees is `agent.surface()`'s to decide; what may exist at all is
decided here.
"""
