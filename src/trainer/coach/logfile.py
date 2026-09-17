"""The rotating file the bot writes what happened to, with the credentials taken out."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path

from trainer.engine import home

LOG_NAME = "trainer.log"
"""The file, in the home with everything else this machine writes.

A name and never a path, because the chat names it: `BLOCKED` and `FAILED`
point the user at this file, and the person reading them is sitting at the
machine it is on. It takes no override of its own for the same reason -- a line
that named a file the user had moved would be a line that lies.
"""

MAX_BYTES = 1_000_000
"""A megabyte a file."""

KEPT = 3
"""The live file and three behind it: four megabytes, whatever the bot is told.

Enough to hold the evening that went wrong plus the days around it, and small
enough that the whole home is still one directory somebody copies.
"""

LINE = "%(asctime)s %(levelname)-8s %(name)s %(message)s"

NOISY = ("httpx", "httpcore")
"""Quieted to warnings, because long polling is one request every few seconds.

At INFO the HTTP client writes a line per poll, which is a megabyte a day of
`getUpdates` and four days before the evening that went wrong has rotated out
under them. What they have to say about a request that *failed* is a warning
and is kept.
"""

HIDDEN = "[redacted]"


def log_path() -> Path:
    """Where the bot logs."""
    return home.inside(LOG_NAME)


class Rotating(RotatingFileHandler):
    """Ours, so a second start replaces the handler instead of stacking one on it."""


class Hiding(logging.Formatter):
    """The record, with the value of each named variable taken out of it.

    A formatter and not a filter, because what carries the token is rarely the
    message: it is the traceback under it, where the URL the request was made
    to is quoted along with the source line that raised. A filter sees the
    message; this sees everything that is about to be written.
    """

    def __init__(self, hiding: Sequence[str]) -> None:
        super().__init__(LINE)
        self._hiding = tuple(hiding)

    def format(self, record: logging.LogRecord) -> str:
        return without(super().format(record), self._hiding)


def without(written: str, names: Sequence[str]) -> str:
    """`written`, with the current value of each named environment variable gone.

    Read here rather than captured when the log is started: the names are
    constants and the values are the machine's, and a value read once is one
    that goes on being written after the user changes it.
    """
    for name in names:
        secret = os.environ.get(name)
        if not secret:
            continue
        if secret.isdigit():
            # A bare number, bounded: an owner id of 642 must not eat the 642
            # inside every longer number the log happens to hold.
            written = re.sub(rf"(?<!\d){re.escape(secret)}(?!\d)", HIDDEN, written)
        else:
            # Never bounded. The token lives inside `.../bot<token>/sendMessage`,
            # with a letter on one side of it and a slash on the other.
            written = written.replace(secret, HIDDEN)
    return written


_LEVEL: int | None = None
"""The root logger's level before the bot took it, so `stop` gives it back."""

_QUIETED: dict[str, int] = {}
"""The same, for `NOISY`: what this took, it gives back rather than guesses at."""


def start(hiding: Sequence[str]) -> Path:
    """Send every record to the rotating file under the home, and return where it is.

    Called where the bot starts and nowhere else: a library that configures
    logging on import steals it from every other caller, and this one would
    steal it from the test suite too.

    `hiding` names the environment variables whose values must never be
    written. They are named rather than passed so that nothing has to have read
    a credential in order to configure a log.
    """
    global _LEVEL

    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = Rotating(
        path, maxBytes=MAX_BYTES, backupCount=KEPT, encoding="utf-8"
    )
    handler.setFormatter(Hiding(hiding))
    root = logging.getLogger()
    stop()
    _LEVEL = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    for name in NOISY:
        quieted = logging.getLogger(name)
        _QUIETED[name] = quieted.level
        quieted.setLevel(logging.WARNING)
    return path


def stop() -> None:
    """Give the file up, closing it. The process ending does this too; a test cannot."""
    global _LEVEL

    root = logging.getLogger()
    for handler in [held for held in root.handlers if isinstance(held, Rotating)]:
        root.removeHandler(handler)
        handler.close()
    if _LEVEL is not None:
        root.setLevel(_LEVEL)
        _LEVEL = None
    for name, level in _QUIETED.items():
        logging.getLogger(name).setLevel(level)
    _QUIETED.clear()
