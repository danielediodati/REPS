# REPS

> *Reasoning Engine for Personal Strength.*

Not a workout plan generator. **A loop.** A plan is a prompt: equipment + time + limitations → a table. The value is not in generating it, it is in adapting it over time — at week 3 the lunges at the end of the session have cost three missed workouts, and the system changes.

- **[TRAINER.md](TRAINER.md)** — what gets built, and why.
- **[ROADMAP.md](ROADMAP.md)** — in what order, and where the cuts fall.

The design principle everything else follows from:

> The analytic layer defines the space. The agent moves inside it.

The engine is deterministic, reproducible and verifiable, and it answers questions. The agent decides which questions to ask, and chooses inside the space the answers leave open. It cannot prescribe outside that space, by construction rather than by instruction.

## Status

**`0.1.0` — session 1 of 11, tickets 01-03 done.** The package runs, the database migrates, the catalog is in it — 876 exercises from free-exercise-db — and you can query it from the command line. Still to come in this session: a versioned markdown snapshot of the catalog, and a profile of what it actually contains.

## Getting started

Requires [uv](https://docs.astral.sh/uv/); it provisions the Python interpreter itself, so nothing else needs installing.

```sh
uv sync                     # one command, from a clean checkout
uv run trainer --version
uv run trainer db init      # create the database and migrate it
uv run trainer db import    # load the exercise catalog into it
uv run trainer db status    # which schema version it is on

uv run trainer catalog --equipment dumbbell --level beginner
uv run trainer catalog --values equipment     # what that field actually holds
```

## The catalog

876 exercises from [free-exercise-db](https://github.com/yuhonas/free-exercise-db), vendored into the package so the import needs no network and cannot change underneath the work between one session and the next. Public domain, checksum and upstream commit recorded in `src/trainer/data/free-exercise-db/PROVENANCE.md`.

Images are references into the upstream repository, never bytes. Re-running the import changes nothing; an import that would remove most of the catalog is refused, because a truncated re-vendor otherwise deletes rows and reports success.

`trainer catalog` filters on the source's own fields, and the filters compose. The vocabulary is the source's — `dumbbell`, not `dumbbells` — and `--values FIELD` prints what a field holds, read from the table rather than from a list in the code. A value that is not in the catalog is rejected with the valid ones, so a typo never looks like a legitimately empty result.

Enrichment — the seven fields the catalog does not have, and which the whole engine depends on — is session 2.

## The database

A single SQLite file, `trainer.sqlite` in the working directory. Override it with the `TRAINER_DB` environment variable — that is what the test suite does, so tests never touch a real one.

The file is never committed: `git` diffs of a binary blob are useless. The readable history is a regenerated markdown snapshot beside it. **The DB is the truth, the snapshot is the readable history.**

## Development

```sh
uv run pytest               # the full suite
uv run mypy                 # strict type checking
```

The suite runs with no network access and no credentials — both are removed in `conftest.py`, so a test that grows a dependency on either fails rather than passing on a laptop that happens to be online.

## Layout

```
src/trainer/
  engine/     pure library: no LLM, no network, no knowledge of any client
  cli.py      argument parsing and formatting, nothing else
docs/
  agents/     configuration the engineering skills read
  work/       tickets, one file each
```

Every form of exposure — CLI, MCP wrapper, direct call — is a thin wrapper over the same engine. A test enforces that boundary rather than trusting the convention.
