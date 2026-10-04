"""The demo's home: the committed history, built from nothing, one report away from the next mesocycle."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from trainer import cli, demo
from trainer import plan as plans
from trainer.engine import config, database, mesocycles, state, workouts
from trainer.supervise_evaluation import as_performed

TODAY = "2026-10-04"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The committed demo, built once: the real catalog is imported and enriched."""
    home = tmp_path_factory.mktemp("demo")
    demo.build(home, TODAY)
    return home


@pytest.fixture()
def opened(built: Path, tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A copy of the built demo, for a test to write into."""
    with (
        closing(database.connect(built / database.DEFAULT_DATABASE_NAME)) as source,
        closing(database.connect(tmp_path / "copy.sqlite")) as connection,
    ):
        source.backup(connection)
        yield connection


def test_three_mesocycles_are_performed_and_the_last_is_one_workout_from_its_end(
    opened: sqlite3.Connection,
) -> None:
    past = mesocycles.history(opened)

    assert [(one.performed, one.workouts) for one in past] == [(8, 8), (8, 8), (7, 8)]
    assert past[0].direction is None
    assert all(one.direction is not None for one in past[1:])
    assert config.load(opened).goal == "strength"
    assert [one.declaration.goal for one in config.versions(opened)] == ["strength", "hypertrophy"], "newest first"
    assert mesocycles.finished(opened) is None


def test_reporting_the_workout_left_ends_the_mesocycle_and_asks_for_the_next(
    opened: sqlite3.Connection,
) -> None:
    served, workout_id = mesocycles.record_served(opened, TODAY)
    workouts.record_performed(
        opened,
        tuple(as_performed(block) for block in served.blocks),
        on=TODAY,
        report="as prescribed",
        workout_id=workout_id,
    )

    request = plans.next_requested(opened, TODAY)

    assert request.continuing is not None
    assert request.continuing.mesocycle == mesocycles.history(opened)[-1].id
    assert request.slots[0].goal == "strength"


def test_a_lift_shows_the_load_the_history_lifted_it_with_and_a_pull_up_none(opened: sqlite3.Connection) -> None:
    assert state.last_performed_load(opened, "Barbell_Squat").value == 80
    assert state.last_performed_load(opened, "Chin-Up").value is None


def test_the_history_ends_the_day_before_today(opened: sqlite3.Connection) -> None:
    (last,) = opened.execute("SELECT MAX(performed_on) FROM workouts").fetchone()

    assert last == "2026-10-03"


def test_a_home_already_holding_a_database_is_left_alone(built: Path) -> None:
    with pytest.raises(demo.DemoError, match="delete it"):
        demo.build(built, TODAY)


def test_a_mesocycle_the_validator_refuses_is_named_and_nothing_is_written(tmp_path: Path) -> None:
    history = demo.history_path().read_text(encoding="utf-8").replace(
        "duration_cap_min = 45", "duration_cap_min = 15"
    )

    with pytest.raises(demo.DemoError, match=r"\[mesocycles.hypertrophy\] budget"):
        demo.build(tmp_path, TODAY, demo.parse(history))

    assert not (tmp_path / database.DEFAULT_DATABASE_NAME).exists()


def test_the_command_says_where_the_home_is_and_how_to_point_the_bot_at_it(tmp_path: Path) -> None:
    home = tmp_path / "reps-demo"

    result = CliRunner().invoke(cli.main, ["demo", str(home)])

    assert result.exit_code == 0, result.output
    assert f"TRAINER_HOME={home}" in result.output
    assert result.output.isascii()
    assert (home / database.DEFAULT_DATABASE_NAME).exists()


def test_a_history_that_is_not_there_is_named_as_a_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(demo.DemoError, match="run it from the repository"):
        demo.build(tmp_path / "home", TODAY)


def test_a_direction_missing_its_theme_is_refused_naming_what_it_needs() -> None:
    text = demo.history_path().read_text(encoding="utf-8").replace('theme = "new angles"', 'thema = "new angles"')

    with pytest.raises(demo.DemoError, match="a direction has a theme, changes and why"):
        demo.parse(text)


def test_a_direction_varying_what_no_direction_varies_is_refused() -> None:
    text = demo.history_path().read_text(encoding="utf-8").replace(
        'varies = ["exercises", "reps", "rest"]', 'varies = ["tempo"]', 1
    )

    with pytest.raises(demo.DemoError, match="varies some of"):
        demo.parse(text)


def test_the_first_mesocycle_follows_nothing_so_it_has_no_direction() -> None:
    text = demo.history_path().read_text(encoding="utf-8").replace(
        '[[history]]\nmesocycle = "hypertrophy"\n',
        '[[history]]\nmesocycle = "hypertrophy"\n'
        'direction = { theme = "t", changes = "c", why = "w", varies = ["rest"] }\n',
    )

    with pytest.raises(demo.DemoError, match="follows nothing"):
        demo.parse(text)
