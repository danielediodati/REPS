"""The methodology the planner reasons with, and the goals read from its ranges table.

`src/trainer/data/methodology.md` is written by a person from the literature
(TRAINER.md). The planner reads it whole; the engine reads only its goal
columns, which are the vocabulary the declared `goal` is checked against.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

METHODOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "methodology.md"

RANGES_HEADING = "## Ranges by goal"
SOURCES_HEADING = "## Sources"


class MethodologyError(RuntimeError):
    """The methodology file on disk is not usable."""


@dataclass(frozen=True)
class Methodology:
    """The document, and the goals its ranges table has a column for."""

    text: str
    goals: tuple[str, ...]

    @property
    def for_planner(self) -> str:
        """The document without its list of sources."""
        return self.text.split(SOURCES_HEADING, 1)[0].rstrip() + "\n"


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
