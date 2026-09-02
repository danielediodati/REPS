# 01 — The seven enrichment fields, and where each value came from

**What to build:** a migration that makes room for the seven fields from TRAINER.md's appendix, plus `demo_url`, on a catalog that already holds 876 unenriched rows. Nothing gets enriched here. This ticket establishes the shape everything downstream writes into, and the guarantees that stop a cheap mistake from destroying an expensive run.

Three constraints decide that shape.

**The admissibility filter is a `WHERE`.** TRAINER.md rests on it — that is the stated reason the project chose SQLite over files. So the enriched values live as columns on `exercises`, never in a key/value table that would turn every session 3 query into one join per field.

**`required_rom` is a triple, and there can be more than one of them.** A military press loads the shoulder in flexion and the elbow in extension, and an exclusion has to be able to catch either. So: a child table keyed by exercise and queried with `NOT EXISTS`, not three columns holding whichever requirement the enrichment happened to pick first. The appendix's *«structured and not textual because it exists to isolate one variable at a time»* is the same argument one level down.

**Provenance is per field, not per row.** This session fills these fields three different ways — a rule reading the native columns, a hand-decided reference, a majority vote between models — and how much a value can be trusted is entirely a function of which one wrote it. A table that cannot tell them apart cannot be audited, cannot be re-run one field at a time, and cannot be scored against the reference set in ticket 03.

Reference: TRAINER.md § Appendix, § Persistent state; ROADMAP.md § Declared deviations (the `demo_url` row).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A migration adds `movement_pattern`, `loaded_joints`, `spinal_axial_load`, `required_stability`, `setup_cost_min`, `regression_of`, `variant_of` and `demo_url`, every one of them nullable — 876 rows already exist and none of them is enriched
- [ ] `required_rom` is a structured child table accepting several rows per exercise, with `joint`, `movement` and a numeric `degrees` typed as such
- [ ] `regression_of` and `variant_of` reference an exercise id, enforced; a value pointing at nothing is refused rather than stored
- [ ] Every enriched field records where its value came from, per field per exercise — a rule, a hand decision, or a vote
- [ ] **A re-import leaves enrichment untouched.** `trainer db import` overwrites the native fields and nothing else, with a test for it: this failure is silent, and it would cost the one external spend in the project
- [ ] `trainer catalog --stats` reports how much of each enriched field is filled, against the total
- [ ] `trainer catalog --values movement_pattern` against an unenriched catalog names that state rather than rejecting a correct value against an empty vocabulary
- [ ] `trainer db snapshot` carries the new fields, still one exercise per line, still byte-identical when nothing changed
- [ ] `demo_url` is documented as holding a link and never hosted media, filled by hand from session 5, and never written by a model

## Comments
