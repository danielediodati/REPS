"""The onboarding eval set: scripted users, the messages to route, and the bars they are held to."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trainer import eval_set
from trainer.coach import entrance, onboarding

ONBOARD_SET_ENV_VAR = "TRAINER_ONBOARD_SET"
DEFAULT_PARTS = ("docs", "onboarding", "eval-set.toml")

INTERVIEW, CHANGE, ROUTE = "interview", "change", "route"
KINDS = (INTERVIEW, CHANGE, ROUTE)
ROUTES = (entrance.CHANGE_DECLARATION, entrance.ADAPT_THIS_WORKOUT)
BARS = ("on_time", "remembered", "routed")


class OnboardSetError(eval_set.SetError):
    """A set that cannot be run as written, saying where."""


@dataclass(frozen=True)
class Reply:
    """One answer a persona gives, and the declarations it settles."""

    fields: tuple[str, ...]
    says: str


@dataclass(frozen=True)
class Case:
    """One scripted user: an interview, a change to what is declared, or a message to route."""

    name: str
    kind: str
    describes: str
    opens: str
    replies: tuple[Reply, ...] = ()
    afterwards: tuple[str, ...] = ()
    otherwise: str = ""
    remembers: tuple[str, ...] = ()
    confirms: bool = True
    pause_after: int | None = None
    back: str = ""
    before: Mapping[str, Any] = field(default_factory=dict)
    changes: tuple[str, ...] = ()
    open: tuple[str, ...] = ()
    routed: str = ""


@dataclass(frozen=True)
class OnboardSet:
    today: str
    bar_on_time: int
    bar_remembered: int
    bar_routed: int
    cases: tuple[Case, ...]

    @property
    def held(self) -> tuple[Case, ...]:
        """The interviews and the changes: the cases code holds at 100%."""
        return tuple(case for case in self.cases if case.kind != ROUTE)

    @property
    def routes(self) -> tuple[Case, ...]:
        return tuple(case for case in self.cases if case.kind == ROUTE)


def path() -> Path:
    """Where the set is read from: `TRAINER_ONBOARD_SET`, or the committed one."""
    return eval_set.path(ONBOARD_SET_ENV_VAR, DEFAULT_PARTS)


def load(where: Path | None = None) -> OnboardSet:
    """The set, off disk; refused naming the file when it is not there."""
    return eval_set.load(where, ONBOARD_SET_ENV_VAR, DEFAULT_PARTS, "onboarding eval set", parse, OnboardSetError)


def parse(text: str) -> OnboardSet:
    """A set out of its TOML, every case checked against what the graphs take."""
    raw = eval_set.toml(text, OnboardSetError)
    bars = raw.get("bars")
    if not isinstance(bars, dict) or not set(BARS) <= set(bars):
        raise OnboardSetError(f"the set declares no [bars] with {', '.join(BARS)}")
    cases = tuple(_case(entry) for entry in raw.get("cases", ()))
    eval_set.unique([case.name for case in cases], OnboardSetError)
    return OnboardSet(
        today=str(raw.get("today", "")),
        bar_on_time=int(bars["on_time"]),
        bar_remembered=int(bars["remembered"]),
        bar_routed=int(bars["routed"]),
        cases=cases,
    )


def _case(entry: Mapping[str, Any]) -> Case:
    name = str(entry.get("name", ""))
    kind = str(entry.get("kind", ""))
    if kind not in KINDS:
        raise OnboardSetError(f"{name}: kind {kind!r} is not one of {', '.join(KINDS)}")
    replies = tuple(
        Reply(tuple(str(one) for one in reply["fields"]), str(reply["says"]))
        for reply in entry.get("replies", ())
    )
    case = Case(
        name=name,
        kind=kind,
        describes=str(entry.get("describes", "")),
        opens=str(entry.get("opens", "")),
        replies=replies,
        afterwards=tuple(str(line) for line in entry.get("afterwards", ())),
        otherwise=str(entry.get("otherwise", "")),
        remembers=tuple(str(line) for line in entry.get("remembers", ())),
        confirms=bool(entry.get("confirms", True)),
        pause_after=entry.get("pause_after"),
        back=str(entry.get("back", "")),
        before=dict(entry.get("before", {})),
        changes=tuple(str(one) for one in entry.get("changes", ())),
        open=tuple(str(one) for one in entry.get("open", ())),
        routed=str(entry.get("routed", "")),
    )
    _checked(case)
    return case


def _checked(case: Case) -> None:
    """Refuse a case the runner could not drive to its end."""
    named = case.name
    unknown = sorted(
        {one for reply in case.replies for one in reply.fields} - set(onboarding.FIELDS)
        | set(case.changes) - set(onboarding.FIELDS)
    )
    if unknown:
        raise OnboardSetError(f"{named}: {', '.join(unknown)} is not a declaration")
    if case.kind == INTERVIEW:
        covered = {one for reply in case.replies for one in reply.fields}
        missing = [one for one in onboarding.FIELDS if one not in covered]
        if missing:
            raise OnboardSetError(f"{named}: no reply settles {', '.join(missing)}")
        if case.pause_after is not None and not 0 < case.pause_after < len(case.replies):
            raise OnboardSetError(f"{named}: pause_after must fall between two replies")
    if case.kind == CHANGE:
        if not case.changes:
            raise OnboardSetError(f"{named}: a change names the fields it changes")
        closed = [one for one in case.open if one not in onboarding.PATHS]
        if closed:
            raise OnboardSetError(f"{named}: {', '.join(closed)} is not a path")
    if case.kind == ROUTE and case.routed not in ROUTES:
        raise OnboardSetError(
            f"{named}: routed {case.routed!r} is not one of {', '.join(ROUTES)}"
        )
