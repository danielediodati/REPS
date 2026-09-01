# 02 — Import the free-exercise-db catalog

**What to build:** one command fills `exercises` with the whole free-exercise-db catalog, and any exercise can be fetched back by its id with its instructions and images. That is the shape the appendix asks for: instructions and images live on the row but are never queried — they are retrieved by id when the agent shows them.

The dataset is vendored into the repo rather than fetched at import time: the import stays offline and reproducible, and the catalog cannot change underneath the work between one session and the next. Images are stored as **references**, never as blobs — the upstream repository hosts them, and a few hundred megabytes of binaries would ruin a repo meant to be cloned.

Reference: TRAINER.md § Appendix — catalog and enrichment.

**Source vocabulary, verified against the live dataset** — note the singular `dumbbell`, which differs from the example command in ROADMAP.md:

```
equipment : body only, barbell, dumbbell, kettlebells, cable, machine,
            bands, exercise ball, foam roll, medicine ball, other
force     : push, pull, static, null
level     : beginner, intermediate, expert
mechanic  : compound, isolation, null
category  : strength, stretching, plyometrics, powerlifting, strongman, cardio
```

**Blocked by:** 01 — Walking skeleton

**Status:** ready-for-agent

- [ ] The dataset is vendored into the repo, together with its licence (Unlicense) and the upstream commit it was taken from
- [ ] The import loads every record; the resulting row count equals the record count in the vendored file, and the command reports that number
- [ ] Native fields are stored as published: `id`, `name`, `force`, `level`, `mechanic`, `equipment`, `primaryMuscles`, `secondaryMuscles`, `instructions`, `category`, `images`
- [ ] The source's own string id is the primary key — no surrogate key invented alongside it
- [ ] An exercise is retrievable by id, with instructions and images, through an engine function
- [ ] Images are stored as references; no binary lands in the database
- [ ] Re-running the import is idempotent: same row count, no duplicates, no growth
- [ ] The import needs no network access
- [ ] Nulls in `force` and `mechanic` survive as nulls — they are absent data, not empty strings

## Comments
