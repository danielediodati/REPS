"""One run of the planner graph, as JSON: what it called, what was refused, what it cost."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from trainer import agent
from trainer.coach.calls import answered

MODEL = "model"
PROVIDER = "provider"
BUDGET = "budget"

UNKNOWN = "unknown"
"""What a run that was checkpointed before `on` carried its identity is named by."""

REFUSED = "refused"
VALID = "valid"

UNFINISHED = "unfinished"
"""A run that never reached the validator: nothing refused it and it has no plan.

The third outcome, and the one this vocabulary was missing. Without it a run
cut mid-flight reads as `valid`, which is a plan claimed for a run that never
emitted one.
"""


@dataclass(frozen=True)
class Run:
    """Who answered a run, and inside what budget.

    The three things the record needs that the graph's state does not hold.
    They travel in the run's config, which is how `on` below puts them where a
    later reader can find them.
    """

    model: str
    provider: str
    budget: int


def on(thread: str, run: Run) -> RunnableConfig:
    """The config a run travels on: its thread, and who is answering it.

    LangGraph keeps every extra `configurable` key in each checkpoint's
    metadata, so the model, the provider and the budget are on disk beside the
    state without being part of it. That is what lets `trainer runs` report a
    run it did not start -- asked of the model afterwards, the name and the
    provider are two attributes on two classes, and the environment may have
    named a different one since.
    """
    return {
        "configurable": {
            "thread_id": thread,
            MODEL: run.model,
            PROVIDER: run.provider,
            BUDGET: run.budget,
        }
    }


def ran(metadata: Mapping[str, Any]) -> Run:
    """A run's identity, as a checkpoint's metadata kept it.

    Forgiving of a checkpoint written before this was carried: those exist on
    disk, and refusing to read them would take the whole history with them.
    """
    declared = metadata.get(BUDGET)
    return Run(
        model=str(metadata.get(MODEL, UNKNOWN)),
        provider=str(metadata.get(PROVIDER, UNKNOWN)),
        budget=int(declared) if isinstance(declared, int) else agent.CALL_BUDGET,
    )


def outcome(state: Mapping[str, Any]) -> str:
    """Where a run got to: refused by the validator, holding a valid plan, or neither yet."""
    if state.get("violations"):
        return REFUSED
    if not state.get("attempts"):
        return UNFINISHED
    return VALID


def of(state: Mapping[str, Any], model: str, provider: str) -> dict[str, Any]:
    """The run record, derived from the graph's own state rather than kept alongside it."""
    messages: Sequence[AnyMessage] = state.get("messages", ())
    emitted = state.get("plan")
    return {
        "provider": provider,
        "model": model,
        "outcome": outcome(state),
        "attempts": [
            {
                "violations": [
                    {"rule": violation.rule, "says": violation.says}
                    for violation in refused
                ]
            }
            for refused in state.get("refusals", ())
        ],
        "calls": _calls(messages),
        "tokens": _tokens(messages),
        "nodes": [
            {"node": node, "seconds": round(seconds, 3)}
            for node, seconds in state.get("timings", ())
        ],
        "plan": None if emitted is None else emitted.model_dump(),
    }


def written(state: Mapping[str, Any], model: str, provider: str) -> str:
    """The record of one run, as a document."""
    return document(of(state, model, provider))


def document(record: Mapping[str, Any]) -> str:
    """One record written down. The one definition of how, so that `--record` and the eval's files read alike."""
    return json.dumps(record, indent=1)


def summary(state: Mapping[str, Any], model: str, provider: str, budget: int) -> list[str]:
    """The run in a few lines, for the terminal. ASCII.

    The attempts are said out loud because they are the thing session 6 added:
    a plan that was refused and fixed is a different run from one that passed
    first time, and the record is the only other place that says so.
    """
    messages: Sequence[AnyMessage] = state.get("messages", ())
    spent = state.get("spent", 0)
    used = f"{spent} of {budget} tool calls"
    if spent >= budget:
        used += " (budget spent; the plan was emitted with what it had)"
    lines = [f"{model} on {provider} -- {used}"]
    failed = sum(1 for call in _calls(messages) if call["failed"])
    if failed:
        lines.append(f"  {failed} of those calls came back an error")
    attempts = state.get("attempts", 0)
    if attempts > 1:
        lines.append(f"  {attempts} attempts; the validator refused the earlier ones")
    counted = _tokens(messages)
    lines.append(f"  {counted['input']} tokens in, {counted['output']} out")
    spent_on = _seconds(state)
    if spent_on:
        lines.append(f"  {spent_on}")
    return lines


def _seconds(state: Mapping[str, Any]) -> str:
    """What each node cost, summed over the times it ran. ASCII, one line."""
    totals: dict[str, float] = {}
    for node, seconds in state.get("timings", ()):
        totals[node] = totals.get(node, 0.0) + seconds
    return ", ".join(f"{node} {seconds:.1f}s" for node, seconds in totals.items())


def _calls(messages: Sequence[AnyMessage]) -> list[dict[str, Any]]:
    """Every tool call the model made, with what it asked for and whether it came back an error."""
    failed = {
        message.tool_call_id: message.status == "error"
        for message in messages
        if isinstance(message, ToolMessage)
    }
    return [
        {
            "name": call["name"],
            "arguments": call["args"],
            "failed": failed.get(answered(call), False),
        }
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]


def _tokens(messages: Sequence[AnyMessage]) -> dict[str, int]:
    """What the run read and wrote, as the provider counted it."""
    counted = [
        message.usage_metadata
        for message in messages
        if isinstance(message, AIMessage) and message.usage_metadata
    ]
    return {
        "input": sum(usage["input_tokens"] for usage in counted),
        "output": sum(usage["output_tokens"] for usage in counted),
    }
