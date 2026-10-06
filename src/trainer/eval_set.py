"""What the TOML eval sets share: where one is read from, its TOML, and the error a set that cannot be run raises."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class SetError(ValueError):
    """A set that cannot be run as written, saying where."""


def path(env_var: str, parts: Sequence[str]) -> Path:
    """Where a set is read from: the file `env_var` names, or the committed one."""
    override = os.environ.get(env_var)
    return Path(override).expanduser() if override else Path.cwd().joinpath(*parts)


def load(
    where: Path | None,
    env_var: str,
    parts: Sequence[str],
    what: str,
    parse: Callable[[str], T],
    error: type[SetError],
) -> T:
    """The set off disk, parsed; refused naming the file when it is not there."""
    target = where if where is not None else path(env_var, parts)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as missing:
        raise error(f"the {what} is not at {target}") from missing
    return parse(text)


def toml(text: str, error: type[SetError]) -> dict[str, Any]:
    """The set's TOML, or the error saying it is not TOML."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as broken:
        raise error(f"the set is not TOML: {broken}") from broken


def unique(names: Sequence[str], error: type[SetError]) -> None:
    """Refuse a set naming two cases alike."""
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise error(f"cases named twice: {', '.join(repeated)}")
