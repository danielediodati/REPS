"""How a tool call and the answer to it are tied together."""

from __future__ import annotations

from langchain_core.messages import ToolCall


def answered(call: ToolCall) -> str:
    """What the answer to this call is filed under.

    One definition, because the node that files it and the record that reads
    it back have to agree: a local model does not always send an id, and two
    different fallbacks would make every one of those calls read as having
    worked.
    """
    return call["id"] or call["name"]
