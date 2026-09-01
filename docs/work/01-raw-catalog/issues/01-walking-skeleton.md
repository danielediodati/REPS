# 01 — Walking skeleton: package, database, CLI

**What to build:** from a clean checkout, `trainer` runs, creates its SQLite database on first use, and reports which schema version it is on. Nothing about exercises yet — this is the narrow path that proves every layer exists and talks to the next one.

The architectural split that TRAINER.md requires is in place from the first commit rather than retrofitted: the engine is a pure library, the CLI is a thin wrapper over it, and a test enforces the boundary instead of a convention asking politely.

Reference: TRAINER.md § Technical architecture, § The engine is a library, not a service, § Persistent state.

**Environment note:** this machine has no Python interpreter installed, but `uv` (0.11.28) is available and can provision one. Use it for the interpreter, the virtualenv, dependencies and the entry point; do not ask the developer to install Python by hand.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `trainer --version` works from a clean checkout after a single documented setup command
- [ ] First use creates the SQLite database and applies every migration from empty to current
- [ ] Migrations are versioned, applied in order, and the applied version is queryable from the CLI
- [ ] Running against a database already at the current version changes nothing and says so
- [ ] The engine layer imports nothing from the CLI layer, makes no network calls and no model calls — enforced by a test, not by convention
- [ ] The full test suite runs with no network access and no API key present
- [ ] The database lives at a documented path, and that path is in `.gitignore` (already covered by `*.sqlite`)

## Comments
