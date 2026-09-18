"""The chat models the coach builds from the environment, and their preconditions."""

from __future__ import annotations

from typing import Any, cast

import ollama
import pytest
from langchain_core.language_models import BaseChatModel

from conftest import serving
from trainer.coach import models


def test_a_context_length_that_is_not_a_number_is_a_state_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_LENGTH", "16k")

    with pytest.raises(models.ModelError, match="OLLAMA_CONTEXT_LENGTH is '16k'"):
        models.ollama_model()


def test_the_context_length_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_LENGTH", "16384")

    assert models.ollama_model().num_ctx == 16384


# -- which provider ------------------------------------------------------------


def test_the_backend_defaults_to_ollama_when_nothing_names_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0004 item 8: the default is the laptop, not the paid provider."""
    monkeypatch.delenv(models.BACKEND_ENV, raising=False)

    assert models.backend() == models.OLLAMA


def test_a_backend_nobody_built_is_named_with_the_ones_that_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falling through to a provider the user did not ask for would spend
    their key, or their laptop, on a typo."""
    monkeypatch.setenv(models.BACKEND_ENV, "openai")

    with pytest.raises(models.ModelError) as raised:
        models.backend()

    assert "openai" in str(raised.value)
    assert models.OLLAMA in str(raised.value)
    assert models.GROQ in str(raised.value)


def test_the_ollama_chat_says_which_provider_and_model_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record's `provider` comes from here rather than from a constant."""
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.MODEL_ENV, "qwen3.5:9b")

    chat = models.chat()

    assert chat.provider == models.OLLAMA
    assert chat.name == "qwen3.5:9b"


def test_the_groq_chat_says_which_provider_and_model_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "groq")
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")

    chat = models.chat()

    assert chat.provider == models.GROQ
    assert chat.name == "openai/gpt-oss-20b"


def test_groq_with_no_key_is_a_state_with_the_way_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`conftest.py` takes every credential away, so this is the state under
    test rather than something about this machine. Checked before a request
    goes out: left to the SDK it is a 401 after a round-trip."""
    monkeypatch.setenv(models.BACKEND_ENV, "groq")

    with pytest.raises(models.ModelError) as raised:
        models.chat()

    assert models.API_KEY_ENV in str(raised.value)
    assert ".env" in str(raised.value)


# -- the provider's state ------------------------------------------------------


def listing(*names: str) -> Any:
    """What `ollama.Client.list` answers, with only the field `ready` reads."""

    class Listed:
        def __init__(self, name: str) -> None:
            self.model = name

    class Response:
        def __init__(self) -> None:
            self.models = [Listed(name) for name in names]

    def answer(self: ollama.Client, *args: Any, **kwargs: Any) -> Any:
        return Response()

    return answer


def test_an_unreachable_ollama_is_a_state_with_the_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(self: ollama.Client, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("Failed to connect to Ollama.")

    monkeypatch.setattr(ollama.Client, "list", unreachable)
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")

    with pytest.raises(models.ModelError, match="start Ollama"):
        models.ready(models.chat())


def test_a_model_that_is_not_pulled_names_the_command_that_pulls_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The state a fresh clone hits. Left to the run it arrives as a 404 from
    the server, which names neither the model nor the way out."""
    monkeypatch.setattr(ollama.Client, "list", listing("llama3.1:latest"))
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.MODEL_ENV, "gpt-oss:20b")

    with pytest.raises(models.ModelError, match="ollama pull gpt-oss:20b"):
        models.ready(models.chat())


def test_a_model_named_without_its_tag_is_the_one_that_is_pulled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama resolves a bare name to `:latest` and `ollama list` always
    reports the tag, so the two name one model. Compared as written, a model
    that is there is refused with a pull that would change nothing."""
    monkeypatch.setattr(ollama.Client, "list", listing("llama3.1:latest"))
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.MODEL_ENV, "llama3.1")

    models.ready(models.chat())


def test_a_model_that_is_pulled_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama.Client, "list", listing("gpt-oss:20b"))
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.MODEL_ENV, "gpt-oss:20b")

    models.ready(models.chat())


def test_an_unset_context_length_is_a_state_saying_what_it_does_to_planning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.delenv(models.CONTEXT_ENV, raising=False)

    with pytest.raises(models.ModelError) as raised:
        models.context_length(models.chat())

    said = str(raised.value)
    assert models.CONTEXT_ENV in said
    assert str(models.MEASURED_CONTEXT) in said
    assert "truncated" in said
    assert said.isascii()


def test_a_context_length_under_the_measured_one_is_refused_the_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.CONTEXT_ENV, "4096")

    with pytest.raises(models.ModelError, match="truncated"):
        models.context_length(models.chat())


def test_a_context_length_at_the_measured_one_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.CONTEXT_ENV, str(models.MEASURED_CONTEXT))

    assert models.context_length(models.chat()) == models.MEASURED_CONTEXT


def test_groq_needs_no_context_length(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "groq")
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")
    monkeypatch.delenv(models.CONTEXT_ENV, raising=False)

    assert models.context_length(models.chat()) is None


def test_groq_is_not_asked_whether_ollama_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each provider is checked against itself. Groq is asked what it serves,
    and no local server is consulted to answer that."""

    def refuse(self: ollama.Client, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Groq must not be checked against a local server")

    monkeypatch.setattr(ollama.Client, "list", refuse)
    monkeypatch.setenv(models.BACKEND_ENV, "groq")
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")

    with pytest.raises(models.ModelError) as raised:
        models.ready(models.chat())

    assert "Groq cannot be reached" in str(raised.value), "the suite has no network"


def groq_chat(name: str) -> models.Chat:
    """A `Chat` on Groq without building one, so a stubbed SDK is only ever
    asked the question under test."""
    return models.Chat(cast(BaseChatModel, object()), models.GROQ, name)


def test_a_model_groq_does_not_serve_is_a_state_with_its_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retired model arrives mid-run as a 404, which reads as the run being
    broken rather than as one name being gone."""
    serving(monkeypatch, "openai/gpt-oss-120b")
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")

    with pytest.raises(models.ModelError) as raised:
        models.ready(groq_chat("a/model-nobody-serves"))

    said = str(raised.value)
    assert "a/model-nobody-serves" in said
    assert models.GROQ_MODEL_ENV in said
    assert "openai/gpt-oss-120b" in said, "it names one that would work"


def test_a_model_groq_serves_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    serving(monkeypatch, models.DEFAULT_GROQ_MODEL)
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")

    models.ready(groq_chat(models.DEFAULT_GROQ_MODEL))


def test_groq_with_no_key_is_not_asked_what_it_serves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The credentials state comes first: without a key there is no request to
    make, and *Groq cannot be reached* would name the wrong thing."""
    monkeypatch.setenv(models.BACKEND_ENV, "groq")
    monkeypatch.delenv(models.API_KEY_ENV, raising=False)

    with pytest.raises(models.ModelError) as raised:
        models.ready(groq_chat("a-model"))

    assert models.API_KEY_ENV in str(raised.value)


# -- values a person can get wrong in .env -----------------------------------


def test_a_max_tokens_that_is_not_a_number_is_a_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is interpolated into the rate-limit message, so left unchecked it
    raises *while handling* the 429 it was meant to explain."""
    monkeypatch.setenv(models.MAX_TOKENS_ENV, "2k")

    with pytest.raises(models.ModelError, match="whole number"):
        models.max_tokens()


def test_a_max_tokens_of_zero_is_a_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(models.MAX_TOKENS_ENV, "0")

    with pytest.raises(models.ModelError, match="at least one"):
        models.max_tokens()


def test_max_tokens_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.MAX_TOKENS_ENV, "4096")

    assert models.max_tokens() == 4096
