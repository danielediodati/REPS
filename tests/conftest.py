"""Test-wide guarantees.

The suite must run on a machine with no network and no credentials. That is not
a hope about how the tests were written: both are taken away here, so a test
that quietly grows a dependency on either fails instead of passing on a laptop
that happens to be online.
"""

from __future__ import annotations

import json
import socket
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from trainer.engine.catalog import Exercise

_CREDENTIAL_HINTS = ("API_KEY", "_TOKEN", "SECRET")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempt to open a socket fails loudly."""

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the test suite must not touch the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing in the suite may depend on a key being present."""
    import os

    for name in list(os.environ):
        if any(hint in name.upper() for hint in _CREDENTIAL_HINTS):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def database_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A throwaway database, pointed at by the documented environment variable."""
    path = tmp_path / "trainer.sqlite"
    monkeypatch.setenv("TRAINER_DB", str(path))
    yield path


def make_exercise(**overrides: Any) -> Exercise:
    """A catalog row, with only the fields a test cares about spelled out.

    Shared because three test modules build one, and a builder that drifts
    between them is three suites quietly asking about different catalogs.
    """
    base: dict[str, Any] = {
        "id": "Some_Exercise",
        "name": "Some Exercise",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primary_muscles": ("shoulders",),
        "secondary_muscles": (),
        "instructions": (),
        "images": (),
    }
    base.update(overrides)
    return Exercise(**base)


def enrich(
    connection: sqlite3.Connection,
    patterns: Mapping[str, tuple[str, str, str, str, int]],
) -> None:
    """Write session 2's enrichment onto rows a test already imported.

    `patterns` maps an exercise id to `(movement_pattern, loaded_joints,
    spinal_axial_load, required_stability, setup_cost_min)`, with the joints
    given as a comma-separated string because that is what reads well in a
    fixture table.

    One copy of the column list, in one place. Spread across the test modules
    that need it, the next migration touching an enrichment column has to be
    found in each of them, and the one that is missed keeps passing against a
    catalog the others no longer describe.
    """
    for exercise_id, (pattern, joints, axial, stability, setup) in patterns.items():
        connection.execute(
            "UPDATE exercises SET movement_pattern = ?, movement_pattern_source = 'rule', "
            "loaded_joints = ?, loaded_joints_source = 'rule', "
            "spinal_axial_load = ?, spinal_axial_load_source = 'rule', "
            "required_stability = ?, required_stability_source = 'rule', "
            "setup_cost_min = ?, setup_cost_min_source = 'rule' WHERE id = ?",
            (
                pattern,
                json.dumps([joint.strip() for joint in joints.split(",")]),
                axial,
                stability,
                setup,
                exercise_id,
            ),
        )


DECLARED_CONFIG = """\
cycle_length = 4
duration_cap_min = 60
volume_denominator = "cycle"
split = [["chest", "arms"], ["back", "core"], ["legs"], ["shoulders", "arms"]]
"""
"""What a test reads when it asks what the user declared.

A four-workout rotation, because `state.window` multiplies the cycle length by
the cycles asked for and a length of 1 would make every window test pass for
the wrong reason.
"""


@pytest.fixture(autouse=True)
def declared_training(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A training configuration, for every test that does not bring its own.

    Autouse for the reason `no_network` is: `config.config_path()` falls back
    to `Path.cwd() / "training.toml"`, so a developer who has declared their
    own rotation in the checkout would have the suite read it -- and every
    window, split and cycle assertion would be about their file rather than
    about the code. Pointed somewhere disposable, the suite says the same thing
    on every machine.

    Overridden by any test that sets `TRAINER_CONFIG` itself, which is how the
    absent-configuration and broken-configuration states are still exercised.
    It is written to a directory of its own rather than to `tmp_path`, because
    those tests point at `tmp_path / "training.toml"` to mean *there is no such
    file* -- and a fixture that had already written one there would answer them
    with a configuration.
    """
    directory = tmp_path / "declared"
    directory.mkdir(exist_ok=True)
    path = directory / "training.toml"
    path.write_text(DECLARED_CONFIG, encoding="utf-8")
    monkeypatch.setenv("TRAINER_CONFIG", str(path))
    return path
