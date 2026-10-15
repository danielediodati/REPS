"""The language the chat speaks, and the words of its own it says in it, read from one catalog per language."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, get_args

from langgraph.config import get_config

from trainer.coach import logfile

Language = Literal["it", "en"]

ITALIAN: Language = "it"
ENGLISH: Language = "en"
LANGUAGES: tuple[Language, ...] = get_args(Language)

KEY = "language"
"""Where a run's config carries the language its words are written in."""

NAMES = {ITALIAN: "Italian", ENGLISH: "English"}

CATALOGS = Path(__file__).resolve().parent.parent / "data" / "chat"


def of(code: str | None) -> Language:
    """The chat's language for a Telegram `language_code`; English when the app sends none."""
    return ITALIAN if code is not None and code.lower().startswith(ITALIAN) else ENGLISH


@dataclass(frozen=True)
class ChatLines:
    working: str
    failed: str
    blocked: str
    turned_down: str
    exclusion: str


@dataclass(frozen=True)
class ButtonLines:
    kept: str
    turned_down: str
    confirmed: str
    declined: str


@dataclass(frozen=True)
class PlanLines:
    heading: str
    last: str
    last_unknown: str
    served: str
    mesocycle: str
    slot: str
    said_no: str
    total: str
    reps: str
    seconds: str


@dataclass(frozen=True)
class ProgressLines:
    looking: str
    looking_workout: str
    writing: str
    checking: str
    refused: str
    rewriting: str
    exhausted: str
    valid: str
    one_block: str
    blocks: str
    workouts: str
    again: str
    reading_report: str
    writing_report: str
    read: str
    not_read: str


@dataclass(frozen=True)
class Texts:
    """One language's catalog: a missing or unknown key fails on load."""

    chat: ChatLines
    buttons: ButtonLines
    plan: PlanLines
    progress: ProgressLines


def catalog(spoken: Language) -> dict[str, Any]:
    """One language's catalog file, as written."""
    with (CATALOGS / f"{spoken}.toml").open("rb") as file:
        return tomllib.load(file)


@cache
def texts(spoken: Language) -> Texts:
    """The words the chat says in `spoken`, loaded once."""
    raw = catalog(spoken)
    chat = {key: value.replace("{log}", logfile.LOG_NAME) for key, value in raw["chat"].items()}
    return Texts(
        chat=ChatLines(**chat),
        buttons=ButtonLines(**raw["buttons"]),
        plan=PlanLines(**raw["plan"]),
        progress=ProgressLines(**raw["progress"]),
    )


def running() -> Language:
    """The language of the run in flight; Italian on a door that names none, the terminal and the evals."""
    try:
        named = get_config().get("configurable", {}).get(KEY)
    except RuntimeError:
        return ITALIAN
    return ENGLISH if named == ENGLISH else ITALIAN


def told() -> str:
    """The end of every prompt whose words reach the chat: the language they are written in."""
    name = NAMES[running()]
    return f"\n\nThey read {name}: everything you write that reaches them is in {name}."
