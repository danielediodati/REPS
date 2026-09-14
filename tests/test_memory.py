"""What a pass costs this laptop, measured without a socket.

`memory.py` stopped being a throwaway script the moment `trainer eval --suite
plan` started running it. The branch that measures nothing, the one line it
prints and the sample that could not be taken are asserted here rather than
watched once by hand.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import ollama
import pytest

from trainer.coach import memory, models


def chat(provider: str) -> models.Chat:
    """A `Chat` naming a provider and holding no model: nothing here invokes one."""
    return models.Chat(cast(Any, None), provider, "a-model")


def answering(*scripted: list[int | None] | Exception) -> Any:
    """A stand-in Ollama client answering `/api/ps` from a script, or raising."""
    remaining = list(scripted)

    def ps() -> Any:
        answer = remaining.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(models=[SimpleNamespace(size=size) for size in answer])

    return SimpleNamespace(ps=ps)


def test_nothing_is_measured_off_the_provider_this_laptop_hosts() -> None:
    """On Groq the model runs in a data centre, and what this machine had free
    says nothing at all about the run."""
    with memory.sampling(chat(models.GROQ)) as sampler:
        assert sampler.lines() == []


def test_what_it_measured_is_one_ascii_line() -> None:
    """CLAUDE.md's standing rule: anything the CLI prints is ASCII."""
    sampler = memory.Sampler(answering([12 * memory.GIB]))

    sampler.sample()
    (line,) = sampler.lines()

    assert line.isascii()
    assert "12.0 GiB" in line
    assert "/api/ps" in line
    assert sampler.least_free > 0


def test_the_weights_are_asked_of_ollama_rather_than_read_off_its_process() -> None:
    """On the integrated GPU they sit in shared memory, outside the working
    set: a run holding twelve gigabytes reads as a few hundred megabytes
    there, which is the number that would have said this laptop could run
    anything. Every model it reports counts."""
    sampler = memory.Sampler(answering([8 * memory.GIB, 4 * memory.GIB]))

    sampler.sample()

    assert sampler.loaded == 12 * memory.GIB


def test_the_most_it_ever_held_is_what_is_reported() -> None:
    """The model is unloaded between samples, and a pass that reported the
    last sample would say this laptop ran a 12 GB model on nothing."""
    sampler = memory.Sampler(answering([12 * memory.GIB], []))

    sampler.sample()
    sampler.sample()

    assert sampler.loaded == 12 * memory.GIB


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("connection refused"),
        ollama.ResponseError("model not found"),
    ],
)
def test_a_sample_nobody_could_take_does_not_end_the_pass(
    failure: Exception,
) -> None:
    """Ollama restarting mid-pass is not a reason to lose a measurement that
    costs forty minutes; the next sample, a second later, usually works."""
    sampler = memory.Sampler(answering(failure, [12 * memory.GIB]))

    sampler.sample()
    assert sampler.loaded == 0

    sampler.sample()
    assert sampler.loaded == 12 * memory.GIB


def test_a_model_reporting_no_size_is_not_an_error() -> None:
    """`size` is optional on what Ollama answers with, and `None` there would
    take the whole pass down on an arithmetic error at the very end of it."""
    sampler = memory.Sampler(answering([None, 4 * memory.GIB]))

    sampler.sample()

    assert sampler.loaded == 4 * memory.GIB
