"""The engine: a pure Python library.

Zero LLM calls, zero network, no knowledge of any client. The CLI, an MCP
wrapper and a direct call are all thin wrappers over this same surface, and a
test enforces that rather than trusting the convention.
"""

from trainer.engine.database import DATABASE_ENV_VAR, connect, database_path
from trainer.engine.migrations import (
    Migration,
    MigrationError,
    applied_version,
    discover,
    latest_version,
    migrate,
)

__all__ = [
    "DATABASE_ENV_VAR",
    "Migration",
    "MigrationError",
    "applied_version",
    "connect",
    "database_path",
    "discover",
    "latest_version",
    "migrate",
]
