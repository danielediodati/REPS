"""The methodology the planner reasons with, and the goals read from it."""

from __future__ import annotations

from pathlib import Path

import pytest

from trainer.engine import methodology

RANGES = """\
# Methodology

## Ranges by goal

| | power | stamina |
|---|---|---|
| reps per set | 1–3 | 20–40 |

## Principles

Compound before isolation.

## Sources

1. Somebody. A paper.
"""


def test_the_goals_are_the_columns_of_the_ranges_table() -> None:
    assert methodology.parse(RANGES).goals == ("power", "stamina")


def test_the_committed_methodology_ships_with_the_package() -> None:
    """It is read by the planner at run time, so it cannot live under `docs/`."""
    assert methodology.METHODOLOGY_PATH.is_file()
    assert "trainer" in methodology.METHODOLOGY_PATH.parts
    assert methodology.goals()


def test_the_planner_reads_everything_but_the_sources() -> None:
    """The references are for a person checking a claim; the model reasons with the rest."""
    read = methodology.parse(RANGES).for_planner

    assert "Compound before isolation." in read
    assert "| power | stamina |" in read
    assert "A paper" not in read
    assert "Sources" not in read


def test_a_methodology_with_no_ranges_table_is_refused() -> None:
    with pytest.raises(methodology.MethodologyError, match="Ranges by goal"):
        methodology.parse("# Methodology\n\n## Principles\n\nNothing.\n")


def test_a_ranges_section_with_no_goal_column_is_refused() -> None:
    with pytest.raises(methodology.MethodologyError, match="no goal"):
        methodology.parse("## Ranges by goal\n\n| |\n|---|\n| reps | \n")


def test_a_missing_file_says_where_it_was_looked_for(tmp_path: Path) -> None:
    absent = tmp_path / "methodology.md"

    with pytest.raises(methodology.MethodologyError, match=str(absent).replace("\\", "\\\\")):
        methodology.load(absent)


def test_a_header_with_no_row_label_column_is_refused_rather_than_losing_a_goal() -> None:
    """Without the blank first cell, the first goal would be read as the row-label column and silently dropped."""
    with pytest.raises(methodology.MethodologyError, match="blank"):
        methodology.parse("## Ranges by goal\n\n| power | stamina |\n|---|---|\n")
