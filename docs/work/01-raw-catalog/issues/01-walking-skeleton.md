# 01 — Walking skeleton: package, database, CLI

**What to build:** from a clean checkout, `trainer` runs, creates its SQLite database on first use, and reports which schema version it is on. Nothing about exercises yet — this is the narrow path that proves every layer exists and talks to the next one.

The architectural split that TRAINER.md requires is in place from the first commit rather than retrofitted: the engine is a pure library, the CLI is a thin wrapper over it, and a test enforces the boundary instead of a convention asking politely.

Reference: TRAINER.md § Technical architecture, § The engine is a library, not a service, § Persistent state.

**Environment note:** this machine has no Python interpreter installed, but `uv` (0.11.28) is available and can provision one. Use it for the interpreter, the virtualenv, dependencies and the entry point; do not ask the developer to install Python by hand.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `trainer --version` works from a clean checkout after a single documented setup command
- [x] First use creates the SQLite database and applies every migration from empty to current
- [x] Migrations are versioned, applied in order, and the applied version is queryable from the CLI
- [x] Running against a database already at the current version changes nothing and says so
- [x] The engine layer imports nothing from the CLI layer, makes no network calls and no model calls — enforced by a test, not by convention
- [x] The full test suite runs with no network access and no API key present
- [x] The database lives at a documented path, and that path is in `.gitignore` (already covered by `*.sqlite`)

## Comments

**Delivered.** `uv sync` then `uv run trainer --version`; `db init` migrates, `db status` reports. Python 3.14.6, provisioned by uv. 25 tests, mypy strict clean.

**The transaction bug the tests caught.** The first implementation used `executescript()` for migration bodies. Python's `sqlite3` commits any open transaction *before* running a script, and its implicit transactions only ever open before DML, never before DDL — so a migration that failed halfway left its `CREATE TABLE` committed while its version row was not written. The database ends up in a state that can neither be re-run (the table already exists) nor rolled back, and nothing in the schema records that it happened.

The fix is in two parts: connections open with `isolation_level=None` so transactions are driven explicitly rather than guessed at by the driver, and migration bodies are split into statements and executed one at a time inside an explicit `BEGIN`/`COMMIT`. Splitting uses `sqlite3.complete_statement`, which respects string literals and comments — a naive split on `;` would corrupt any migration containing a semicolon inside a string.

`test_a_failing_migration_leaves_no_trace` is the regression test, and it was written before the fix.

**Two decisions worth recording.**

*The first migration creates a `meta` table, not a domain table.* The mechanism needed something real to apply, but every domain table belongs to the ticket that fills it — creating `exercises` here would have front-run ticket 02's decision that the source's own string id is the primary key.

*The migration runner is tested against migration sets written by the tests*, not against the shipped ones. Those tests then keep testing the mechanism as the schema grows, rather than quietly becoming assertions about whatever the schema happens to look like today.

**Console output is ASCII.** An em dash in `db status` rendered as `�` in the Windows console. The documents keep their typography; anything the CLI prints does not.

**Review, and what it found.** Seven findings, all real, all fixed. Three were reproduced before touching anything.

*A trailing comment bricked `db init`.* The statement splitter only tested for completeness right after a `;`, so anything following the last statement stayed in the buffer and was reported as a truncated statement. In a repo whose migrations open with three lines of explanation, appending a closing remark to any migration would have made the database refuse to initialise. The tail is now stripped of comments before being judged incomplete.

*The boundary guard missed the one import it exists to catch.* `from trainer import cli` puts the module name in the alias, not in `node.module`, so it contributed only the name `trainer` and matched no forbidden prefix. The guard now checks `module.alias` too, and a parametrised test asserts it fails on each forbidden form — a guard nobody has watched fail is not a guard.

*A broken migration set reached the terminal as a traceback.* The CLI now converts `MigrationError` and `sqlite3.Error` into `ClickException`: `Error: the migration set is unusable: expected migration 1, found 3`, exit code 1.

The rest: `BEGIN IMMEDIATE` plus a version re-read inside the transaction, so two processes migrating at once cannot both decide to apply the same migration; the rollback in the error path is now itself guarded, because SQLite rolls back on its own for a full disk and the second rollback would have raised over the error that actually explained the failure; `discover()` on a missing directory raises instead of reporting version 0, which would have made a broken install indistinguishable from a healthy one; and a database *ahead* of the checkout is now warned about rather than reported as fine.

39 tests, mypy strict clean.

One test was withdrawn rather than kept. It claimed to prove that a second process cannot apply a migration twice, but `migrate` re-reads the version at entry, so the test never reached the in-transaction check it was named for. It now tests the read that decision rests on, and says plainly that the interleaving itself is not reachable without a hook inside the transaction.
