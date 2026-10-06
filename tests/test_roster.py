"""Every node's model, effort and host, on every backend and every setting, held to a recording."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from trainer.coach import models

RECORDED = Path(__file__).parent / "roster.json"
"""What each node resolved to before the roster; `RECORD_ROSTER=1` writes it instead of comparing."""

NODES = tuple(models.NODES)

SETTINGS = (
    models.BACKEND_ENV,
    models.ENTRANCE_BACKEND_ENV,
    models.MODEL_ENV,
    models.GROQ_MODEL_ENV,
    models.OPENROUTER_MODEL_ENV,
    models.OPENROUTER_PROVIDER_ENV,
    *(f"{node.upper()}_{kind}" for node in NODES for kind in ("MODEL", "REASONING", "HOST")),
)

SCENARIOS: dict[str, dict[str, str]] = {
    "bare": {},
    "own models": {f"{node.upper()}_MODEL": f"own/{node}" for node in NODES},
    "own efforts": {f"{node.upper()}_REASONING": "medium" for node in NODES},
    "own hosts": {f"{node.upper()}_HOST": f"host-{node}" for node in NODES},
    "coach's models": {
        models.MODEL_ENV: "coach-local",
        models.GROQ_MODEL_ENV: "coach/groq",
        models.OPENROUTER_MODEL_ENV: "coach/openrouter",
    },
    "coach's measured model": {models.OPENROUTER_MODEL_ENV: "deepseek/deepseek-v4-flash"},
    "one host for all": {models.OPENROUTER_PROVIDER_ENV: "everyone"},
    "own and coach's": {
        models.OPENROUTER_MODEL_ENV: "coach/openrouter",
        models.GROQ_MODEL_ENV: "coach/groq",
        "PLANNER_MODEL": "own/planner",
        models.ENTRANCE_MODEL_ENV: "own/entrance",
    },
}


def cases() -> list[tuple[str, str, str]]:
    return [
        (backend, front, scenario)
        for backend in models.BACKENDS
        for front in ("", *models.BACKENDS)
        for scenario in SCENARIOS
    ]


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
        "class": type(built).__name__,
        "model": getattr(built, "model", None) or getattr(built, "model_name", None),
        "ollama_reasoning": getattr(built, "reasoning", "n/a") if isinstance(built, models.ChatOllama) else "n/a",
        "extra_body": getattr(built, "extra_body", None),
    }


def everything(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for backend, front, scenario in cases():
        with monkeypatch.context() as patched:
            for setting in SETTINGS:
                patched.delenv(setting, raising=False)
            patched.setenv(models.API_KEY_ENV, "groq-key")
            patched.setenv(models.OPENROUTER_KEY_ENV, "openrouter-key")
            patched.setenv(models.BACKEND_ENV, backend)
            if front:
                patched.setenv(models.ENTRANCE_BACKEND_ENV, front)
            for setting, value in SCENARIOS[scenario].items():
                patched.setenv(setting, value)
            seen[f"{backend} / entrance {front or '-'} / {scenario}"] = {
                node: resolved(node) for node in NODES
            }
    return seen


def test_every_node_resolves_as_it_did_before_the_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = everything(monkeypatch)

    if os.environ.get("RECORD_ROSTER"):
        RECORDED.write_text(json.dumps(seen, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert seen == json.loads(RECORDED.read_text(encoding="utf-8"))


def test_one_stand_in_covers_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_cli import stand_in

    held = models.Chat(object(), "scripted", "a-stand-in")  # type: ignore[arg-type]
    stand_in(monkeypatch, lambda: held)

    assert models.roster() == {node: held for node in models.NODES}
