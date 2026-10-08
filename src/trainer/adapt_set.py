"""The adaptation eval set: messages to the entrance, where each must go, and what an adapted plan must hold."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trainer import eval_set
from trainer import plan as plans
from trainer.coach import entrance

ADAPT_SET_ENV_VAR = "TRAINER_ADAPT_SET"
DEFAULT_PARTS = ("docs", "adapting", "eval-set.toml")

ASK, TRIAGE, REMEMBER, ANSWER = "ask", "triage", "remember", "answer"
HANDED = (
    entrance.ADAPT_THIS_WORKOUT,
    entrance.CHANGE_MESOCYCLE,
    entrance.CHANGE_DECLARATION,
    entrance.LOG_WORKOUT,
    *entrance.ANSWERS,
)
DESTINATIONS = (*HANDED, ASK, TRIAGE, REMEMBER, ANSWER)
ASKING = (ASK, TRIAGE)
"""Where nothing may start and the answer is a question."""


class AdaptSetError(eval_set.SetError):
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
    holds: tuple[tuple[str, ...], ...] = ()
    """Each entry one exercise the plan must hold: any one of its ids."""
    without_pattern: tuple[str, ...] = ()
    without_named: tuple[str, ...] = ()
    untrained: tuple[str, ...] = ()
    longer: bool = False
    told: bool = False
    proposed: bool = False
    """An adaptation of this workout is waiting on the user's answer when the message arrives."""

    @property
    def planned(self) -> bool:
        return self.goes == entrance.ADAPT_THIS_WORKOUT and not self.proposed


@dataclass(frozen=True)
class AdaptSet:
    today: str
    bar_held: int
    bar_routed: int
    declared: Mapping[str, Any]
    mesocycle: plans.Mesocycle
    cases: tuple[Case, ...] = field(default_factory=tuple)


def path() -> Path:
    """Where the set is read from: `TRAINER_ADAPT_SET`, or the committed one."""
    return eval_set.path(ADAPT_SET_ENV_VAR, DEFAULT_PARTS)


def load(where: Path | None = None) -> AdaptSet:
    """The set, off disk; refused naming the file when it is not there."""
    return eval_set.load(where, ADAPT_SET_ENV_VAR, DEFAULT_PARTS, "adaptation eval set", parse, AdaptSetError)


def parse(text: str) -> AdaptSet:
    """A set out of its TOML, every case checked against what the runner can score."""
    raw = eval_set.toml(text, AdaptSetError)
    bars = raw.get("bars")
    if not isinstance(bars, dict) or not {"held", "routed"} <= bars.keys():
        raise AdaptSetError("the set declares no [bars] with held and routed")
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
    eval_set.unique([case.name for case in cases], AdaptSetError)
    return AdaptSet(
        today=str(raw.get("today", "")),
        bar_held=int(bars["held"]),
        bar_routed=int(bars["routed"]),
        declared=declared,
        mesocycle=mesocycle,
        cases=cases,
    )


PLAN_KEYS = (
    "minutes", "equipment", "holds", "without_pattern", "without_named", "untrained", "longer", "told"
)


def _case(entry: Mapping[str, Any]) -> Case:
    name = str(entry.get("name", ""))
    goes = str(entry.get("goes", ""))
    if goes not in DESTINATIONS:
        raise AdaptSetError(f"{name}: goes {goes!r} is not one of {', '.join(DESTINATIONS)}")
    proposed = bool(entry.get("proposed", False))
    if (goes != entrance.ADAPT_THIS_WORKOUT or proposed) and any(key in entry for key in PLAN_KEYS):
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
        holds=tuple(
            tuple(str(one) for one in entry) if isinstance(entry, list) else (str(entry),)
            for entry in entry.get("holds", ())
        ),
        without_pattern=listed("without_pattern"),
        without_named=listed("without_named"),
        untrained=listed("untrained"),
        longer=bool(entry.get("longer", False)),
        told=bool(entry.get("told", False)),
        proposed=proposed,
    )
