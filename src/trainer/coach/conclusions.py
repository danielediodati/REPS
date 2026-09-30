"""Conclusions: what the user said about themselves, kept in the LangGraph store with its source."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.config import get_config
from langgraph.store.base import BaseStore
from langgraph.store.sqlite import SqliteStore

from trainer.coach import checkpoints

PROVISIONAL = "provisional"
RETIRED = "retired"

USER = "user"
"""The configurable key naming whose conclusions a run reads and writes."""

DEFAULT_NAME = "store.sqlite"

KEPT = "Kept, as provisional. Carry on with the turn."

NOT_SAID = (
    "Not kept: {quote!r} is not in anything the user wrote. `quote` is their "
    "own sentence exactly as they typed it -- never a paraphrase, a summary or "
    "a translation. Quote it again from their message, or keep nothing."
)

UNSAID = "Not kept: `conclusion` is empty. Say in one line what the quote tells you about them."

NOWHERE = "Nothing is kept here: this conversation has no memory. Carry on with the turn."


def remember(conclusion: str, quote: str) -> str:
    """Keep something lasting the user told you about themselves.

    - `conclusion`: what it says about them, in one short line, with the
      reason when they gave one.
    - `quote`: the sentence it comes from, exactly as they typed it.

    Only what they said is kept: a quote that is not in one of their messages
    is refused, and you are told so.

    The body is never run. The graph answers this call by checking the quote
    and writing the conclusion to the store.
    """
    raise AssertionError("the graph answers remember; nothing calls it")


REMEMBER = remember.__name__


@dataclass(frozen=True)
class Conclusion:
    """One conclusion as the store keeps it."""

    conclusion: str
    quote: str
    state: str
    on: str


def store_path() -> Path:
    """Where the store is kept: next to the checkpointer, so one override moves both."""
    return checkpoints.checkpoints_path().with_name(DEFAULT_NAME)


@contextmanager
def opened(path: Path | None = None) -> Iterator[SqliteStore]:
    """The store over its own file, open for as long as the graphs run."""
    target = path if path is not None else store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit, because the store opens its own transactions.
    connection = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
    try:
        yield SqliteStore(connection)
    finally:
        connection.close()


def namespace(user: str) -> tuple[str, ...]:
    """One user's conclusions."""
    return ("conclusions", user)


def whose() -> str | None:
    """The user the running graph was invoked for, or `None` on a door that names nobody."""
    user = get_config().get("configurable", {}).get(USER)
    return None if user is None else str(user)


def _plain(text: str) -> str:
    """Text as the admission compares it: case, spacing and typographic quotes set aside."""
    for curly, straight in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(curly, straight)
    return " ".join(text.casefold().split())


def admitted(quote: str, said: Iterable[str]) -> bool:
    """Whether `quote` is in one of the user's messages, word for word."""
    wanted = _plain(quote).strip(" \"'«»").rstrip(".!?,;:")
    return bool(wanted) and any(wanted in _plain(message) for message in said)


def kept(
    store: BaseStore,
    user: str | None,
    arguments: Mapping[str, Any],
    said: Sequence[str],
    today: str,
) -> tuple[str, bool]:
    """A `remember` call answered: what the model is told, and whether it was refused.

    Keyed on what it says, so a node that runs again after an interrupt writes
    the same conclusion once.
    """
    if user is None:
        return NOWHERE, False
    conclusion = str(arguments.get("conclusion", "")).strip()
    quote = str(arguments.get("quote", "")).strip()
    if not conclusion:
        return UNSAID, True
    if not admitted(quote, said):
        return NOT_SAID.format(quote=quote), True
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{conclusion}\n{quote}"))
    store.put(
        namespace(user),
        key,
        {"conclusion": conclusion, "quote": quote, "state": PROVISIONAL, "on": today},
        index=False,
    )
    return KEPT, False


def live(store: BaseStore, user: str | None) -> list[Conclusion]:
    """Every conclusion not retired, oldest first."""
    if user is None:
        return []
    found = store.search(namespace(user), limit=10_000)
    held = [
        Conclusion(
            conclusion=str(item.value["conclusion"]),
            quote=str(item.value["quote"]),
            state=str(item.value["state"]),
            on=str(item.value["on"]),
        )
        for item in sorted(found, key=lambda item: item.created_at)
    ]
    return [one for one in held if one.state != RETIRED]
