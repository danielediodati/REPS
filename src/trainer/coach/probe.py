"""Run the planner graph once over the six situations on Ollama, and print what each run cost."""

from __future__ import annotations

import dataclasses
import os
import threading
import time
from types import TracebackType
from typing import Any

import ollama
import psutil
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from trainer import evaluation, tools
from trainer import plan as plans
from trainer.coach import models, planner
from trainer.engine import database

Planner = CompiledStateGraph[
    planner.PlannerState, None, planner.PlannerState, planner.PlannerState
]


class MemorySampler:
    """Samples, once a second, the memory Ollama reports its models use and the least memory the system had free."""

    def __init__(self, client: ollama.Client) -> None:
        self.loaded = 0
        self.least_free = psutil.virtual_memory().available
        self._client = client
        self._stop = threading.Event()
        self._sampler = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self) -> MemorySampler:
        self._sampler.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._sampler.join()

    def _sample(self) -> None:
        while not self._stop.wait(1.0):
            self.least_free = min(self.least_free, psutil.virtual_memory().available)
            # Asked of Ollama rather than read off its process: on the integrated
            # GPU the weights sit in shared memory, outside the working set.
            try:
                running = self._client.ps().models
            except (ConnectionError, ollama.ResponseError):
                continue
            self.loaded = max(self.loaded, sum(model.size or 0 for model in running))


def ready(client: ollama.Client) -> None:
    """Stop with the fix when Ollama cannot be reached."""
    try:
        client.ps()
    except (ConnectionError, ollama.ResponseError) as error:
        raise SystemExit(
            f"Ollama cannot be reached ({error}); start Ollama, or point "
            f"{models.BASE_URL_ENV} at the server"
        ) from error


def say(text: str) -> None:
    """Print ASCII only, whatever the model or the server wrote."""
    print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def timed(graph: Planner, request: plans.Request) -> tuple[dict[str, Any], float]:
    """One run of the graph, and its wall time in seconds."""
    started = time.monotonic()
    final = graph.invoke({"request": request})
    return final, time.monotonic() - started


def show(name: str, final: dict[str, Any], seconds: float) -> None:
    """One run's line, then every refusal the validator sent back."""
    outcome = "valid" if final["violations"] is None else "refused"
    say(
        f"{name:<36} {outcome:<8} attempts {final['attempts']}  "
        f"tool calls {final.get('spent', 0):>2}  {seconds:5.0f} s"
    )
    for message in final["messages"]:
        if isinstance(message, HumanMessage) and message.name == "validator":
            say("    fed back: " + message.text.replace("\n", "\n    "))
    if final["violations"] is not None:
        say("    final refusal: " + final["violations"].replace("\n", "\n    "))


def main() -> None:
    """Measure the planner graph over the six situations."""
    model = models.ollama()
    client = ollama.Client(host=model.base_url)
    ready(client)

    path = database.database_path().resolve()
    # The tools open their own connection from this variable, so the situations
    # have to be built on the same file they read.
    os.environ[database.DATABASE_ENV_VAR] = str(path)
    try:
        with tools.opened() as connection:
            situations = evaluation.situations(connection)
    except tools.ToolFailure as error:
        raise SystemExit(str(error)) from error

    graph = planner.build(model)
    context = model.num_ctx or "the server's default"
    say(f"{model.model}, reasoning {model.reasoning}, context {context}, database {path}")

    with MemorySampler(client) as memory:
        started = time.monotonic()
        for situation in situations:
            request = situation.request
            try:
                if situation.after_a_refusal:
                    first, seconds = timed(graph, request)
                    show(f"{situation.name} (turned down)", first, seconds)
                    request = dataclasses.replace(
                        request,
                        refused=first["plan"],
                        because=evaluation.TURNED_DOWN_BECAUSE,
                    )
                final, seconds = timed(graph, request)
            except Exception as error:  # a probe records every failure and carries on
                say(f"{situation.name:<36} failed: {error}")
                continue
            show(situation.name, final, seconds)
        total = time.monotonic() - started

    gib = 2**30
    say(
        f"total {total:.0f} s; loaded model memory {memory.loaded / gib:.1f} GiB "
        f"(Ollama's /api/ps); least free system memory {memory.least_free / gib:.1f} GiB"
    )


if __name__ == "__main__":
    main()
