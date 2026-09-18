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
    "trainer.log",
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
    # models -- every provider SDK this project has used or might reach for.
    # `groq` is the one in use; `anthropic` stays because the guard is about
    # what `engine/` may never import, not about what is installed today.
    "groq",
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
        "from trainer.log import PerformedWorkout",
        "from trainer.mcp_server import server",
        "from anthropic import Anthropic",
        "import groq",
        "from groq import Groq",
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


# -- nobody but a door writes -------------------------------------------------
#
# ROADMAP.md § Session 5: writes are never tools. If the model can call the
# write, the model decides when the database changes -- the single door
# disappears, the validator becomes optional, and an interrupted run leaves
# half a workout behind. A graph emits; the engine writes, from the command or
# from the node that the user's *yes* put there.
#
# These lived in `test_agent.py` until session 9 deleted the loop they were
# written beside. They are not about that loop: they are the claim itself.

PACKAGE_NAME = "trainer"

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "trainer"


def _importers_of(
    name: str, root: Path = PACKAGE_ROOT, package: str = PACKAGE_NAME
) -> set[str]:
    """Every module under `root` whose source imports `name`.

    Every form the import can take, absolute and relative, because a guard
    that catches four of five is a guard that tells you the writer is
    unreachable while somebody is calling it -- and the one it misses is the
    one a future module inside the package is most likely to be written with.
    """
    found: set[str] = set()
    for module in sorted(root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        here = _module_name(module, root, package)
        for node in ast.walk(tree):
            imported: set[str] = set()
            if isinstance(node, ast.Import):
                imported = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = _resolved(node, here)
                if base is not None:
                    imported = {base} | {
                        f"{base}.{alias.name}" for alias in node.names
                    }
            if name in imported:
                found.add(str(module.relative_to(root)).replace("\\", "/"))
    return found


def _module_name(module: Path, root: Path, package: str) -> str:
    """The dotted name of a file, as Python would import it."""
    parts = module.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((package, *parts))


def _resolved(node: ast.ImportFrom, here: str) -> str | None:
    """What `from ... import` names, absolute or relative to `here`.

    `node.level` is the number of leading dots: zero is absolute, one means
    the importing module's own package, and each further dot climbs one more.
    """
    if node.level == 0:
        return node.module
    ancestors = here.split(".")[: -node.level]
    if not ancestors:
        return None
    return ".".join((*ancestors, node.module)) if node.module else ".".join(ancestors)


@pytest.mark.parametrize(
    "source",
    [
        "import trainer.engine.workouts",
        "from trainer.engine import workouts",
        "from trainer.engine.workouts import record_prescribed",
        "from .engine import workouts",
        "from .engine.workouts import record_prescribed",
    ],
)
def test_the_writer_guard_catches_every_form_of_the_import(
    source: str, tmp_path: Path
) -> None:
    """The guard is only worth having if it fails on the code it forbids --
    `test_engine_boundary.py` makes the same point about its own. The two
    relative forms are here because the guard once missed both, and a module
    added inside the package is exactly where they would be written."""
    (tmp_path / "offender.py").write_text(source, encoding="utf-8")

    assert _importers_of("trainer.engine.workouts", tmp_path) == {"offender.py"}


def test_the_writer_guard_does_not_fire_on_something_else(tmp_path: Path) -> None:
    """A guard that matched everything would pass this suite while saying
    nothing at all."""
    (tmp_path / "innocent.py").write_text(
        "from trainer.engine import duration\nfrom .engine import catalog\n",
        encoding="utf-8",
    )

    assert _importers_of("trainer.engine.workouts", tmp_path) == set()


def test_only_the_cli_and_the_document_reach_the_writer_module() -> None:
    """A short, explicit list of who may even see the module.

    `log.py` joined it in session 5 and does not write: it reads the
    prescribed phase back, because adherence has to know what was prescribed
    in order to fill in what a report did not mention, and it names the two
    performed dataclasses because those are what a complete block is.
    `tools.py` joined it for `prescribed_workout`, which is the same read
    offered to a model. `log_set.py` names `PrescribedBlock` because a
    prescription in the log set *is* one and there is no second shape for it,
    and `log_evaluation.py` writes those four blocks into the fixture the set
    is measured against -- see the next test, which is the one that matters
    and which says exactly what that exception covers.
    """
    assert _importers_of("trainer.engine.workouts") == {
        "cli.py",
        # Session 7: a plan becomes a prescribed workout when the user accepts
        # it (ADR-0005), and the node after the resume is what writes it.
        "coach/planner.py",
        # Session 9: the logger graph does not write, and `logger.performed`
        # is the one writer a report reaches -- called from the door that
        # asked, never from a node. See the next test.
        "coach/logger.py",
        "log.py",
        "log_evaluation.py",
        "log_set.py",
        "tools.py",
    }


WRITERS = ("record_prescribed", "record_performed")
"""The two functions that change what the database says happened. The guard
below is about these names, not about the module that holds them."""


def _callers_of(
    writers: tuple[str, ...] = WRITERS, root: Path = PACKAGE_ROOT
) -> set[str]:
    """Every module under `root` outside the engine that names one of the
    writers -- called as `workouts.record_performed(...)` or imported bare and
    called by name.

    A call rather than an import, because `log.py` legitimately needs the
    module: it reads the prescribed phase back in order to fill in what a
    report did not mention, and it names the two performed dataclasses because
    those are what a complete block is. Reading is not writing. What must stay
    impossible is the *call*, from anywhere but the command.
    """
    found: set[str] = set()
    for module in sorted(root.rglob("*.py")):
        if module.is_relative_to(root / "engine"):
            # The engine defines them and may call its own; the claim is about
            # everything above it.
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            named = (
                node.attr
                if isinstance(node, ast.Attribute)
                else node.id
                if isinstance(node, ast.Name)
                else None
            )
            if named in writers:
                found.add(str(module.relative_to(root)).replace("\\", "/"))
    return found


def test_only_the_cli_and_an_accepted_plan_call_a_writer() -> None:
    """The runtime assertions above say the writer was not called on these
    paths. This says it cannot be, from anywhere but the command -- which is
    the claim that has to survive somebody adding a tool next session.

    It is about the two writer names rather than about the module because
    session 5 gave that module readers as well: `log.py` reads the prescribed
    phase to fill in what a report left out. Written as *nobody but the CLI
    may import `workouts`*, this test would have had to be relaxed to let a
    reader through, and relaxing it is what loses the claim. Written about the
    writers, it says exactly what ROADMAP.md says -- the agent emits, the
    engine writes -- and it stays sharp.

    **`log_evaluation.py` is the one exception, and it is a narrow one.** The
    log set is measured against four prescribed workouts and one performed
    one, and building those means writing them: there is no fixture without a
    writer. What the exception does not cover is the part that would matter --
    **scoring a run writes nothing**, because a document is resolved and
    costed with `workouts.volume`, which reads -- and what the fixture writes
    into is a throwaway copy, deleted with the temp directory it was made in.
    The database the user trains against is opened once, read, and never
    written. `test_log_evaluation.py` holds the runtime guard on that claim,
    and it is what keeps this line from being a hole.

    **The graph joined the list in session 7, and the rule is not weaker for
    it.** A plan becomes a prescribed workout when the user accepts it
    (ADR-0005): the run stops at the plan, and only the node *after* the
    resume writes. `trainer eval` invokes eighteen runs and resumes none of
    them, so it cannot reach that node -- the guarantee the command used to
    hold by keeping the write to itself, held now by the shape of the graph.
    What a graph emits is still a document, and a document is not a workout
    until somebody says yes to it.

    **`coach/logger.py` joined it in session 9 and is the narrowest of the
    four.** The logger graph has six tools, all reads, and no node of it
    writes: `logger.performed` is a plain function beside the graph, and the
    door that asked for the run calls it once the document is in hand. That is
    what lets thirty reports be measured without leaving thirty performed
    workouts in the state the measurement is taken from.
    """
    assert _callers_of() == {
        "cli.py",
        "coach/planner.py",
        "coach/logger.py",
        "log_evaluation.py",
    }


@pytest.mark.parametrize(
    "source",
    [
        "workouts.record_prescribed(connection, blocks, on='2026-09-09')",
        "workouts.record_performed(connection, blocks, on='2026-09-09', report='')",
        "record_performed(connection, blocks, on='2026-09-09', report='')",
        "engine.workouts.record_prescribed(connection, blocks, on='2026-09-09')",
    ],
)
def test_the_writer_guard_catches_every_form_of_the_call(
    source: str, tmp_path: Path
) -> None:
    """The guard is only worth having if it fails on the code it forbids --
    `test_engine_boundary.py` makes the same point about its own."""
    (tmp_path / "offender.py").write_text(source, encoding="utf-8")

    assert _callers_of(root=tmp_path) == {"offender.py"}


def test_the_writer_call_guard_does_not_fire_on_a_reader(tmp_path: Path) -> None:
    """Reading the prescribed phase and naming the performed dataclasses is
    what `log.py` does, and it must not read as a write."""
    (tmp_path / "innocent.py").write_text(
        "from trainer.engine import workouts\n"
        "blocks = workouts.prescribed(connection, 1)\n"
        "item = workouts.PerformedItem(exercise_id='x', unit='reps', amount=8,\n"
        "                              amount_source='reported')\n",
        encoding="utf-8",
    )

    assert _callers_of(root=tmp_path) == set()
