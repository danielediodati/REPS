"""Loading the hand-read residue into the catalog, with `curated` provenance.

`docs/enrichment/residue.md` decides `movement_pattern` for the strength rows
`enrichment.derive_movement_pattern` cannot -- the answer is in the exercise's
own `instructions`, not in its columns, and deciding it needs a person to read
them. This module does not decide anything itself: it reads the file (in
`reference_set.py`'s own table format, so one parser serves both) and writes
what it says.

Once a pattern is fixed by reading, the other four enrichment fields are
functions of the pattern and the equipment -- `docs/enrichment/definitions.md`
is explicit about this -- so the file carries all five, computed with exactly
the same `enrichment.derive_loaded_joints` / `derive_spinal_axial_load` /
`derive_required_stability` / `derive_setup_cost_min` the rule itself calls,
rather than a second, independent judgement for each row.

Every field this writes gets `curated` provenance, not just `movement_pattern`.
`enrichment.run` skips a row entirely the moment its `movement_pattern_source`
is `curated` -- it never falls through to fill the other four -- so a row
whose pattern comes from here and whose joints/axial/stability/setup did not
would sit unenriched on those four fields forever.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from trainer.engine.catalog import known_ids
from trainer.engine.enrichment import Derived, write
from trainer.engine.reference_set import ReferenceRow, ReferenceSetError, parse

RESIDUE_ENV_VAR = "TRAINER_RESIDUE"
"""Environment variable that overrides the residue file location, the same
way `TRAINER_REFERENCE_SET` does for the reference set."""

DEFAULT_RESIDUE_PARTS = ("docs", "enrichment", "residue.md")


class ResidueError(RuntimeError):
    """The residue file, or what it asks to write, is not usable."""


def residue_path() -> Path:
    override = os.environ.get(RESIDUE_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.cwd().joinpath(*DEFAULT_RESIDUE_PARTS)


def load(path: Path | None = None) -> tuple[ReferenceRow, ...]:
    """Read the decisions. Every row here was examined by a person, so unlike
    the reference set, a row naming no pattern means the pattern was decided
    to be null (`B6`) -- never "not yet looked at"."""
    target = path if path is not None else residue_path()
    if not target.is_file():
        raise ResidueError(f"no residue file at {target}")
    try:
        rows = parse(target.read_text(encoding="utf-8"))
    except ReferenceSetError as error:
        raise ResidueError(str(error)) from error
    if not rows:
        raise ResidueError(f"{target} has no data rows")
    return rows


@dataclass(frozen=True)
class CuratedReport:
    """What one application of the residue did.

    `decided` and `null` partition the rows: every one of them was examined,
    and the file records which examined rows came back with an honest pattern
    and which did not -- `B6`, on purpose, not a gap.
    """

    considered: int
    decided: tuple[str, ...]
    null: tuple[str, ...]


def apply(connection: sqlite3.Connection, rows: tuple[ReferenceRow, ...]) -> CuratedReport:
    """Write every row's decision with `curated` provenance.

    Curated always wins: the trigger in `0003_enrichment.sql` only refuses the
    other direction, a rule overwriting a curated value, so this runs
    regardless of whatever `movement_pattern_source` a row currently carries.
    """
    unknown = sorted({row.id for row in rows} - known_ids(connection))
    if unknown:
        raise ResidueError(
            f"the residue file names ids the catalog does not have: {', '.join(unknown)}"
        )

    for row in rows:
        if row.movement_pattern is not None and (
            row.loaded_joints is None
            or row.spinal_axial_load is None
            or row.required_stability is None
            or row.setup_cost_min is None
        ):
            raise ResidueError(
                f"{row.id}: a pattern is decided but one of loaded_joints/"
                "spinal_axial_load/required_stability/setup_cost_min is not -- "
                "all five are decided together once the pattern is fixed"
            )

    decided: list[str] = []
    null_rows: list[str] = []

    connection.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            if row.movement_pattern is None:
                connection.execute(
                    "UPDATE exercises SET movement_pattern = NULL, "
                    "movement_pattern_source = 'curated' WHERE id = ?",
                    (row.id,),
                )
                null_rows.append(row.id)
                continue

            derived = Derived(
                movement_pattern=row.movement_pattern,
                loaded_joints=row.loaded_joints,
                spinal_axial_load=row.spinal_axial_load,
                required_stability=row.required_stability,
                setup_cost_min=row.setup_cost_min,
            )
            write(connection, row.id, derived, "curated", only_if_not_curated=False)
            decided.append(row.id)
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    connection.execute("COMMIT")

    return CuratedReport(considered=len(rows), decided=tuple(decided), null=tuple(null_rows))
