"""The chat models the coach builds from the environment."""

from __future__ import annotations

import pytest

from trainer.coach import models


def test_a_context_length_that_is_not_a_number_is_a_state_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_LENGTH", "16k")

    with pytest.raises(models.ModelError, match="OLLAMA_CONTEXT_LENGTH is '16k'"):
        models.ollama()


def test_the_context_length_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_LENGTH", "16384")

    assert models.ollama().num_ctx == 16384
