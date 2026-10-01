"""What the user declares: cycle, cap, split, denominator, equipment and goal, one version per change.

The versions are rows in the database (ADR-0013). Onboarding writes them; this
module reads them, records one, and imports a `training.toml` left by an
installation from before, once.
"""

from __future__ import annotations

import json
import sqlite3
import tomllib
from dataclasses import dataclass
from datetime import date

from trainer.engine import home, methodology, muscle_groups

LEGACY_NAME = "training.toml"
"""The file the declarations lived in before ADR-0013, imported once from the home."""

DENOMINATORS = ("cycle",)
"""What volume may be counted over.

Not read from data, because it is not a vocabulary anything measured: it is the
partition the project draws, the way `catalog.STRENGTH_CATEGORY` is. One value
today -- CONTEXT.md is explicit that a week counts days and a user who trains
when they have time completes a rotation in a span no calendar decides.
"""

_KEYS = (
    "cycle_length",
    "duration_cap_min",
    "split",
    "volume_denominator",
    "equipment",
    "goal",
)
"""Every declaration, and nothing more. An unrecognised key is refused rather
than ignored: a misspelled `cycle_lenght` that is silently skipped is a
setting the user believes they changed and did not."""


class ConfigError(RuntimeError):
    """The declarations are missing, or what they say is not usable."""


class NoTrainingConfig(ConfigError):
    """Nothing has been declared yet: a state, whose fix is the bot's interview."""

    def __init__(self, why: str = ""):
        super().__init__(
            "nothing declared yet: write to the bot, and it asks about your goal, "
            "rotation, time and equipment"
            + (f" ({why})" if why else "")
        )


@dataclass(frozen=True)
class TrainingConfig:
    """The six declarations, typed.

    `split` is as long as `cycle_length` by construction -- the reader refuses a
    file where it is not -- so a caller indexing the split by position in the
    rotation can do so without checking.
    """

    cycle_length: int
    duration_cap_min: int
    """The minutes a workout is built to when no other time is asked for, give or take `plan.TOLERANCE_MIN`, and the most that may be asked for except by an adaptation."""
    split: tuple[tuple[str, ...], ...]
    volume_denominator: str
    equipment: tuple[str, ...]
    """What the user has to train with, and the default a door plans against
    when nobody names equipment for today.

    Not checked against the catalog here, and that is the standing rule kept
    rather than broken: the vocabulary lives in the imported exercises, parsing
    reads no catalog, and a hand-copied list of equipment values is the thing the rule exists to forbid. An unknown value
    is refused where the catalog is open, by `admissible_set`, which names the
    ones that exist.
    """

    goal: str
    """One of the methodology's goal columns; changing it is a new mesocycle."""

    def groups_for(self, workout: int) -> tuple[str, ...]:
        """The groups the `workout`-th workout of the cycle trains, counted
        from 1 the way the user counts them when writing the file.

        `IndexError` and not `ConfigError` for a position outside the cycle:
        the configuration is fine, the caller asked for a workout that is not
        in it. A `ConfigError` here reaches the terminal as *«the training
        configuration is unusable»* and sends the user to edit a file that has
        nothing wrong with it.
        """
        if not 1 <= workout <= self.cycle_length:
            raise IndexError(
                f"workout {workout} is outside a cycle of {self.cycle_length}; "
                f"the workouts are numbered 1 to {self.cycle_length}"
            )
        return self.split[workout - 1]


@dataclass(frozen=True)
class Version:
    """One set of declarations, and the day it was declared."""

    id: int
    declared_on: str
    declaration: TrainingConfig


def load(connection: sqlite3.Connection) -> TrainingConfig:
    """The declarations in force, or `NoTrainingConfig`."""
    return current(connection).declaration


def declared(connection: sqlite3.Connection) -> TrainingConfig | None:
    """The declarations in force, or `None` when nothing is declared yet."""
    try:
        return load(connection)
    except NoTrainingConfig:
        return None


def current(connection: sqlite3.Connection) -> Version:
    """The version in force, importing a legacy `training.toml` when there is none."""
    found = versions(connection, latest=True)
    if found:
        return found[0]
    return _imported(connection)


def versions(connection: sqlite3.Connection, latest: bool = False) -> tuple[Version, ...]:
    """Every version, newest first; only the newest when `latest`."""
    rows = connection.execute(
        "SELECT * FROM declarations ORDER BY id DESC" + (" LIMIT 1" if latest else "")
    ).fetchall()
    return tuple(
        Version(
            id=int(row["id"]),
            declared_on=str(row["declared_on"]),
            declaration=parse(
                {
                    "cycle_length": row["cycle_length"],
                    "duration_cap_min": row["duration_cap_min"],
                    "split": json.loads(row["split"]),
                    "volume_denominator": row["volume_denominator"],
                    "equipment": json.loads(row["equipment"]),
                    "goal": row["goal"],
                }
            ),
        )
        for row in rows
    )


def record(connection: sqlite3.Connection, declaration: TrainingConfig, on: str) -> int:
    """Add a version, in force from now; the caller holds the transaction."""
    cursor = connection.execute(
        "INSERT INTO declarations (declared_on, cycle_length, duration_cap_min, split, "
        "volume_denominator, equipment, goal) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            on,
            declaration.cycle_length,
            declaration.duration_cap_min,
            json.dumps(declaration.split),
            declaration.volume_denominator,
            json.dumps(declaration.equipment),
            declaration.goal,
        ),
    )
    assert cursor.lastrowid is not None  # an INSERT always has one
    return cursor.lastrowid


def _imported(connection: sqlite3.Connection) -> Version:
    """A `training.toml` in the home, recorded as the first version; `NoTrainingConfig` without one."""
    legacy = home.inside(LEGACY_NAME)
    if not legacy.is_file():
        raise NoTrainingConfig()
    try:
        # `utf-8-sig`: Notepad writes a byte-order mark by default.
        declaration = parse(tomllib.loads(legacy.read_text(encoding="utf-8-sig")))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, ConfigError) as error:
        raise NoTrainingConfig(f"{legacy} could not be imported: {error}") from error
    on = date.today().isoformat()
    return Version(record(connection, declaration, on), on, declaration)


def parse(
    raw: dict[str, object],
    *,
    mapping: muscle_groups.MuscleGroups | None = None,
    valid_goals: tuple[str, ...] | None = None,
) -> TrainingConfig:
    """Validate a decoded configuration.

    `mapping` defaults to the committed muscle groups, and
    `valid_goals` to the methodology's columns. They are parameters so a test
    can drive the unknown-value errors against a vocabulary it controls, never
    so a caller can bring one of its own.
    """
    groups = muscle_groups.committed() if mapping is None else mapping
    goals = methodology.goals() if valid_goals is None else valid_goals

    unknown = sorted(set(raw) - set(_KEYS))
    if unknown:
        raise ConfigError(
            f"unrecognised setting(s) {', '.join(repr(key) for key in unknown)}; "
            f"the configuration holds {', '.join(_KEYS)} and nothing else"
        )
    missing = [key for key in _KEYS if key not in raw]
    if missing:
        raise ConfigError(
            f"the configuration is missing {', '.join(missing)}; "
            f"all {len(_KEYS)} of {', '.join(_KEYS)} have to be declared"
        )

    cycle_length = _positive("cycle_length", raw["cycle_length"], "workouts")
    duration_cap_min = _positive("duration_cap_min", raw["duration_cap_min"], "minutes")

    denominator = raw["volume_denominator"]
    if denominator not in DENOMINATORS:
        raise ConfigError(
            f"volume_denominator is {denominator!r}; it has to be one of "
            f"{', '.join(repr(value) for value in DENOMINATORS)}"
        )

    return TrainingConfig(
        cycle_length=cycle_length,
        duration_cap_min=duration_cap_min,
        split=_split(raw["split"], cycle_length, groups),
        volume_denominator=str(denominator),
        equipment=_equipment(raw["equipment"]),
        goal=_goal(raw["goal"], goals),
    )


def _goal(value: object, goals: tuple[str, ...]) -> str:
    """One of the methodology's goals."""
    if value not in goals:
        raise ConfigError(
            f"goal is {value!r}, which is not a goal of the methodology; "
            f"the goals are {', '.join(goals)}"
        )
    return str(value)


def _positive(key: str, value: object, unit: str) -> int:
    """A whole, positive count. Zero is refused and named, not clamped: a
    duration cap of zero says no workout may run at all, which is not a
    training configuration, it is a typo with a plausible shape."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} is a whole number of {unit}, got {value!r}")
    if value <= 0:
        raise ConfigError(f"{key} has to be at least 1, got {value}")
    return value


def _equipment(value: object) -> tuple[str, ...]:
    """The equipment the user has, as the catalog spells it.

    At least one entry, because a file declaring nothing to train with is a
    declaration no plan can be made against -- and "body only" is what the
    catalog calls having none.
    """
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(
            "equipment is a list of the values the catalog uses, "
            'e.g. ["body only", "dumbbell"]'
        )
    names = tuple(str(item).strip() for item in value)
    if not names or any(not name for name in names):
        raise ConfigError(
            "equipment declares nothing to train with; name at least one "
            'value, and "body only" is what the catalog calls having none'
        )
    if len(set(names)) != len(names):
        twice = sorted({name for name in names if names.count(name) > 1})
        raise ConfigError(f"equipment names {', '.join(twice)} more than once")
    return names


def _split(
    value: object, cycle_length: int, groups: muscle_groups.MuscleGroups
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or any(not isinstance(item, list) for item in value):
        raise ConfigError(
            "split is a list of one list of groups or muscles per workout, "
            'e.g. [["chest", "triceps"], ["back", "core"]]'
        )
    if len(value) != cycle_length:
        raise ConfigError(
            f"the split declares {len(value)} workout(s) but the cycle is "
            f"{cycle_length} workout(s) long; the split holds one entry per "
            "workout of the cycle"
        )

    workouts: list[tuple[str, ...]] = []
    for position, entry in enumerate(value, start=1):
        assert isinstance(entry, list)
        if any(not isinstance(name, str) for name in entry):
            raise ConfigError(
                f"workout {position} of the split holds something that is not a "
                "group or muscle name"
            )
        names = tuple(str(name) for name in entry)
        if not names:
            raise ConfigError(
                f"workout {position} of the split trains nothing; every workout "
                "of the cycle trains at least one group"
            )
        if len(set(names)) != len(names):
            twice = sorted({name for name in names if names.count(name) > 1})
            raise ConfigError(
                f"workout {position} of the split names {', '.join(twice)} "
                "more than once"
            )
        try:
            groups.muscles_in(names)
        except ValueError as error:
            raise ConfigError(f"workout {position} of the split: {error}") from error
        workouts.append(names)
    return tuple(workouts)
