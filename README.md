# REPS

> *Reasoning Engine for Personal Strength.*

Not a workout plan generator. **A loop.** A plan is a prompt: equipment + time + limitations → a table. The value is not in generating it, it is in adapting it over time — at week 3 the lunges at the end of the session have cost three missed workouts, and the system changes.

- **[TRAINER.md](TRAINER.md)** — what gets built, and why.
- **[ROADMAP.md](ROADMAP.md)** — in what order, and where the cuts fall.

The design principle everything else follows from:

> The analytic layer defines the space. The agent moves inside it.

The engine is deterministic, reproducible and verifiable, and it answers questions. The agent decides which questions to ask, and chooses inside the space the answers leave open. It cannot prescribe outside that space, by construction rather than by instruction.

## Status

**`0.2.0` — session 2 of 10, complete.** All 584 strength rows carry a `movement_pattern` and the five fields that follow from it — a rule decides 546, a person reading the exercise's own instructions decides the other 38, each citing the line it rests on — and the `variant_of`/`regression_of` graph links equivalent movements across equipment. `trainer admissible --equipment "body only" --time 45 --exclude "vertical push"` answers *«what can I do today»*: exclusions live in their own table, two granularities only (a pattern or a joint, never an exercise id), each with a re-test date that lets it expire. No model and no network anywhere in the session. Next: session 3, which adds the duration model and ends at telling a selection how long it takes and what it would drop to fit a shorter budget.

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
uv run trainer catalog --stats                # what the catalog actually holds

uv run trainer enrich derive                  # the rule: movement_pattern for 546 of 584
uv run trainer enrich curated                 # the other 38, read by hand, plus the graph
uv run trainer enrich check                   # score both against the hand-built reference set

uv run trainer admissible --equipment "body only" --time 45 --exclude "vertical push"

uv run trainer db snapshot  # regenerate snapshots/catalog.md, then commit it
```

## The catalog

876 exercises from [free-exercise-db](https://github.com/yuhonas/free-exercise-db), vendored into the package so the import needs no network and cannot change underneath the work between one session and the next. Public domain, checksum and upstream commit recorded in `src/trainer/data/free-exercise-db/PROVENANCE.md`.

Images are references into the upstream repository, never bytes. Re-running the import changes nothing; an import that would remove most of the catalog is refused, because a truncated re-vendor otherwise deletes rows and reports success.

`trainer catalog` filters on the source's own fields, and the filters compose. The vocabulary is the source's — `dumbbell`, not `dumbbells` — and `--values FIELD` prints what a field holds, read from the table rather than from a list in the code. A value that is not in the catalog is rejected with the valid ones, so a typo never looks like a legitimately empty result.

`trainer catalog --stats` counts those same rows instead of listing them: **584 of the 876 are `category: strength`**, and the other 292 are stretching, plyometrics, powerlifting, olympic weightlifting, strongman and cardio. That is the real size of the pool the admissible set is drawn from, and the multiplier on session 2's enrichment. The filters narrow the counts too, so a filtered question never gets an answer about the whole catalog. Rows holding no value are counted as `(none)`, shown even when there are none, so every column visibly adds up to the total: 87 exercises have no `mechanic`, 77 no `equipment` and 30 no `force`, while every one of them has a `level` and a `category`. Coverage is worth knowing before a field is relied on — `force` in particular, which TRAINER.md's appendix already judges insufficient on its own terms (*«`force: "push"` does not distinguish a bench press from a military press»*), and which is missing outright for thirty of them.

Enrichment — the six fields the catalog does not have, and which the whole engine depends on — is session 2. Every value records where it came from. A **rule** over the native columns decides most of `movement_pattern` and all the fields that follow from it. What a rule cannot decide, it cannot decide because the answer is in the exercise's `instructions` rather than in its columns, so those rows are **read and decided, each quoting the sentence it rests on**. And 60-80 movements are decided by hand as the **reference set** both are measured against, chosen before the rules have run.

There is no model and no network anywhere in it. The first model in the project is the agent that writes plans, in session 4.

A seventh field, `required_rom` — a range of motion in degrees per joint — was specified and then dropped from v1. It needed a number the catalog cannot supply and a number the user does not know, multiplied together into a safety boundary. Exclusion works at pattern and joint granularity instead, which is what a person can actually report. See TRAINER.md § Appendix.

## What can I do today

`trainer admissible` is the answer: the exercises today's equipment, the time available and every active exclusion leave standing. Exclusions live in their own table, at exactly two granularities and no third — a movement pattern (*«it hurts when I press overhead»* excludes `vertical push`) or a joint (*«the shoulder is bad»* excludes everything with `shoulder` among its `loaded_joints`) — never an exercise id, and always with a re-test date, so a wall placed today does not stand forever by accident. `--exclude` classifies a value against the catalog's own vocabulary for a single query without persisting it; a persisted exclusion is read automatically once its re-test date has not yet arrived.

This is the sentence the rest of the architecture rests on: *the analytic layer defines the space, the agent moves inside it*. From session 4 on, an agent chooses inside whatever `admissible_set` returns and cannot prescribe outside it — not by instruction, but because nothing outside the set exists for it to choose.

## The database

A single SQLite file, `trainer.sqlite` in the working directory. Override it with the `TRAINER_DB` environment variable — that is what the test suite does, so tests never touch a real one.

The file is never committed: `git` diffs of a binary blob are useless. The readable history is `snapshots/catalog.md`, regenerated beside it by `trainer db snapshot` and committed. **The DB is the truth, the snapshot is the readable history.**

That snapshot is never hand-edited and never read back by the engine — it exists to be diffed. Regenerating against an unchanged database produces a byte-identical file, so `git diff` stays empty and a diff that does appear means the catalog moved. One exercise is one line and its text depends on nothing but that exercise, so a rename changes one line rather than reflowing the table around it. Instructions and images are counts, not text: the file is for reading, not a second copy of the database. `TRAINER_SNAPSHOT` overrides where it goes.

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
