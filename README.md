# REPS

> *Reasoning Engine for Personal Strength.*

Not a workout plan generator. **A loop.** A plan is a prompt: equipment + time + limitations → a table. The value is not in generating it, it is in adapting it over time — at week 3 the lunges at the end of the workout have cost three missed workouts, and the system changes.

- **[TRAINER.md](TRAINER.md)** — what gets built, and why.
- **[ROADMAP.md](ROADMAP.md)** — in what order, and where the cuts fall.

The design principle everything else follows from:

> The analytic layer defines the space. The agent moves inside it.

The engine is deterministic, reproducible and verifiable, and it answers questions. The agent decides which questions to ask, and chooses inside the space the answers leave open. It cannot prescribe outside that space, by construction rather than by instruction.

## Status

**`0.4.0` — session 4 of 10, complete.** `trainer plan --workout 3 --equipment dumbbell` asks a model for a workout and prints one you can do tonight. It loops over the same tool surface `trainer mcp` serves — one set of definitions, two registrations, so a tool cannot exist behind one door and not the other — inside a **call budget**, and when the budget runs out it stops offering tools and **emits anyway**. The plan is structured, never prose, and it leaves through a deterministic validator with **no way back in**: an id outside the admissible set or a plan over the declared budget is rejected whole, never trimmed and never handed back to be fixed ([ADR-0001](docs/adr/0001-the-engine-costs-and-constrains-it-never-prescribes.md)). The request is assembled from what the project already knows — which workout of the declared split, the time under your cap, the exclusions in force, and what you would rather not do, which stays admissible but cannot be prescribed silently. `--refused FILE --because "..."` hands a plan back and asks for another; nothing about that exchange is written down. The provider is Groq. And `trainer eval` is the measurement the session is judged on: six deliberately nasty situations, six invariants decided by code rather than by a second model, and a bar of **100%**. Next: session 5, logging by deviation — do the workout, write *«bench fine, only 3 sets of military because the shoulder was pulling, 4 out of 10»*, and the state moves. The `workouts` table arrives, the default is adherence and you report only what changed, and `pattern_history` and `last_performed_load` finally have something to read.

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

uv run trainer plan --equipment dumbbell                      # the next workout of your split
uv run trainer plan --equipment dumbbell --workout 3          # or name which one of it
uv run trainer plan --equipment dumbbell --workout 3 --avoid Dumbbell_Lunges
uv run trainer plan --equipment dumbbell --workout 3 --refused plan.json --because "not today"
uv run trainer plan --from workout.json --equipment dumbbell --time 45   # no model: check a plan you wrote

uv run trainer log --from report.json                          # no model: report a workout you did

uv run trainer state                          # where the rotation is, and what it has accumulated
uv run trainer state --cycles 3               # over a wider window

uv run trainer config                         # what you declared: cycle, cap, split
uv run trainer config --muscle-groups         # the seventeen muscles, and their six groups

uv run trainer mcp                            # serve the engine's tools over MCP, on stdio

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

## What you declare

Four values are yours to declare, not the system's to measure: how many workouts one complete rotation of your cycle holds, the most a single workout may run, which muscle groups each workout of the cycle trains, and what volume is counted over. They live in `training.toml` in the working directory — copy `src/trainer/data/training.example.toml` and edit it; `trainer config` prints that path when there is nothing to read — because `git diff` on that file is itself training history, and a declaration sitting in a table beside rows the system measured is indistinguishable from a measurement ([ADR-0003](docs/adr/0003-training-requirements-live-in-a-config-file.md)). `TRAINER_CONFIG` overrides where it lives. Nothing in trainer writes it; session 6's onboarding is what will fill it by talking to you.

`trainer config` reads it back, and says *«no training configuration yet»* when there is nothing to read rather than complaining about a field nobody filled in. A split that is not as long as the cycle, or a group name that is not one of the six, is refused with both numbers or with the six listed.

The six muscle groups — `chest`, `back`, `shoulders`, `arms`, `legs`, `core` — are a curated grouping of the catalog's own seventeen `primary_muscles` values, and they exist in exactly one place: `src/trainer/data/muscle-groups.md`, which carries the reason for every assignment. `lower back` is core, not back: the spinal erectors are trunk musculature, and a back day that counts them is counting bracing as pulling. `neck` maps to no group at all — its eight rows stay reachable in the catalog and no split ever asks for them. Everything that needs the vocabulary reads it from that file, so a hand-copied list can never drift from it, and a test fails the day the catalog grows an eighteenth muscle rather than letting it fall silently out of every allocation.

**Allocating time is all a muscle group does.** Volume is counted per movement pattern and per *muscle* — `arms` erases exactly the biceps/triceps distinction that axis exists to keep.

## A plan is a document

A plan is a **sequence of blocks**: a block is one or more exercises, a number of rounds, the rest taken after each round, and the reason it is there. Straight sets are the block holding one exercise, a superset holds two, a circuit as many as it has — one shape and one formula, ADR-0002.

```json
{"blocks": [
  {"items": [{"exercise_id": "Dumbbell_Squat",
              "prescription": {"unit": "reps", "amount": 8}}],
   "rounds": 4, "rest": 150,
   "reason": "the heaviest lift first, while the legs are fresh"}
]}
```

A prescription is an amount and the unit it counts — reps, or seconds for a carry or a plank. One field and a tag rather than an optional `reps` beside an optional `seconds`, because *exactly one of these two is set* is a rule no schema can state, and whoever writes against the schema is then being asked to guess.

`trainer plan --from FILE` reads one, checks it against the request, and either prints the workout or names the rule that refused it. Three rules, and they **reject** — nothing is trimmed to fit and nothing is asked again (ADR-0001): every exercise is inside `admissible_set` for that request, the plan's duration is inside the declared budget, and no exercise appears twice. A rejection names the id **and** why it is out — the equipment it needs, the exclusion it trips, or the setup cost that does not fit — and a rejected plan is not rendered at all, because half a workout with a refusal under it reads as a workout with a footnote.

The reason a block carries is the field that makes this the agent's shape rather than the engine's: TRAINER.md has the agent give its reasons, and a plan with nowhere to put them turns those reasons into prose beside the plan — which is what structured output exists to stop.

This is the door session 4's agent comes out through, built and testable before there is an agent. Reading the plan from a file instead of a model changes what is upstream of the validator and nothing downstream of it.

## The report

The other half of the same door. `trainer log --from FILE` reads a **performed
workout** — which prescribed workout it is about, the blocks actually done with
their rounds, rest and an optional RPE, a load where there was one, and the
user's own words verbatim — writes it in one transaction, and prints what was
prescribed set against what was performed.

```json
{"workout_id": 12,
 "report": "bench fine, only 3 sets of military because the shoulder was pulling",
 "blocks": [
   {"items": [{"exercise_id": "Standing_Military_Press", "unit": "reps",
               "amount": 10, "amount_source": "reported"}],
    "rounds": 3, "rounds_source": "reported", "rest": 90, "rest_source": "assumed"}
 ]}
```

**Logging is by deviation.** What the report does not mention was done as
prescribed: the unmentioned exercises come back filled in from the plan, and
every value that arrived that way carries a **provenance** of `assumed` — a
column, not a slogan, printed marked so you can see at a glance which numbers
are yours. `workout_id` may be null, because training nobody planned is still
training.

**And this validator does not reject.** Session 4's refuses a plan outside the
admissible set, because that plan has not happened and can still be prevented.
This one cannot refuse **a fact**: you had an exclusion on `vertical push` and
you pressed anyway, and that row is the most valuable one in the database. So a
performed workout is **recorded and flagged** — the substitution, the exclusion
trained straight through, the workout nobody planned, a load that moved further
than the history explains. What is still refused is only ever a statement about
the *document*: an exercise id the catalog does not have, a provenance outside
the three, a proposed exclusion naming neither a movement pattern nor a joint.

A report may propose an **exclusion** — a value and the day to try it again —
and it is written in the same transaction as the workout or not at all.
`exclusions.classify` decides whether the value is a pattern or a joint,
against the catalog's own vocabulary; the document never says which.

This is the door session 5's logging agent comes out through, built and
testable before there is an agent.

## The agent

`trainer plan` asks a model for the workout. It gets the tools `trainer.tools` defines — the same ones `trainer mcp` serves, derived from the same function signatures — calls them until it has what it needs, and emits a plan in the shape above.

**A node that loops, not a graph.** TRAINER.md is explicit that the workout loop *«is a node looping over a tool surface, and a graph adds nothing to a node that loops»*. LangGraph arrives in session 6, for onboarding, where checkpointing and resume are the point.

**A call budget.** Tool calls are local Python — zero network, zero tokens to execute — so what they cost is the context round-trip, and that is bounded. When the budget runs out the loop does not fail: it stops offering tools and asks for the plan with what it has. `--call-budget N` overrides the default of 12.

**No way back in.** A plan the validator refuses is reported as refused, with the rule that refused it. It is not trimmed and it is not handed back to the model to fix: *propose → check → correct* is the loop this project deliberately does not have, because the constraints are applied upstream, in the request. A refusal is a bug to go and read.

**What it is asked.** `--workout N` says which workout of the rotation this is; its muscle groups come from the `split` you declared, and the time divides evenly over them — offered as a starting point, not imposed, because the agent has `allocate` and ADR-0001 leaves the proportions to it. The time defaults to your declared `duration_cap_min` and is **refused** above it rather than clamped: quietly planning 60 minutes for someone who asked for 90 is the engine deciding how long you train. Persisted exclusions still inside their re-test date apply without being asked for; `--exclude` adds more for one run and writes nothing down.

**Preferences are not exclusions.** `--avoid EXERCISE_ID` says what you would rather not do. An exclusion is safety and the engine removes it from the space; a preference is knowledge of you, so it stays admissible and the agent may still reach for it — as long as it says why, in that item's `despite`, which the renderer prints on its own line. Proposing one silently is rejected. That is both halves of *«nothing the user has refused; and if it proposes it again, it says so and asks»*.

**The plan you don't want.** `--refused FILE --because "..."` hands back a plan you turned down and asks for another one. Two turns, not a conversation: the refused plan and what you said are inputs to a fresh run, and the only rule is that the new plan is not the old one — what makes it better is the agent's business. Nothing about the exchange is written down; SQLite never persists a conversation fact.

**The run record.** `--record FILE` writes what the model called, in what order, with what arguments, how much budget went, whether it emitted on exhaustion, what it cost in tokens, and the plan — written whichever way the run went, because a refusal is exactly the case you open it for. Session 4's evaluation decides its invariants by reading this rather than by asking the model what it did.

**The provider is Groq**, and the model defaults to `qwen/qwen3.8-27b` — the Qwen whose structured output runs in *strict* mode, where constrained decoding makes the emitted plan conform to the schema by construction rather than by luck. That matters because a malformed plan is a whole run thrown away: the loop has no way to ask again. Groq also refuses structured output and tool use in the same request, which is why the emission is a call of its own.

Copy `.env.example` to `.env` and set `GROQ_API_KEY`; `GROQ_MODEL` overrides the model and `LLM_BACKEND` names the provider (only `groq` is built — `ollama` is refused by name rather than quietly falling through). `.env` is read by the `trainer` command and by nothing else: the suite never loads it, because `conftest.py` takes credentials away from every test and a file that put them back would turn that guarantee into a guarantee about one machine. Missing credentials are reported as that state, before any request goes out.

The suite never reaches a provider: `conftest.py` removes sockets and credentials from every test, so the loop is covered against a stand-in model with scripted replies, and the real one runs only under the evaluation command.

## The measurement

`trainer eval` runs six hand-written, deliberately nasty situations against the real agent and checks six properties over every run — **decided by code**, never by a second model judging the first. For a decidable constraint a validator costs nothing, is not persuadable, and catches all of them rather than most.

The six situations are data: a seventh is a row. Each runs a declared number of times, because a model is a distribution and one green run is not a measurement, and **every run counts** — a run that could not be made counts against the metric too, since a measurement that quietly skipped what it could not do would report on the easy ones. The output is the situation-by-invariant matrix, the single percentage, and what the pass cost in tool calls and tokens. The bar is 100% and the command exits non-zero below it.

```
                 terminates      time      constraints   preferences   equipment   not degenerate
no-equipment         ok           ok            ok            ok           ok            ok
no-history           ok           ok            ok            ok           ok            ok
contradictory        ok           ok            ok            ok           ok            ok

3 of 3 runs held every invariant -- 100%
cost: 10 tool calls, 65854 tokens in, 3726 out
```

Every run's record is written to `eval-runs/`, and a failure names the situation, the invariant and the file — *invariant 3 failed* is a fact, and the record is the only thing that says why.

**It is the one command that reaches a provider**, and the only one that spends money. `pytest` never runs it: the suite has no sockets and no credentials, and the checks are pure functions over a record, so all of them are covered there instead.

**A full pass does not fit Groq's free tier in one day.** The daily ceiling is 200,000 tokens and a pass at three repetitions is roughly twice that. `--only NAME` and `--repetitions N` cut it down; a paid tier runs it whole.

## Inspecting the engine from a generic client

`trainer mcp` serves the engine's tool surface over MCP on stdio — `admissible_set`, `remaining_budget`, `allocate`, `pattern_history`, `last_performed_load` and `compare_variants`. Point the MCP inspector, or any other generic client, at it and you can call the engine exactly as the agent will, without going through the agent.

That is the whole reason MCP is here earlier than TRAINER.md's own plan has it: from session 4 on the agent will get things wrong, and watching the engine answer the same calls it is making — from an inspector, rather than through the agent's own account of what happened — is what makes the difference between debugging the engine and debugging a story about it.

Each tool is a wrapper and nothing else: it unpacks its arguments, opens the connection, calls the library function, and shapes the result for the wire. No validation of its own and no decisions. A failure the library states in words arrives as a tool error with that sentence intact, and the server stays up. `mcp` is in `test_engine_boundary.py`'s forbidden-import list beside `click`, so the engine can never learn that this door exists.

The tools are defined once, in `tools.py`, and `mcp_server.py` is the registration of that list plus `server.run()`. Session 4's agent registers the same list, so a tool cannot exist behind one door and not the other — the test reads the surface from `tools.TOOLS` rather than from a second copy of the names.

## The database

A single SQLite file, `trainer.sqlite` in the working directory. Override it with the `TRAINER_DB` environment variable — that is what the test suite does, so tests never touch a real one.

**SQLite 3.35 or newer** (March 2021). Migration 0006 drops a column, and `ALTER TABLE ... DROP COLUMN` arrived in that release; the migration set is applied as a whole, so an older library fails `trainer db init` with a syntax error rather than half-migrating. `uv` provisions the interpreter and the library comes with it, so this only matters if you run the package under an interpreter you brought yourself: `python -c "import sqlite3; print(sqlite3.sqlite_version)"` is the check.

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
  data/       what ships with the package: the exercise dataset, the muscle group mapping, the config example
  cli.py      argument parsing and formatting, nothing else
  tools.py    the tool surface: one definition per tool, registered behind every door
  plan.py     the plan's wire shape, the validator and the renderer
  agent.py    the model: a node looping over the tool surface, inside a call budget
  mcp_server.py  one of those doors; registration and server.run(), beside cli.py and never inside engine/
docs/
  agents/     configuration the engineering skills read
  work/       tickets, one file each
```

Every form of exposure — CLI, MCP wrapper, direct call — is a thin wrapper over the same engine. A test enforces that boundary rather than trusting the convention: `click` and `mcp` are both in its forbidden-import list, and it checks the loaded module graph as well as the source text.
