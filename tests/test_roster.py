"""Every node's model, effort and host, under every setting, held to a recording."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from trainer.coach import models

RECORDED = Path(__file__).parent / "roster.json"
"""What each node resolves to; `RECORD_ROSTER=1` writes it instead of comparing."""

NODES = tuple(models.NODES)

SETTINGS = (
    models.OPENROUTER_MODEL_ENV,
    models.OPENROUTER_PROVIDER_ENV,
    *(f"{node.upper()}_{kind}" for node in NODES for kind in ("MODEL", "REASONING", "HOST")),
)

SCENARIOS: dict[str, dict[str, str]] = {
    "bare": {},
    "own models": {f"{node.upper()}_MODEL": f"own/{node}" for node in NODES},
    "own efforts": {f"{node.upper()}_REASONING": "medium" for node in NODES},
    "own hosts": {f"{node.upper()}_HOST": f"host-{node}" for node in NODES},
    "coach's model": {models.OPENROUTER_MODEL_ENV: "coach/openrouter"},
    "coach's measured model": {models.OPENROUTER_MODEL_ENV: "deepseek/deepseek-v4-flash"},
    "one host for all": {models.OPENROUTER_PROVIDER_ENV: "everyone"},
    "own and coach's": {
        models.OPENROUTER_MODEL_ENV: "coach/openrouter",
        "PLANNER_MODEL": "own/planner",
        "ENTRANCE_MODEL": "own/entrance",
    },
}


def resolved(node: models.Node) -> dict[str, Any]:
    chat = models.chat_for(node)
    built: Any = chat.model
    return {
        "provider": chat.provider,
        "name": chat.name,
        "setting": chat.setting,
        "reasoning": chat.reasoning,
        "reasoning_setting": chat.reasoning_setting,
        "host": chat.host,
        "model": built.model_name,
        "extra_body": built.extra_body,
    }


def everything(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for scenario, settings in SCENARIOS.items():
        with monkeypatch.context() as patched:
            for setting in SETTINGS:
                patched.delenv(setting, raising=False)
            patched.setenv(models.OPENROUTER_KEY_ENV, "openrouter-key")
            for setting, value in settings.items():
                patched.setenv(setting, value)
            seen[scenario] = {
                node: resolved(node) for node in NODES
            }
    return seen


def test_every_node_resolves_as_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = everything(monkeypatch)

    if os.environ.get("RECORD_ROSTER"):
        RECORDED.write_text(json.dumps(seen, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert seen == json.loads(RECORDED.read_text(encoding="utf-8"))


def test_one_stand_in_covers_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_cli import stand_in

    held = models.Chat(object(), "scripted", "a-stand-in")  # type: ignore[arg-type]
    stand_in(monkeypatch, lambda: held)

    assert models.roster() == {node: held for node in models.NODES}
