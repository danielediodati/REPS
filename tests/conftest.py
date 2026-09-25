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

from trainer.coach import logfile
from trainer.engine.catalog import Exercise

_CREDENTIAL_HINTS = ("API_KEY", "_TOKEN", "SECRET")


_REAL_SOCKET = socket.socket
_REAL_SOCKETPAIR = socket.socketpair


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempt to reach something outside this process fails loudly.

    `socketpair` is the one exception, and it is not a hole: it returns two
    ends of the same pipe inside this process, reaches nothing, and works with
    the network cable out. It is allowed because asyncio's event loop opens one
    to wake itself up -- on Windows through `socket.socketpair()` -- so with it
    refused `asyncio.run` dies before any test body runs, and nothing
    asynchronous can be tested at all. The bot is asynchronous by nature: a run
    that blocked the loop could not receive the message it is supposed to queue.

    It is rebuilt on the real class rather than passed through, because
    `socket.socketpair` reaches for the module global `socket`, which is
    `refuse` by the time it runs.

    That swap is process-wide for the length of the call, so a thread opening a
    socket inside that window meets no guard. Left that way on purpose: closing
    it means copying the standard library's `socketpair` into this file, and
    what the guard is for is catching a test that *grows* a dependency on the
    network -- which it still does, because every attempt outside the window,
    including the next one, fails loudly.
    """

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the test suite must not touch the network")

    class Refusing(type):
        """`isinstance` still answers about real sockets, whatever stands in for the class.

        Windows' event loop wakes itself from another thread through a socket
        pair, and reads it with `isinstance(conn, socket.socket)`. With a
        function in that name the check raises TypeError, the wake-up is lost,
        and a test that waits on a thread -- `asyncio.to_thread`, which is how
        the bot keeps a run off the loop -- hangs until it is killed. It cost a
        pytest run that never finished and a log full of *Error on reading from
        the event loop self pipe*.
        """

        def __instancecheck__(cls, instance: Any) -> bool:
            return isinstance(instance, _REAL_SOCKET)

    class Refused(metaclass=Refusing):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            refuse()

    def paired(*args: Any, **kwargs: Any) -> Any:
        setattr(socket, "socket", _REAL_SOCKET)
        try:
            return _REAL_SOCKETPAIR(*args, **kwargs)
        finally:
            setattr(socket, "socket", Refused)

    monkeypatch.setattr(socket, "socket", Refused)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "socketpair", paired)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing in the suite may depend on a key being present."""
    import os

    for name in list(os.environ):
        if any(hint in name.upper() for hint in _CREDENTIAL_HINTS):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def machine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Everything the machine writes, pointed somewhere disposable.

    Autouse for the reason `no_network` is: the home defaults to `~/.reps`, so
    a test that resolves a path without an override of its own would reach the
    developer's real installation -- and `pytest` would write into the database
    the bot is running on.
    """
    directory = tmp_path / "home"
    directory.mkdir(exist_ok=True)
    monkeypatch.setenv("TRAINER_HOME", str(directory))
    return directory


@pytest.fixture(autouse=True)
def bot_log() -> Iterator[None]:
    """No test leaves the bot's log attached to the root logger.

    Autouse, because the handler is process-wide and holds its file open: left
    behind, every later test writes into a `tmp_path` that has been deleted,
    and on Windows the open handle stops it being deleted at all.
    """
    yield
    logfile.stop()


@pytest.fixture()
def database_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A throwaway database, pointed at by the documented environment variable."""
    path = tmp_path / "trainer.sqlite"
    monkeypatch.setenv("TRAINER_DB", str(path))
    yield path


def serving(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """What Groq answers when it is asked for its models, without a network.

    `models.ready` checks the name against what Groq actually serves, so every
    test that takes the Groq path has to say what that is -- and the suite has
    no sockets, which is the point. Stood in for at this project's own seam
    rather than at the SDK's, so nothing here has to know the shape of
    somebody else's client.
    """
    from trainer.coach import models

    monkeypatch.setattr(models, "groq_models", lambda key: set(names))


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
goal = "hypertrophy"
split = [["chest", "arms"], ["back", "core"], ["legs"], ["shoulders", "arms"]]
equipment = ["barbell"]
"""
"""What a test reads when it asks what the user declared.

A four-workout rotation, because `state.window` multiplies the cycle length by
the cycles asked for and a length of 1 would make every window test pass for
the wrong reason. One piece of equipment, and `barbell`, because it is what
the fixture catalogs are built out of: the declaration is what a door plans
against when nobody names equipment for today.
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


@pytest.fixture(autouse=True)
def checkpointed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway checkpointer file, for every test that does not bring its own.

    Autouse for the reason `declared_training` is: `checkpoints_path()` falls
    back to `checkpoints.sqlite` in the working directory, and `trainer plan`
    opens a checkpointer as of session 7. Left alone, the suite would write
    threads into the developer's own file -- and a run of `pytest` would leave
    the project's checkpoints holding conversations nobody had.

    Its own directory, so the tests that point `TRAINER_CHECKPOINTS` at
    `tmp_path` themselves still mean what they say.
    """
    directory = tmp_path / "checkpointed"
    directory.mkdir(exist_ok=True)
    path = directory / "checkpoints.sqlite"
    monkeypatch.setenv("TRAINER_CHECKPOINTS", str(path))
    return path


DAILY_QUOTA = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`qwen/qwen3.8-27b` in organization `org_x` service tier `on_demand` on "
    "tokens per day (TPD): Limit 200000, Used 198660, Requested 3303. Please "
    "try again in 14m8.016s. Need more tokens? Upgrade to Dev Tier today at "
    "https://console.groq.com/settings/billing', 'type': 'tokens', 'code': "
    "'rate_limit_exceeded'}}"
)
"""What Groq raised on 2026-09-21 when the free tier's day ran out, verbatim."""


def refused_by_groq(message: str = DAILY_QUOTA) -> Exception:
    """Groq's own rate-limit error, carrying `message`, with no request sent."""
    import groq
    import httpx

    response = httpx.Response(
        429, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat")
    )
    return groq.RateLimitError(message, response=response, body=None)


class Exhausted:
    """A chat model whose provider has no quota left: every call raises, and is counted."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, *args: Any, **kwargs: Any) -> Exhausted:
        return self

    def with_structured_output(self, *args: Any, **kwargs: Any) -> Exhausted:
        return self

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise refused_by_groq()
