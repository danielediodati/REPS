"""The chat models the coach builds from the environment, and their preconditions."""

from __future__ import annotations

from collections.abc import Callable
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


# -- the entrance's own model (ADR-0006, item 3) -------------------------------


def test_the_entrance_runs_on_a_smaller_model_than_the_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not `DEFAULT_MODEL`. The entrance is read and answered on every turn,
    and half a minute to say hello is worse than the silence it replaces."""
    monkeypatch.delenv(models.ENTRANCE_MODEL_ENV, raising=False)
    monkeypatch.delenv(models.MODEL_ENV, raising=False)

    front = models.entrance()

    assert front.name == models.DEFAULT_ENTRANCE_MODEL
    assert front.name != models.DEFAULT_MODEL
    assert front.provider == models.OLLAMA


def test_the_entrance_takes_the_model_the_environment_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.ENTRANCE_MODEL_ENV, "llama3.2:3b")

    assert models.entrance().name == "llama3.2:3b"


def test_the_entrance_falls_back_to_the_provider_the_coach_runs_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One provider to think about on a fresh clone, and two lines when the
    planner goes to Groq and the entrance stays here."""
    monkeypatch.delenv(models.ENTRANCE_BACKEND_ENV, raising=False)
    monkeypatch.setenv(models.BACKEND_ENV, models.GROQ)
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")

    assert models.entrance().provider == models.GROQ


def test_the_entrance_can_stay_local_while_the_planner_goes_to_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, models.GROQ)
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.ENTRANCE_BACKEND_ENV, models.OLLAMA)

    assert models.entrance().provider == models.OLLAMA
    assert models.chat().provider == models.GROQ


def test_an_entrance_backend_nobody_built_names_its_own_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.ENTRANCE_BACKEND_ENV, "vllm")

    with pytest.raises(models.ModelError, match=models.ENTRANCE_BACKEND_ENV):
        models.entrance()


def test_a_model_groq_does_not_serve_names_the_line_that_chose_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two nodes name two models, and *set `GROQ_MODEL`* on the entrance's 404
    sends the reader to the planner's line."""
    monkeypatch.setenv(models.BACKEND_ENV, models.GROQ)
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.ENTRANCE_MODEL_ENV, "a-name-groq-retired")
    serving(monkeypatch, models.DEFAULT_GROQ_MODEL)

    with pytest.raises(models.ModelError, match=models.ENTRANCE_MODEL_ENV):
        models.ready(models.entrance())


def test_the_entrance_never_asks_a_local_model_to_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama refuses the setting outright on a model with no thinking phase:
    `"llama3.1" does not support thinking`, a 400, and the first turn of the
    conversation lost. The default entrance model is one of those, and the
    entrance would not want it anyway -- the seconds spent reasoning are the
    seconds the user is looking at an empty chat."""
    monkeypatch.delenv(models.ENTRANCE_MODEL_ENV, raising=False)

    assert cast(Any, models.entrance().model).reasoning is None
    assert cast(Any, models.chat().model).reasoning == models.REASONING


def test_groqs_day_running_out_is_a_state_saying_when_to_come_back() -> None:
    """Every request after it is refused the same way, so it is not a run that failed."""
    from conftest import refused_by_groq

    spent = models.spent(refused_by_groq())

    assert spent is not None
    said = str(spent)
    assert "daily" in said and "14m8s" in said and "qwen/qwen3.8-27b" in said
    assert said.isascii()


def test_a_limit_per_minute_is_not_the_day_running_out() -> None:
    """The SDK waits those out itself; the next request may well go through."""
    from conftest import refused_by_groq

    minute = refused_by_groq(
        "Error code: 429 - Rate limit reached on tokens per minute (TPM): "
        "Limit 8000. Please try again in 1.2s."
    )

    assert models.spent(minute) is None


def test_any_other_failure_is_not_a_spent_quota() -> None:
    assert models.spent(ConnectionError("the server went away")) is None


# -- OpenRouter ----------------------------------------------------------------


def routing(
    monkeypatch: pytest.MonkeyPatch,
    *names: str,
    entries: dict[str, dict[str, Any]] | None = None,
) -> None:
    """What OpenRouter answers when asked for its models, without a network; `entries` by model name."""

    def listed(key: str) -> dict[str, dict[str, Any]]:
        return {name: (entries or {}).get(name, {}) for name in names}

    monkeypatch.setattr(models, "openrouter_listing", listed)


def openrouter_chat(name: str) -> models.Chat:
    return models.Chat(cast(BaseChatModel, object()), models.OPENROUTER, name)


def test_the_openrouter_chat_says_which_provider_and_model_it_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "openrouter")
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.OPENROUTER_MODEL_ENV, "anthropic/claude-haiku-4.5")

    chat = models.chat()

    assert chat.provider == models.OPENROUTER
    assert chat.name == "anthropic/claude-haiku-4.5"
    assert chat.setting == models.OPENROUTER_MODEL_ENV


def test_openrouter_is_asked_only_for_hosts_that_honour_the_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that ignores `response_format` would make the strict schema a suggestion."""
    monkeypatch.setenv(models.BACKEND_ENV, "openrouter")
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    built = cast(Any, models.chat().model)

    assert built.openai_api_base == models.OPENROUTER_URL
    assert built.extra_body["provider"] == {"require_parameters": True}


def test_openrouter_is_asked_what_each_request_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dollars are read from the provider, never from a price typed here."""
    built = cast(Any, openrouter_logger(monkeypatch).model)

    assert built.extra_body["usage"] == {"include": True}


def test_openrouter_with_no_key_is_a_state_with_the_way_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "openrouter")

    with pytest.raises(models.ModelError) as raised:
        models.chat()

    assert models.OPENROUTER_KEY_ENV in str(raised.value)
    assert ".env" in str(raised.value)


def test_the_entrance_can_talk_on_openrouter_while_the_planner_stays_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.ENTRANCE_BACKEND_ENV, "openrouter")
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    monkeypatch.delenv(models.ENTRANCE_MODEL_ENV, raising=False)

    front = models.entrance()

    assert front.provider == models.OPENROUTER
    assert front.name == models.DEFAULT_OPENROUTER_MODEL
    assert models.chat().provider == models.OLLAMA


def test_a_model_openrouter_does_not_route_to_names_the_line_that_chose_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing(monkeypatch, models.DEFAULT_OPENROUTER_MODEL)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    chat = models.Chat(
        cast(BaseChatModel, object()),
        models.OPENROUTER,
        "a/model-nobody-routes",
        models.ENTRANCE_MODEL_ENV,
    )

    with pytest.raises(models.ModelError) as raised:
        models.ready(chat)

    said = str(raised.value)
    assert "a/model-nobody-routes" in said
    assert models.ENTRANCE_MODEL_ENV in said
    assert models.DEFAULT_OPENROUTER_MODEL in said
    assert said.isascii()


def test_a_model_openrouter_routes_to_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing(monkeypatch, models.DEFAULT_OPENROUTER_MODEL)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    models.ready(openrouter_chat(models.DEFAULT_OPENROUTER_MODEL))


def test_a_routing_suffix_is_ready_when_its_model_is_routed_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`:nitro` picks the fastest host; the listing names only the model."""
    routing(monkeypatch, models.DEFAULT_OPENROUTER_MODEL)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    models.ready(openrouter_chat(f"{models.DEFAULT_OPENROUTER_MODEL}:nitro"))

    with pytest.raises(models.ModelError):
        models.ready(openrouter_chat("a/model-nobody-routes:nitro"))


def test_an_unreachable_openrouter_is_a_state_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def offline(key: str) -> dict[str, dict[str, Any]]:
        raise ConnectionError("no route to host")

    monkeypatch.setattr(models, "openrouter_listing", offline)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    with pytest.raises(models.ModelError) as raised:
        models.ready(openrouter_chat(models.DEFAULT_OPENROUTER_MODEL))

    assert "OpenRouter cannot be reached" in str(raised.value)


def openrouter_logger(monkeypatch: pytest.MonkeyPatch, **env: str) -> models.Chat:
    """The logger's model on OpenRouter, built under `env`."""
    monkeypatch.setenv(models.BACKEND_ENV, "openrouter")
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return models.logger()


def test_the_loggers_effort_reaches_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = openrouter_logger(monkeypatch, LOGGER_REASONING="low")

    built = cast(Any, chat.model)
    assert built.extra_body["reasoning"] == {"effort": "low"}
    assert chat.reasoning == "low"
    assert chat.reasoning_setting == models.LOGGER_REASONING_ENV


def test_no_effort_sends_nothing_and_leaves_the_models_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = cast(Any, openrouter_logger(monkeypatch).model)

    assert "reasoning" not in built.extra_body


def test_each_node_reads_its_own_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    openrouter_logger(
        monkeypatch, PLANNER_REASONING="high", ENTRANCE_REASONING="none", LOGGER_REASONING="low"
    )

    assert models.planner().reasoning == "high"
    assert models.entrance().reasoning == "none"
    assert models.logger().reasoning == "low"


def test_an_effort_nobody_built_is_refused_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(models.ModelError) as raised:
        openrouter_logger(monkeypatch, LOGGER_REASONING="lots")

    said = str(raised.value)
    assert models.LOGGER_REASONING_ENV in said and "none, low, medium, high" in said
    assert said.isascii()


def test_a_pinned_host_is_the_only_one_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    built = cast(Any, openrouter_logger(monkeypatch, OPENROUTER_PROVIDER="groq").model)

    assert built.extra_body["provider"] == {
        "require_parameters": True,
        "order": ["groq"],
        "allow_fallbacks": False,
    }


def test_a_model_with_no_reasoning_is_refused_its_effort_by_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing(
        monkeypatch,
        "anthropic/claude-haiku-4.5",
        entries={"anthropic/claude-haiku-4.5": {"supported_parameters": ["tools", "response_format"]}},
    )
    chat = openrouter_logger(
        monkeypatch, LOGGER_MODEL="anthropic/claude-haiku-4.5", LOGGER_REASONING="low"
    )

    with pytest.raises(models.ModelError) as raised:
        models.ready(chat)

    said = str(raised.value)
    assert models.LOGGER_REASONING_ENV in said and "anthropic/claude-haiku-4.5" in said
    assert said.isascii()


def test_an_effort_the_model_does_not_list_is_refused_by_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing(
        monkeypatch,
        "openai/gpt-oss-20b",
        entries={
            "openai/gpt-oss-20b": {
                "supported_parameters": ["reasoning", "tools"],
                "reasoning": {"supported_efforts": ["low", "medium", "high"]},
            }
        },
    )
    chat = openrouter_logger(
        monkeypatch, LOGGER_MODEL="openai/gpt-oss-20b", LOGGER_REASONING="none"
    )

    with pytest.raises(models.ModelError) as raised:
        models.ready(chat)

    assert "low, medium, high" in str(raised.value)


def test_a_model_that_takes_the_effort_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    routing(
        monkeypatch,
        models.DEFAULT_OPENROUTER_MODEL,
        entries={models.DEFAULT_OPENROUTER_MODEL: {"supported_parameters": ["reasoning"]}},
    )

    models.ready(openrouter_logger(monkeypatch, LOGGER_REASONING="low"))


def test_an_effort_off_openrouter_is_refused_by_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = models.Chat(
        cast(BaseChatModel, object()),
        models.GROQ,
        models.DEFAULT_GROQ_MODEL,
        models.GROQ_MODEL_ENV,
        reasoning="low",
        reasoning_setting=models.PLANNER_REASONING_ENV,
    )

    with pytest.raises(models.ModelError) as raised:
        models.ready(chat)

    assert models.PLANNER_REASONING_ENV in str(raised.value)


def test_the_host_that_answered_is_kept_on_the_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter names it at the top of the response; the stock client drops it."""
    built = cast(Any, openrouter_logger(monkeypatch).model)
    response = {
        "id": "gen-1",
        "model": "qwen/qwen3.8-27b",
        "provider": "Groq",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }

    result = built._create_chat_result(response)

    assert result.generations[0].message.response_metadata["host"] == "Groq"


def openrouter_reply(usage: dict[str, Any]) -> dict[str, Any]:
    """A chat completion as OpenRouter sends it, with `usage` as given."""
    return {
        "id": "gen-1",
        "model": "qwen/qwen3.8-27b",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
        ],
        "usage": usage,
    }


def test_the_cost_the_provider_reports_is_kept_on_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = cast(Any, openrouter_logger(monkeypatch).model)
    usage = {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4, "cost": 0.00123}

    result = built._create_chat_result(openrouter_reply(usage))

    assert result.generations[0].message.response_metadata["cost"] == 0.00123


def test_a_reply_with_no_cost_carries_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent is not zero: a provider that says nothing has not said the call was free."""
    built = cast(Any, openrouter_logger(monkeypatch).model)
    usage = {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}

    result = built._create_chat_result(openrouter_reply(usage))

    assert "cost" not in result.generations[0].message.response_metadata


def test_openrouter_out_of_credits_is_a_spent_quota() -> None:
    """A paid key does not run out by the day; it runs out of credit, answered 402."""
    import httpx2
    import openai

    response = httpx2.Response(
        402, request=httpx2.Request("POST", models.OPENROUTER_URL + "/chat/completions")
    )
    refused = openai.APIStatusError(
        "Insufficient credits", response=response, body=None
    )

    spent = models.spent(refused)

    assert spent is not None
    assert "credits" in str(spent)
    assert str(spent).isascii()


def served_by(
    monkeypatch: pytest.MonkeyPatch, answer: Callable[[Any], Any], **env: str
) -> Any:
    """The logger's OpenRouter model, talking to `answer` instead of the network."""
    import httpx2

    built = cast(Any, openrouter_logger(monkeypatch, **env).model)
    return models.OpenRouterChat(
        model=built.model_name,
        api_key=built.openai_api_key,
        base_url=built.openai_api_base,
        extra_body=built.extra_body,
        http_client=httpx2.Client(transport=httpx2.MockTransport(answer)),
        max_retries=0,
    )


def failing_on(host: str) -> Callable[[Any], Any]:
    """An OpenRouter that relays `host`'s error in a 200, with no choices."""
    import httpx2

    def answer(request: Any) -> Any:
        return httpx2.Response(
            200,
            json={
                "error": {
                    "code": 502,
                    "message": "upstream went away",
                    "metadata": {"provider_name": host},
                },
                "choices": None,
            },
        )

    return answer


def test_openrouter_calls_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A host that stops answering once held a run for minutes."""
    built = cast(Any, openrouter_logger(monkeypatch).model)

    assert built.request_timeout == models.TIMEOUT_S
    assert built.max_retries == models.RETRIES


def test_a_host_error_on_a_structured_emission_names_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It reached the matrix as "'NoneType' object is not iterable"."""
    model = served_by(monkeypatch, failing_on("CoreWeave"))
    schema = {
        "title": "Said",
        "type": "object",
        "properties": {"said": {"type": "string"}},
        "required": ["said"],
        "additionalProperties": False,
    }

    with pytest.raises(models.ProviderFailed) as raised:
        model.with_structured_output(schema, method="json_schema").invoke("hello")

    assert "CoreWeave" in str(raised.value)
    assert "upstream went away" in str(raised.value)
    assert str(raised.value).isascii()


def test_a_host_error_on_a_tool_turn_names_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    model = served_by(monkeypatch, failing_on("AkashML"))

    with pytest.raises(models.ProviderFailed, match="AkashML"):
        model.invoke("hello")


def test_a_host_that_does_not_answer_is_named_with_the_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx2

    def silent(request: Any) -> Any:
        raise httpx2.ReadTimeout("timed out", request=request)

    model = served_by(monkeypatch, silent, OPENROUTER_PROVIDER="deepinfra")

    with pytest.raises(models.ProviderFailed) as raised:
        model.invoke("hello")

    assert "deepinfra" in str(raised.value)
    assert f"{models.TIMEOUT_S} s" in str(raised.value)


# -- a model per subgraph ------------------------------------------------------


def test_each_subgraph_takes_the_model_its_own_variable_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.BACKEND_ENV, "openrouter")
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.PLANNER_MODEL_ENV, "openai/gpt-oss-120b")
    monkeypatch.setenv(models.LOGGER_MODEL_ENV, "anthropic/claude-haiku-4.5")

    planner, logger = models.planner(), models.logger()

    assert (planner.name, planner.setting) == (
        "openai/gpt-oss-120b",
        models.PLANNER_MODEL_ENV,
    )
    assert (logger.name, logger.setting) == (
        "anthropic/claude-haiku-4.5",
        models.LOGGER_MODEL_ENV,
    )
    assert planner.provider == logger.provider == models.OPENROUTER


def test_a_subgraph_that_names_no_model_runs_on_the_coachs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One variable still moves both, for an installation that set neither."""
    monkeypatch.setenv(models.BACKEND_ENV, "groq")
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.GROQ_MODEL_ENV, "openai/gpt-oss-20b")
    monkeypatch.delenv(models.PLANNER_MODEL_ENV, raising=False)
    monkeypatch.delenv(models.LOGGER_MODEL_ENV, raising=False)

    for chat in (models.planner(), models.logger()):
        assert (chat.name, chat.setting) == ("openai/gpt-oss-20b", models.GROQ_MODEL_ENV)


def test_a_subgraph_model_groq_does_not_serve_names_its_own_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serving(monkeypatch, models.DEFAULT_GROQ_MODEL)
    monkeypatch.setenv(models.BACKEND_ENV, "groq")
    monkeypatch.setenv(models.API_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.LOGGER_MODEL_ENV, "a/model-nobody-serves")

    with pytest.raises(models.ModelError) as raised:
        models.ready(models.logger())

    assert models.LOGGER_MODEL_ENV in str(raised.value)


def test_a_local_subgraph_model_is_asked_to_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the entrance talks without reasoning; both subgraphs plan or extract."""
    monkeypatch.setenv(models.BACKEND_ENV, "ollama")
    monkeypatch.setenv(models.PLANNER_MODEL_ENV, "gpt-oss:120b")

    assert cast(Any, models.planner().model).reasoning == models.REASONING
