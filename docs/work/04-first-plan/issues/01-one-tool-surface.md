# 01 — One tool surface, two doors

**Status:** ready-for-agent

**Blocked by:** None — can start immediately.

## What to build

The tools the agent will call and the tools `trainer mcp` already serves become
**one set of definitions with two registrations**, rather than two modules that
happen to wrap the same library.

Everything `mcp_server.py` grew in session 3 that is not MCP-specific moves into
that shared layer: the connection with its preconditions named (no database,
schema behind this checkout), the translation of a stated engine failure into a
tool error, and the shaping of the engine's frozen dataclasses into what a JSON
client can read. What stays in `mcp_server.py` is registration and `server.run()`.

`compare_variants(id_a, id_b)` joins the surface. TRAINER.md § *The tool surface*
has listed it since the beginning and it had nothing to wrap until session 2
shipped the `variant_of` / `regression_of` graph; substitution is the first thing
the agent will need it for — *the Arnold and the military press are the same
pattern, to the engine they are interchangeable*.

`adherence_history` and `active_conclusions` stay out. They need `workouts`
(session 5) and `conclusions` (session 8), and wrapping a function that does not
exist is not this ticket's job.

The module goes **beside** the CLI and the MCP server, never inside `engine/`.
`tests/test_engine_boundary.py` is the reason that sentence is enforceable
rather than decorative.

**Read first:** TRAINER.md § *The tool surface*, § *The engine is a library, not
a service*, § *MCP*. `src/trainer/mcp_server.py`'s own module docstring, which
already carries the argument for why it is a wrapper and what is deliberately
not in it.

## Acceptance criteria

- [ ] `trainer mcp` serves the five tools it served before plus `compare_variants`, and the existing MCP tests pass without their expectations being loosened.
- [ ] A test fails if a tool exists behind one door and not the other — the surface is enumerated from one place, not asserted twice.
- [ ] `compare_variants` answers for two ids with the four fields TRAINER.md names — movement pattern, loaded joints, required stability, setup cost — and with the relation the graph holds between them: same movement, one a regression of the other, or neither.
- [ ] An id the catalog does not have is an error naming that id, never an empty comparison that reads as *«these two have nothing in common»*.
- [ ] The precondition states are reported once, in the shared layer, each with the command that fixes it: no database → `trainer db init`; schema behind the checkout → `trainer db init`; catalog not enriched → `trainer enrich derive`.
- [ ] `tests/test_engine_boundary.py` still passes: the new module reads from `engine/`, and `engine/` gains no knowledge that it exists.
