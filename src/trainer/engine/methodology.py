"""The methodology the planner reasons with, and the goals read from its ranges table.

`src/trainer/data/methodology.md` is written by a person from the literature
(TRAINER.md). The planner reads it whole; the engine reads only its goal
columns, which are the vocabulary the declared `goal` is checked against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

METHODOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "methodology.md"

RANGES_HEADING = "## Ranges by goal"
SOURCES_HEADING = "## Sources"
REPS_ROW = "reps per set"
REST_ROW = "rest between sets"
SECONDS = {"s": 1, "min": 60}


class MethodologyError(RuntimeError):
    """The methodology file on disk is not usable."""


@dataclass(frozen=True)
class Bounds:
    """One goal's reps per set and rest between sets in seconds, lowest and highest."""

    reps: tuple[int, int]
    rest: tuple[int, int]


@dataclass(frozen=True)
class Methodology:
    """The document, and the goals its ranges table has a column for."""

    text: str
    goals: tuple[str, ...]

    @property
    def for_planner(self) -> str:
        """The document without its list of sources."""
        return self.text.split(SOURCES_HEADING, 1)[0].rstrip() + "\n"

    @property
    def ranges(self) -> str:
        """The ranges section alone, heading included."""
        _, _, after = self.text.partition(RANGES_HEADING)
        return RANGES_HEADING + after.split("\n## ", 1)[0].rstrip() + "\n"

    def bounds(self, goal: str) -> Bounds:
        """The goal's column of the ranges table, as reps and seconds of rest."""
        if goal not in self.goals:
            raise MethodologyError(f"the ranges table has no column for {goal!r}")
        rows = {
            cells[0]: cells[1:]
            for line in self.ranges.splitlines()
            if line.strip().startswith("|")
            for cells in [[cell.strip() for cell in line.strip().strip("|").split("|")]]
        }
        column = self.goals.index(goal)
        try:
            reps, rest = rows[REPS_ROW][column], rows[REST_ROW][column]
        except (KeyError, IndexError) as error:
            raise MethodologyError(
                f"the ranges table needs a {REPS_ROW!r} and a {REST_ROW!r} row"
            ) from error
        low, high = _span(reps.split(",", 1)[0])
        rest_low, rest_high = _span(rest)
        return Bounds(
            reps=(int(low[0]), int(high[0])),
            rest=(_seconds(*rest_low), _seconds(*rest_high)),
        )


def _span(cell: str) -> tuple[tuple[str, str | None], tuple[str, str | None]]:
    """`45 s–2 min` as its two ends, each a number and its unit; an end with none takes the other's."""
    ends = [re.fullmatch(r"(\d+)\s*([a-z]*)", end.strip()) for end in re.split("[–-]", cell)]
    if len(ends) != 2 or ends[0] is None or ends[1] is None:
        raise MethodologyError(f"{cell!r} is not a range like 6–15 or 45 s–2 min")
    (low, low_unit), (high, high_unit) = ends[0].groups(), ends[1].groups()
    return (low, low_unit or high_unit or None), (high, high_unit or None)


def _seconds(amount: str, unit: str | None) -> int:
    if unit not in SECONDS:
        raise MethodologyError(f"{amount} {unit or ''} is not a time in s or min")
    return int(amount) * SECONDS[unit]


def parse(text: str) -> Methodology:
    """Read the goals off the header row of the first table under the ranges heading."""
    _, found, after = text.partition(RANGES_HEADING)
    if not found:
        raise MethodologyError(f"the methodology has no {RANGES_HEADING!r} section")
    section = after.split("\n## ", 1)[0]
    header = next(
        (line.strip() for line in section.splitlines() if line.strip().startswith("|")),
        None,
    )
    cells = [] if header is None else [cell.strip() for cell in header.strip("|").split("|")]
    if cells and cells[0]:
        raise MethodologyError(
            f"the {RANGES_HEADING!r} table's header starts with {cells[0]!r}; its "
            "first cell is blank, over the column that names each row"
        )
    goals = tuple(cell for cell in cells[1:] if cell)
    if not goals:
        raise MethodologyError(
            f"the {RANGES_HEADING!r} table has no goal column; its header row "
            "names one goal per column after the first"
        )
    return Methodology(text=text, goals=goals)


def load(path: Path = METHODOLOGY_PATH) -> Methodology:
    if not path.is_file():
        raise MethodologyError(f"no methodology at {path}")
    return parse(path.read_text(encoding="utf-8"))


@cache
def committed() -> Methodology:
    """The methodology that ships with the package."""
    return load()


def goals() -> tuple[str, ...]:
    """The goals the committed methodology has ranges for."""
    return committed().goals
