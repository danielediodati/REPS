"""One run of the planner graph, as JSON: what it called, what was refused, what it cost."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from trainer.coach.calls import answered


def of(state: Mapping[str, Any], model: str, provider: str) -> dict[str, Any]:
    """The run record, derived from the graph's own state rather than kept alongside it."""
    messages: Sequence[AnyMessage] = state.get("messages", ())
    emitted = state.get("plan")
    return {
        "provider": provider,
        "model": model,
        "outcome": "refused" if state.get("violations") else "valid",
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
    """The record as a document, indented the way today's `--record` writes one."""
    return json.dumps(of(state, model, provider), indent=1)


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
    return lines


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
