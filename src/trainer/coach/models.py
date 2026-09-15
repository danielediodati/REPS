"""The chat models the coach runs on, and the state of the provider behind them."""

from __future__ import annotations

import os
from dataclasses import dataclass

import ollama
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from pydantic import SecretStr

from trainer import agent

BACKEND_ENV = "LLM_BACKEND"
MODEL_ENV = "OLLAMA_MODEL"
CONTEXT_ENV = "OLLAMA_CONTEXT_LENGTH"
BASE_URL_ENV = "OLLAMA_BASE_URL"

OLLAMA = "ollama"
GROQ = "groq"
BACKENDS = (OLLAMA, GROQ)
"""What `LLM_BACKEND` may name; any other value is refused by name rather than ignored."""

DEFAULT_MODEL = "gpt-oss:20b"

REASONING = "low"
"""How hard `gpt-oss` reasons before it answers."""


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


def backend() -> str:
    """Which provider the coach runs on, and a state for one nobody built."""
    named = os.environ.get(BACKEND_ENV) or OLLAMA
    if named not in BACKENDS:
        raise ModelError(
            f"{BACKEND_ENV} names {named!r}, and the providers built are "
            f"{', '.join(BACKENDS)}"
        )
    return named


def chat() -> Chat:
    """The chat model the environment names, on either provider."""
    if backend() == GROQ:
        return Chat(groq_model(), GROQ, agent.model_name())
    return Chat(ollama_model(), OLLAMA, model_name())


def model_name() -> str:
    """The local model the environment names."""
    return os.environ.get(MODEL_ENV) or DEFAULT_MODEL


def ollama_model() -> ChatOllama:
    """The Ollama chat model the environment names."""
    return ChatOllama(
        model=model_name(),
        base_url=os.environ.get(BASE_URL_ENV) or None,
        num_ctx=_context_length(),
        reasoning=REASONING,
    )


def groq_model() -> ChatGroq:
    """The Groq chat model, on the settings the old loop already reads."""
    key = os.environ.get(agent.API_KEY_ENV)
    if not key:
        raise ModelError(agent.NO_CREDENTIALS)
    try:
        return ChatGroq(
            model=agent.model_name(),
            api_key=SecretStr(key),
            max_tokens=agent.max_tokens(),
        )
    except agent.AgentError as error:
        # `GROQ_MAX_TOKENS` states its own failure. Re-raised as this module's
        # error so a caller has one exception type to report the provider with.
        raise ModelError(str(error)) from error


def ready(on: Chat) -> None:
    """Stop with the fix when the provider cannot answer the run that is about to start.

    Checked before the graph runs rather than left to the first call. An
    unreachable server arrives mid-run as a connection error and a model
    nobody pulled as a 404, and neither names the command that fixes it.
    """
    if on.provider != OLLAMA:
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
