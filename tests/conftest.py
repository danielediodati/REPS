"""Test-wide guarantees.

The suite must run on a machine with no network and no credentials. That is not
a hope about how the tests were written: both are taken away here, so a test
that quietly grows a dependency on either fails instead of passing on a laptop
that happens to be online.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

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
