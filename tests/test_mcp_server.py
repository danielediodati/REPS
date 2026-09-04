"""The MCP wrapper: the same answers the library gives, through the other door.

Two things are checked here and nothing else. That a generic client sees five
tools with usable schemas, and that each one returns what the equivalent direct
library call returns -- because the moment the two disagree, the wrapper has
grown logic, which is the one thing this module is not allowed to have.

`server.call_tool` is what an MCP client's request lands on after the transport
has decoded it, so calling it directly exercises the wrapper without a socket:
`conftest.py` takes the network away from the whole suite, and a server that
needed one to be tested would be a server the tests cannot honestly cover.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from conftest import enrich, make_exercise
from trainer import mcp_server
from trainer.engine import admissible, budget, catalog, database, migrations, state
from trainer.engine.duration import Block, BlockItem
from trainer.engine.exclusions import Exclusion

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Standing_Military_Press", name="Standing Military Press", equipment="barbell"
    ),
    make_exercise(
        id="Bodyweight_Squat",
        name="Bodyweight Squat",
        equipment="body only",
        primary_muscles=("quadriceps",),
    ),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
    "Bodyweight_Squat": ("squat", "hip, knee, ankle", "no", "medium", 0),
}

TOOLS = (
    "admissible_set",
    "remaining_budget",
    "allocate",
    "pattern_history",
    "last_performed_load",
)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    """A database the tools will find: `TRAINER_DB` points the wrapper at it."""
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


_LOOP = asyncio.SelectorEventLoop()
"""Built at import, deliberately, and a selector loop rather than the Windows
default.

`conftest.no_network` replaces `socket.socket` -- the class -- with a function
that raises, which is what makes the suite's no-network guarantee real. An
event loop built after that cannot create its own wake-up pipe, and the
Proactor loop additionally runs `isinstance(conn, socket.socket)` on every
poll, which raises `TypeError` against a function and hangs the run. Building
one loop here, at collection time, gives every test a loop whose pipe already
exists; nothing in this module ever opens a socket of its own, so the guarantee
stands.
"""
atexit.register(_LOOP.close)


def call(name: str, **arguments: Any) -> Any:
    """One tool call, as a client makes it, with the payload read back.

    `structured_content` is what a modern client reads; the JSON text block is
    the fallback the SDK renders beside it, and falling back to parsing that is
    how this asserts on what actually goes over the wire rather than on a
    Python object.
    """
    result = _LOOP.run_until_complete(mcp_server.server.call_tool(name, arguments))
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        # A tool returning something that is not an object is wrapped under
        # `result` by the SDK, because JSON Schema has no way to describe a
        # bare integer as a tool's output.
        return structured["result"] if set(structured) == {"result"} else structured
    return json.loads(result.content[0].text)  # type: ignore[union-attr]


# -- what a generic client sees -----------------------------------------------


def test_all_five_tools_are_listed() -> None:
    listed = _LOOP.run_until_complete(mcp_server.server.list_tools())

    assert {tool.name for tool in listed} == set(TOOLS)


def test_every_tool_has_a_usable_schema_and_a_description() -> None:
    """A tool a client cannot fill in the arguments for is a tool it cannot
    call, which makes the inspector this session bought worth nothing."""
    for tool in _LOOP.run_until_complete(mcp_server.server.list_tools()):
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert schema.get("properties"), f"{tool.name} declares no arguments"
        assert tool.description, f"{tool.name} has no description"


def test_the_tools_are_exactly_this_session_s_surface() -> None:
    """`adherence_history`, `compare_variants` and `active_conclusions` are in
    TRAINER.md's tool surface and have nothing to wrap yet. A tool that exists
    and cannot work is worse than one that does not exist."""
    listed = {tool.name for tool in _LOOP.run_until_complete(mcp_server.server.list_tools())}

    assert "adherence_history" not in listed
    assert "compare_variants" not in listed
    assert "active_conclusions" not in listed


# -- the same answers as a direct call ----------------------------------------


def test_admissible_set_matches_the_library(connection: sqlite3.Connection) -> None:
    direct = admissible.admissible_set(connection, [], ["barbell"], 45)

    through_mcp = call("admissible_set", equipment=["barbell"], budget_min=45)

    assert [row["id"] for row in through_mcp] == [found.id for found in direct]
    assert through_mcp[0]["name"] == direct[0].name


def test_admissible_set_honours_an_exclusion(connection: sqlite3.Connection) -> None:
    direct = admissible.admissible_set(
        connection, [Exclusion("pattern", "vertical push")], ["barbell"], 45
    )

    through_mcp = call(
        "admissible_set",
        equipment=["barbell"],
        budget_min=45,
        exclusions=[{"granularity": "pattern", "value": "vertical push"}],
    )

    assert [row["id"] for row in through_mcp] == [found.id for found in direct]
    assert "Standing_Military_Press" not in [row["id"] for row in through_mcp]


def test_an_exercise_crosses_the_wire_whole(connection: sqlite3.Connection) -> None:
    """Nothing is dropped in the shaping: the row a client reads is the row the
    library returned, tuples turned into lists and nothing else."""
    (found,) = [
        row
        for row in call("admissible_set", equipment=["body only"], budget_min=45)
        if row["id"] == "Bodyweight_Squat"
    ]
    direct = catalog.exercise(connection, "Bodyweight_Squat")

    assert direct is not None
    assert found["name"] == direct.name
    assert found["primary_muscles"] == list(direct.primary_muscles)
    assert set(found) == {field for field in direct.__dataclass_fields__}


def test_remaining_budget_matches_the_library(connection: sqlite3.Connection) -> None:
    plan = [Block(items=(BlockItem("Barbell_Squat", reps=8),), rounds=4, rest=150)]
    direct = budget.remaining_budget(connection, plan, 40)

    through_mcp = call(
        "remaining_budget",
        partial_plan=[
            {
                "items": [{"exercise_id": "Barbell_Squat", "reps": 8}],
                "rounds": 4,
                "rest": 150,
            }
        ],
        budget_min=40,
    )

    assert through_mcp == direct


def test_remaining_budget_costs_a_superset_as_a_superset(
    connection: sqlite3.Connection,
) -> None:
    """The block vocabulary survives the wire -- two exercises in one block are
    not two adjacent blocks, and that is the whole of ADR-0002."""
    superset = [
        {
            "items": [
                {"exercise_id": "Barbell_Squat", "reps": 8},
                {"exercise_id": "Standing_Military_Press", "reps": 8},
            ],
            "rounds": 3,
            "rest": 120,
        }
    ]
    apart = [
        {"items": [{"exercise_id": "Barbell_Squat", "reps": 8}], "rounds": 3, "rest": 120},
        {
            "items": [{"exercise_id": "Standing_Military_Press", "reps": 8}],
            "rounds": 3,
            "rest": 120,
        },
    ]

    assert call("remaining_budget", partial_plan=superset, budget_min=60) > call(
        "remaining_budget", partial_plan=apart, budget_min=60
    )


def test_remaining_budget_is_negative_when_the_plan_is_over(
    connection: sqlite3.Connection,
) -> None:
    """Not clamped at zero across the wire either: how far over is what the
    caller acts on, and this engine never trims a plan to fit."""
    through_mcp = call(
        "remaining_budget",
        partial_plan=[
            {
                "items": [{"exercise_id": "Barbell_Squat", "reps": 10}],
                "rounds": 8,
                "rest": 180,
            }
        ],
        budget_min=10,
    )

    assert through_mcp < 0


def test_allocate_matches_the_library() -> None:
    direct = budget.allocate(40, {"chest": 0.6, "arms": 0.4})

    through_mcp = call("allocate", minutes=40, proportions={"chest": 0.6, "arms": 0.4})

    assert through_mcp == direct


def test_allocate_needs_no_database() -> None:
    """It is arithmetic. A tool that opened a connection it does not read would
    make a missing database look like a failure of the arithmetic."""
    assert call("allocate", minutes=30, proportions={"legs": 1.0}) == {"legs": 30}


def test_pattern_history_answers_that_it_does_not_know(
    connection: sqlite3.Connection,
) -> None:
    direct = state.pattern_history(connection, "squat", 3)

    through_mcp = call("pattern_history", pattern="squat", cycles=3)

    assert through_mcp["known"] is False
    assert through_mcp["value"] is None
    assert through_mcp["about"] == direct.about


def test_pattern_history_carries_real_history_when_there_is_some(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "INSERT INTO pattern_state (movement_pattern, cycle_volume, load_trend, pain) "
        "VALUES ('squat', 42, 'up', 'none')"
    )

    through_mcp = call("pattern_history", pattern="squat", cycles=3)

    assert through_mcp["known"] is True
    assert through_mcp["value"]["volume"] == 42
    assert through_mcp["value"]["axis"] == "pattern"


def test_last_performed_load_answers_that_it_does_not_know(
    connection: sqlite3.Connection,
) -> None:
    through_mcp = call("last_performed_load", exercise_id="Barbell_Squat")

    assert through_mcp["known"] is False
    assert through_mcp["value"] is None


# -- errors surface as tool errors, never as a crashed server -----------------


def test_an_unenriched_catalog_surfaces_as_a_tool_error(database_file: Path) -> None:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)

    with pytest.raises(ToolError, match="enrich derive"):
        call("admissible_set", equipment=["barbell"], budget_min=45)


def test_an_unknown_pattern_surfaces_as_a_tool_error(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(ToolError, match="no such pattern"):
        call("pattern_history", pattern="vertical yeet", cycles=3)


def test_an_unknown_exercise_id_surfaces_as_a_tool_error(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(ToolError, match="no such exercise"):
        call("last_performed_load", exercise_id="Barbell_Sqvat")


def test_an_unknown_muscle_group_surfaces_as_a_tool_error() -> None:
    with pytest.raises(ToolError, match="not a muscle group"):
        call("allocate", minutes=40, proportions={"Chest": 1.0})


def test_a_missing_database_is_a_state_with_its_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`no such table: exercises` names neither the state nor the way out."""
    monkeypatch.setenv("TRAINER_DB", str(tmp_path / "absent.sqlite"))

    with pytest.raises(ToolError, match="trainer db init"):
        call("admissible_set", equipment=["barbell"], budget_min=45)


def test_a_malformed_block_surfaces_as_a_tool_error(
    connection: sqlite3.Connection,
) -> None:
    """Reps and seconds both given is the dataclass's own refusal, not a check
    this wrapper grew."""
    with pytest.raises(ToolError):
        call(
            "remaining_budget",
            partial_plan=[
                {
                    "items": [
                        {"exercise_id": "Barbell_Squat", "reps": 8, "seconds": 30}
                    ],
                    "rounds": 3,
                    "rest": 120,
                }
            ],
            budget_min=40,
        )


def test_the_server_survives_a_failed_call(connection: sqlite3.Connection) -> None:
    """A tool error is a result, not the end of the session: an agent that got
    one argument wrong has to be able to try again."""
    with pytest.raises(ToolError):
        call("pattern_history", pattern="vertical yeet", cycles=3)

    assert call("pattern_history", pattern="squat", cycles=3)["known"] is False


def test_a_corrupt_database_surfaces_with_its_reason_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opening the connection has to happen *inside* the error translator.

    Outside it, the SDK catches the raw exception and re-raises it as
    `Error executing tool <name>` with the reason kept on the server -- which
    is exactly the boundary leak the translator exists to close, in the one
    case where the client can do nothing without being told why.
    """
    corrupt = tmp_path / "trainer.sqlite"
    corrupt.write_bytes(b"this is not a database")
    monkeypatch.setenv("TRAINER_DB", str(corrupt))

    with pytest.raises(ToolError) as raised:
        call("pattern_history", pattern="squat", cycles=3)

    assert "not a database" in str(raised.value)
