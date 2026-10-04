"""The supervisor's eval set: scripted histories, and what the next direction and the mesocycle planned from it must hold."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trainer import plan as plans
from trainer.engine import mesocycles

SUPERVISE_SET_ENV_VAR = "TRAINER_SUPERVISE_SET"
DEFAULT_PARTS = ("docs", "supervising", "eval-set.toml")

SHORTER, LONGER = "shorter", "longer"
FEWER, MORE = "fewer", "more"

CHECKS = ("changes", "keeps", "rotates", "without", "ranges", "varies", "rest", "reps")


class SuperviseSetError(ValueError):
    """A set that cannot be run as written, saying where."""


@dataclass(frozen=True)
class Past:
    """One mesocycle of a history, performed to its end, and the direction it was planned from."""

    mesocycle: str
    direction: mesocycles.Direction | None = None


@dataclass(frozen=True)
class Said:
    """A conclusion in the store when the history ends, with the words it was drawn from."""

    conclusion: str
    quote: str


@dataclass(frozen=True)
class Case:
    """One history, and what code holds on the direction and the plan that follow it."""

    name: str
    history: tuple[Past, ...]
    goal: str | None = None
    said: tuple[Said, ...] = ()
    changes: bool = False
    """The planned mesocycle differs from the one that ended in exercises, reps or rest."""

    keeps: tuple[tuple[str, ...], ...] = ()
    """Each entry one exercise the plan must hold: any one of its ids."""

    rotates: bool = False
    """At least one exercise of the ended mesocycle that `keeps` does not name is gone."""

    without: tuple[str, ...] = ()
    ranges: bool = False
    """Every rep count and rest inside the goal's column of the methodology."""

    varies: tuple[str, ...] = ()
    """What the direction must name among what it varies."""

    rest: str | None = None
    reps: str | None = None


@dataclass(frozen=True)
class SuperviseSet:
    bar_held: int
    bar_followed: int
    declared: Mapping[str, Any]
    mesocycles: Mapping[str, plans.Mesocycle]
    cases: tuple[Case, ...] = field(default_factory=tuple)


def path() -> Path:
    """Where the set is read from: `TRAINER_SUPERVISE_SET`, or the committed one."""
    override = os.environ.get(SUPERVISE_SET_ENV_VAR)
    return Path(override).expanduser() if override else Path.cwd().joinpath(*DEFAULT_PARTS)


def load(where: Path | None = None) -> SuperviseSet:
    """The set, off disk; refused naming the file when it is not there."""
    target = where if where is not None else path()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as error:
        raise SuperviseSetError(f"the supervisor's eval set is not at {target}") from error
    return parse(text)


def parse(text: str) -> SuperviseSet:
    """A set out of its TOML, every case checked against what the runner can score."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise SuperviseSetError(f"the set is not TOML: {error}") from error
    bars = raw.get("bars")
    if not isinstance(bars, dict) or not {"held", "followed"} <= bars.keys():
        raise SuperviseSetError("the set declares no [bars] with held and followed")
    declared = raw.get("declared")
    if not isinstance(declared, dict):
        raise SuperviseSetError("the set declares no [declared]")
    named = {name: mesocycle(name, meso) for name, meso in dict(raw.get("mesocycles", {})).items()}
    cases = tuple(_case(entry, named) for entry in raw.get("cases", ()))
    names = [case.name for case in cases]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise SuperviseSetError(f"cases named twice: {', '.join(repeated)}")
    return SuperviseSet(
        bar_held=int(bars["held"]),
        bar_followed=int(bars["followed"]),
        declared=declared,
        mesocycles=named,
        cases=cases,
    )


def mesocycle(name: str, raw: Mapping[str, Any]) -> plans.Mesocycle:
    """A mesocycle out of its TOML table, its workouts written as `slots`."""
    meso = dict(raw)
    try:
        return plans.Mesocycle.model_validate(
            {"workouts": [{"blocks": slot.get("blocks", [])} for slot in meso.pop("slots", [])], **meso}
        )
    except ValidationError as error:
        raise SuperviseSetError(f"[mesocycles.{name}] is not a mesocycle: {error}") from error


def _case(entry: Mapping[str, Any], named: Mapping[str, plans.Mesocycle]) -> Case:
    name = str(entry.get("name", ""))
    history = tuple(_past(name, at, one, named) for at, one in enumerate(entry.get("history", ())))
    if not history:
        raise SuperviseSetError(f"{name}: a history is at least one mesocycle")
    if not any(key in entry for key in CHECKS):
        raise SuperviseSetError(f"{name}: holds nothing; a case names one of {', '.join(CHECKS)}")
    varies = tuple(str(one) for one in entry.get("varies", ()))
    unknown = [one for one in varies if one not in mesocycles.VARIES]
    if unknown:
        raise SuperviseSetError(f"{name}: varies {', '.join(unknown)} is not one of {', '.join(mesocycles.VARIES)}")
    rest, reps = entry.get("rest"), entry.get("reps")
    if rest not in (None, SHORTER, LONGER):
        raise SuperviseSetError(f"{name}: rest is {SHORTER} or {LONGER}, not {rest!r}")
    if reps not in (None, FEWER, MORE):
        raise SuperviseSetError(f"{name}: reps is {FEWER} or {MORE}, not {reps!r}")
    return Case(
        name=name,
        history=history,
        goal=None if entry.get("goal") is None else str(entry["goal"]),
        said=tuple(Said(str(one["conclusion"]), str(one["quote"])) for one in entry.get("said", ())),
        changes=bool(entry.get("changes", False)),
        keeps=tuple(
            tuple(str(one) for one in kept) if isinstance(kept, list) else (str(kept),)
            for kept in entry.get("keeps", ())
        ),
        rotates=bool(entry.get("rotates", False)),
        without=tuple(str(one) for one in entry.get("without", ())),
        ranges=bool(entry.get("ranges", False)),
        varies=varies,
        rest=None if rest is None else str(rest),
        reps=None if reps is None else str(reps),
    )


def _past(name: str, at: int, raw: Mapping[str, Any], named: Mapping[str, plans.Mesocycle]) -> Past:
    mesocycle = str(raw.get("mesocycle", ""))
    if mesocycle not in named:
        raise SuperviseSetError(f"{name}: no [mesocycles.{mesocycle}] in the set")
    given = raw.get("direction")
    if given is None:
        return Past(mesocycle)
    if at == 0:
        raise SuperviseSetError(f"{name}: the first mesocycle of a history follows nothing, so it has no direction")
    try:
        direction = mesocycles.Direction(
            theme=str(given["theme"]),
            changes=str(given["changes"]),
            why=str(given["why"]),
            varies=tuple(str(one) for one in given.get("varies", ())),
        )
    except KeyError as error:
        raise SuperviseSetError(f"{name}: a direction has a theme, changes and why") from error
    if not direction.varies or not set(direction.varies) <= set(mesocycles.VARIES):
        raise SuperviseSetError(f"{name}: a direction varies some of {', '.join(mesocycles.VARIES)}")
    return Past(mesocycle, direction)
