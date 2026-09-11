"""What limits training today, answered in one place so no door can forget a part of it."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trainer.engine import config
from trainer.engine import exclusions as exclusion_state
from trainer.engine.exclusions import Exclusion


class ConstraintError(RuntimeError):
    """A request today's declarations refuse, stated with the way out."""


@dataclass(frozen=True)
class Constraints:
    """What narrows today's admissible set, gathered before it is asked for.

    Not every constraint CONTEXT.md names: a preference leaves the set
    standing and travels with the request instead.
    """

    exclusions: tuple[Exclusion, ...]
    budget_min: int
    groups: tuple[str, ...]


def constraining_today(
    connection: sqlite3.Connection,
    today: str,
    *,
    budget_min: int,
    groups: Sequence[str] = (),
    given: Sequence[Exclusion] = (),
) -> Constraints:
    """The standing exclusions as of `today`, plus the ones this caller adds, with the time and the groups asked for."""
    standing = exclusion_state.active(connection, today)
    return Constraints(
        # Deduplicated: a caller that already folded the standing ones into
        # what it passes -- `trainer plan` does -- would otherwise send each
        # of them twice.
        exclusions=tuple(dict.fromkeys((*standing, *given))),
        budget_min=within_the_cap(budget_min),
        groups=tuple(groups),
    )


def within_the_cap(budget_min: int) -> int:
    """The minutes asked for, refused rather than clamped when a shorter cap is declared."""
    try:
        declared = config.load()
    except config.NoTrainingConfig:
        # Nobody has declared a cap, so there is no ceiling to be over.
        return budget_min
    if budget_min > declared.duration_cap_min:
        raise ConstraintError(
            f"{budget_min} minutes is over the {declared.duration_cap_min} "
            f"declared as the cap in {config.config_path().name}; ask for at "
            f"most that, or raise the cap there"
        )
    return budget_min
