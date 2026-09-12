"""Where the graph keeps its own state: a SQLite file of its own, never the training database."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from trainer.engine import database


class CheckpointError(RuntimeError):
    """The checkpointer was pointed somewhere it may not write, stated with the way out."""


CHECKPOINTS_ENV = "TRAINER_CHECKPOINTS"
"""Overrides the checkpointer's location, the way `TRAINER_DB` does for the database."""

DEFAULT_PATH = Path("checkpoints.sqlite")


def checkpoints_path() -> Path:
    """Where the checkpointer writes, from the environment or the working directory."""
    override = os.environ.get(CHECKPOINTS_ENV)
    return Path(override).expanduser() if override else DEFAULT_PATH


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
        yield SqliteSaver(connection)
    finally:
        connection.close()
