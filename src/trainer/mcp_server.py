"""The tool surface, served over MCP. Registration, and nothing else.

Every tool this serves is defined in `trainer.tools`, along with the
preconditions it reads through, the translation of a stated engine failure and
the shaping of the engine's frozen dataclasses into what a JSON client can
read. What is left here is what is actually about MCP: the server object, the
loop that registers `tools.TOOLS`, the one line that turns a `ToolFailure`
into the SDK's own `ToolError`, and `server.run()`.

**Why the split.** Session 4's agent loops over the same surface, and a second
copy of the wrapper would diverge at the first tool added to one door and not
the other -- invisibly, because the agent's door is the one nobody is watching.
`tests/test_mcp_server.py` checks this server against `tools.TOOLS` rather than
against a list of names, so a tool that reaches one door and not the other
fails the build.

**Why MCP this early.** TRAINER.md pulls it in ahead of where the roadmap first
has it, on the bet that it costs little and pays back from here on: session 4's
agent will get things wrong, and watching the engine answer the same calls the
agent is making -- from a generic inspector, rather than through the agent's own
account of what happened -- is the whole return.

Run it with `trainer mcp`, or `python -m trainer.mcp_server`.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from trainer import __version__, tools

server: MCPServer[None] = MCPServer(
    name="reps-trainer",
    title="REPS engine",
    version=__version__,
    instructions=tools.INSTRUCTIONS,
)


def _translated(tool: Callable[..., Any]) -> Callable[..., Any]:
    """The shared surface's failure, in the type this door's clients expect.

    A `ToolError` reaches the client as a tool result marked failed; anything
    else is caught by the SDK and re-raised as `Error executing tool <name>`
    with the reason kept on the server, which is the boundary leak the shared
    translator exists to close.

    `functools.wraps` is what keeps the tool recognisable through the wrapper:
    the SDK builds each schema from `inspect.signature`, which follows
    `__wrapped__` back to the definition in `trainer.tools` and reads its
    annotations against that module's namespace. The name and the docstring --
    which is the tool's description to the model -- come the same way.
    """

    @functools.wraps(tool)
    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except tools.ToolFailure as error:
            raise ToolError(str(error)) from error

    return call


for _tool in tools.TOOLS:
    server.tool()(_translated(_tool))


def main() -> None:
    """Serve over stdio, which is what a generic MCP client connects to."""
    server.run()


if __name__ == "__main__":
    main()
