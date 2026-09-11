"""The chat models the coach runs on, configured from the environment."""

from __future__ import annotations

import os

from langchain_ollama import ChatOllama

MODEL_ENV = "OLLAMA_MODEL"
CONTEXT_ENV = "OLLAMA_CONTEXT_LENGTH"
BASE_URL_ENV = "OLLAMA_BASE_URL"

DEFAULT_MODEL = "gpt-oss:20b"

REASONING = "low"
"""How hard `gpt-oss` reasons before it answers."""


class ModelError(RuntimeError):
    """A model setting the environment gets wrong, stated with its fix."""


def ollama() -> ChatOllama:
    """The Ollama chat model the environment names."""
    return ChatOllama(
        model=os.environ.get(MODEL_ENV) or DEFAULT_MODEL,
        base_url=os.environ.get(BASE_URL_ENV) or None,
        num_ctx=_context_length(),
        reasoning=REASONING,
    )


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
