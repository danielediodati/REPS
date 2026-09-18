"""The chat models the coach runs on, and the state of the provider behind them."""

from __future__ import annotations

import os
from dataclasses import dataclass

import ollama
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from pydantic import SecretStr

BACKEND_ENV = "LLM_BACKEND"
MODEL_ENV = "OLLAMA_MODEL"
CONTEXT_ENV = "OLLAMA_CONTEXT_LENGTH"
BASE_URL_ENV = "OLLAMA_BASE_URL"

GROQ_MODEL_ENV = "GROQ_MODEL"
API_KEY_ENV = "GROQ_API_KEY"
MAX_TOKENS_ENV = "GROQ_MAX_TOKENS"

ENTRANCE_BACKEND_ENV = "ENTRANCE_BACKEND"
ENTRANCE_MODEL_ENV = "ENTRANCE_MODEL"
"""The entrance's own provider and model (ADR-0006, item 3).

Two settings and not one, because the entrance is the node latency is felt on
and the planner is the node that needs the reasoning: the useful arrangement
on this laptop is a small local model answering hello while `LLM_BACKEND`
points the planner at Groq. Either of them empty falls back to what the coach
runs on, so a fresh clone still has one provider to think about.
"""

OLLAMA = "ollama"
GROQ = "groq"
BACKENDS = (OLLAMA, GROQ)
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
    """The chat model the environment names, on either provider."""
    if backend() == GROQ:
        return Chat(groq_model(), GROQ, groq_model_name(), GROQ_MODEL_ENV)
    return Chat(ollama_model(), OLLAMA, model_name(), MODEL_ENV)


def entrance() -> Chat:
    """The model the entrance holds the conversation on, which is its own (ADR-0006).

    Falls back to the coach's provider and to that provider's default model, so
    an installation that has said nothing about the entrance still gets one --
    on Ollama a smaller model than the planner's, because this is the node the
    user waits on.
    """
    if entrance_backend() == GROQ:
        named = os.environ.get(ENTRANCE_MODEL_ENV) or groq_model_name()
        return Chat(groq_model(named), GROQ, named, ENTRANCE_MODEL_ENV)
    named = os.environ.get(ENTRANCE_MODEL_ENV) or DEFAULT_ENTRANCE_MODEL
    return Chat(
        ollama_model(named, reasoning=None), OLLAMA, named, ENTRANCE_MODEL_ENV
    )


def model_name() -> str:
    """The local model the environment names."""
    return os.environ.get(MODEL_ENV) or DEFAULT_MODEL


def groq_model_name() -> str:
    """The Groq model the environment names."""
    return os.environ.get(GROQ_MODEL_ENV) or DEFAULT_GROQ_MODEL


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


def ready(on: Chat) -> None:
    """Stop with the fix when the provider cannot answer the run that is about to start.

    Checked before the graph runs rather than left to the first call. An
    unreachable server arrives mid-run as a connection error and a model
    nobody pulled as a 404, and neither names the command that fixes it --
    and on Groq the 404 is a model that was retired between releases, which
    reads as *the run is broken* rather than *this name is gone*.
    """
    if on.provider == GROQ:
        _groq_ready(on)
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
