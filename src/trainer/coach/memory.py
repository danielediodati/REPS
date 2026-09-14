"""What a pass costs this laptop: the memory Ollama's models hold, and the least the system had free."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

import ollama
import psutil

from trainer.coach import models

GIB = 2**30


class Sampler:
    """Samples, once a second, the memory Ollama reports its models use and the least memory the system had free.

    **Asked of Ollama rather than read off its process.** On the integrated
    GPU the weights sit in shared memory, outside the working set: a run
    holding twelve gigabytes reads as a few hundred megabytes there, which is
    the number that would have said this laptop could run anything.

    Built with no client off Ollama, where it measures nothing: the model runs
    in a data centre and what this machine had free says nothing about the run.
    """

    def __init__(self, client: ollama.Client | None) -> None:
        self.loaded = 0
        self.least_free = psutil.virtual_memory().available
        self._client = client
        self._stop = threading.Event()
        self._sampler = threading.Thread(target=self._sample, daemon=True)

    def lines(self) -> list[str]:
        """What it measured, in one line, or nothing at all when it measured nothing. ASCII."""
        if self._client is None:
            return []
        return [
            f"loaded model memory {self.loaded / GIB:.1f} GiB (Ollama's "
            f"/api/ps); least free system memory {self.least_free / GIB:.1f} GiB"
        ]

    def __enter__(self) -> Sampler:
        if self._client is not None:
            self._sampler.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._client is None:
            return
        self._stop.set()
        self._sampler.join()

    def sample(self) -> None:
        """One sample: the least the system has had free, and the most Ollama has held."""
        assert self._client is not None  # `__enter__` starts no thread without one
        self.least_free = min(self.least_free, psutil.virtual_memory().available)
        try:
            running = self._client.ps().models
        except (ConnectionError, ollama.ResponseError):
            # A sample nobody could take is not a measurement to abandon a
            # paid-for pass over: the next one a second later usually works.
            return
        self.loaded = max(self.loaded, sum(model.size or 0 for model in running))

    def _sample(self) -> None:
        while not self._stop.wait(1.0):
            self.sample()


@contextmanager
def sampling(on: models.Chat) -> Iterator[Sampler]:
    """Memory sampled for as long as the block runs, on the provider this laptop hosts.

    A sampler is yielded either way, saying nothing off Ollama, so the caller
    has no branch to get wrong.
    """
    client = (
        ollama.Client(host=os.environ.get(models.BASE_URL_ENV) or None)
        if on.provider == models.OLLAMA
        else None
    )
    with Sampler(client) as sampler:
        yield sampler
