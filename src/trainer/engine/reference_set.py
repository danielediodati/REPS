"""Scoring the database against the hand-decided reference set.

`docs/enrichment/reference-set.md` is 60-80 movements decided by a reader
with no access to what `enrichment.derive()` produces for them -- the file
itself says how that was enforced, because an accuracy figure computed
against a reference that has seen the rule's answers is inflated by an
amount nobody can estimate, and there is no way to repair that after the
fact. This module only reads the file and compares it against whatever the
database currently holds; it never decides anything itself.

`movement_pattern` is reported on its own and never averaged into the other
four fields: it is the field the rules were measured on before they existed,
and blending it into a combined figure would let a strong loaded_joints
score hide a weak movement_pattern one, or the other way round.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

REFERENCE_SET_ENV_VAR = "TRAINER_REFERENCE_SET"
"""Environment variable that overrides the reference set location, the same
way `TRAINER_DB` and `TRAINER_SNAPSHOT` do -- tests point it at a throwaway
file rather than the committed 60-80 rows."""

DEFAULT_REFERENCE_SET_PARTS = ("docs", "enrichment", "reference-set.md")


class ReferenceSetError(RuntimeError):
    """The reference set on disk is not usable."""


@dataclass(frozen=True)
class ReferenceRow:
    """One movement, decided by hand against docs/enrichment/definitions.md.

    `loaded_joints` is `None` rather than `()` when the reference set does
    not record a value for it -- an empty set and "not decided" are
    different claims, and only the field's own column says which one the
    reference actually made.
    """

    id: str
    movement_pattern: str | None
    loaded_joints: tuple[str, ...] | None
    spinal_axial_load: str | None
    required_stability: str | None
    setup_cost_min: int | None
    uncertain: bool


def reference_set_path() -> Path:
    override = os.environ.get(REFERENCE_SET_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.cwd().joinpath(*DEFAULT_REFERENCE_SET_PARTS)


_COLUMNS = (
    "id",
    "name",
    "equipment",
    "pattern",
    "joints",
    "axial",
    "stability",
    "setup",
    "uncertain",
    "note",
)
"""`| id | name | equipment | pattern | joints | axial | stability | setup |
+/- | note |` -- ten cells. `name` and `equipment` are read by a person and
not by this parser; they exist so a disagreement about a row is legible as
a diff without cross-referencing the id against the catalog."""

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-']*$")
"""A real catalog id: word characters, hyphens, underscores, the odd
apostrophe (`Landmine_180's`). Used to tell a data row's first cell apart
from a header cell (`id`) or a separator cell (`---`), neither of which a
plain `|` split can distinguish on its own."""

_EMPTY = ("", "-", "—", "none", "n/a", "null", "(null)")

_AXIAL = {"y": "yes", "yes": "yes", "n": "no", "no": "no"}
_STABILITY = {"h": "high", "high": "high", "m": "medium", "medium": "medium", "l": "low", "low": "low"}


def _cell(value: str) -> str | None:
    stripped = value.strip().strip("*")
    return None if stripped.lower() in _EMPTY else stripped


def _coded(value: str, table: dict[str, str]) -> str | None:
    """A cell that may be given as a single letter (`Y`, `H`) or the word it
    stands for -- the reference set's own legend states which, and this
    accepts either rather than forcing one spelling on a document written
    for a person to read."""
    cell = _cell(value)
    if cell is None:
        return None
    coded = table.get(cell.lower())
    if coded is None:
        raise ReferenceSetError(f"not one of {sorted(set(table.values()))!r}: {cell!r}")
    return coded


def parse(text: str) -> tuple[ReferenceRow, ...]:
    """Read the reference set's data rows. Raises on a duplicate id --
    'sixty *distinct* movements' is part of what the file promises."""
    rows: list[ReferenceRow] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < len(_COLUMNS):
            continue
        exercise_id = cells[0].strip("`").strip()
        if exercise_id.lower() == "id" or not _ID.match(exercise_id):
            continue  # the header row, a separator row, or prose that starts with "|"

        if exercise_id in seen:
            raise ReferenceSetError(f"duplicate id in the reference set: {exercise_id}")
        seen.add(exercise_id)

        by_column = dict(zip(_COLUMNS, cells))
        joints_cell = _cell(by_column["joints"])
        setup_cell = _cell(by_column["setup"])

        rows.append(
            ReferenceRow(
                id=exercise_id,
                movement_pattern=_cell(by_column["pattern"]),
                loaded_joints=(
                    tuple(j.strip() for j in joints_cell.split(","))
                    if joints_cell is not None
                    else None
                ),
                spinal_axial_load=_coded(by_column["axial"], _AXIAL),
                required_stability=_coded(by_column["stability"], _STABILITY),
                setup_cost_min=int(setup_cell) if setup_cell is not None else None,
                uncertain=_cell(by_column["uncertain"]) is not None,
            )
        )
    return tuple(rows)


def load(path: Path | None = None) -> tuple[ReferenceRow, ...]:
    target = path if path is not None else reference_set_path()
    if not target.is_file():
        raise ReferenceSetError(f"no reference set at {target}")
    rows = parse(target.read_text(encoding="utf-8"))
    if not rows:
        raise ReferenceSetError(f"{target} has no data rows")
    return rows


FIELDS = (
    "movement_pattern",
    "loaded_joints",
    "spinal_axial_load",
    "required_stability",
    "setup_cost_min",
)


@dataclass(frozen=True)
class FieldCheck:
    """How one field's reference values compare to what the database holds.

    `total` is the number of reference rows that name a value for this
    field at all -- `matches + disagreements + missing` always equals it,
    the same reconciling property `catalog.Breakdown` and
    `catalog.EnrichmentCoverage` already hold.
    """

    field: str
    total: int
    matches: int
    disagreements: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def accuracy(self) -> float:
        """Share of the rows where the database already agrees -- undefined,
        as 0.0, when the reference names no value for this field at all."""
        return self.matches / self.total if self.total else 0.0


def check(
    connection: sqlite3.Connection, reference: tuple[ReferenceRow, ...]
) -> tuple[FieldCheck, ...]:
    """Score whatever the database currently holds against the reference,
    per field. Reads the database's current value regardless of its source
    -- a row a person has since corrected by hand is compared the same way
    as one a rule decided, because this reports what is true now, not who
    said so."""
    columns = ", ".join(f"{field}, {field}_source" for field in FIELDS)
    rows = {
        str(row["id"]): row
        for row in connection.execute(f"SELECT id, {columns} FROM exercises")
    }

    # An id the catalog does not have at all is a typo in the reference set,
    # not a row the rules have yet to reach -- the two must not be conflated
    # under "missing", or a broken reference set would silently score as an
    # unenriched catalog instead of failing loudly.
    unknown = sorted({row.id for row in reference} - rows.keys())
    if unknown:
        raise ReferenceSetError(
            f"the reference set names ids the catalog does not have: {', '.join(unknown)}"
        )

    checks = []
    for field in FIELDS:
        matches: list[str] = []
        disagreements: list[str] = []
        missing: list[str] = []
        total = 0
        for reference_row in reference:
            expected = getattr(reference_row, field)
            if expected is None:
                continue
            total += 1

            db_row = rows.get(reference_row.id)
            actual = _actual_value(db_row, field) if db_row is not None else None

            if actual is None:
                missing.append(reference_row.id)
            elif _agrees(field, actual, expected):
                matches.append(reference_row.id)
            else:
                disagreements.append(reference_row.id)

        checks.append(
            FieldCheck(
                field=field,
                total=total,
                matches=len(matches),
                disagreements=tuple(disagreements),
                missing=tuple(missing),
            )
        )
    return tuple(checks)


def _actual_value(db_row: sqlite3.Row, field: str) -> object:
    """`None` means nothing has decided this field yet -- read from the
    `_source` column, never from the value being empty. `loaded_joints`
    genuinely is an empty set for an isolation movement whose muscle crosses
    none of the seven joints (`neck`, per docs/enrichment/definitions.md),
    and that is a real, decided answer, not an absence of one."""
    if db_row[f"{field}_source"] is None:
        return None
    if field == "loaded_joints":
        return tuple(json.loads(db_row["loaded_joints"]))
    return db_row[field]


def _agrees(field: str, actual: object, expected: object) -> bool:
    """`loaded_joints` is a set: the reference set and the database can list
    the same two joints in a different order and still agree completely."""
    if field == "loaded_joints":
        assert isinstance(actual, tuple) and isinstance(expected, tuple)
        return set(actual) == set(expected)
    return actual == expected
