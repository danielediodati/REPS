"""The adaptation eval set: messages to the entrance, where each must go, and what an adapted plan must hold."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trainer import plan as plans
from trainer.coach import entrance

ADAPT_SET_ENV_VAR = "TRAINER_ADAPT_SET"
DEFAULT_PARTS = ("docs", "adapting", "eval-set.toml")

ASK, TRIAGE, REMEMBER, REFUSED = "ask", "triage", "remember", "refused"
HANDED = (entrance.ADAPT_THIS_WORKOUT, entrance.CHANGE_MESOCYCLE, entrance.CHANGE_DECLARATION)
DESTINATIONS = (*HANDED, ASK, TRIAGE, REMEMBER, REFUSED)
ASKING = (ASK, TRIAGE)
"""Where nothing may start and the answer is a question."""


class AdaptSetError(ValueError):
    """A set that cannot be run as written, saying where."""


@dataclass(frozen=True)
class Case:
    """One message, where it must go, and what its plan must hold when it is planned."""

    name: str
    says: str
    goes: str
    excluded: tuple[str, ...] = ()
    minutes: int | None = None
    equipment: tuple[str, ...] = ()
    holds: tuple[str, ...] = ()
    without_pattern: tuple[str, ...] = ()
    without_named: tuple[str, ...] = ()
    untrained: tuple[str, ...] = ()
    longer: bool = False

    @property
    def planned(self) -> bool:
        return self.goes == entrance.ADAPT_THIS_WORKOUT


@dataclass(frozen=True)
class AdaptSet:
    today: str
    bar_routed: int
    declared: Mapping[str, Any]
    mesocycle: plans.Mesocycle
    cases: tuple[Case, ...] = field(default_factory=tuple)


def path() -> Path:
    """Where the set is read from: `TRAINER_ADAPT_SET`, or the committed one."""
    override = os.environ.get(ADAPT_SET_ENV_VAR)
    return Path(override).expanduser() if override else Path.cwd().joinpath(*DEFAULT_PARTS)


def load(where: Path | None = None) -> AdaptSet:
    """The set, off disk; refused naming the file when it is not there."""
    target = where if where is not None else path()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as error:
        raise AdaptSetError(f"the adaptation eval set is not at {target}") from error
    return parse(text)


def parse(text: str) -> AdaptSet:
    """A set out of its TOML, every case checked against what the runner can score."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise AdaptSetError(f"the set is not TOML: {error}") from error
    bars = raw.get("bars")
    if not isinstance(bars, dict) or "routed" not in bars:
        raise AdaptSetError("the set declares no [bars] with routed")
    declared = raw.get("declared")
    if not isinstance(declared, dict):
        raise AdaptSetError("the set declares no [declared]")
    meso = dict(raw.get("mesocycle", {}))
    try:
        mesocycle = plans.Mesocycle.model_validate(
            {
                "workouts": [{"blocks": slot.get("blocks", [])} for slot in meso.pop("slots", [])],
                **meso,
            }
        )
    except ValidationError as error:
        raise AdaptSetError(f"the [mesocycle] is not a mesocycle: {error}") from error
    cases = tuple(_case(entry) for entry in raw.get("cases", ()))
    names = [case.name for case in cases]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise AdaptSetError(f"cases named twice: {', '.join(repeated)}")
    return AdaptSet(
        today=str(raw.get("today", "")),
        bar_routed=int(bars["routed"]),
        declared=declared,
        mesocycle=mesocycle,
        cases=cases,
    )


PLAN_KEYS = ("minutes", "equipment", "holds", "without_pattern", "without_named", "untrained", "longer")


def _case(entry: Mapping[str, Any]) -> Case:
    name = str(entry.get("name", ""))
    goes = str(entry.get("goes", ""))
    if goes not in DESTINATIONS:
        raise AdaptSetError(f"{name}: goes {goes!r} is not one of {', '.join(DESTINATIONS)}")
    if goes != entrance.ADAPT_THIS_WORKOUT and any(key in entry for key in PLAN_KEYS):
        raise AdaptSetError(f"{name}: only an adaptation is planned, so only one says what its plan holds")

    def listed(key: str) -> tuple[str, ...]:
        return tuple(str(one) for one in entry.get(key, ()))

    minutes = entry.get("minutes")
    return Case(
        name=name,
        says=str(entry.get("says", "")),
        goes=goes,
        excluded=listed("excluded"),
        minutes=None if minutes is None else int(minutes),
        equipment=listed("equipment"),
        holds=listed("holds"),
        without_pattern=listed("without_pattern"),
        without_named=listed("without_named"),
        untrained=listed("untrained"),
        longer=bool(entry.get("longer", False)),
    )
