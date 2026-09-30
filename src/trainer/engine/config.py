"""What the user declares: the training configuration file.

Cycle length, the cap on a workout's duration, the split being trained, the
denominator volume is counted on, the equipment the user has, and the goal of
the mesocycle. ADR-0003 carries why these six live in a file and not in SQLite: **a file you read and
edit by hand, against rows you query.** SQLite keeps what the system measures
-- performed workouts, accumulated volume, exclusions and their re-test dates
-- and a declaration sitting beside them would have nothing to tell the two
apart.

The file lives in `TRAINER_HOME` with everything else this machine writes, and
not in the repository: it carries one user's own cap, split and equipment.

**This module reads. Nothing in `engine/` writes it.** Onboarding
(`coach/onboarding.py`) fills it by talking to the user, and the user may edit
it by hand.

TOML, because `tomllib` is in the standard library and the file has to survive
being edited by hand between sessions: comments stay where they were put, a
number is a number, and a changed cycle length is a one-line diff.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from trainer.engine import home, methodology, muscle_groups

CONFIG_ENV_VAR = "TRAINER_CONFIG"
"""Overrides the configuration's location, the way `TRAINER_DB` does for the
database -- tests point it at a throwaway file rather than the real one."""

DEFAULT_CONFIG_NAME = "training.toml"

EXAMPLE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "training.example.toml"
)
"""The committed example the missing-config state tells the user to copy.

Inside the package, resolved against `__file__` the way the muscle group
mapping is: the state's message names it by absolute path, and a path that
only exists in a source checkout would send a user running from anywhere else
to a file that is not there."""

DENOMINATORS = ("cycle",)
"""What volume may be counted over.

Not read from data, because it is not a vocabulary anything measured: it is the
partition the project draws, the way `catalog.STRENGTH_CATEGORY` is. One value
today -- CONTEXT.md is explicit that a week counts days and a user who trains
when they have time completes a rotation in a span no calendar decides. It is
written down rather than assumed because it is the user's call, and the day a
second denominator is actually implemented it joins this tuple.
"""

_KEYS = (
    "cycle_length",
    "duration_cap_min",
    "split",
    "volume_denominator",
    "equipment",
    "goal",
)
"""Everything the file holds, and nothing more. An unrecognised key is refused
rather than ignored: a misspelled `cycle_lenght` that is silently skipped is a
setting the user believes they changed and did not."""


class ConfigError(RuntimeError):
    """The training configuration is missing, or what it says is not usable."""


class NoTrainingConfig(ConfigError):
    """There is no configuration file at all.

    Its own class, and not a validation failure, because it is a **state**:
    nobody has declared anything yet, and reporting that as a complaint about a
    field nobody filled in sends the reader looking for a mistake they have not
    made. CLAUDE.md's standing rule, in the case it was written for.
    """

    def __init__(self, path: Path):
        super().__init__(
            f"no training configuration yet -- there is no {path}. "
            f"Copy {EXAMPLE_CONFIG_PATH} there and edit it: it declares the "
            "cycle length, the duration cap, the split, the volume "
            "denominator, the equipment you have and your goal."
        )
        self.path = path


class NoGoal(ConfigError):
    """The file predates the goal: a state with its fix, not a mistake in the file."""

    def __init__(self, goals: tuple[str, ...]):
        super().__init__(
            "no goal declared yet in training.toml. Add one line, "
            f'e.g. goal = "{goals[0]}"; the goals are {", ".join(goals)}, '
            "the columns of the methodology"
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
    """The minutes a workout is built to when no other time is asked for, give or take `plan.TOLERANCE_MIN`, and the most that may be asked for."""
    split: tuple[tuple[str, ...], ...]
    volume_denominator: str
    equipment: tuple[str, ...]
    """What the user has to train with, and the default a door plans against
    when nobody names equipment for today.

    Not checked against the catalog here, and that is the standing rule kept
    rather than broken: the vocabulary lives in the imported exercises, this
    module reads no database by design (ADR-0003), and a hand-copied list of
    equipment values is the thing the rule exists to forbid. An unknown value
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


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return home.inside(DEFAULT_CONFIG_NAME)


def load(path: Path | None = None) -> TrainingConfig:
    """Read the configuration, or say which of the ways it can be wrong it is."""
    target = path if path is not None else config_path()
    if not target.is_file():
        raise NoTrainingConfig(target)
    try:
        # `utf-8-sig` and not `utf-8`: Notepad writes a byte-order mark by
        # default, and TOML reads one as part of the first key -- a correct
        # file coming back as "Invalid statement at line 1, column 1", which
        # names nothing anyone can act on. Plain UTF-8 decodes the same way.
        raw = tomllib.loads(target.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{target.name} is not valid TOML: {error}") from error
    except UnicodeDecodeError as error:
        # The one file the README tells the user to hand-edit, so the editor
        # that saved it is not this project's choice. A Windows editor writing
        # cp1252 produces bytes TOML cannot be read from at all, and left
        # uncaught this reaches the terminal as a traceback about a codec.
        raise ConfigError(
            f"{target.name} is not UTF-8 ({error.reason}); TOML files are "
            "UTF-8, so re-save it in that encoding"
        ) from error
    return parse(raw)


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
    missing = [key for key in _KEYS if key not in raw and key != "goal"]
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
        goal=_goal(raw.get("goal"), goals),
    )


def _goal(value: object, goals: tuple[str, ...]) -> str:
    """One of the methodology's goals; absent is `NoGoal`, since files written before 0.11 have none."""
    if value is None:
        raise NoGoal(goals)
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
