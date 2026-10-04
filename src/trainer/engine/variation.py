"""The methodology between mesocycles, which the supervisor reasons with and the planner never reads (ADR-0014 item 7)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from trainer.engine import methodology

VARIATION_PATH = methodology.METHODOLOGY_PATH.with_name("variation.md")


class VariationError(RuntimeError):
    """The variation file on disk is not usable."""


@dataclass(frozen=True)
class Variation:
    """The document as written, sources included."""

    text: str

    @property
    def for_supervisor(self) -> str:
        """The document without its list of sources."""
        return self.text.split(methodology.SOURCES_HEADING, 1)[0].rstrip() + "\n"


def load(path: Path = VARIATION_PATH) -> Variation:
    if not path.is_file():
        raise VariationError(f"no variation methodology at {path}")
    return Variation(text=path.read_text(encoding="utf-8"))


@cache
def committed() -> Variation:
    """The variation methodology that ships with the package."""
    return load()
