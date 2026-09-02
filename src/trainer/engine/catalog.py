"""The exercise catalog: reading the vendored dataset, and storing it.

The dataset ships inside the package rather than being fetched, so the import
needs no network and the catalog cannot change underneath the work between one
session and the next. Images are references into the upstream repository, never
bytes: a few hundred megabytes of binaries would ruin a repo meant to be cloned.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DATASET_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "free-exercise-db"
DATASET_PATH = DATASET_DIRECTORY / "exercises.json"

_REQUIRED = ("id", "name", "level", "category")
_OPTIONAL = ("force", "mechanic", "equipment")
_LISTS = ("primaryMuscles", "secondaryMuscles", "instructions", "images")


class CatalogError(RuntimeError):
    """The dataset on disk is not usable."""


@dataclass(frozen=True)
class Exercise:
    """One record of the source catalog, with its own field names preserved.

    Column names are snake_case because that is what the rest of the schema
    reads like; the values are exactly as published.
    """

    id: str
    name: str
    force: str | None
    level: str
    mechanic: str | None
    equipment: str | None
    category: str
    primary_muscles: tuple[str, ...]
    secondary_muscles: tuple[str, ...]
    instructions: tuple[str, ...]
    images: tuple[str, ...]


@dataclass(frozen=True)
class ImportResult:
    inserted: int
    updated: int
    removed: int
    total: int


def load(path: Path = DATASET_PATH) -> tuple[Exercise, ...]:
    """Read the vendored dataset.

    Every departure from the expected shape is an error rather than a skipped
    record: a catalog quietly missing rows is the kind of fault that only
    surfaces weeks later as an exercise the agent can never prescribe.
    """
    if not path.is_file():
        raise CatalogError(f"no dataset at {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CatalogError(f"{path.name} is not valid JSON: {error}") from error

    if not isinstance(raw, list):
        raise CatalogError(f"{path.name} should hold a list of exercises")

    if not raw:
        raise CatalogError(f"{path.name} holds no exercises")

    exercises = tuple(_parse(record, position) for position, record in enumerate(raw))

    identifiers = {exercise.id for exercise in exercises}
    if len(identifiers) != len(exercises):
        raise CatalogError("the dataset contains duplicate ids")
    return exercises


def _parse(record: object, position: int) -> Exercise:
    where = f"record {position}"
    if not isinstance(record, dict):
        raise CatalogError(f"{where} is not an object")

    values: dict[str, object] = {}
    for field in _REQUIRED:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise CatalogError(f"{where}: {field} must be a non-empty string")
        values[field] = value
    for field in _OPTIONAL:
        value = record.get(field)
        if value is not None and not isinstance(value, str):
            raise CatalogError(f"{where}: {field} must be a string or null")
        values[field] = value
    for field in _LISTS:
        value = record.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise CatalogError(f"{where}: {field} must be a list of strings")
        values[field] = tuple(value)

    return Exercise(
        id=str(values["id"]),
        name=str(values["name"]),
        force=_optional(values["force"]),
        level=str(values["level"]),
        mechanic=_optional(values["mechanic"]),
        equipment=_optional(values["equipment"]),
        category=str(values["category"]),
        primary_muscles=_strings(values["primaryMuscles"]),
        secondary_muscles=_strings(values["secondaryMuscles"]),
        instructions=_strings(values["instructions"]),
        images=_strings(values["images"]),
    )


def _optional(value: object) -> str | None:
    """Absent is absent, however the source spells it.

    An empty string would sit in the data beside the genuine nulls and become a
    phantom value the moment ticket 03 reads the vocabulary out of the table.
    """
    if value is None or value == "":
        return None
    return str(value)


def _strings(value: object) -> tuple[str, ...]:
    assert isinstance(value, tuple)
    return tuple(str(item) for item in value)


PRUNE_LIMIT = 0.5
"""The share of the catalog an import may remove before it stops and asks.

An import that removes most of the catalog is far more likely to be a truncated
re-vendor than a real upstream deletion, and the damage looks like success:
rows gone, exit code zero. `load()` already refuses an empty file; this catches
the partial one, which is the same fault wearing a plausible record count.
"""


def import_exercises(
    connection: sqlite3.Connection,
    exercises: tuple[Exercise, ...],
    *,
    allow_pruning: bool = False,
) -> ImportResult:
    """Make the table match the dataset, in one transaction.

    Re-running changes nothing: rows are upserted by id, and rows the dataset no
    longer carries are removed, so the table is the dataset rather than
    everything the dataset has ever said.

    Removing more than `PRUNE_LIMIT` of the catalog is refused unless
    `allow_pruning` says it was meant.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing = {
            str(row["id"]) for row in connection.execute("SELECT id FROM exercises")
        }
        incoming = {exercise.id for exercise in exercises}

        doomed = existing - incoming
        if existing and not allow_pruning and len(doomed) > len(existing) * PRUNE_LIMIT:
            raise CatalogError(
                f"this import would remove {len(doomed)} of {len(existing)} "
                "exercises, which looks more like a truncated dataset than an "
                "upstream deletion"
            )

        connection.executemany(
            """
            INSERT INTO exercises (
                id, name, force, level, mechanic, equipment, category,
                primary_muscles, secondary_muscles, instructions, images
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                force = excluded.force,
                level = excluded.level,
                mechanic = excluded.mechanic,
                equipment = excluded.equipment,
                category = excluded.category,
                primary_muscles = excluded.primary_muscles,
                secondary_muscles = excluded.secondary_muscles,
                instructions = excluded.instructions,
                images = excluded.images
            """,
            [_to_row(exercise) for exercise in exercises],
        )

        removed = sorted(doomed)
        connection.executemany(
            "DELETE FROM exercises WHERE id = ?", [(identifier,) for identifier in removed]
        )
        total = count(connection)
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    connection.execute("COMMIT")

    return ImportResult(
        inserted=len(incoming - existing),
        updated=len(incoming & existing),
        removed=len(removed),
        total=total,
    )


def _to_row(exercise: Exercise) -> tuple[object, ...]:
    return (
        exercise.id,
        exercise.name,
        exercise.force,
        exercise.level,
        exercise.mechanic,
        exercise.equipment,
        exercise.category,
        json.dumps(list(exercise.primary_muscles)),
        json.dumps(list(exercise.secondary_muscles)),
        json.dumps(list(exercise.instructions)),
        json.dumps(list(exercise.images)),
    )


def count(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS total FROM exercises").fetchone()
    return int(row["total"])


def exercise(connection: sqlite3.Connection, exercise_id: str) -> Exercise | None:
    """One exercise, whole — instructions and images included.

    This is the retrieval the appendix describes: those two fields are never
    queried, they are fetched by id when something needs to show the exercise.
    """
    row = connection.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    return None if row is None else _from_row(row)


def _from_row(row: sqlite3.Row) -> Exercise:
    return Exercise(
        id=row["id"],
        name=row["name"],
        force=row["force"],
        level=row["level"],
        mechanic=row["mechanic"],
        equipment=row["equipment"],
        category=row["category"],
        primary_muscles=tuple(json.loads(row["primary_muscles"])),
        secondary_muscles=tuple(json.loads(row["secondary_muscles"])),
        instructions=tuple(json.loads(row["instructions"])),
        images=tuple(json.loads(row["images"])),
    )


SCALAR_FILTERS = ("force", "level", "mechanic", "equipment", "category")
"""Native fields holding one value per exercise, each usable as a filter."""

LIST_FILTERS = ("primary_muscles", "secondary_muscles")
"""Native fields holding a JSON array, filtered by membership."""

NULLABLE_FILTERS = ("force", "mechanic", "equipment")
"""The three the source leaves empty. `missing` reaches those rows.

Without it 77 exercises with no recorded equipment are unreachable from every
equipment query, present in the table and invisible from the command line.
"""

FILTERABLE = SCALAR_FILTERS + LIST_FILTERS

# `instructions` and `images` are deliberately not filterable. The appendix is
# explicit that they are never queried: they are fetched by id when something
# needs to show the exercise.


class UnknownFilterValue(CatalogError):
    """A filter value that is not in the catalog.

    Carries the valid values so the CLI can show them. A typo and a genuinely
    empty result must not look alike, and the only way to tell them apart is to
    say what the field actually holds.
    """

    def __init__(self, field: str, value: str, valid: tuple[str, ...], missing: int):
        super().__init__(f"no such {field}: {value!r}")
        self.field = field
        self.value = value
        self.valid = valid
        self.missing = missing


def _check_field(field: str, allowed: tuple[str, ...]) -> str:
    """Field names reach SQL by interpolation, so they are checked, not trusted."""
    if field not in allowed:
        raise CatalogError(
            f"{field!r} is not a filterable field; try one of {', '.join(allowed)}"
        )
    return field


def values(connection: sqlite3.Connection, field: str) -> tuple[str, ...]:
    """The values this field actually holds, read from the table.

    Never a constant in the code: the hand-copied vocabulary in ticket 02 missed
    `e-z curl bar` and `olympic weightlifting`, and a CLI carrying that copy
    would reject a real value as a typo.
    """
    _check_field(field, FILTERABLE)
    if field in LIST_FILTERS:
        rows = connection.execute(
            f"SELECT DISTINCT item.value AS value "  # field checked above
            f"FROM exercises, json_each(exercises.{field}) AS item "
            f"ORDER BY value"
        )
    else:
        rows = connection.execute(
            f"SELECT DISTINCT {field} AS value FROM exercises "  # field checked above
            f"WHERE {field} IS NOT NULL ORDER BY value"
        )
    return tuple(str(row["value"]) for row in rows)


def missing_count(connection: sqlite3.Connection, field: str) -> int:
    """How many exercises have no value for this field."""
    _check_field(field, SCALAR_FILTERS)
    row = connection.execute(
        f"SELECT COUNT(*) AS total FROM exercises WHERE {field} IS NULL"  # field checked above
    ).fetchone()
    return int(row["total"])


def check_value(connection: sqlite3.Connection, field: str, value: str) -> None:
    """Raise unless the catalog actually holds this value for this field."""
    valid = values(connection, field)
    if value in valid:
        return
    missing = missing_count(connection, field) if field in SCALAR_FILTERS else 0
    raise UnknownFilterValue(field, value, valid, missing)


def search(
    connection: sqlite3.Connection,
    *,
    name: str | None = None,
    filters: Mapping[str, str] | None = None,
    missing: Sequence[str] = (),
    limit: int | None = None,
) -> tuple[Exercise, ...]:
    """Exercises matching every criterion given. Filters compose as AND.

    `filters` maps a field in `FILTERABLE` to one of the values that field
    holds; `missing` names scalar fields the exercise must have no value for.
    Both are checked against the table before any SQL is built, so an unknown
    field or value fails as itself rather than as an empty result.

    Ordering is by name, always: a caller that shows the rows, diffs them or
    slices them with `limit` needs the same answer twice.
    """
    filters = dict(filters or {})
    conditions: list[str] = []
    parameters: list[object] = []

    if name is not None:
        # instr() rather than LIKE: no % or _ to escape, and no way for a
        # search term to become a pattern by accident.
        conditions.append("instr(lower(name), lower(?)) > 0")
        parameters.append(name)

    for field, value in filters.items():
        _check_field(field, FILTERABLE)
        check_value(connection, field, value)
        if field in LIST_FILTERS:
            conditions.append(
                f"EXISTS (SELECT 1 FROM json_each(exercises.{field}) AS item "  # field checked above
                f"WHERE item.value = ?)"
            )
        else:
            conditions.append(f"{field} = ?")  # field checked above
        parameters.append(value)

    for field in missing:
        # NULLABLE_FILTERS, not SCALAR_FILTERS: `level` and `category` are NOT
        # NULL, so asking for the ones without a value is unsatisfiable by
        # construction and would come back as an ordinary empty result -- the
        # exact confusion this command exists to prevent.
        _check_field(field, NULLABLE_FILTERS)
        conditions.append(f"{field} IS NULL")  # field checked above

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    clause = "LIMIT ?" if limit is not None else ""
    if limit is not None:
        parameters.append(limit)

    rows = connection.execute(
        f"SELECT * FROM exercises {where} ORDER BY name {clause}",  # field checked above
        parameters,
    )
    return tuple(_from_row(row) for row in rows)
