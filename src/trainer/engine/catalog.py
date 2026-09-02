"""The exercise catalog: reading the vendored dataset, and storing it.

The dataset ships inside the package rather than being fetched, so the import
needs no network and the catalog cannot change underneath the work between one
session and the next. Images are references into the upstream repository, never
bytes: a few hundred megabytes of binaries would ruin a repo meant to be cloned.
"""

from __future__ import annotations

import json
import sqlite3
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
