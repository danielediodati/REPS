"""The one directory everything this machine writes lives in."""

from __future__ import annotations

import os
from pathlib import Path

HOME_ENV_VAR = "TRAINER_HOME"
"""Environment variable that moves the whole directory somewhere else."""

DEFAULT_HOME_NAME = ".reps"
"""Resolved against the user's home directory, not the working one.

The working directory was the old answer, and it made `trainer` two
installations with two histories the moment it was launched from two places,
with nothing saying so. Beside the user, there is one of it, and replacing the
laptop is one directory to copy.
"""


def home() -> Path:
    """Where the database, the checkpointer, the declarations and the eval records live."""
    override = os.environ.get(HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_HOME_NAME


def inside(name: str) -> Path:
    """One thing in the home, by file name.

    The per-artifact variables are checked by their own modules and win over
    this: the home is where a thing lands when nobody says otherwise.
    """
    return home() / name
