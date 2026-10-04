"""A closed run as a document: how it ended, what it called, what was refused, what it cost."""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import StateSnapshot

from trainer.coach.calls import answered
from trainer.engine import home

if TYPE_CHECKING:
    from trainer.coach import models

logger = logging.getLogger(__name__)


class Graph(Protocol):
    """The half of a compiled graph this module reads: where its live run got to.

    A protocol rather than either graph's type, because both write their runs
    here and neither is this module's to import.
    """

    def get_state(self, config: RunnableConfig) -> StateSnapshot: ...


class Node(Protocol):
    """One step of a graph. The parameter is named, which is what LangGraph asks of a node.

    Typed on the state as `Any`, because the three graphs hold three different
    states and what `timing` below does to a node is the same for all of them.
    """

    def __call__(self, state: Any) -> dict[str, Any]: ...

ARCHIVE_NAME = "runs"
"""The directory in the home the closed runs land in, one per negotiation."""

ACCEPTED = "accepted"
TURNED_DOWN = "turned down"
DONE = "done"
"""The run finished its work and there was nothing to accept or turn down.

A report read and a document emitted is this: ADR-0007 names a run *one
proposal pursued* because the only graph then was the planner, and a run of
the logger pursues nothing -- the report is already a fact.
"""

REFUSED = "refused"
"""The validator refused every attempt the run had."""

FAILED = "failed"
"""The run raised, and whoever caught it wrote the ending the node could not.

These five are every way a run can finish. A run still waiting on an
answer has no ending, and neither has one that was cut: where the reader found
it is the reader's to derive (ADR-0007, item 7).
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


def negotiation_id() -> str:
    """A negotiation's name: when it was asked, and enough to tell two of them apart."""
    return f"{datetime.now().astimezone():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"


def identity(negotiation: str, follows: str | None) -> dict[str, Any]:
    """Who a run is: its name, the ask it belongs to, what it follows, and no ending yet.

    Shared by every graph that writes runs, because a run is one thing
    whatever produced it -- and a second copy of these six keys would be a
    second answer to what a run is.
    """
    return {
        "negotiation": negotiation,
        "run": uuid4().hex[:8],
        "follows": follows,
        "began": now(),
        "ended": "",
        "ending": "",
    }


def born(state: Mapping[str, Any]) -> dict[str, Any]:
    """The identity a run that was started without one needs, or nothing when it has one.

    Studio and the HTTP API open a thread with the graph's own input and
    nothing else, and a run has to be a thing that can be read back whichever
    door opened it. Nothing once there is a run: every later turn of it would
    otherwise give it a new name.
    """
    return {} if state.get("run") else identity(negotiation_id(), None)


def timing(on: models.Chat) -> Callable[[str, Node], Node]:
    """Wrap a graph's nodes so each says who answered it and what it cost.

    The seconds are the thing being measured, and the model is beside them
    because from ADR-0006 there is no one model per run: the entrance answers
    its own node on a small fast model and the subgraph it opens answers the
    rest on the one `LLM_BACKEND` names. Read off the top of the document
    instead, a planning run would report the entrance's model for work the
    planner did.

    A node that started a new run says so by handing back timings of its own,
    and keeps them: its seconds belong to neither run. On `propose`, the only
    node that does it, they are how long the user took to answer, which is not
    a cost of planning at all.
    """

    def timed(node: str, step: Node) -> Node:
        def counted(state: Any) -> dict[str, Any]:
            started = time.monotonic()
            produced = step(state)
            if "timings" in produced:
                return produced
            spent = time.monotonic() - started
            return produced | {
                "timings": [
                    *state.get("timings", []),
                    (
                        node,
                        on.name,
                        on.provider,
                        spent,
                        on.reasoning,
                        ", ".join(_hosts(produced.get("messages", ()))),
                        _dollars(produced.get("messages", ())),
                    ),
                ]
            }

        return counted

    return timed


def closing(
    state: Mapping[str, Any],
    ending: str,
    budget: int,
    archive: Path | None,
    **also: Any,
) -> dict[str, Any]:
    """This run is over: the ending is written the moment it happens.

    Returns what the node contributes to the state, so the live run agrees
    with the document beside it. The closing node's own seconds are not in
    that document, because it is written before the node returns -- which is
    when the ending became true, and the alternative is a record that exists a
    super-step after the thing it records.

    `archive` of `None` keeps nothing, which is what a measurement passes: an
    eval pass is dozens of runs nobody had, and in the home they would be the
    history session 11 reads.
    """
    finished: dict[str, Any] = {"ending": ending, "ended": now(), **also}
    if archive is not None and state.get("run"):
        keep({**state, **finished}, budget, archive)
    return finished


def failed(
    graph: Graph,
    config: RunnableConfig,
    budget: int,
    archive: Path | None = None,
) -> None:
    """The run an exception left behind, ended as fallen over.

    A node cannot write after it has raised, so whoever catches the exception
    writes the ending for it (ADR-0007, item 1). Never at the cost of the
    exception itself: a failure to write the document is logged and swallowed,
    because the caller is already on its way to telling the user something
    went wrong.
    """
    if archive is None:
        return
    try:
        state = graph.get_state(config).values
        if not state.get("run") or state.get("ending"):
            return
        keep({**state, "ending": FAILED, "ended": now()}, budget, archive)
    except Exception:
        logger.exception("the run that fell over could not be written down")


def of(state: Mapping[str, Any], budget: int) -> dict[str, Any]:
    """The run record, derived from the graph's own state rather than kept alongside it.

    `budget` is what the run had, for a state that does not say -- a checkpoint
    written before runs carried theirs. The run's own wins: `trainer plan
    --call-budget 3` cut mid-flight is read back by a reader that was never
    told, and *3 of 12 tool calls* would be a number about nobody's run.
    """
    messages: Sequence[AnyMessage] = state.get("messages", ())
    emitted = state.get("plan")
    document = state.get("document")
    direction = state.get("direction")
    return {
        "negotiation": str(state.get("negotiation", "")),
        "run": str(state.get("run", "")),
        "follows": state.get("follows"),
        "began": str(state.get("began", "")),
        "ended": str(state.get("ended", "")),
        "ending": str(state.get("ending", "")),
        "because": str(state.get("because", "")),
        "unasked": bool(state.get("unasked", False)),
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
        "dollars": _dollars(messages),
        "spent": int(state.get("spent", 0)),
        "budget": int(state.get("budget", budget)),
        "nodes": [_node(entry) for entry in state.get("timings", ())],
        "emitted": list(state.get("emitted", ())),
        "questions": [list(said) for said in state.get("questions", ())],
        "plan": None if emitted is None else emitted.model_dump(),
        "performed": None if document is None else document.model_dump(),
        "workout": state.get("workout"),
        "mesocycle": state.get("mesocycle"),
        "direction": None if direction is None else dataclasses.asdict(direction),
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
    asked = len(record.get("questions", ()))
    if asked:
        lines.append(f"  {asked} question(s) asked")
    counted = record.get("tokens", {"input": 0, "output": 0})
    cached = counted.get("cached", 0)
    read = f", {cached} from the cache" if cached else ""
    lines.append(f"  {counted['input']} tokens in{read}, {counted['output']} out")
    dollars = record.get("dollars")
    lines.append(
        "  cost not reported by the provider" if dollars is None else f"  ${dollars:.4f}"
    )
    spent_on = _seconds(record)
    if spent_on:
        lines.append(f"  {spent_on}")
    wrote = record.get("workout")
    if wrote is not None:
        lines.append(f"  wrote prescribed workout {wrote}")
    kept = record.get("mesocycle")
    if kept is not None:
        lines.append(f"  kept mesocycle {kept}")
    return lines


def _answered_by(record: Mapping[str, Any]) -> str:
    """Who did the work, as the nodes name them, in the order they first ran.

    Read off the nodes rather than the top of the document, because from this
    ticket on there is no one model to read there: the entrance and the two
    subgraphs run on models of their own (ADR-0006).
    """
    hosts: dict[str, list[str]] = {}
    for node in record.get("nodes", ()):
        model, provider = node.get("model", ""), node.get("provider", "")
        if not model and not provider:
            continue
        answered_by = f"{model} on {provider}"
        if node.get("reasoning"):
            answered_by += f" at {node['reasoning']} effort"
        seen = hosts.setdefault(answered_by, [])
        for host in str(node.get("host", "")).split(", "):
            if host and host not in seen:
                seen.append(host)
    if not hosts:
        return "nobody on record"
    return ", ".join(
        named + (f" via {', '.join(served)}" if served else "")
        for named, served in hosts.items()
    )


def _node(entry: Sequence[Any]) -> dict[str, Any]:
    """One timing, as the state kept it.

    Two shapes, because the checkpoints on disk hold the one session 6 wrote:
    a node and its seconds, with nobody named. Read as what it is rather than
    refused, which would take the history with it.
    """
    if len(entry) == 2:
        node, seconds = entry
        return {
            "node": node,
            "model": "",
            "provider": "",
            "seconds": round(seconds, 3),
            "reasoning": "",
            "host": "",
            "dollars": None,
        }
    node, model, provider, seconds, *rest = entry
    return {
        "node": node,
        "model": model,
        "provider": provider,
        "seconds": round(seconds, 3),
        "reasoning": rest[0] if rest else "",
        "host": rest[1] if len(rest) > 1 else "",
        "dollars": rest[2] if len(rest) > 2 else None,
    }


def _seconds(record: Mapping[str, Any]) -> str:
    """What each node cost in seconds, and in dollars where priced, summed over the times it ran. ASCII, one line."""
    totals: dict[str, float] = {}
    priced: dict[str, float] = {}
    for node in record.get("nodes", ()):
        name = str(node["node"])
        totals[name] = totals.get(name, 0.0) + float(node["seconds"])
        if node.get("dollars") is not None:
            priced[name] = priced.get(name, 0.0) + float(node["dollars"])
    return ", ".join(
        f"{node} {seconds:.1f}s" + (f" ${priced[node]:.4f}" if node in priced else "")
        for node, seconds in totals.items()
    )


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


def _hosts(messages: Sequence[AnyMessage]) -> list[str]:
    """The hosts that answered the model's turns, as OpenRouter named them, in the order they first did."""
    found: list[str] = []
    for message in messages:
        host = message.response_metadata.get("host") if isinstance(message, AIMessage) else None
        if host and host not in found:
            found.append(str(host))
    return found


def _dollars(messages: Sequence[AnyMessage]) -> float | None:
    """What the model's turns cost, as the provider priced them; `None` when none was priced."""
    priced = [
        float(message.response_metadata["cost"])
        for message in messages
        if isinstance(message, AIMessage) and message.response_metadata.get("cost") is not None
    ]
    return sum(priced) if priced else None


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
        "cached": sum(
            usage.get("input_token_details", {}).get("cache_read", 0) or 0
            for usage in counted
        ),
    }
