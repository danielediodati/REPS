"""The shared tool surface: the answers, and the states that are not answers.

`tests/test_mcp_server.py` checks that one door serves exactly what is defined
here. This file checks what the definitions actually do -- the new tool, the
shaping, and the three preconditions that have to arrive as states with the
command that fixes them rather than as a plausible-looking empty answer.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import enrich, make_exercise
from trainer import tools
from trainer.engine import catalog, database, graph, migrations

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Dumbbell_Squat",
        name="Dumbbell Squat",
        equipment="dumbbell",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        primary_muscles=("quadriceps",),
    ),
    make_exercise(
        id="Standing_Military_Press", name="Standing Military Press", equipment="barbell"
    ),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Dumbbell_Squat": ("squat", "hip, knee, ankle", "yes", "medium", 1),
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
}

GRAPH = """\
# A throwaway graph

## Variant groups

| representative | member | note |
|---|---|---|
| `Barbell_Squat` | `Dumbbell_Squat` | the same squat, held at the sides |

## Regression edges

| easier | harder | note |
|---|---|---|
| `Bodyweight_Squat` | `Barbell_Squat` | the same squat, no load yet |
"""


@pytest.fixture()
def stocked(database_file: Path) -> Iterator[sqlite3.Connection]:
    """A database the tools will find: `TRAINER_DB` points them at it."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        graph.apply(opened, *graph.parse(GRAPH))
        yield opened


# -- compare_variants, the tool this ticket adds ------------------------------


def test_compare_variants_answers_with_the_four_fields(
    stocked: sqlite3.Connection,
) -> None:
    """TRAINER.md names them beside the call: movement pattern, loaded joints,
    required stability, setup cost."""
    found = tools.compare_variants("Barbell_Squat", "Dumbbell_Squat")

    for side in (found["a"], found["b"]):
        assert side["movement_pattern"] == "squat"
        assert side["loaded_joints"] == ["hip", "knee", "ankle"]
        assert side["required_stability"] in ("high", "medium")
        assert isinstance(side["setup_cost_min"], int)
    assert found["a"]["required_stability"] != found["b"]["required_stability"]


def test_compare_variants_says_two_members_of_a_group_are_one_movement(
    stocked: sqlite3.Connection,
) -> None:
    found = tools.compare_variants("Dumbbell_Squat", "Barbell_Squat")

    assert found["same_movement"] is True
    assert found["easier"] is None


def test_compare_variants_names_the_easier_of_a_regression_pair(
    stocked: sqlite3.Connection,
) -> None:
    found = tools.compare_variants("Barbell_Squat", "Bodyweight_Squat")

    assert found["easier"] == "Bodyweight_Squat"
    assert found["same_movement"] is False


def test_compare_variants_says_so_when_the_graph_relates_nothing(
    stocked: sqlite3.Connection,
) -> None:
    """Not an empty answer, which reads as *these two have nothing in common*
    whether the graph says nothing or the ids were wrong."""
    found = tools.compare_variants("Barbell_Squat", "Standing_Military_Press")

    assert found["same_movement"] is False
    assert found["easier"] is None
    assert "neither" in found["summary"]
    assert found["a"]["movement_pattern"] != found["b"]["movement_pattern"]


def test_compare_variants_names_an_id_the_catalog_does_not_have(
    stocked: sqlite3.Connection,
) -> None:
    with pytest.raises(tools.ToolFailure, match="Barbell_Sqvat"):
        tools.compare_variants("Barbell_Squat", "Barbell_Sqvat")


def test_compare_variants_asks_the_same_question_of_an_id_and_itself(
    stocked: sqlite3.Connection,
) -> None:
    """Read off the edges alone this answers *the same movement* for a group
    member, whose two sides share a `variant_of`, and *neither* for the
    representative of that same group -- one question, two answers, decided by
    where in the graph the id happens to sit."""
    member = tools.compare_variants("Dumbbell_Squat", "Dumbbell_Squat")
    representative = tools.compare_variants("Barbell_Squat", "Barbell_Squat")

    assert member["same_movement"] is representative["same_movement"] is True
    assert member["summary"] == representative["summary"] == "the same exercise"


def test_compare_variants_refuses_a_catalog_the_graph_was_never_applied_to(
    database_file: Path,
) -> None:
    """`trainer enrich curated` is a command of its own. Without it every pair
    comes back *neither the same movement nor a regression of one another* --
    a decided no, indistinguishable from a real one, and the running example
    TRAINER.md is built on is the first casualty."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)

    with pytest.raises(tools.ToolFailure, match="trainer enrich curated"):
        tools.compare_variants("Barbell_Squat", "Dumbbell_Squat")


# -- the preconditions, stated once and with the way out ----------------------


def test_a_missing_database_is_a_state_with_its_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`no such table: exercises` names neither the state nor the way out."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))

    with pytest.raises(tools.ToolFailure, match="trainer db init"):
        tools.admissible_set(equipment=["barbell"], budget_min=45)


def test_a_database_behind_this_checkout_is_a_state_with_its_remedy(
    stocked: sqlite3.Connection,
) -> None:
    stocked.execute(
        "DELETE FROM schema_migrations WHERE version = (SELECT MAX(version) "
        "FROM schema_migrations)"
    )

    with pytest.raises(tools.ToolFailure, match="trainer db init"):
        tools.admissible_set(equipment=["barbell"], budget_min=45)


def test_an_empty_catalog_is_a_state_with_its_remedy(database_file: Path) -> None:
    """A vocabulary read from an empty table is empty, so every correct value
    would come back rejected as a typo. CLAUDE.md's standing rule."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())

    with pytest.raises(tools.ToolFailure, match="trainer db import"):
        tools.compare_variants("Barbell_Squat", "Dumbbell_Squat")


def test_an_unenriched_catalog_is_a_state_with_its_remedy(database_file: Path) -> None:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)

    with pytest.raises(tools.ToolFailure, match="trainer enrich derive"):
        tools.admissible_set(equipment=["barbell"], budget_min=45)


def test_arithmetic_needs_no_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`allocate` opens no connection. A tool that opened one it does not read
    would make a missing database look like a failure of the arithmetic."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))

    assert tools.allocate(minutes=30, proportions={"legs": 1.0}) == {"legs": 30}


# -- the surface itself -------------------------------------------------------


def test_every_tool_is_documented_and_annotated() -> None:
    """The docstring is what a model reads to decide whether to call the tool,
    and the annotations are what both doors build a schema from."""
    for tool in tools.TOOLS:
        assert tool.__doc__, f"{tool.__name__} has no description"
        assert "return" in tool.__annotations__, f"{tool.__name__} has no return type"


def test_the_tools_with_nothing_to_wrap_are_not_here() -> None:
    """`adherence_history` needs `workouts` and `active_conclusions` needs
    `conclusions`; neither table exists."""
    named = {tool.__name__ for tool in tools.TOOLS}

    assert "adherence_history" not in named
    assert "active_conclusions" not in named
