# 05 — Inspect the engine from a generic client

**What to build:** an MCP server exposing this session's tool surface — `admissible_set`, `remaining_budget`, `simulate_cut`, `pattern_history`, `last_performed_load` — as MCP tools, each a thin wrapper doing nothing but unpacking arguments, opening the connection, calling the library function, and shaping the result for the wire. No new logic, the same discipline `trainer.cli` already holds: `test_engine_boundary.py` exists precisely so that CLI, MCP and a direct call are three doors onto the same code, never three copies of it.

**Why now, and why half a day is the right budget.** TRAINER.md pulls MCP in ahead of where it first appears in the roadmap's own "First steps" list, on the stated bet that it costs little and pays back over every session from here on — session 4's agent gets things wrong, and being able to watch the engine answer the same calls the agent is making, from a generic inspector rather than through the agent's own account of what happened, is the whole payoff. That bet is only good if this ticket stays a wrapper: no new validation, no new shaping of the data beyond what MCP's content types require.

**Library: the official `mcp` SDK (`modelcontextprotocol` org), not the standalone `fastmcp` package.** It is the reference implementation of the protocol, which is what makes it the one worth depending on for a project meant to still make sense in a year. One naming detail to check at implementation time rather than assume: the SDK's v2 line renamed the decorator-based server class from `FastMCP` to `MCPServer` (same decorator API, snake_case fields) — pin `mcp>=2,<3` in `pyproject.toml`'s `dependencies` and use whichever class name that installed version actually exports.

**The wrapper lives beside `trainer.cli`, never inside `engine/`.** `engine/` is the pure library `test_engine_boundary.py` enforces zero LLM, zero network and zero knowledge of any client into — an MCP import inside `engine/` is exactly the kind of thing that guard exists to catch. Put the server in its own module (e.g. `trainer/mcp_server.py`), parallel to `cli.py`, importing from `engine/` the same way `cli.py` already does.

**Extend the boundary guard's forbidden-imports list with `mcp`.** The project has already been burned once by a convention that lived only in someone's memory — CLAUDE.md's own standing rules exist because of it — and `test_engine_boundary.py`'s docstring says outright that a convention not enforced is a convention forgotten in a month. `mcp` belongs in `FORBIDDEN_PREFIXES` next to `click`, for the same reason `click` is there.

**Nothing here talks to `pattern_state` or `workouts` beyond what ticket 04 already built.** `adherence_history`, `compare_variants` and `active_conclusions` are named in TRAINER.md's tool surface but are not part of this session's issues — they stay unimplemented until the sessions that build what they need (`workouts` for the first, the variant graph exposed as a tool for the second, `conclusions` for the third). Wrapping a function that does not exist is not this ticket's job.

Reference: TRAINER.md § Technical architecture (MCP), § The tool surface; ROADMAP.md § Session 3, § Declared deviations (MCP pulled in early).

**Blocked by:** 01 — How long does this actually take; 02 — What gets cut when it doesn't fit; 03 — The rest period is not a knob; 04 — Two questions the state can't answer yet

**Status:** ready-for-agent

- [ ] `mcp>=2,<3` added to `pyproject.toml`'s `dependencies`
- [ ] An MCP server module outside `engine/`, exposing `admissible_set`, `remaining_budget`, `simulate_cut`, `pattern_history` and `last_performed_load` as tools, each a thin wrapper with no logic beyond argument unpacking and calling the library function
- [ ] `mcp` added to `test_engine_boundary.py`'s `FORBIDDEN_PREFIXES`, with a test proving it is actually caught
- [ ] Connecting a generic MCP client (e.g. the MCP inspector) lists all five tools with usable schemas and each one, called against the real database, returns what the equivalent direct library call returns
- [ ] An error the library already raises (unenriched catalog, unknown pattern, unknown exercise id) surfaces as a tool error, not a crashed server
- [ ] `tests/test_engine_boundary.py` still passes in full

## Comments
