"""Where the database lives, and how to open it.

The engine is a pure library: it never reads command-line arguments and never
prints. Callers pass a path or accept the documented default.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from trainer.engine import home

DATABASE_ENV_VAR = "TRAINER_DB"
"""Environment variable that overrides the default database location."""

DEFAULT_DATABASE_NAME = "trainer.sqlite"
"""Default file name, resolved against `TRAINER_HOME`.

Covered by the `*.sqlite` rule in .gitignore: the database is never committed.
The readable history is the markdown snapshot beside it, not the file itself.
"""


def database_path() -> Path:
    """The database this process should use.

    `TRAINER_DB` wins when set, so tests and throwaway runs never touch the
    real file.
    """
    override = os.environ.get(DATABASE_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return home.inside(DEFAULT_DATABASE_NAME)


def connect(path: Path) -> sqlite3.Connection:
    """Open (creating the file if needed) with the pragmas we rely on.

    Transactions are driven explicitly rather than by the driver. Python's
    sqlite3 only opens one implicitly before DML, never before DDL, so a
    migration relying on the implicit behaviour would leave its `CREATE TABLE`
    committed when a later statement failed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
