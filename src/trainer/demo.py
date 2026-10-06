"""The demo's home: a history of mesocycles performed, the last one a report from its end."""

from __future__ import annotations

import sqlite3
import tomllib
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trainer import history, supervise_set
from trainer import plan as plans
from trainer.coach import onboarding
from trainer.engine import catalog, config, database, enrichment, graph, mesocycles, migrations, residue

DEFAULT_PARTS = ("docs", "demo", "history.toml")


class DemoError(RuntimeError):
    """A demo that cannot be built as written, or a home that already holds one."""


@dataclass(frozen=True)
class Accepted:
    """One mesocycle of the history, the goal declared for it and the direction it was planned from."""

    name: str
    mesocycle: plans.Mesocycle
    goal: str | None = None
    direction: mesocycles.Direction | None = None


@dataclass(frozen=True)
class History:
    declared: Mapping[str, Any]
    accepted: tuple[Accepted, ...]
    loads: Mapping[str, float] = field(default_factory=dict)
    """The load in kg of every set of an exercise, by its id."""


def history_path() -> Path:
    """Where the committed history is read from."""
    return Path.cwd().joinpath(*DEFAULT_PARTS)


def parse(text: str) -> History:
    """A history out of its TOML, every mesocycle it names defined in it."""
    raw = tomllib.loads(text)
    declared = raw.get("declared")
    if not isinstance(declared, dict):
        raise DemoError("the history declares no [declared]")
    try:
        named = {name: supervise_set.mesocycle(name, one) for name, one in dict(raw.get("mesocycles", {})).items()}
    except supervise_set.SuperviseSetError as error:
        raise DemoError(str(error)) from error
    accepted = tuple(_accepted(at, entry, named) for at, entry in enumerate(raw.get("history", ())))
    if not accepted:
        raise DemoError("the history has no mesocycle")
    loads = {str(name): float(kg) for name, kg in dict(raw.get("loads", {})).items()}
    return History(declared=declared, accepted=accepted, loads=loads)


def _accepted(at: int, entry: Mapping[str, Any], named: Mapping[str, plans.Mesocycle]) -> Accepted:
    name = str(entry.get("mesocycle", ""))
    if name not in named:
        raise DemoError(f"no [mesocycles.{name}] in the history")
    goal = entry.get("goal")
    given = entry.get("direction")
    if given is None:
        return Accepted(name, named[name], None if goal is None else str(goal))
    if at == 0:
        raise DemoError(f"{name}: the first mesocycle of a history follows nothing, so it has no direction")
    try:
        direction = mesocycles.Direction(
            theme=str(given["theme"]),
            changes=str(given["changes"]),
            why=str(given["why"]),
            varies=tuple(str(one) for one in given.get("varies", ())),
        )
    except KeyError as error:
        raise DemoError(f"{name}: a direction has a theme, changes and why") from error
    if not direction.varies or not set(direction.varies) <= set(mesocycles.VARIES):
        raise DemoError(f"{name}: a direction varies some of {', '.join(mesocycles.VARIES)}")
    return Accepted(name, named[name], None if goal is None else str(goal), direction)


def build(home: Path, today: str, history: History | None = None) -> Path:
    """The demo's database in `home`, built from nothing; refused, writing nothing, when a mesocycle would be."""
    target = home / database.DEFAULT_DATABASE_NAME
    if target.exists():
        raise DemoError(f"{target} already exists; delete it to build the demo again")
    told = history if history is not None else _committed()
    building = target.with_name(target.name + ".building")
    building.unlink(missing_ok=True)
    try:
        with closing(database.connect(building)) as connection:
            _catalogued(connection)
            _performed(connection, told, today)
    except BaseException:
        building.unlink(missing_ok=True)
        raise
    building.replace(target)
    return target


def _committed() -> History:
    """The committed history; a state naming where it was looked for when it is not there."""
    where = history_path()
    try:
        text = where.read_text(encoding="utf-8")
    except OSError as error:
        raise DemoError(f"the demo's history is not at {where}; run it from the repository") from error
    return parse(text)


def _catalogued(connection: sqlite3.Connection) -> None:
    """The schema, the vendored catalog and its enrichment, as `db init`, `db import` and `enrich` leave them."""
    migrations.migrate(connection, migrations.discover())
    catalog.import_exercises(connection, catalog.load())
    enrichment.run(connection)
    residue.apply(connection, residue.load())
    graph.apply(connection, *graph.load())


def _performed(connection: sqlite3.Connection, told: History, today: str) -> None:
    """Every mesocycle accepted and performed as prescribed, but for the last workout of the last."""
    base = dict(told.declared)
    steps = sum(1 + len(one.mesocycle.workouts) * one.mesocycle.cycles for one in told.accepted) - 1
    on = date.fromisoformat(today) - timedelta(days=steps + 1)
    declaration = onboarding.settled(base)
    config.record(connection, declaration, on.isoformat())
    for at, one in enumerate(told.accepted):
        on += timedelta(days=1)
        if one.goal is not None and one.goal != declaration.goal:
            declaration = onboarding.settled({**base, "goal": one.goal})
            config.record(connection, declaration, on.isoformat())
        asked = plans.mesocycle_requested(connection, on.isoformat(), declared=declaration)
        refused = plans.validate_mesocycle(connection, one.mesocycle, asked)
        if refused:
            raise DemoError(
                "; ".join(f"[mesocycles.{one.name}] {violation.rule}: {violation.says}" for violation in refused)
            )
        on = history.performed_as_prescribed(
            connection,
            one.mesocycle,
            on,
            direction=one.direction,
            left=1 if at == len(told.accepted) - 1 else 0,
            loads=told.loads,
        )
