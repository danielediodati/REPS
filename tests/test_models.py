"""The chat models the coach builds from the environment, and their preconditions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from langchain_core.language_models import BaseChatModel

from trainer.coach import models


# -- spent credit --------------------------------------------------------------


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
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.OPENROUTER_MODEL_ENV, "anthropic/claude-haiku-4.5")

    chat = models.chat_for("planner")

    assert chat.provider == models.OPENROUTER
    assert chat.name == "anthropic/claude-haiku-4.5"
    assert chat.setting == models.OPENROUTER_MODEL_ENV


def test_openrouter_is_asked_only_for_hosts_that_honour_the_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that ignores `response_format` would make the strict schema a suggestion."""
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    built = cast(Any, models.openrouter_model("a/model", host=""))

    assert built.openai_api_base == models.OPENROUTER_URL
    assert built.extra_body["provider"] == {"require_parameters": True}


def test_openrouter_is_asked_what_each_request_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dollars are read from the provider, never from a price typed here."""
    built = cast(Any, openrouter_logger(monkeypatch).model)

    assert built.extra_body["usage"] == {"include": True}


def test_openrouter_with_no_key_is_a_state_with_the_way_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    with pytest.raises(models.ModelError) as raised:
        models.chat_for("planner")

    assert models.OPENROUTER_KEY_ENV in str(raised.value)
    assert ".env" in str(raised.value)


def test_a_model_openrouter_does_not_route_to_names_the_line_that_chose_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing(monkeypatch, models.NODES["planner"].choice.model)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    chat = models.Chat(
        cast(BaseChatModel, object()),
        models.OPENROUTER,
        "a/model-nobody-routes",
        models.NODES["entrance"].model,
    )

    with pytest.raises(models.ModelError) as raised:
        models.ready(chat)

    said = str(raised.value)
    assert "a/model-nobody-routes" in said
    assert models.NODES["entrance"].model in said
    assert models.NODES["entrance"].choice.model in said
    assert said.isascii()


def test_a_model_openrouter_routes_to_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing(monkeypatch, models.NODES["planner"].choice.model)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    models.ready(openrouter_chat(models.NODES["planner"].choice.model))


def test_a_routing_suffix_is_ready_when_its_model_is_routed_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`:nitro` picks the fastest host; the listing names only the model."""
    routing(monkeypatch, models.NODES["planner"].choice.model)
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    models.ready(openrouter_chat(f"{models.NODES["planner"].choice.model}:nitro"))

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
        models.ready(openrouter_chat(models.NODES["planner"].choice.model))

    assert "OpenRouter cannot be reached" in str(raised.value)


def openrouter_logger(monkeypatch: pytest.MonkeyPatch, **env: str) -> models.Chat:
    """The logger's model on OpenRouter, built under `env`."""
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return models.chat_for("logger")


def test_the_loggers_effort_reaches_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = openrouter_logger(monkeypatch, LOGGER_REASONING="low")

    built = cast(Any, chat.model)
    assert built.extra_body["reasoning"] == {"effort": "low"}
    assert chat.reasoning == "low"
    assert chat.reasoning_setting == models.NODES["logger"].reasoning


def test_each_node_reads_its_own_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    openrouter_logger(
        monkeypatch, PLANNER_REASONING="high", ENTRANCE_REASONING="none", LOGGER_REASONING="low"
    )

    assert models.chat_for("planner").reasoning == "high"
    assert models.chat_for("entrance").reasoning == "none"
    assert models.chat_for("logger").reasoning == "low"


def test_an_effort_nobody_built_is_refused_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(models.ModelError) as raised:
        openrouter_logger(monkeypatch, LOGGER_REASONING="lots")

    said = str(raised.value)
    assert models.NODES["logger"].reasoning in said and "none, low, medium, high" in said
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
    assert models.NODES["logger"].reasoning in said and "anthropic/claude-haiku-4.5" in said
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
        models.NODES["logger"].choice.model,
        entries={models.NODES["logger"].choice.model: {"supported_parameters": ["reasoning"]}},
    )

    models.ready(openrouter_logger(monkeypatch, LOGGER_REASONING="low"))


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
    monkeypatch: pytest.MonkeyPatch,
    answer: Callable[[Any], Any],
    retries: int = 0,
    **env: str,
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
        max_retries=retries,
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


def recording(into: list[dict[str, Any]]) -> Callable[[Any], Any]:
    """An OpenRouter that keeps each request's body and answers with an empty reply."""
    import json

    import httpx2

    def answer(request: Any) -> Any:
        into.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "a",
                "object": "chat.completion",
                "created": 0,
                "model": "a",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
            },
        )

    return answer


CONVERSATION: list[Any] = [
    ("system", "You plan."),
    ("human", "The brief."),
    ("ai", "Reading."),
    ("human", "The latest turn."),
]


def test_a_request_to_an_anthropic_model_marks_its_last_message_for_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic caches only up to a breakpoint, so without one each turn paid for the whole run again."""
    sent: list[dict[str, Any]] = []
    model = served_by(
        monkeypatch, recording(sent), LOGGER_MODEL="anthropic/claude-haiku-4.5"
    )

    model.invoke(CONVERSATION)

    *before, last = sent[0]["messages"]
    assert last["content"] == [
        {"type": "text", "text": "The latest turn.", "cache_control": {"type": "ephemeral"}}
    ]
    assert all("cache_control" not in str(message) for message in before)


def test_a_breakpoint_goes_on_the_last_part_of_a_message_already_in_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.messages import HumanMessage

    sent: list[dict[str, Any]] = []
    model = served_by(
        monkeypatch, recording(sent), LOGGER_MODEL="anthropic/claude-haiku-4.5"
    )
    parts = HumanMessage(
        content=[{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]
    )

    model.invoke([parts])

    first, second = sent[0]["messages"][-1]["content"]
    assert "cache_control" not in first
    assert second["cache_control"] == {"type": "ephemeral"}
    assert parts.content == [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]


def test_a_structured_emission_to_an_anthropic_model_is_marked_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []
    model = served_by(
        monkeypatch, recording(sent), LOGGER_MODEL="anthropic/claude-haiku-4.5"
    )
    schema = {
        "title": "Said",
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    model.with_structured_output(schema, method="json_schema", strict=True).invoke(
        CONVERSATION
    )

    assert sent[0]["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_a_request_to_a_model_that_caches_by_itself_carries_no_breakpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []
    model = served_by(monkeypatch, recording(sent))

    model.invoke(CONVERSATION)

    assert sent[0]["messages"][-1]["content"] == "The latest turn."
    assert "cache_control" not in str(sent[0])


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
    # The client retries a timeout before it raises, so the wait is every try, not one.
    assert f"{models.RETRIES + 1} tries of {models.TIMEOUT_S} s" in str(raised.value)


def rate_limited_until(answered_on: int, calls: list[Any]) -> Callable[[Any], Any]:
    """An OpenRouter whose pool at AkashML is full for the first `answered_on - 1` calls."""
    import httpx2

    def answer(request: Any) -> Any:
        calls.append(request)
        if len(calls) < answered_on:
            return httpx2.Response(
                429,
                json={
                    "error": {
                        "message": "Provider returned error",
                        "code": 429,
                        "metadata": {
                            "provider_name": "AkashML",
                            "limit_source": "upstream_provider_shared_pool",
                        },
                    }
                },
            )
        usage = {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}
        return httpx2.Response(200, json=openrouter_reply(usage))

    return answer


def test_a_rate_limited_call_waits_and_is_asked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """One quick retry lost two thirds of a pass to a shared pool that empties in seconds."""
    waited: list[float] = []
    monkeypatch.setattr(models, "_sleep", waited.append)
    calls: list[Any] = []
    model = served_by(monkeypatch, rate_limited_until(3, calls))

    assert model.invoke("hello").text == "ok"
    assert waited == list(models.BUSY_WAITS_S[:2])
    assert len(calls) == 3


def test_a_call_rate_limited_past_every_wait_names_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waited: list[float] = []
    monkeypatch.setattr(models, "_sleep", waited.append)
    calls: list[Any] = []
    model = served_by(monkeypatch, rate_limited_until(99, calls))

    with pytest.raises(models.ProviderFailed) as raised:
        model.invoke("hello")

    assert waited == list(models.BUSY_WAITS_S)
    assert len(calls) == len(models.BUSY_WAITS_S) + 1
    assert "AkashML" in str(raised.value)
    assert str(raised.value).isascii()


def test_the_rate_limit_message_counts_the_sdk_retries_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client retries a 429 itself inside each wait; code review of 12.3."""
    monkeypatch.setattr(models, "_sleep", lambda seconds: None)
    calls: list[Any] = []
    model = served_by(
        monkeypatch, rate_limited_until(99, calls), retries=models.RETRIES
    )

    with pytest.raises(models.ProviderFailed) as raised:
        model.invoke("hello")

    assert f"{len(calls)} calls" in str(raised.value)


def test_a_rate_limited_call_waits_on_the_async_path_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bot calls the graph asynchronously; the eval does not."""
    import asyncio

    import httpx2

    waited: list[float] = []

    async def asleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(models, "_asleep", asleep)
    calls: list[Any] = []
    answer = rate_limited_until(2, calls)
    built = cast(Any, openrouter_logger(monkeypatch).model)
    model = models.OpenRouterChat(
        model=built.model_name,
        api_key=built.openai_api_key,
        base_url=built.openai_api_base,
        extra_body=built.extra_body,
        http_async_client=httpx2.AsyncClient(transport=httpx2.MockTransport(answer)),
        max_retries=0,
    )

    assert asyncio.run(model.ainvoke("hello")).text == "ok"
    assert waited == [models.BUSY_WAITS_S[0]]


# -- a model per subgraph ------------------------------------------------------


def test_each_subgraph_takes_the_model_its_own_variable_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")
    monkeypatch.setenv(models.NODES["planner"].model, "openai/gpt-oss-120b")
    monkeypatch.setenv(models.NODES["logger"].model, "anthropic/claude-haiku-4.5")

    planner, logger = models.chat_for("planner"), models.chat_for("logger")

    assert (planner.name, planner.setting) == (
        "openai/gpt-oss-120b",
        models.NODES["planner"].model,
    )
    assert (logger.name, logger.setting) == (
        "anthropic/claude-haiku-4.5",
        models.NODES["logger"].model,
    )
    assert planner.provider == logger.provider == models.OPENROUTER


def test_the_default_backend_starts_every_node_on_the_key_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ticket 12.5: an empty `.env` apart from the key runs the measured choices."""
    monkeypatch.setenv(models.OPENROUTER_KEY_ENV, "a-stand-in")

    for chat, choice in (
        (models.chat_for("planner"), models.NODES["planner"].choice),
        (models.chat_for("logger"), models.NODES["logger"].choice),
        (models.chat_for("entrance"), models.NODES["entrance"].choice),
    ):
        built = cast(Any, chat.model)
        assert (chat.provider, chat.name, chat.reasoning) == (
            models.OPENROUTER,
            choice.model,
            choice.effort,
        )
        assert built.extra_body["reasoning"] == {"effort": choice.effort}
        assert built.extra_body["provider"]["order"] == [choice.host]
        assert built.extra_body["provider"]["allow_fallbacks"] is False


def test_the_choices_are_the_ones_adr_0011_records() -> None:
    assert models.NODES["planner"].choice == models.Choice("anthropic/claude-haiku-4.5", "none", "anthropic")
    assert models.NODES["logger"].choice == models.Choice("deepseek/deepseek-v4-flash", "high", "parasail")
    assert models.NODES["entrance"].choice == models.Choice("deepseek/deepseek-v4-flash", "high", "parasail")
    assert models.NODES["supervisor"].choice == models.Choice("openai/gpt-6-luna", "", "openai")


def test_a_node_defaulted_to_its_choice_names_its_own_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model the listing lost is fixed on the node's line, not on the coach's."""
    openrouter_logger(monkeypatch)

    assert models.chat_for("planner").setting == models.NODES["planner"].model
    assert models.chat_for("logger").setting == models.NODES["logger"].model


def test_a_model_other_than_the_choice_gets_no_effort_and_no_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured effort and host belong to the measured model; on another they may not exist."""
    chat = openrouter_logger(monkeypatch, LOGGER_MODEL="openai/gpt-oss-20b")

    built = cast(Any, chat.model)
    assert chat.reasoning == ""
    assert "reasoning" not in built.extra_body
    assert built.extra_body["provider"] == {"require_parameters": True}


def test_naming_the_choice_by_hand_keeps_its_effort_and_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = openrouter_logger(monkeypatch, LOGGER_MODEL=models.NODES["logger"].choice.model)

    built = cast(Any, chat.model)
    assert chat.reasoning == models.NODES["logger"].choice.effort
    assert built.extra_body["provider"]["order"] == [models.NODES["logger"].choice.host]


def test_the_coachs_model_moves_every_node_off_its_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OPENROUTER_MODEL` is how a matrix row runs every node on one model."""
    openrouter_logger(monkeypatch, OPENROUTER_MODEL="qwen/qwen3.8-27b")

    for chat in (models.chat_for("planner"), models.chat_for("logger"), models.chat_for("entrance")):
        assert chat.name == "qwen/qwen3.8-27b"
        assert chat.reasoning == ""
        assert "order" not in cast(Any, chat.model).extra_body["provider"]


def test_onboarding_runs_on_its_choice_with_its_effort_and_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openrouter_logger(monkeypatch)

    chat = models.chat_for("onboarding")

    assert (chat.name, chat.reasoning, chat.host) == (
        models.NODES["onboarding"].choice.model,
        models.NODES["onboarding"].choice.effort,
        models.NODES["onboarding"].choice.host,
    )
    assert chat.setting == models.NODES["onboarding"].model


def test_onboarding_takes_a_model_effort_and_host_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """How a matrix row moves the interview alone."""
    openrouter_logger(
        monkeypatch,
        ONBOARDING_MODEL="qwen/qwen3.8-27b",
        ONBOARDING_REASONING="low",
        ONBOARDING_HOST="deepinfra",
    )

    chat = models.chat_for("onboarding")

    assert (chat.name, chat.reasoning, chat.host) == ("qwen/qwen3.8-27b", "low", "deepinfra")
    assert models.chat_for("entrance").name == models.NODES["entrance"].choice.model


def test_an_effort_named_wins_over_the_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = openrouter_logger(monkeypatch, LOGGER_REASONING="medium")

    assert chat.reasoning == "medium"
    assert cast(Any, chat.model).extra_body["reasoning"] == {"effort": "medium"}


def test_each_node_can_pin_a_host_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """The planner's and the logger's choices live on two different hosts."""
    openrouter_logger(monkeypatch, LOGGER_HOST="deepinfra", OPENROUTER_PROVIDER="groq")

    assert cast(Any, models.chat_for("logger").model).extra_body["provider"]["order"] == ["deepinfra"]
    assert cast(Any, models.chat_for("planner").model).extra_body["provider"]["order"] == ["groq"]
    assert cast(Any, models.chat_for("entrance").model).extra_body["provider"]["order"] == ["groq"]


def test_the_supervisor_runs_on_its_own_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openrouter_logger(monkeypatch)

    chat = models.chat_for("supervisor")

    assert (chat.name, chat.reasoning, chat.host) == (
        models.NODES["supervisor"].choice.model,
        models.NODES["supervisor"].choice.effort,
        models.NODES["supervisor"].choice.host,
    )
    assert chat.setting == models.NODES["supervisor"].model


def test_the_supervisor_takes_a_model_effort_and_host_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openrouter_logger(
        monkeypatch,
        SUPERVISOR_MODEL="qwen/qwen3.8-27b",
        SUPERVISOR_REASONING="low",
        SUPERVISOR_HOST="deepinfra",
    )

    chat = models.chat_for("supervisor")

    assert (chat.name, chat.reasoning, chat.host) == ("qwen/qwen3.8-27b", "low", "deepinfra")
    assert models.chat_for("planner").name == models.NODES["planner"].choice.model
