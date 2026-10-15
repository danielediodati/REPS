"""The chat models the coach runs on, all of them on OpenRouter, and the state of the provider behind them."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx2
import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

OPENROUTER = "openrouter"
"""The one provider; what the run record names as each model's."""

OPENROUTER_MODEL_ENV = "OPENROUTER_MODEL"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_URL = "https://openrouter.ai/api/v1"

EFFORTS = ("none", "low", "medium", "high")
"""What a node's `<NODE>_REASONING` may ask for; empty is the model's default."""

OPENROUTER_PROVIDER_ENV = "OPENROUTER_PROVIDER"
"""The one host OpenRouter may route to, by its slug; empty keeps OpenRouter's routing."""


@dataclass(frozen=True)
class Choice:
    """A node's measured configuration: model, effort and host (ADR-0011)."""

    model: str
    effort: str
    host: str


Node = Literal["planner", "logger", "entrance", "onboarding", "supervisor"]


@dataclass(frozen=True)
class Seat:
    """One node's settings and its measured choice."""

    model: str
    """The variable naming its own model; empty falls back to `OPENROUTER_MODEL`, then the choice."""

    reasoning: str
    """The variable asking how hard its model reasons."""

    host: str
    """The variable naming its own host, winning over `OPENROUTER_PROVIDER`."""

    choice: Choice


NODES: dict[Node, Seat] = {
    "planner": Seat(
        "PLANNER_MODEL",
        "PLANNER_REASONING",
        "PLANNER_HOST",
        Choice("anthropic/claude-haiku-4.5", "none", "anthropic"),
    ),
    "logger": Seat(
        "LOGGER_MODEL",
        "LOGGER_REASONING",
        "LOGGER_HOST",
        Choice("deepseek/deepseek-v4-flash", "high", "parasail"),
    ),
    "entrance": Seat(
        "ENTRANCE_MODEL",
        "ENTRANCE_REASONING",
        "ENTRANCE_HOST",
        Choice("deepseek/deepseek-v4-flash", "high", "parasail"),
    ),
    "onboarding": Seat(
        "ONBOARDING_MODEL",
        "ONBOARDING_REASONING",
        "ONBOARDING_HOST",
        Choice("deepseek/deepseek-v4-flash", "high", "parasail"),
    ),
    # Its default effort: the supervisor's set was measured without one.
    "supervisor": Seat(
        "SUPERVISOR_MODEL",
        "SUPERVISOR_REASONING",
        "SUPERVISOR_HOST",
        Choice("openai/gpt-6-luna", "", "openai"),
    ),
}
"""Every node the coach runs, by name: the one place a node's model is configured (ADR-0011)."""

NO_OPENROUTER_CREDENTIALS = (
    f"no OpenRouter credentials: set {OPENROUTER_KEY_ENV} in .env (copy "
    ".env.example) or in the environment"
)
"""A state with the way out, checked before any request goes out."""


class ModelError(RuntimeError):
    """A provider the environment gets wrong, stated with its fix."""


class QuotaSpent(ModelError):
    """The provider will take no more requests, stated with the way out."""


def spent(error: BaseException) -> QuotaSpent | None:
    """The state a refused request is in, when what refused it is spent credit."""
    if isinstance(error, QuotaSpent):
        return error
    if isinstance(error, openai.APIStatusError) and error.status_code == 402:
        return QuotaSpent(
            "OpenRouter's credits are spent; top up at "
            "https://openrouter.ai/settings/credits"
        )
    return None


WRITTEN_CALL = re.compile(
    r"</?[|｜][\w▁]+"  # special tokens: <|python_tag|>, <｜DSML｜tool_calls>
    r"|</?tool_calls?>"
    r"|\[TOOL_CALLS\]"
    r"|<function=",
)
"""The call markup hosts are known to leak into a reply's text."""


def written_call(text: str) -> bool:
    """Whether a reply's text is a tool call the host failed to parse, rather than words."""
    return WRITTEN_CALL.search(text) is not None


@dataclass(frozen=True)
class Chat:
    """The model one run talks to, and what the run record calls it.

    The name and the provider travel with the model because the record is
    written from them: asked of the model afterwards they are attributes the
    caller would have to know the class of to read.
    """

    model: BaseChatModel
    provider: str
    name: str
    setting: str = ""
    """Which variable named this model, so a state about it names the line to edit."""

    reasoning: str = ""
    """The effort asked of the model, or empty for its default."""

    reasoning_setting: str = ""
    """Which variable asked for that effort."""

    host: str = ""
    """The one host OpenRouter may send it to, or empty for its own routing."""

    @property
    def described(self) -> str:
        """The model with the effort and the host it runs at, for the terminal."""
        said = self.name
        if self.reasoning:
            said += f" at {self.reasoning} effort"
        return said + (f" via {self.host}" if self.host else "")


Roster = Mapping[Node, Chat]
"""The model each node runs on, by name."""


def chat_for(node: Node) -> Chat:
    """The model a node runs on: what the environment names, or else its measured choice."""
    seat = NODES[node]
    own = os.environ.get(seat.model)
    coachs = os.environ.get(OPENROUTER_MODEL_ENV)
    named = own or coachs or seat.choice.model
    # The measured effort and host belong to the measured model; another may
    # take neither.
    measured = named == seat.choice.model
    effort = effort_of(seat.reasoning) or (seat.choice.effort if measured else "")
    host = (
        os.environ.get(seat.host)
        or os.environ.get(OPENROUTER_PROVIDER_ENV)
        or (seat.choice.host if measured else "")
    )
    return Chat(
        openrouter_model(named, effort, host),
        OPENROUTER,
        named,
        OPENROUTER_MODEL_ENV if coachs and not own else seat.model,
        effort,
        seat.reasoning,
        host,
    )


def roster(nodes: Iterable[Node] = tuple(NODES)) -> dict[Node, Chat]:
    """The model each of `nodes` runs on, every node by default."""
    return {node: chat_for(node) for node in nodes}


def ready_all(cast: Roster) -> None:
    """Stop with the fix when any node's model cannot be answered."""
    for on in cast.values():
        ready(on)


def effort_of(variable: str) -> str:
    """The effort a variable asks for, or empty; any value outside `EFFORTS` is refused by name."""
    asked = os.environ.get(variable, "")
    if asked and asked not in EFFORTS:
        raise ModelError(f"{variable} is {asked!r}; it is one of {', '.join(EFFORTS)}, or empty")
    return asked


TIMEOUT_S = 180
"""How long one OpenRouter call may take before it is a host that stopped answering."""

RETRIES = 1
"""One more try after a failure, so a host that hangs costs two timeouts and not three."""

BUSY_WAITS_S = (5, 15, 45)
"""The waits before each retry of a call refused as rate-limited, longest last."""

_logged = logging.getLogger(__name__)
_sleep = time.sleep
_asleep = asyncio.sleep
_clock = time.monotonic


def _overdue(request: httpx2.Request, began: float) -> None:
    """Raise the client's own read timeout once the whole call has outlived `TIMEOUT_S`."""
    if _clock() - began > TIMEOUT_S:
        raise httpx2.ReadTimeout(f"no answer within {TIMEOUT_S} s", request=request)


class _Bounded(httpx2.SyncByteStream):
    """A response body that stops being read when its call is overdue."""

    def __init__(self, body: httpx2.SyncByteStream, request: httpx2.Request, began: float) -> None:
        self._body, self._request, self._began = body, request, began

    def __iter__(self) -> Iterator[bytes]:
        for part in self._body:
            _overdue(self._request, self._began)
            yield part

    def close(self) -> None:
        self._body.close()


class _AsyncBounded(httpx2.AsyncByteStream):
    """`_Bounded`, for the async client."""

    def __init__(self, body: httpx2.AsyncByteStream, request: httpx2.Request, began: float) -> None:
        self._body, self._request, self._began = body, request, began

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for part in self._body:
            _overdue(self._request, self._began)
            yield part

    async def aclose(self) -> None:
        await self._body.aclose()


class Deadline(httpx2.BaseTransport):
    """A transport whose every call ends within `TIMEOUT_S`, however the body arrives."""

    # The client's timeout is per read, and OpenRouter keeps a waiting
    # connection alive with whitespace: each byte restarts the clock, and a
    # host that never answers is waited on for ever.
    def __init__(self, over: httpx2.BaseTransport) -> None:
        self._over = over

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        began = _clock()
        answered = self._over.handle_request(request)
        assert isinstance(answered.stream, httpx2.SyncByteStream)
        answered.stream = _Bounded(answered.stream, request, began)
        return answered

    def close(self) -> None:
        self._over.close()


class AsyncDeadline(httpx2.AsyncBaseTransport):
    """`Deadline`, for the async client."""

    def __init__(self, over: httpx2.AsyncBaseTransport) -> None:
        self._over = over

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        began = _clock()
        answered = await self._over.handle_async_request(request)
        assert isinstance(answered.stream, httpx2.AsyncByteStream)
        answered.stream = _AsyncBounded(answered.stream, request, began)
        return answered

    async def aclose(self) -> None:
        await self._over.aclose()


class ProviderFailed(ModelError):
    """The host behind OpenRouter answered with an error, or not at all, named."""

    def __init__(self, message: str, emitted: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.emitted = tuple(emitted)


BREAKPOINT_PREFIX = "anthropic/"
"""The models that cache only up to a breakpoint the request marks; the others cache by themselves."""

EPHEMERAL = {"type": "ephemeral"}


def _mark_for_the_cache(messages: list[dict[str, Any]]) -> None:
    """A breakpoint on the last part of the last message, so the next turn reads everything before it."""
    if not messages:
        return
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, str) and content:
        last["content"] = [{"type": "text", "text": content, "cache_control": EPHEMERAL}]
    elif isinstance(content, list) and content and isinstance(content[-1], dict):
        last["content"] = [*content[:-1], {**content[-1], "cache_control": EPHEMERAL}]


class OpenRouterChat(ChatOpenAI):
    """`ChatOpenAI` on OpenRouter, keeping the host that answered and what it cost on each reply."""

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        for wait in (*BUSY_WAITS_S, None):
            try:
                return self._answered(*args, **kwargs)
            except openai.RateLimitError as error:
                if wait is None:
                    raise self._busy(error) from error
                self._waiting(error, wait)
                _sleep(wait)
        raise AssertionError("unreachable")

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        for wait in (*BUSY_WAITS_S, None):
            try:
                return await self._aanswered(*args, **kwargs)
            except openai.RateLimitError as error:
                if wait is None:
                    raise self._busy(error) from error
                self._waiting(error, wait)
                await _asleep(wait)
        raise AssertionError("unreachable")

    def _answered(self, *args: Any, **kwargs: Any) -> ChatResult:
        try:
            return super()._generate(*args, **kwargs)
        except openai.APITimeoutError as error:
            raise self._silent() from error
        except TypeError as error:
            if (failed := self._surfaced(error)) is None:
                raise
            raise failed from error

    async def _aanswered(self, *args: Any, **kwargs: Any) -> ChatResult:
        try:
            return await super()._agenerate(*args, **kwargs)
        except openai.APITimeoutError as error:
            raise self._silent() from error
        except TypeError as error:
            if (failed := self._surfaced(error)) is None:
                raise
            raise failed from error

    def _waiting(self, error: openai.RateLimitError, wait: float) -> None:
        # OpenRouter's pool at a cheap host fills at busy hours and empties in
        # seconds; one quick retry lost two thirds of a pass to it (12.3). The
        # SDK's own `max_retries` still runs inside each of these.
        _logged.warning("%s is rate-limited, again in %s s: %s", self._host(error), wait, error)

    def _busy(self, error: openai.RateLimitError) -> ProviderFailed:
        return ProviderFailed(
            f"{self._host(error)} kept {self.model_name} rate-limited: "
            f"{(len(BUSY_WAITS_S) + 1) * ((self.max_retries or 0) + 1)} calls "
            f"over at least {sum(BUSY_WAITS_S)} s"
        )

    def _host(self, error: openai.APIStatusError) -> str:
        body = error.body if isinstance(error.body, dict) else {}
        said = body.get("error", body)
        metadata = (said.get("metadata") if isinstance(said, dict) else None) or {}
        return str(metadata.get("provider_name") or self._pinned())

    def _surfaced(self, error: TypeError) -> ProviderFailed | None:
        # A host's error can arrive in a 200 with null `choices`. On the
        # structured-output path the SDK iterates them before langchain looks,
        # and the run ends on "'NoneType' object is not iterable"; langchain
        # leaves the HTTP response on the exception, and the body names the host.
        answered = getattr(error, "response", None)
        if answered is None:
            return None
        try:
            body = answered.json()
        except ValueError:
            return None
        return self._failed(body if isinstance(body, dict) else {})

    def _failed(self, body: dict[str, Any]) -> ProviderFailed:
        error = body.get("error")
        said = error if isinstance(error, dict) else {"message": error}
        host = (said.get("metadata") or {}).get("provider_name") or body.get("provider")
        return ProviderFailed(
            f"{host or self._pinned()} failed {self.model_name}: "
            f"{said.get('message') or 'a reply with no choices'}"
        )

    def _silent(self) -> ProviderFailed:
        return ProviderFailed(
            f"{self._pinned()} did not answer {self.model_name}: "
            f"{RETRIES + 1} tries of {TIMEOUT_S} s each"
        )

    def _pinned(self) -> str:
        order = ((self.extra_body or {}).get("provider") or {}).get("order") or ()
        return order[0] if order else "OpenRouter's host"

    def _get_request_payload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = super()._get_request_payload(*args, **kwargs)
        if self.model_name.startswith(BREAKPOINT_PREFIX):
            _mark_for_the_cache(payload.get("messages") or [])
        return payload

    def _create_chat_result(
        self, response: dict[str, Any] | openai.BaseModel, generation_info: dict[str, Any] | None = None
    ) -> ChatResult:
        body = response if isinstance(response, dict) else response.model_dump()
        if body.get("error"):
            raise self._failed(body)
        result = super()._create_chat_result(response, generation_info)
        host = body.get("provider")
        cost = (body.get("usage") or {}).get("cost")
        for generation in result.generations:
            if host:
                generation.message.response_metadata["host"] = str(host)
            if cost is not None:
                generation.message.response_metadata["cost"] = float(cost)
        return result


def openrouter_model(named: str, reasoning: str = "", host: str | None = None) -> ChatOpenAI:
    """The OpenRouter chat model by that name; `host` pins one host, `None` leaves it to `OPENROUTER_PROVIDER`."""
    key = os.environ.get(OPENROUTER_KEY_ENV)
    if not key:
        raise ModelError(NO_OPENROUTER_CREDENTIALS)
    # Routed only to hosts that honour every parameter sent. Without it a
    # host that ignores `response_format` can serve the emission, and the
    # strict schema is a suggestion again.
    provider: dict[str, Any] = {"require_parameters": True}
    pinned = os.environ.get(OPENROUTER_PROVIDER_ENV) if host is None else host
    if pinned:
        provider |= {"order": [pinned], "allow_fallbacks": False}
    body: dict[str, Any] = {"provider": provider, "usage": {"include": True}}
    if reasoning:
        body["reasoning"] = {"effort": reasoning}
    return OpenRouterChat(
        model=named,
        api_key=SecretStr(key),
        base_url=OPENROUTER_URL,
        extra_body=body,
        timeout=TIMEOUT_S,
        max_retries=RETRIES,
        http_client=httpx2.Client(transport=Deadline(httpx2.HTTPTransport())),
        http_async_client=httpx2.AsyncClient(transport=AsyncDeadline(httpx2.AsyncHTTPTransport())),
    )


def ready(on: Chat) -> None:
    """Stop with the fix when OpenRouter cannot answer the run that is about to start.

    Checked before the graph runs rather than left to the first call: a model
    retired between releases arrives mid-run as a 404 that reads as *the run
    is broken* rather than *this name is gone*.
    """
    if on.provider == OPENROUTER:
        _openrouter_ready(on)


def openrouter_listing(key: str) -> dict[str, dict[str, Any]]:
    """Every model OpenRouter routes to, by name, with its listing entry; the seam the suite stands in for."""
    listed = openai.OpenAI(api_key=key, base_url=OPENROUTER_URL).models.list()
    return {model.id: model.model_dump() for model in listed.data}


def _openrouter_ready(on: Chat) -> None:
    """The model OpenRouter routes to under that name, taking the effort asked, or the state that says otherwise."""
    key = os.environ.get(OPENROUTER_KEY_ENV)
    if not key:
        raise ModelError(NO_OPENROUTER_CREDENTIALS)
    try:
        served = openrouter_listing(key)
    except Exception as error:
        raise ModelError(f"OpenRouter cannot be reached ({error})") from error
    # A routing suffix such as `:nitro` is not in the listing; the model it
    # routes is.
    entry = served.get(on.name, served.get(on.name.rsplit(":", 1)[0]))
    if entry is None:
        # Hundreds of names, so the page is the way out rather than the list.
        choice = next((seat.choice for seat in NODES.values() if seat.model == on.setting), None)
        raise ModelError(
            f"OpenRouter does not route to {on.name}; set "
            f"{on.setting or OPENROUTER_MODEL_ENV} to one listed at "
            f"https://openrouter.ai/models, or leave it empty for "
            + (choice.model if choice else "each node's measured choice")
        )
    if on.reasoning:
        _takes(on, entry)


def _takes(on: Chat, entry: dict[str, Any]) -> None:
    """Refuse an effort the model's listing says it does not take, naming the variable."""
    if "reasoning" not in (entry.get("supported_parameters") or ()):
        raise ModelError(
            f"{on.name} takes no reasoning effort; leave {on.reasoning_setting} empty"
        )
    efforts = (entry.get("reasoning") or {}).get("supported_efforts")
    if efforts and on.reasoning not in efforts:
        raise ModelError(
            f"{on.name} takes {', '.join(efforts)} as an effort, not {on.reasoning!r}; "
            f"set {on.reasoning_setting} to one of them"
        )
