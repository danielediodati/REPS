# 01 — The six enrichment fields, and where each value came from

**What to build:** a migration that makes room for the six enrichment fields, plus `demo_url`, on a catalog that already holds 876 unenriched rows. Nothing gets enriched here. This ticket establishes the shape everything downstream writes into, and the guarantees that stop a cheap mistake from destroying work that does not regenerate.

**Six and not seven.** TRAINER.md's appendix specified `required_rom` as a triple `(joint, movement, degrees)` in a child table. It has been removed from v1: the filter needs a degree value on the catalog side that no source publishes, and a degree value on the user side that no user knows — the triage asks *«does it hurt when you press overhead? at what range?»* and a person answers *«yes, at the top»*. Two invented numbers multiplied into a safety boundary. So there is **no child table in this migration**, and exclusion works at the two granularities a person can actually report: the movement pattern, and the joint. TRAINER.md § Appendix and ROADMAP.md § Session 2 carry the full argument; it is not re-litigated here.

Two constraints decide the rest of the shape.

**The admissibility filter is a `WHERE`.** TRAINER.md rests on it — that is the stated reason the project chose SQLite over files. So the enriched values live as columns on `exercises`, never in a key/value table that would turn every query in ticket 05 into one join per field. The exception is `loaded_joints`, which is a set and has to be queryable with `NOT EXISTS` — *«the shoulder is bad, nothing that loads the shoulder»* is a real request and it is the coarse replacement for the field that went.

**Provenance is per field, not per row.** This session fills these fields two ways — a rule reading the native columns, and a decision made by reading the exercise's own `instructions` and recorded in a committed file — and how much a value can be trusted is entirely a function of which one wrote it. A rule regenerates identically on a re-vendor of the dataset; a decision does not, and must never be silently overwritten by one. A table that cannot tell them apart cannot be audited, cannot be re-run one field at a time, and cannot be scored against the reference set in ticket 03.

The vocabulary of sources is `rule` and `curated`, and it is closed. Nothing in this session calls a model or opens a socket, so there is no third value to add.

Reference: TRAINER.md § Appendix, § Persistent state; ROADMAP.md § Session 2, § Declared deviations.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A migration adds `movement_pattern`, `spinal_axial_load`, `required_stability`, `setup_cost_min`, `regression_of`, `variant_of` and `demo_url`, every one of them nullable — 876 rows already exist and none of them is enriched
- [ ] `loaded_joints` is queryable as a set: given a joint, the exercises loading it come back without parsing a string, and the exercises *not* loading it come back too
- [ ] `regression_of` and `variant_of` reference an exercise id, enforced; a value pointing at nothing is refused rather than stored
- [ ] Every enriched field records where its value came from, per field per exercise: `rule` or `curated`, and nothing else is accepted
- [ ] **A re-import leaves enrichment untouched.** `trainer db import` overwrites the native fields and nothing else, with a test for it: this failure is silent, and it would throw away the hand decisions, which unlike the rules do not regenerate
- [ ] **A rule never overwrites a curated value**, enforced where the write happens rather than in each caller
- [ ] `trainer catalog --stats` reports how much of each enriched field is filled, against the total, broken down by source
- [ ] `trainer catalog --values movement_pattern` against an unenriched catalog names that state rather than rejecting a correct value against an empty vocabulary
- [ ] `trainer db snapshot` carries the new fields, still one exercise per line, still byte-identical when nothing changed
- [ ] `demo_url` is documented as holding a link and never hosted media, and filled by hand from session 4
- [ ] No `required_rom` table, column or CLI surface is created. If a later session wants it back it adds a migration; building the empty shape now would invite something to fill it
- [ ] `movement_pattern` stays **one column**, and the limitation is written down where session 5 will read it: a thruster is a squat and an overhead press, a muscle-up is a vertical pull and a dip, and the column records only one of the two. `docs/enrichment/residue.md` names the five rows this affects and the rule that resolves them

## Comments
