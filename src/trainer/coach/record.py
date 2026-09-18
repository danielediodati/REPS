"""A closed run as a document: how it ended, what it called, what was refused, what it cost."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from trainer.coach.calls import answered
from trainer.engine import home

ARCHIVE_NAME = "runs"
"""The directory in the home the closed runs land in, one per negotiation."""

ACCEPTED = "accepted"
TURNED_DOWN = "turned down"
REFUSED = "refused"
"""The validator refused every attempt the run had."""

FAILED = "failed"
"""The run raised, and whoever caught it wrote the ending the node could not.

These four are every way a run can finish. A run still waiting on an answer
has no ending, and neither has one that was cut: where the reader found it is
the reader's to derive (ADR-0007, item 7).
"""


def archive() -> Path:
    """Where the closed runs live: the home's, unless a caller names another."""
    return home.inside(ARCHIVE_NAME)


def now() -> str:
    """This moment, in this machine's own time zone.

    To the microsecond, because it is what orders the runs of one negotiation:
    three plans turned down inside a minute are three runs, and to the second
    they would sort by nothing.
    """
    return datetime.now().astimezone().isoformat()


def of(state: Mapping[str, Any], budget: int) -> dict[str, Any]:
    """The run record, derived from the graph's own state rather than kept alongside it.

    `budget` is what the run had, for a state that does not say -- a checkpoint
    written before runs carried theirs. The run's own wins: `trainer plan
    --call-budget 3` cut mid-flight is read back by a reader that was never
    told, and *3 of 12 tool calls* would be a number about nobody's run.
    """
    messages: Sequence[AnyMessage] = state.get("messages", ())
    emitted = state.get("plan")
    return {
        "negotiation": str(state.get("negotiation", "")),
        "run": str(state.get("run", "")),
        "follows": state.get("follows"),
        "began": str(state.get("began", "")),
        "ended": str(state.get("ended", "")),
        "ending": str(state.get("ending", "")),
        "because": str(state.get("because", "")),
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
        "spent": int(state.get("spent", 0)),
        "budget": int(state.get("budget", budget)),
        "nodes": [_node(entry) for entry in state.get("timings", ())],
        "plan": None if emitted is None else emitted.model_dump(),
        "workout": state.get("workout"),
    }


def document(record: Mapping[str, Any]) -> str:
    """One record written down. The one definition of how, so that the archive and `--record` read alike."""
    return json.dumps(record, indent=1)


def keep(state: Mapping[str, Any], budget: int, into: Path) -> Path:
    """One closed run, written where it outlives the checkpointer (ADR-0007, item 6).

    A file per run under a directory per negotiation: the grouping the reader
    needs is the directory listing, so reading an evening back never means
    opening every document the home holds.
    """
    written = of(state, budget)
    path = path_of(into, written["negotiation"], written["run"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document(written), encoding="utf-8")
    return path


def path_of(into: Path, negotiation: str, run: str) -> Path:
    """Where one run's document lives."""
    return into / negotiation / f"{run}.json"


def summary(record: Mapping[str, Any]) -> list[str]:
    """The run in a few lines, for the terminal. ASCII.

    The attempts are said out loud because they are the thing session 6 added:
    a plan that was refused and fixed is a different run from one that passed
    first time, and the document is the only other place that says so.
    """
    budget = int(record.get("budget", 0))
    spent = int(record.get("spent", 0))
    used = f"{spent} of {budget} tool calls"
    if budget and spent >= budget:
        used += " (budget spent; the plan was emitted with what it had)"
    lines = [f"{_answered_by(record)} -- {used}"]
    failed = sum(1 for call in record.get("calls", ()) if call["failed"])
    if failed:
        lines.append(f"  {failed} of those calls came back an error")
    attempts = len(record.get("attempts", ()))
    if attempts > 1:
        lines.append(f"  {attempts} attempts; the validator refused the earlier ones")
    counted = record.get("tokens", {"input": 0, "output": 0})
    lines.append(f"  {counted['input']} tokens in, {counted['output']} out")
    spent_on = _seconds(record)
    if spent_on:
        lines.append(f"  {spent_on}")
    wrote = record.get("workout")
    if wrote is not None:
        lines.append(f"  wrote prescribed workout {wrote}")
    return lines


def _answered_by(record: Mapping[str, Any]) -> str:
    """Who did the work, as the nodes name them, in the order they first ran.

    Read off the nodes rather than the top of the document, because from this
    ticket on there is no one model to read there: the entrance and the two
    subgraphs run on models of their own (ADR-0006).
    """
    named: list[str] = []
    for node in record.get("nodes", ()):
        model, provider = node.get("model", ""), node.get("provider", "")
        if not model and not provider:
            continue
        answered_by = f"{model} on {provider}"
        if answered_by not in named:
            named.append(answered_by)
    return ", ".join(named) if named else "nobody on record"


def _node(entry: Sequence[Any]) -> dict[str, Any]:
    """One timing, as the state kept it.

    Two shapes, because the checkpoints on disk hold the one session 6 wrote:
    a node and its seconds, with nobody named. Read as what it is rather than
    refused, which would take the history with it.
    """
    if len(entry) == 2:
        node, seconds = entry
        return {"node": node, "model": "", "provider": "", "seconds": round(seconds, 3)}
    node, model, provider, seconds = entry
    return {
        "node": node,
        "model": model,
        "provider": provider,
        "seconds": round(seconds, 3),
    }


def _seconds(record: Mapping[str, Any]) -> str:
    """What each node cost, summed over the times it ran. ASCII, one line."""
    totals: dict[str, float] = {}
    for node in record.get("nodes", ()):
        name = str(node["node"])
        totals[name] = totals.get(name, 0.0) + float(node["seconds"])
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
