"""The six muscle groups, and the mapping they are read from.

The committed mapping is the only place the six names exist, so these tests
guard two different things: that the parser reads a file correctly, and that
the file itself still accounts for every value the catalog actually holds.
The second one is what fails the day the catalog grows an eighteenth muscle.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, migrations, muscle_groups

THE_SIX = ("arms", "back", "chest", "core", "legs", "shoulders")
"""CONTEXT.md's six, alphabetically. Written out here on purpose: this is the
one assertion that would catch a typo in the mapping turning `back` into a
seventh group nobody meant to create."""


@pytest.fixture()
def imported(database_file: Path) -> Iterator[sqlite3.Connection]:
    """The real catalog, imported -- these tests are about its real vocabulary."""
    with closing(database.connect(database_file)) as connection:
        migrations.migrate(connection, migrations.discover())
        catalog.import_exercises(connection, catalog.load())
        yield connection


def test_the_committed_mapping_names_exactly_the_six() -> None:
    assert muscle_groups.groups() == THE_SIX


def test_every_muscle_the_catalog_holds_is_accounted_for(
    imported: sqlite3.Connection,
) -> None:
    """The one that fails the day an eighteenth value arrives.

    A muscle absent from the mapping is a muscle silently dropped from every
    allocation, which is exactly the kind of fault that surfaces weeks later as
    a body part nobody is training.
    """
    in_the_catalog = set(catalog.values(imported, "primary_muscles"))
    in_the_mapping = set(muscle_groups.committed().muscles)

    assert in_the_catalog - in_the_mapping == set(), "unmapped muscles"
    assert in_the_mapping - in_the_catalog == set(), "mapped muscles the catalog lost"


def test_lower_back_is_core_and_neck_is_no_group() -> None:
    """The two rulings CONTEXT.md and the ticket both call out by name."""
    mapping = muscle_groups.committed()

    assert mapping.group_of("lower back") == "core"
    assert mapping.group_of("neck") is None


def test_a_muscle_the_mapping_does_not_name_is_a_caller_error() -> None:
    """Distinct from `neck`, which is decided to be in no group -- and a
    `KeyError`, not a `MuscleGroupError`: the mapping is not unusable, the
    caller asked about something that is not in it."""
    with pytest.raises(KeyError, match="does not name"):
        muscle_groups.committed().group_of("gills")

    assert not issubclass(KeyError, muscle_groups.MuscleGroupError)


def test_the_groups_are_derived_from_the_assignments() -> None:
    parsed = muscle_groups.parse(
        "| muscle | group | why |\n"
        "|---|---|---|\n"
        "| `biceps` | `arms` | elbow flexion |\n"
        "| `neck` | `-` | no group |\n"
    )

    assert parsed.muscles == ("biceps", "neck")
    assert parsed.groups == ("arms",)


def test_prose_and_the_header_are_not_read_as_rows() -> None:
    parsed = muscle_groups.parse(
        "# A heading\n"
        "Some prose about the mapping.\n"
        "| muscle | group | why |\n"
        "|:---|:---:|---|\n"
        "| `chest` | `chest` | the group is named for it |\n"
    )

    assert parsed.muscles == ("chest",)


def test_a_duplicated_muscle_is_refused() -> None:
    with pytest.raises(muscle_groups.MuscleGroupError, match="twice"):
        muscle_groups.parse(
            "| muscle | group | why |\n"
            "|---|---|---|\n"
            "| `traps` | `back` | one |\n"
            "| `traps` | `shoulders` | and another |\n"
        )


def test_an_empty_group_cell_is_refused_rather_than_read_as_no_group() -> None:
    """A blank and a decision are different claims, and only one of them is a
    decision. The marker is spelled so the file cannot express the difference
    by accident."""
    with pytest.raises(muscle_groups.MuscleGroupError, match="empty group cell"):
        muscle_groups.parse(
            "| muscle | group | why |\n|---|---|---|\n| `traps` |  | unfinished |\n"
        )


def test_a_mapping_with_no_rows_is_refused() -> None:
    with pytest.raises(muscle_groups.MuscleGroupError, match="no data rows"):
        muscle_groups.parse("# Just a heading\n")


def test_a_missing_mapping_file_says_where_it_looked(tmp_path: Path) -> None:
    with pytest.raises(muscle_groups.MuscleGroupError, match="no muscle group mapping"):
        muscle_groups.load(tmp_path / "absent.md")


def test_the_mapping_ships_inside_the_package() -> None:
    """Not resolved against the working directory: `allocate` reads this
    vocabulary from inside an agent loop, and an answer that depends on where
    the process was started is not a vocabulary."""
    package = Path(muscle_groups.__file__).resolve().parent.parent

    assert muscle_groups.MUSCLE_GROUPS_PATH.is_file()
    assert muscle_groups.MUSCLE_GROUPS_PATH.is_relative_to(package)


def test_the_mapping_is_readable_prose_and_not_only_a_table() -> None:
    """Every grouping decision is visible in the file itself -- the whole
    reason it is markdown rather than a dictionary literal."""
    text = muscle_groups.MUSCLE_GROUPS_PATH.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| `")]

    for row in rows:
        why = row.strip("|").split("|")[2].strip()
        assert len(why) > 10, f"no reason given: {row}"


def test_the_catalog_still_has_neck_rows_to_reach(imported: sqlite3.Connection) -> None:
    """`neck` maps to no group; its rows stay reachable in the catalog. If they
    ever vanished, the mapping's ruling would be about nothing."""
    found = catalog.search(imported, filters={"primary_muscles": "neck"})

    assert found.total > 0


def test_the_committed_mapping_is_read_once() -> None:
    """`committed()` is cached, so a caller reading the vocabulary per
    `allocate` call is not reparsing the file each time."""
    assert muscle_groups.committed() is muscle_groups.committed()


def test_a_row_missing_the_why_column_is_refused_rather_than_dropped() -> None:
    """Skipping it on its length would take the muscle out of the mapping
    altogether, and time allocated to its group would silently stop covering
    it -- a fault only the separate catalog-coverage test would ever catch."""
    with pytest.raises(muscle_groups.MuscleGroupError, match="cell"):
        muscle_groups.parse(
            "| muscle | group | why |\n|---|---|---|\n| `traps` | `back` |\n"
        )


def test_a_row_that_names_no_muscle_is_refused_rather_than_skipped() -> None:
    """Blanking the muscle cell on the three `arms` rows would take `arms` out
    of the vocabulary entirely, and `allocate` would start refusing it as a
    typo -- with nothing in the parse saying a row had gone."""
    with pytest.raises(muscle_groups.MuscleGroupError, match="names no muscle"):
        muscle_groups.parse(
            "| muscle | group | why |\n|---|---|---|\n|  | `arms` | elbow flexion |\n"
        )


def test_prose_beginning_with_a_pipe_is_still_not_a_row() -> None:
    """The blank first cell only means a lost muscle when the rest of the row
    is filled in; an empty line of table framing is just framing."""
    parsed = muscle_groups.parse(
        "| muscle | group | why |\n|---|---|---|\n|  |  |  |\n| `chest` | `chest` | it |\n"
    )

    assert parsed.muscles == ("chest",)
