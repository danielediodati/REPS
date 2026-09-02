"""The readable history: a markdown snapshot regenerated from the database.

The snapshot exists to be diffed by a human, and everything asserted here
follows from that. If it churns on a run that changed nothing, or reflows rows
nobody touched, its diffs stop being read -- which was the only job it had.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import catalog, database, migrations, snapshot


def exercise(**overrides: object) -> catalog.Exercise:
    base: dict[str, object] = {
        "id": "Bench_Press",
        "name": "Bench Press",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("chest",),
        "secondary_muscles": ("triceps", "shoulders"),
        "instructions": ("Lie on the bench.", "Press."),
        "images": ("Bench_Press/0.jpg", "Bench_Press/1.jpg"),
    }
    base.update(overrides)
    return catalog.Exercise(**base)  # type: ignore[arg-type]


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened)
        yield opened


def stock(connection: sqlite3.Connection, *exercises: catalog.Exercise) -> None:
    catalog.import_exercises(connection, exercises, allow_pruning=True)


def last_row(text: str) -> str:
    return text.splitlines()[-1]


# --- determinism ------------------------------------------------------------


def test_rendering_twice_gives_the_same_text(connection: sqlite3.Connection) -> None:
    stock(connection, exercise(), exercise(id="Squat", name="Squat"))

    assert snapshot.render(connection) == snapshot.render(connection)


def test_the_snapshot_carries_no_date(connection: sqlite3.Connection) -> None:
    """A generation date would make every regeneration a diff."""
    stock(connection, exercise())

    text = snapshot.render(connection)

    assert not re.search(r"\d{4}-\d{2}-\d{2}", text)


def test_writing_an_unchanged_database_leaves_the_file_byte_identical(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(connection, exercise(), exercise(id="Squat", name="Squat"))
    path = tmp_path / "snapshots" / "catalog.md"

    snapshot.write(connection, path)
    before = path.read_bytes()
    changed = snapshot.write(connection, path)

    assert path.read_bytes() == before
    assert changed is False


def test_writing_after_a_change_reports_it(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    stock(connection, exercise())
    path = tmp_path / "snapshots" / "catalog.md"
    snapshot.write(connection, path)

    stock(connection, exercise(), exercise(id="Squat", name="Squat"))

    assert snapshot.write(connection, path) is True
    assert "Squat" in path.read_text(encoding="utf-8")


def test_the_file_uses_newlines_git_will_not_rewrite(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Written on Windows, read anywhere: CRLF would be a diff of the whole file."""
    stock(connection, exercise())
    path = tmp_path / "catalog.md"

    snapshot.write(connection, path)

    assert b"\r" not in path.read_bytes()


def test_the_order_does_not_depend_on_insertion_order(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    forwards = (
        exercise(id="A_Lift", name="A Lift"),
        exercise(id="B_Lift", name="B Lift"),
    )
    stock(connection, *forwards)
    one = snapshot.render(connection)

    with closing(database.connect(tmp_path / "other.sqlite")) as second:
        migrations.migrate(second)
        stock(second, *reversed(forwards))
        two = snapshot.render(second)

    assert one == two


# --- readable as a diff -----------------------------------------------------


def test_changing_one_exercise_changes_one_line(connection: sqlite3.Connection) -> None:
    """Padded columns would reflow the table; this is why the rows are not padded."""
    others = (exercise(), exercise(id="Row", name="Row"))
    stock(connection, *others, exercise(id="Squat", name="Squat"))
    before = snapshot.render(connection).splitlines()

    stock(
        connection,
        *others,
        exercise(id="Squat", name="Squat, Very Long Barbell Back Variation"),
    )
    after = snapshot.render(connection).splitlines()

    assert len(before) == len(after)
    differing = [index for index, line in enumerate(before) if line != after[index]]
    assert len(differing) == 1


def test_one_row_per_exercise(connection: sqlite3.Connection) -> None:
    stock(connection, exercise(), exercise(id="Squat", name="Squat"))

    rows = [
        line
        for line in snapshot.render(connection).splitlines()
        if line.startswith("|") and not line.startswith("| ---")
    ]

    assert len(rows) == 1 + 2  # the header row, then one per exercise


def test_a_row_is_the_exercise_reduced_to_what_can_be_read(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, exercise())

    assert last_row(snapshot.render(connection)) == (
        "| Bench_Press | Bench Press | strength | barbell | push | compound "
        "| beginner | chest | triceps, shoulders | 2 | 2 |"
    )


def test_absent_values_read_as_absent(connection: sqlite3.Connection) -> None:
    stock(
        connection,
        exercise(force=None, mechanic=None, equipment=None, secondary_muscles=()),
    )

    assert last_row(snapshot.render(connection)) == (
        "| Bench_Press | Bench Press | strength | - | - | - "
        "| beginner | chest | - | 2 | 2 |"
    )


def test_instructions_and_images_are_counted_not_copied(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, exercise())

    text = snapshot.render(connection)

    assert "Lie on the bench." not in text
    assert "Bench_Press/0.jpg" not in text
    assert text.rstrip().endswith("| 2 | 2 |")


def test_a_pipe_in_a_value_cannot_break_the_table(
    connection: sqlite3.Connection,
) -> None:
    stock(connection, exercise(name="Press | Pull"))

    row = last_row(snapshot.render(connection))

    assert r"Press \| Pull" in row
    assert row.count("|") == 12 + row.count(r"\|")  # 11 columns, 12 delimiters


def test_a_newline_in_a_value_cannot_split_a_row(
    connection: sqlite3.Connection,
) -> None:
    """One exercise is one line.

    A stray newline would make it two, and every diff below it would then
    be off by one -- the same damage as reflowing the table.
    """
    stock(connection, exercise(name="Press\r\nand Pull"))

    rows = [
        line
        for line in snapshot.render(connection).splitlines()
        if line.startswith("| Bench_Press")
    ]

    assert rows == [
        "| Bench_Press | Press and Pull | strength | barbell | push "
        "| compound | beginner | chest | triceps, shoulders | 2 | 2 |"
    ]


def test_the_header_says_it_is_generated(connection: sqlite3.Connection) -> None:
    stock(connection, exercise())

    text = snapshot.render(connection)

    assert "trainer db snapshot" in text
    assert "do not edit" in text.lower()


def test_the_totals_are_stated(connection: sqlite3.Connection) -> None:
    stock(connection, exercise(), exercise(id="Squat", name="Squat"))

    assert "2 exercises" in snapshot.render(connection)


def test_an_empty_catalog_still_renders(connection: sqlite3.Connection) -> None:
    text = snapshot.render(connection)

    assert "0 exercises" in text


def test_the_snapshot_states_the_schema_it_was_taken_from(
    connection: sqlite3.Connection,
) -> None:
    """A diff after a migration explains itself instead of looking like data loss."""
    stock(connection, exercise())
    latest = migrations.latest_version(migrations.discover())

    assert f"schema version {latest}" in snapshot.render(connection)


# --- the path ---------------------------------------------------------------


def test_the_default_path_is_under_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(snapshot.SNAPSHOT_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert snapshot.snapshot_path() == tmp_path / "snapshots" / "catalog.md"


def test_the_path_is_overridable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.md"
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV_VAR, str(elsewhere))

    assert snapshot.snapshot_path() == elsewhere


# --- the committed file -----------------------------------------------------


COMMITTED = Path(__file__).resolve().parents[1] / "snapshots" / "catalog.md"


def test_the_committed_snapshot_matches_the_vendored_dataset(
    connection: sqlite3.Connection,
) -> None:
    """The file in git is regenerated from the dataset the import reads.

    Bytes, not text: reading it as text would translate CRLF away and the
    check would pass on a checkout where every regeneration rewrites all 890
    lines -- the one failure the `.gitattributes` rule exists to prevent.

    Being committed, the file can go stale in two ways nothing else catches:
    the dataset is re-vendored, or a migration moves the schema version the
    preamble states. Both are fixed by the command the message names.
    """
    stock(connection, *catalog.load())

    assert COMMITTED.read_bytes() == snapshot.render(connection).encode("utf-8"), (
        "the committed snapshot no longer matches the database it describes; "
        "run `trainer db snapshot`"
    )
