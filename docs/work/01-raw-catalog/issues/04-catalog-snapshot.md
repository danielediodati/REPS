# 04 — Versioned markdown snapshot of the catalog

**What to build:** a command that regenerates a readable markdown snapshot of the catalog, committed to git. This is the first half of the mechanism TRAINER.md sets up to pay for choosing SQLite: the `.sqlite` file is an opaque blob whose diffs are useless, so the readable history lives in a regenerated snapshot beside it.

**The DB is the truth, the snapshot is the readable history.** The snapshot is never edited by hand and never read back by the engine — it exists to be diffed by a human.

Determinism is the whole point: if the database has not changed, regenerating must leave `git diff` empty. A snapshot that churns on every run teaches you to ignore its diffs, which is the only thing it was for.

Reference: TRAINER.md § Persistent state.

**Blocked by:** 02 — Import the free-exercise-db catalog

**Status:** ready-for-agent

- [ ] A command regenerates the snapshot at a fixed, documented path
- [ ] Ordering and formatting are deterministic: regenerating against an unchanged database produces a byte-identical file, and `git diff` is empty
- [ ] The generated file states at the top that it is generated and must not be hand-edited
- [ ] Regenerating after a re-import produces a diff a human can actually read — one exercise per row, no reflowing of unrelated lines
- [ ] Instructions and images are omitted or reduced to a count: the snapshot is for reading, not a second copy of the database
- [ ] The snapshot is committed to the repo

## Comments
