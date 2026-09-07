"""The architectural constraint, enforced rather than assumed.

TRAINER.md makes the engine a pure library: no LLM, no network, no knowledge of
any client. That is what makes the tests below it real tests and keeps every
form of exposure — CLI, MCP, direct call — a thin wrapper over the same code.

A convention would be forgotten in a month. This fails the build.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1] / "src" / "trainer" / "engine"

FORBIDDEN_PREFIXES = (
    # the client layer: the engine must not know it exists
    "trainer.cli",
    "click",
    "trainer.tools",
    "trainer.mcp_server",
    "mcp",
    "trainer.plan",
    "trainer.agent",
    # The wire shape's own library. A plan reaches the engine as
    # `duration.Block`, and the day `engine/` imports pydantic it has started
    # knowing what a plan looks like on the way in.
    "pydantic",
    # the network, in every form it usually arrives in
    "socket",
    "http",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    # models
    "openai",
    "anthropic",
    "langchain",
    "langgraph",
)


def engine_modules() -> list[Path]:
    return sorted(ENGINE_ROOT.rglob("*.py"))


def imported_names(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            # `from trainer import cli` names the module in the alias, not in
            # node.module. Without this the guard would miss the one import it
            # exists to catch.
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def forbidden_imports(module: Path) -> set[str]:
    """The names in `module` that the engine is not allowed to reach for."""
    return {
        name
        for name in imported_names(module)
        for prefix in FORBIDDEN_PREFIXES
        if name == prefix or name.startswith(f"{prefix}.")
    }



def test_the_engine_has_modules_to_check() -> None:
    assert engine_modules(), "no engine modules found — the check would pass vacuously"


@pytest.mark.parametrize("module", engine_modules(), ids=lambda path: path.name)
def test_engine_module_imports_nothing_forbidden(module: Path) -> None:
    offenders = forbidden_imports(module)
    assert not offenders, f"{module.name} imports {sorted(offenders)}"


def test_importing_the_engine_does_not_pull_in_the_cli() -> None:
    """Not just the source text — the module graph actually loaded at runtime."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import trainer.engine, sys; "
            "assert 'trainer.cli' not in sys.modules, sorted(sys.modules); "
            "assert 'mcp' not in sys.modules, sorted(sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "import httpx",
        "from trainer import cli",
        "from trainer.cli import main",
        "import trainer.cli",
        "import mcp",
        "from mcp.server import MCPServer",
        "from trainer import tools",
        "from trainer.tools import TOOLS",
        "from pydantic import BaseModel",
        "from trainer.plan import WorkoutPlan",
        "from trainer.agent import plan_workout",
        "from trainer.mcp_server import server",
        "from anthropic import Anthropic",
        "from langgraph.graph import StateGraph",
    ],
)
def test_the_guard_catches_the_forms_it_exists_for(source: str, tmp_path: Path) -> None:
    """The guard is only worth having if it fails on the code it forbids."""
    module = tmp_path / "offender.py"
    module.write_text(source, encoding="utf-8")

    assert forbidden_imports(module), f"{source!r} slipped past the guard"


def test_the_guard_allows_ordinary_imports(tmp_path: Path) -> None:
    module = tmp_path / "innocent.py"
    module.write_text(
        "import sqlite3\nfrom pathlib import Path\nfrom trainer.engine import database\n",
        encoding="utf-8",
    )

    offenders = forbidden_imports(module)
    assert not offenders
