"""The planner probe's preconditions."""

from __future__ import annotations

from typing import Any

import ollama
import pytest

from trainer.coach import probe


def test_an_unreachable_ollama_stops_the_probe_with_the_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(self: ollama.Client, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("Failed to connect to Ollama.")

    monkeypatch.setattr(ollama.Client, "ps", unreachable)

    with pytest.raises(SystemExit, match="start Ollama"):
        probe.ready(ollama.Client(host="http://127.0.0.1:11434"))
