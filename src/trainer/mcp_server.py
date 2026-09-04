"""The engine, exposed as MCP tools. A wrapper, and nothing else.

Five tools -- `admissible_set`, `remaining_budget`, `allocate`,
`pattern_history` and `last_performed_load` -- each of which unpacks its
arguments, opens the connection, calls the library function and shapes the
result for the wire. No validation of its own, no new shaping beyond what MCP's
content types require, no decision. `tests/test_engine_boundary.py` exists
precisely so that the CLI, this module and a direct call stay three doors onto
the same code rather than three copies of it.

**Beside `trainer.cli`, never inside `engine/`.** The engine is the pure library
that guard keeps free of any knowledge of a client, and `mcp` is in its
forbidden list next to `click` for the same reason: a convention that is not
enforced is a convention forgotten in a month.

**Why this early.** TRAINER.md pulls MCP in ahead of where the roadmap first
has it, on the bet that it costs little and pays back from here on: session 4's
agent will get things wrong, and watching the engine answer the same calls the
agent is making -- from a generic inspector, rather than through the agent's own
account of what happened -- is the whole return. That bet is only good while
this file stays a wrapper.

**What is not here.** `adherence_history`, `compare_variants` and
`active_conclusions` are in TRAINER.md's tool surface and have nothing to wrap
yet: they need `workouts`, the variant graph exposed as a tool, and
`conclusions` respectively, none of which exist. Wrapping a function that does
not exist is not this module's job.

Run it with `trainer mcp`, or `python -m trainer.mcp_server`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import asdict, is_dataclass
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from trainer import __version__
from trainer.engine.exclusions import Exclusion, ExclusionError
from trainer.engine import (
    admissible,
    budget,
    catalog,
    database,
    duration,
    migrations,
    muscle_groups,
    state,
)

INSTRUCTIONS = """\
The REPS engine: a deterministic library over an exercise catalog and the
training state. It answers questions and never decides how to train.

`admissible_set` is the space -- an exercise outside what it returns cannot be
prescribed. `remaining_budget` and `allocate` are arithmetic over the time
available; neither cuts a plan that does not fit. `pattern_history` and
`last_performed_load` read state that no workout has been logged into yet, so
today they answer that they do not know, which is an answer and not a failure.
"""

server: MCPServer[None] = MCPServer(
    name="reps-trainer",
    title="REPS engine",
    version=__version__,
    instructions=INSTRUCTIONS,
)

_ENGINE_ERRORS = (
    admissible.AdmissibleError,
    budget.BudgetError,
    catalog.CatalogError,
    duration.DurationError,
    ExclusionError,
    migrations.MigrationError,
    muscle_groups.MuscleGroupError,
    state.StateError,
)
"""Every failure the library states in words. Each is re-raised as a
`ToolError` so it reaches the client as a tool result marked failed, rather
than as a traceback that takes the server down with it -- the same job
`cli.reported()` does for the terminal, with the other layer's error type."""


@contextmanager
def _opened() -> Iterator[sqlite3.Connection]:
    """The connection every tool reads through, with its preconditions named.

    A missing database and a database behind this checkout's migrations are
    both states rather than caller errors, and both have a command that fixes
    them. Left to fail on their own they arrive as `no such table: exercises`,
    which names neither the state nor the way out of it.
    """
    path = database.database_path()
    if not path.exists():
        raise ToolError(
            f"there is no database at {path}; run `trainer db init` and "
            "`trainer db import` first"
        )
    with closing(database.connect(path)) as connection:
        current = migrations.applied_version(connection)
        latest = migrations.latest_version(migrations.discover())
        if current < latest:
            raise ToolError(
                f"the database is at schema version {current} and this "
                f"checkout is at {latest}; run `trainer db init`"
            )
        yield connection


@contextmanager
def _reported() -> Iterator[None]:
    """Turn a stated library failure into a tool error."""
    try:
        yield
    except _ENGINE_ERRORS as error:
        raise ToolError(str(error)) from error
    except sqlite3.Error as error:
        raise ToolError(f"the database could not be used: {error}") from error


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


def _answer(answer: state.Answer[Any]) -> dict[str, Any]:
    """An `Answer`, with its «I don't know» kept legible.

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
        raise ToolError(f"that is not a block: {error}") from error


# -- the tools ----------------------------------------------------------------


@server.tool()
def admissible_set(
    equipment: list[str],
    budget_min: int,
    exclusions: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """The exercises today's equipment, the time available and the exclusions
    given leave standing -- the space a plan is chosen inside.

    `equipment` names the catalog's own values (`barbell`, `body only`) and
    must hold at least one. Each exclusion is `{"granularity": "pattern" |
    "joint", "value": ...}`; an exclusion never names an exercise id.
    """
    given = [
        Exclusion(
            granularity=str(item.get("granularity", "")),
            value=str(item.get("value", "")),
        )
        for item in exclusions or []
    ]
    with _reported(), _opened() as connection:
        found = admissible.admissible_set(connection, given, equipment, budget_min)
    return [_exercise(exercise) for exercise in found]


@server.tool()
def remaining_budget(partial_plan: list[dict[str, Any]], budget_min: int) -> int:
    """How many minutes are left once `partial_plan` is committed.

    A plan is a list of blocks, each `{"items": [{"exercise_id": ..., "reps":
    ...} | {"exercise_id": ..., "seconds": ...}], "rounds": N, "rest": SECONDS}`.
    Negative when the plan is already over, on purpose: how far over is what
    the caller has to act on, and this engine never trims a plan to fit.
    """
    plan = [_block(raw) for raw in partial_plan]
    with _reported(), _opened() as connection:
        return budget.remaining_budget(connection, plan, budget_min)


@server.tool()
def allocate(minutes: int, proportions: dict[str, float]) -> dict[str, int]:
    """Divide a workout's minutes among the muscle groups it trains.

    `proportions` maps a muscle group to its share and has to sum to 1: they
    are refused rather than normalised, because scaling a typo produces a
    different plan that runs the full time and trains something else. The
    group names are the six in the committed mapping.
    """
    with _reported():
        return budget.allocate(minutes, proportions)


@server.tool()
def pattern_history(pattern: str, cycles: int) -> dict[str, Any]:
    """What the state has recorded for one movement pattern, over `cycles`.

    The window is a **cycle** -- one complete rotation through the workouts
    being trained -- never a week. Nothing writes this state until workouts are
    logged, so today the answer comes back with `known: false`, which is an
    answer: nobody has trained this pattern yet.
    """
    with _reported(), _opened() as connection:
        return _answer(state.pattern_history(connection, pattern, cycles))


@server.tool()
def last_performed_load(exercise_id: str) -> dict[str, Any]:
    """The load this exercise was last performed with, if it ever was.

    `known: false` means no load has been recorded for a valid exercise. An id
    the catalog does not have is a tool error instead, so a typo never reads as
    *«you have never done this»*.
    """
    with _reported(), _opened() as connection:
        return _answer(state.last_performed_load(connection, exercise_id))


def main() -> None:
    """Serve over stdio, which is what a generic MCP client connects to."""
    server.run()


if __name__ == "__main__":
    main()
