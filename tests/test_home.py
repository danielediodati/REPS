"""One directory for everything the machine writes, and the overrides over it."""

from __future__ import annotations

from pathlib import Path

import pytest

from trainer import eval_runner
from trainer.coach import checkpoints
from trainer.engine import config, database, home


@pytest.fixture(autouse=True)
def no_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """The variable the suite sets for every other test, taken away here.

    These tests are about what the defaults are, and a fixture answering with
    a temporary directory would hide every one of them.
    """
    monkeypatch.delenv(home.HOME_ENV_VAR, raising=False)
    for name in (
        database.DATABASE_ENV_VAR,
        checkpoints.CHECKPOINTS_ENV,
        eval_runner.RECORDS_ENV_VAR,
    ):
        monkeypatch.delenv(name, raising=False)


class TestHome:
    def test_defaults_beside_the_user(self) -> None:
        assert home.home() == Path.home() / ".reps"

    def test_the_variable_wins(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path / "elsewhere"))

        assert home.home() == tmp_path / "elsewhere"

    def test_a_tilde_is_expanded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(home.HOME_ENV_VAR, "~/somewhere")

        assert home.home() == Path.home() / "somewhere"

    def test_the_working_directory_does_not_reach_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The whole point: two directories are one installation, not two."""
        monkeypatch.chdir(tmp_path)
        from_here = home.home()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        assert home.home() == from_here


class TestWhatLandsInIt:
    """The four paths the home resolves, and the override each one keeps."""

    def test_the_database(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path))

        assert database.database_path() == tmp_path / "trainer.sqlite"

        monkeypatch.setenv(database.DATABASE_ENV_VAR, str(tmp_path / "other.sqlite"))

        assert database.database_path() == tmp_path / "other.sqlite"

    def test_the_checkpointer(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path))

        assert checkpoints.checkpoints_path() == tmp_path / "checkpoints.sqlite"

        monkeypatch.setenv(checkpoints.CHECKPOINTS_ENV, str(tmp_path / "other.sqlite"))

        assert checkpoints.checkpoints_path() == tmp_path / "other.sqlite"

    def test_the_eval_records(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path))

        assert eval_runner.records_path() == tmp_path / "eval-runs"

        monkeypatch.setenv(eval_runner.RECORDS_ENV_VAR, str(tmp_path / "elsewhere"))

        assert eval_runner.records_path() == tmp_path / "elsewhere"

    def test_the_database_and_the_checkpointer_are_not_the_same_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """They share a directory now, which is exactly when this could go wrong."""
        monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path))

        assert database.database_path() != checkpoints.checkpoints_path()
