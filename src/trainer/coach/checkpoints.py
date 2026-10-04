"""Where the graph keeps its own state: a SQLite file of its own, never the training database."""

from __future__ import annotations

import dataclasses
import os
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.serde._msgpack import SAFE_MSGPACK_TYPES
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from trainer import log as logs
from trainer import plan as plans
from trainer.engine import database, home, mesocycles, workouts
from trainer.engine.exclusions import Exclusion


class CheckpointError(RuntimeError):
    """The checkpointer was pointed somewhere it may not write, stated with the way out."""


CHECKPOINTS_ENV = "TRAINER_CHECKPOINTS"
"""Overrides the checkpointer's location, the way `TRAINER_DB` does for the database."""

DEFAULT_NAME = "checkpoints.sqlite"


def checkpoints_path() -> Path:
    """Where the checkpointer writes, from the environment or `TRAINER_HOME`."""
    override = os.environ.get(CHECKPOINTS_ENV)
    return Path(override).expanduser() if override else home.inside(DEFAULT_NAME)


DECLARED: tuple[type, ...] = (
    plans.Request,
    plans.Refusal,
    plans.Violation,
    plans.WorkoutPlan,
    plans.AdaptedPlan,
    plans.MesocycleRequest,
    plans.MesocycleRefusal,
    plans.Mesocycle,
    plans.Adapting,
    plans.Changing,
    plans.Continuing,
    mesocycles.Direction,
    workouts.PerformedBlock,
    workouts.PerformedItem,
    logs.PerformedWorkout,
    Exclusion,
)
"""The types of ours a checkpoint holds, declared so they can be read back.

LangGraph writes an unregistered type and warns that a future version will
refuse to construct it. Refused, it comes back as the keyword arguments it was
written from -- a plain dictionary where a model was -- and the thread fails
somewhere downstream, saying nothing about serialization. Declared, the
serializer is explicit both ways, and strict about everything else.

`PlannerState` holds a `Request`, a tuple of `Violation`s per refusal and a
`WorkoutPlan`; `LoggerState` holds a `PerformedWorkout`. `Exclusion` and `Refusal` travel *inside* the request -- `turn`
folds today's standing exclusions into it before the model is called, and
every plan the negotiation turned down rides in it from ADR-0007 on -- and a
dataclass keeps its field values as objects rather than flattening them.

The plan's nested models -- `PlanBlock`, `PlanItem`, `Prescription` -- are not
here and do not belong here: a pydantic model is written as `model_dump()`, so
the nested ones travel as plain data and are rebuilt by validating the outer
one.
"""

_PLAIN = (str, bytes, bool, int, float, type(None))

_ALLOWED = frozenset(SAFE_MSGPACK_TYPES) | {
    (declared.__module__, declared.__name__) for declared in DECLARED
}


def undeclared(value: Any) -> type | None:
    """The first type in `value` the serializer would write without a declaration.

    Walks the way `_msgpack_default` writes: a pydantic model is dumped whole,
    so nothing inside it needs declaring, while a dataclass keeps its field
    values as objects and each of them does.
    """
    if isinstance(value, _PLAIN):
        return None
    if isinstance(value, Mapping):
        for key, held in value.items():
            found = undeclared(key) or undeclared(held)
            if found is not None:
                return found
        return None
    if isinstance(value, (Sequence, set, frozenset)):
        for held in value:
            found = undeclared(held)
            if found is not None:
                return found
        return None
    kind = type(value)
    if (kind.__module__, kind.__name__) not in _ALLOWED:
        return kind
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            found = undeclared(getattr(value, field.name))
            if found is not None:
                return found
    return None


class Declared(JsonPlusSerializer):
    """The checkpointer's serializer: it writes only what it can read back."""

    def __init__(self) -> None:
        super().__init__(allowed_msgpack_modules=DECLARED)

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        """Refuse an undeclared type here, where the traceback still names the write."""
        found = undeclared(obj)
        if found is not None:
            raise CheckpointError(
                f"{found.__module__}.{found.__name__} would be written to a checkpoint "
                f"undeclared, and read back as a dictionary; add it to "
                f"{__name__}.DECLARED"
            )
        return super().dumps_typed(obj)


@contextmanager
def saver(path: Path | None = None) -> Iterator[SqliteSaver]:
    """A checkpointer over its own file, open for as long as the graph runs (ADR-0004, item 5)."""
    target = path if path is not None else checkpoints_path()
    engine = database.database_path()
    if target.expanduser().resolve() == engine.expanduser().resolve():
        raise CheckpointError(
            f"{target} is the training database; point {CHECKPOINTS_ENV} at a "
            "file of its own, because the graph never writes a training fact"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, check_same_thread=False)
    try:
        yield SqliteSaver(connection, serde=Declared())
    finally:
        connection.close()
