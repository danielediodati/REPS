"""The chat models the coach runs on, and the state of the provider behind them."""

from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass
from typing import Any

import groq
import ollama
import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

BACKEND_ENV = "LLM_BACKEND"
MODEL_ENV = "OLLAMA_MODEL"
CONTEXT_ENV = "OLLAMA_CONTEXT_LENGTH"
BASE_URL_ENV = "OLLAMA_BASE_URL"

GROQ_MODEL_ENV = "GROQ_MODEL"
API_KEY_ENV = "GROQ_API_KEY"
MAX_TOKENS_ENV = "GROQ_MAX_TOKENS"

OPENROUTER_MODEL_ENV = "OPENROUTER_MODEL"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_URL = "https://openrouter.ai/api/v1"

ENTRANCE_BACKEND_ENV = "ENTRANCE_BACKEND"
ENTRANCE_MODEL_ENV = "ENTRANCE_MODEL"
"""The entrance's own provider and model (ADR-0006, item 3).

Two settings and not one, because the entrance is the node latency is felt on
and the planner is the node that needs the reasoning: the useful arrangement
on this laptop is a small local model answering hello while `LLM_BACKEND`
points the planner at Groq. Either of them empty falls back to what the coach
runs on, so a fresh clone still has one provider to think about.
"""

PLANNER_MODEL_ENV = "PLANNER_MODEL"
LOGGER_MODEL_ENV = "LOGGER_MODEL"
"""Each subgraph's own model, on the provider `LLM_BACKEND` names.

Empty falls back to that provider's model, so one variable still moves both.
"""

PLANNER_REASONING_ENV = "PLANNER_REASONING"
LOGGER_REASONING_ENV = "LOGGER_REASONING"
ENTRANCE_REASONING_ENV = "ENTRANCE_REASONING"
"""How hard each node's model reasons, on OpenRouter; empty is the model's default."""

EFFORTS = ("none", "low", "medium", "high")

OPENROUTER_PROVIDER_ENV = "OPENROUTER_PROVIDER"
"""The one host OpenRouter may route to, by its slug; empty keeps OpenRouter's routing."""

OLLAMA = "ollama"
GROQ = "groq"
OPENROUTER = "openrouter"
BACKENDS = (OLLAMA, GROQ, OPENROUTER)
"""What `LLM_BACKEND` may name; any other value is refused by name rather than ignored."""

DEFAULT_MODEL = "gpt-oss:20b"

DEFAULT_ENTRANCE_MODEL = "llama3.1"
"""The local model the entrance talks on, when `ENTRANCE_MODEL` does not name one.

Not `DEFAULT_MODEL`. The entrance is read and answered on every turn, and
`gpt-oss:20b` on this laptop's CPU is half a minute to say hello -- worse than
the silence ADR-0006 replaces. `llama3.1` is the model the roadmap's own risk
note records as running on the Radeon 860M while `gpt-oss:20b` terminates its
Vulkan backend, so on the machine this was written for the entrance is the
node that gets the GPU.
"""

DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
"""The Groq model, when `GROQ_MODEL` does not name one.

Its structured output runs in **strict** mode, where constrained decoding
makes the emitted document conform to the schema by construction rather than
by luck -- a document that comes back malformed is a whole run thrown away.

**This name was believed retired, and it is not.** Asked on 2026-09-18, Groq
serves it and a run of `trainer plan` on it emitted a plan in 1090 output
tokens. What is retired is `qwen/qwen3.6-27b`, one minor version below, which
is what an installation's `.env` may still name -- and that is the 404 nobody
could see coming, because nothing checked.

`openai/gpt-oss-20b` was tried in its place, for holding the model fixed
across the two providers. It does not fit the free tier: it reasons before it
answers, `max_tokens` caps the completion with the reasoning inside it, and at
1000 the whole budget went to thinking and the emission came back empty. Above
about 5600 the request is refused whole -- 8000 tokens per minute, input
included. A default that only works on a paid tier is not a default.
"""

DEFAULT_OPENROUTER_MODEL = "qwen/qwen3.8-27b"
"""The OpenRouter model, when `OPENROUTER_MODEL` does not name one.

Groq's default, so moving provider holds the model fixed and an eval run
measures the provider and nothing else.
"""

DEFAULT_MAX_TOKENS = 1000
"""How much the model may write in one turn, by default.

One thousand because that is Groq's free-tier ceiling on output tokens per
minute, and a request whose declared `max_tokens` exceeds it is refused before
any of it runs -- a 429 about a limit nobody has reached yet.

**It is shared with reasoning.** The default model reasons before it answers
and `max_tokens` caps the completion, thinking included, so the document is
written out of whatever is left. An observed run emitted a six-block plan in
676 tokens all in, so this fits -- but not by much, and a run that reasons
harder loses the document to truncation rather than to a rule. That is why the
truncation state names `GROQ_MAX_TOKENS`: on a paid tier it is the number to
raise first.
"""

NO_CREDENTIALS = (
    f"no Groq credentials: set {API_KEY_ENV} in .env (copy .env.example) or in "
    "the environment"
)
"""A state with the way out, checked before any request goes out.

Left to the SDK this arrives as a 401 after a network round-trip, or as a
connection error on a machine that is offline -- neither of which names the
thing that is actually missing.
"""

NO_OPENROUTER_CREDENTIALS = (
    f"no OpenRouter credentials: set {OPENROUTER_KEY_ENV} in .env (copy "
    ".env.example) or in the environment"
)

REASONING = "low"
"""How hard `gpt-oss` reasons before it answers.

Asked of every model that plans, and of none that talks. Ollama refuses the
setting outright on a model that has no thinking phase -- `llama3.1` answers
`"llama3.1" does not support thinking` with a 400, which is the first turn of
the conversation lost -- and the entrance would not want it anyway: it reads
prose and writes prose, and the seconds spent reasoning are the seconds the
user is looking at an empty chat.
"""


class ModelError(RuntimeError):
    """A provider the environment gets wrong, stated with its fix."""


class QuotaSpent(ModelError):
    """The provider will take no more requests today, stated with when it will."""


_PER_DAY = re.compile(r"per day \(")
_MODEL = re.compile(r"for model `([^`]+)`")
_AGAIN = re.compile(r"try again in ((?:\d+h)?(?:\d+m)?\d+)(?:\.\d+)?s")


def spent(error: BaseException) -> QuotaSpent | None:
    """The state a refused request is in, when what refused it is the day's quota.

    Only the day's: a per-minute limit is waited out by the SDK, and the next
    request may well go through.
    """
    if isinstance(error, QuotaSpent):
        return error
    if isinstance(error, openai.APIStatusError) and error.status_code == 402:
        return QuotaSpent(
            "OpenRouter's credits are spent; top up at "
            "https://openrouter.ai/settings/credits"
        )
    said = str(error)
    if not isinstance(error, groq.RateLimitError) or not _PER_DAY.search(said):
        return None
    model = _MODEL.search(said)
    again = _AGAIN.search(said)
    return QuotaSpent(
        "Groq's daily token quota"
        + (f" for {model.group(1)}" if model else "")
        + " is spent"
        + (f"; try again in {again.group(1)}s" if again else "")
        + ", or run fewer with --only"
    )


@dataclass(frozen=True)
class Chat:
    """The model one run talks to, and what the run record calls it.

    The name and the provider travel with the model because the record is
    written from them: asked of the model afterwards they are two different
    attributes on two different classes, and the caller would have to know
    which provider it built to read either.
    """

    model: BaseChatModel
    provider: str
    name: str
    setting: str = ""
    """Which variable named this model, so a state about it names the line to edit.

    Two nodes now name two models (ADR-0006), and a 404 on the entrance's
    answered with *set `GROQ_MODEL`* sends the reader to the planner's line.
    """

    reasoning: str = ""
    """The effort asked of the model, or empty for its default."""

    reasoning_setting: str = ""
    """Which variable asked for that effort."""


def backend() -> str:
    """Which provider the coach runs on, and a state for one nobody built."""
    return _built(BACKEND_ENV, os.environ.get(BACKEND_ENV) or OLLAMA)


def entrance_backend() -> str:
    """Which provider the entrance talks on: its own, or the coach's when it names none."""
    named = os.environ.get(ENTRANCE_BACKEND_ENV)
    return _built(ENTRANCE_BACKEND_ENV, named) if named else backend()


def _built(variable: str, named: str) -> str:
    if named not in BACKENDS:
        raise ModelError(
            f"{variable} names {named!r}, and the providers built are "
            f"{', '.join(BACKENDS)}"
        )
    return named


def chat() -> Chat:
    """The chat model the environment names, on whichever provider it names."""
    if backend() == GROQ:
        return Chat(groq_model(), GROQ, groq_model_name(), GROQ_MODEL_ENV)
    if backend() == OPENROUTER:
        return Chat(
            openrouter_model(),
            OPENROUTER,
            openrouter_model_name(),
            OPENROUTER_MODEL_ENV,
        )
    return Chat(ollama_model(), OLLAMA, model_name(), MODEL_ENV)


def planner() -> Chat:
    """The model the planner reasons on: `PLANNER_MODEL`, or the coach's."""
    return _subgraph(PLANNER_MODEL_ENV, PLANNER_REASONING_ENV)


def logger() -> Chat:
    """The model the logger extracts on: `LOGGER_MODEL`, or the coach's."""
    return _subgraph(LOGGER_MODEL_ENV, LOGGER_REASONING_ENV)


def _subgraph(setting: str, reasoning_setting: str) -> Chat:
    named = os.environ.get(setting)
    effort = effort_of(reasoning_setting)
    if not named:
        found = chat()
        if effort and found.provider == OPENROUTER:
            found = dataclasses.replace(found, model=openrouter_model(found.name, effort))
    elif backend() == GROQ:
        found = Chat(groq_model(named), GROQ, named, setting)
    elif backend() == OPENROUTER:
        found = Chat(openrouter_model(named, effort), OPENROUTER, named, setting)
    else:
        found = Chat(ollama_model(named), OLLAMA, named, setting)
    return dataclasses.replace(found, reasoning=effort, reasoning_setting=reasoning_setting)


def effort_of(variable: str) -> str:
    """The effort a variable asks for, or empty; any value outside `EFFORTS` is refused by name."""
    asked = os.environ.get(variable, "")
    if asked and asked not in EFFORTS:
        raise ModelError(f"{variable} is {asked!r}; it is one of {', '.join(EFFORTS)}, or empty")
    return asked


def entrance() -> Chat:
    """The model the entrance holds the conversation on, which is its own (ADR-0006).

    Falls back to the coach's provider and to that provider's default model, so
    an installation that has said nothing about the entrance still gets one --
    on Ollama a smaller model than the planner's, because this is the node the
    user waits on.
    """
    effort = effort_of(ENTRANCE_REASONING_ENV)
    if entrance_backend() == GROQ:
        named = os.environ.get(ENTRANCE_MODEL_ENV) or groq_model_name()
        found = Chat(groq_model(named), GROQ, named, ENTRANCE_MODEL_ENV)
    elif entrance_backend() == OPENROUTER:
        named = os.environ.get(ENTRANCE_MODEL_ENV) or openrouter_model_name()
        found = Chat(openrouter_model(named, effort), OPENROUTER, named, ENTRANCE_MODEL_ENV)
    else:
        named = os.environ.get(ENTRANCE_MODEL_ENV) or DEFAULT_ENTRANCE_MODEL
        found = Chat(ollama_model(named, reasoning=None), OLLAMA, named, ENTRANCE_MODEL_ENV)
    return dataclasses.replace(found, reasoning=effort, reasoning_setting=ENTRANCE_REASONING_ENV)


def model_name() -> str:
    """The local model the environment names."""
    return os.environ.get(MODEL_ENV) or DEFAULT_MODEL


def groq_model_name() -> str:
    """The Groq model the environment names."""
    return os.environ.get(GROQ_MODEL_ENV) or DEFAULT_GROQ_MODEL


def openrouter_model_name() -> str:
    """The OpenRouter model the environment names."""
    return os.environ.get(OPENROUTER_MODEL_ENV) or DEFAULT_OPENROUTER_MODEL


def max_tokens() -> int:
    """How much the model may write, from the environment or the default.

    Checked rather than trusted, because this value is interpolated into the
    rate-limit and truncation messages: `GROQ_MAX_TOKENS=2k` would raise a
    `ValueError` *while handling* the 429 it was meant to explain, and the
    user would get a traceback about a codec-shaped mistake instead of the
    state with its way out.
    """
    declared = os.environ.get(MAX_TOKENS_ENV)
    if not declared:
        return DEFAULT_MAX_TOKENS
    try:
        asked = int(declared)
    except ValueError:
        raise ModelError(
            f"{MAX_TOKENS_ENV} is {declared!r}; it is a whole number of tokens"
        ) from None
    if asked < 1:
        raise ModelError(f"{MAX_TOKENS_ENV} is {asked}; it is at least one token")
    return asked


def ollama_model(
    named: str | None = None, reasoning: str | None = REASONING
) -> ChatOllama:
    """The Ollama chat model the environment names, or another this machine has.

    `reasoning` of `None` leaves the setting off the request altogether, which
    is what a model with no thinking phase needs.
    """
    return ChatOllama(
        model=named or model_name(),
        base_url=os.environ.get(BASE_URL_ENV) or None,
        num_ctx=_context_length(),
        reasoning=reasoning,
    )


def groq_model(named: str | None = None) -> ChatGroq:
    """The Groq chat model the environment names, or another Groq serves."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise ModelError(NO_CREDENTIALS)
    return ChatGroq(
        model=named or groq_model_name(),
        api_key=SecretStr(key),
        max_tokens=max_tokens(),
    )


TIMEOUT_S = 180
"""How long one OpenRouter call may take before it is a host that stopped answering."""

RETRIES = 1
"""One more try after a failure, so a host that hangs costs two timeouts and not three."""


class ProviderFailed(ModelError):
    """The host behind OpenRouter answered with an error, or not at all, named."""


class OpenRouterChat(ChatOpenAI):
    """`ChatOpenAI` on OpenRouter, keeping the host that answered and what it cost on each reply."""

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        try:
            return super()._generate(*args, **kwargs)
        except openai.APITimeoutError as error:
            raise self._silent() from error
        except TypeError as error:
            if (failed := self._surfaced(error)) is None:
                raise
            raise failed from error

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        try:
            return await super()._agenerate(*args, **kwargs)
        except openai.APITimeoutError as error:
            raise self._silent() from error
        except TypeError as error:
            if (failed := self._surfaced(error)) is None:
                raise
            raise failed from error

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
            f"{self._pinned()} did not answer {self.model_name} in {TIMEOUT_S} s"
        )

    def _pinned(self) -> str:
        order = ((self.extra_body or {}).get("provider") or {}).get("order") or ()
        return order[0] if order else "OpenRouter's host"

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


def openrouter_model(named: str | None = None, reasoning: str = "") -> ChatOpenAI:
    """The OpenRouter chat model the environment names, or another it routes to."""
    key = os.environ.get(OPENROUTER_KEY_ENV)
    if not key:
        raise ModelError(NO_OPENROUTER_CREDENTIALS)
    # Routed only to hosts that honour every parameter sent. Without it a
    # host that ignores `response_format` can serve the emission, and the
    # strict schema is a suggestion again.
    provider: dict[str, Any] = {"require_parameters": True}
    pinned = os.environ.get(OPENROUTER_PROVIDER_ENV)
    if pinned:
        provider |= {"order": [pinned], "allow_fallbacks": False}
    body: dict[str, Any] = {"provider": provider, "usage": {"include": True}}
    if reasoning:
        body["reasoning"] = {"effort": reasoning}
    return OpenRouterChat(
        model=named or openrouter_model_name(),
        api_key=SecretStr(key),
        base_url=OPENROUTER_URL,
        extra_body=body,
        timeout=TIMEOUT_S,
        max_retries=RETRIES,
    )


def ready(on: Chat) -> None:
    """Stop with the fix when the provider cannot answer the run that is about to start.

    Checked before the graph runs rather than left to the first call. An
    unreachable server arrives mid-run as a connection error and a model
    nobody pulled as a 404, and neither names the command that fixes it --
    and on Groq the 404 is a model that was retired between releases, which
    reads as *the run is broken* rather than *this name is gone*.
    """
    if on.reasoning and on.provider != OPENROUTER:
        raise ModelError(
            f"{on.reasoning_setting} is {on.reasoning!r}, and an effort is sent only "
            f"on OpenRouter; leave it empty on {on.provider}"
        )
    if on.provider == GROQ:
        _groq_ready(on)
        return
    if on.provider == OPENROUTER:
        _openrouter_ready(on)
        return
    if on.provider != OLLAMA:
        # A provider nobody built has no state of its own to be in. Written as
        # *anything that is not Groq is local*, a stand-in would be checked
        # against a server it has nothing to do with.
        return
    client = ollama.Client(host=os.environ.get(BASE_URL_ENV) or None)
    try:
        listed = client.list().models
    except (ConnectionError, ollama.ResponseError) as error:
        raise ModelError(
            f"Ollama cannot be reached ({error}); start Ollama, or point "
            f"{BASE_URL_ENV} at the server"
        ) from error
    pulled = {_tagged(model.model) for model in listed if model.model}
    if _tagged(on.name) not in pulled:
        raise ModelError(f"Ollama does not have {on.name}; run `ollama pull {on.name}`")


def groq_models(key: str) -> set[str]:
    """Every model Groq serves this key, as it names them.

    Its own function because it is the one thing in this module that reaches
    the network, and because that makes it the seam the suite stands in for --
    the alternative is a test that knows the shape of somebody's SDK.
    """
    import groq

    return {model.id for model in groq.Groq(api_key=key).models.list().data}


def _groq_ready(on: Chat) -> None:
    """The model Groq serves under that name, or the state that says it does not."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise ModelError(NO_CREDENTIALS)
    try:
        served = groq_models(key)
    except Exception as error:
        # Every way the check itself can fail -- offline, a key Groq refuses,
        # the endpoint moved -- and none of them is a statement about the
        # model name. Reported as reaching Groq, which is what went wrong.
        raise ModelError(f"Groq cannot be reached ({error})") from error
    if on.name not in served:
        # The fix names the default rather than three of the list, which is
        # sorted alphabetically and opens on a text-to-speech model: a state
        # whose way out does not work is worse than the 404 it replaced.
        raise ModelError(
            f"Groq does not serve {on.name}; set {on.setting or GROQ_MODEL_ENV} to "
            f"{DEFAULT_GROQ_MODEL}, or leave it empty for the same, or pick "
            f"another of: {', '.join(sorted(served))}"
        )


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
        raise ModelError(
            f"OpenRouter does not route to {on.name}; set "
            f"{on.setting or OPENROUTER_MODEL_ENV} to one listed at "
            f"https://openrouter.ai/models, or leave it empty for "
            f"{DEFAULT_OPENROUTER_MODEL}"
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


MEASURED_CONTEXT = 8192
"""The context length session 6 measured the planner at, 6 valid plans of 6."""

SHORT_CONTEXT = (
    f"set it to {MEASURED_CONTEXT} in .env -- below that the "
    "admissible set is truncated and plans are refused for no visible reason"
)


def context_length(on: Chat) -> int | None:
    """The context the local model plans with, refused when unset or short; `None` off Ollama."""
    if on.provider != OLLAMA:
        return None
    declared = _context_length()
    if declared is None:
        raise ModelError(f"{CONTEXT_ENV} is not set; {SHORT_CONTEXT}")
    if declared < MEASURED_CONTEXT:
        raise ModelError(f"{CONTEXT_ENV} is {declared}; {SHORT_CONTEXT}")
    return declared


def _tagged(name: str) -> str:
    """A model name with its tag, the way `ollama list` always reports one.

    Ollama resolves a bare name to `:latest`, so `llama3.1` and
    `llama3.1:latest` are one model. Compared as written, a model that is
    there reads as missing, and the fix offered is a pull that changes nothing.
    """
    return name if ":" in name else f"{name}:latest"


def _context_length() -> int | None:
    declared = os.environ.get(CONTEXT_ENV)
    if not declared:
        return None
    try:
        return int(declared)
    except ValueError:
        raise ModelError(
            f"{CONTEXT_ENV} is {declared!r}; it is a whole number of tokens, such as 16384"
        ) from None
