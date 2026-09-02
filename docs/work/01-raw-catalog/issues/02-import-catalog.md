# 02 — Import the free-exercise-db catalog

**What to build:** one command fills `exercises` with the whole free-exercise-db catalog, and any exercise can be fetched back by its id with its instructions and images. That is the shape the appendix asks for: instructions and images live on the row but are never queried — they are retrieved by id when the agent shows them.

The dataset is vendored into the repo rather than fetched at import time: the import stays offline and reproducible, and the catalog cannot change underneath the work between one session and the next. Images are stored as **references**, never as blobs — the upstream repository hosts them, and a few hundred megabytes of binaries would ruin a repo meant to be cloned.

Reference: TRAINER.md § Appendix — catalog and enrichment.

**Source vocabulary — corrected against the vendored dataset.** The block first written here came from a partial read of the file and was wrong in three places: it missed `e-z curl bar` and `olympic weightlifting`, and it did not record that `equipment` is null for 77 records. Counts are over all 876:

```
equipment : barbell 170, dumbbell 123, other 122, body only 111, cable 81,
            NULL 77, machine 67, kettlebells 56, bands 20, medicine ball 17,
            exercise ball 12, foam roll 11, e-z curl bar 9
force     : pull 371, push 371, static 104, NULL 30
level     : beginner 525, intermediate 294, expert 57
mechanic  : compound 491, isolation 298, NULL 87
category  : strength 584, stretching 123, plyometrics 61, powerlifting 38,
            olympic weightlifting 35, strongman 21, cardio 14
```

Note the singular `dumbbell`, which differs from the example command originally in ROADMAP.md.

**Blocked by:** 01 — Walking skeleton

**Status:** done

- [x] The dataset is vendored into the repo, together with its licence (Unlicense) and the upstream commit it was taken from
- [x] The import loads every record; the resulting row count equals the record count in the vendored file, and the command reports that number
- [x] Native fields are stored as published: `id`, `name`, `force`, `level`, `mechanic`, `equipment`, `primaryMuscles`, `secondaryMuscles`, `instructions`, `category`, `images`
- [x] The source's own string id is the primary key — no surrogate key invented alongside it
- [x] An exercise is retrievable by id, with instructions and images, through an engine function
- [x] Images are stored as references; no binary lands in the database
- [x] Re-running the import is idempotent: same row count, no duplicates, no growth
- [x] The import needs no network access
- [x] Nulls in `force` and `mechanic` survive as nulls — they are absent data, not empty strings

## Comments

**Delivered.** `trainer db import` reads the vendored dataset and fills `exercises`. 876 records, 876 rows, a 983 KB database. Re-running reports 876 updated and no growth. 69 tests, mypy strict clean.

**876, not ~800.** The real count matters twice: it is the pool the admissible set will be drawn from, and it is the multiplier on session 2's enrichment, which is the only step with a real external cost. 584 of the 876 are `category: strength` — ticket 05 reports the full breakdown, but the headline number is already visible and it is a third smaller than the one everyone quotes.

**Two values the ticket did not know about.** `e-z curl bar` and `olympic weightlifting` were both absent from the vocabulary written into this ticket, because that list came from a partial read of the file. The consequence is a rule for ticket 03: the set of valid filter values has to be **read from the data**, never written into the CLI as a constant. A hand-copied list would have rejected `--equipment "e-z curl bar"` as a typo — which is exactly the failure mode ticket 03 exists to prevent, arriving from the other direction.

**`curl -o` writes a 404 into the file.** Fetching the licence without `--fail` produced a fourteen-byte `LICENSE` containing `404: Not Found`; the real file upstream is `LICENSE.md`. It looked like a successful download and would have shipped as the licence of record. `PROVENANCE.md` says to use `--fail` when re-vendoring.

**Decisions worth recording.**

*The dataset ships inside the package*, at `src/trainer/data/free-exercise-db/`, not at the repo root. Data outside the package is not in the wheel, and a catalog missing from an installed copy is the kind of packaging fault that looks like an empty database rather than an error.

*The four list-valued fields are stored as JSON arrays* with `json_type(...) = 'array'` check constraints, one row per source record. An exercise comes back whole, which is what retrieval by id needs, and `json_each()` reaches inside when a query needs to — that is how ticket 03 will filter on muscles.

*The import is a sync, not an append.* Rows are upserted by id and rows the dataset no longer carries are deleted, in one transaction. Upserting alone would satisfy "no duplicates" but not "the row count equals the record count": a stale row from an earlier dataset would sit there forever, and nothing would report it.

*`db import` refuses to run against a database behind the current schema* rather than migrating implicitly. Migrating as a side effect would hide the fact that the database was behind, and `db init` is one command away.

**Two tests from ticket 01 had hardcoded schema version 1** and broke the moment a second migration existed. They now derive the expected version from the migration set. Worth watching for: an assertion about today's schema masquerading as an assertion about behaviour.

**Review, and what it found.** Eight findings, all real, all fixed. 77 tests, mypy strict clean.

*A truncated re-vendor deleted the catalog and reported success.* `load()` accepted `[]` as a valid dataset, and the import then computed every existing row as one the dataset no longer carries and removed it: 876 rows gone, exit code 0. The provenance note warns about a download that writes `404: Not Found` into the file, and JSON parsing catches that one — but a download that writes `[]`, or half the file, walks straight through. Two guards now: an empty dataset is refused outright, and an import that would remove more than half the catalog stops and says so, because a truncated file is far likelier than an upstream deletion of that size. `--allow-pruning` is there for the day the deletion is real. The same argument the parser already made for a single malformed record applies with more force to all of them.

*`db import` created an empty database before refusing to use it.* Connecting creates the file, and the schema check came after, so running the command in the wrong directory left a stray 0-byte database that `db status` then reported as "schema version: 0" rather than "not created yet". It now checks for the file before connecting, as `db status` already did.

*`db import` was silent when the database was ahead of the checkout.* `db init` and `db status` warn; the command that writes did not. Writing into a schema a newer version built is the more dangerous half of the case the warning exists for.

The rest: an upstream empty string was stored as `""` beside the 77 genuine nulls, which would have become a phantom value the moment ticket 03 reads the vocabulary out of the table — absent is now absent however the source spells it; the JSON columns checked `json_valid`, which also accepts an object or a bare number, and now check `json_type(...) = 'array'`, which is what the comment above them always claimed; the rollback test caught `Exception`, so it would have passed just as green if the import had failed for an unrelated reason and nothing had ever been written; the vendored-record assertion was `> 800`, which would not have noticed a re-vendor dropping seventy records, and is now the exact 876 that PROVENANCE.md records; and the README still said "No exercises yet" while shipping the command that loads them.

**One test bit back.** The truncation test patched `catalog.load`, and its helper resolved `load` from the module *after* the patch — so it called the patch, and recursed until Python gave up. The real function is now captured before the patch is installed.
