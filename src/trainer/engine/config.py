"""What the user declares: the training configuration file.

Cycle length, the cap on a workout's duration, the split being trained, and the
denominator volume is counted on. ADR-0003 carries why these four live in a
committed file and not in SQLite: **the line is who writes the value.** SQLite
keeps what the system writes -- performed workouts, accumulated volume,
exclusions and their re-test dates. These four are declared by the user,
changed by hand, and read back by the user, and in a file `git diff` says when
the user changed their mind about the cycle, which is itself training history.

**This module reads. Nothing in `engine/` writes it.** Session 6's onboarding is
what fills the file by talking to the user; until then it is hand-written, and
`training.example.toml` is the committed example to start from.

TOML, because `tomllib` is in the standard library and the file has to survive
being edited by hand between sessions: comments stay where they were put, a
number is a number, and a changed cycle length is a one-line diff.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from trainer.engine import muscle_groups

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

_KEYS = ("cycle_length", "duration_cap_min", "split", "volume_denominator")
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
            "cycle length, the duration cap, the split and the volume "
            "denominator."
        )
        self.path = path


@dataclass(frozen=True)
class TrainingConfig:
    """The four declarations, typed.

    `split` is as long as `cycle_length` by construction -- the reader refuses a
    file where it is not -- so a caller indexing the split by position in the
    rotation can do so without checking.
    """

    cycle_length: int
    duration_cap_min: int
    split: tuple[tuple[str, ...], ...]
    volume_denominator: str

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
    return Path.cwd() / DEFAULT_CONFIG_NAME


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
    raw: dict[str, object], *, valid_groups: tuple[str, ...] | None = None
) -> TrainingConfig:
    """Validate a decoded configuration.

    `valid_groups` defaults to the six read from the committed mapping. It is a
    parameter so a test can drive the unknown-group error against a vocabulary
    it controls, never so a caller can bring one of its own.
    """
    groups = muscle_groups.groups() if valid_groups is None else valid_groups

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
            f"all four of {', '.join(_KEYS)} have to be declared"
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
    )


def _positive(key: str, value: object, unit: str) -> int:
    """A whole, positive count. Zero is refused and named, not clamped: a
    duration cap of zero says no workout may run at all, which is not a
    training configuration, it is a typo with a plausible shape."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} is a whole number of {unit}, got {value!r}")
    if value <= 0:
        raise ConfigError(f"{key} has to be at least 1, got {value}")
    return value


def _split(
    value: object, cycle_length: int, groups: tuple[str, ...]
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or any(not isinstance(item, list) for item in value):
        raise ConfigError(
            "split is a list of one group list per workout, "
            'e.g. [["chest", "arms"], ["back", "core"]]'
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
                "group name"
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
        for name in names:
            if name not in groups:
                raise ConfigError(
                    f"workout {position} of the split names {name!r}, which is "
                    f"not a muscle group; they are {', '.join(groups)}"
                )
        workouts.append(names)
    return tuple(workouts)
