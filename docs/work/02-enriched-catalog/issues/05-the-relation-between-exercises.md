# 05 — `regression_of` and `variant_of`: the two fields that are not fields

**What to build:** the relation between exercises. `variant_of` groups the rows that are the same movement, `regression_of` points at the easier version of one, and both are edges rather than values.

**Neither slicing of this session ever produced them.** The original design enriched one exercise at a time — a prompt, a typed output, one row — and a per-row pass cannot see that `Arnold Dumbbell Press` and `Standing Military Press` are the same movement, because the fact is not in either row. The replacement is a rule pass over columns, and it cannot either. So this was a hole in the appendix's coverage under both plans, and it gets its own ticket rather than a footnote.

**It is worth its slot because TRAINER.md's running example is nothing else.** *«The Arnold and the military press are the same pattern, to the engine they are interchangeable»* is the sentence the whole substitution story rests on, and `movement_pattern` alone does not carry it: `vertical push` holds forty rows, and they are not interchangeable with each other. The Arnold itself exists twice in the catalog, dumbbell and kettlebell, which is the smallest instance of the problem — two ids, one movement. Session 5's agent picks an exercise, session 6 counts volume on what was performed, and session 10 holds every variable fixed but one. All three need to know when two ids are the same thing.

**Scope, deliberately small.** This is not a complete graph over 584 rows. It is the clusters that a name and an equipment column make obvious — the same movement across dumbbell, barbell, kettlebell, cable and machine — plus the regressions that matter for a return from a break: knee push-up before push-up, assisted before unassisted, box squat before squat. What cannot be decided stays null, and a null here costs nothing until session 5.

**A cycle is a bug, not a taxonomy.** `regression_of` is a direction: if A is a regression of B, B is not a regression of A, and no chain returns to where it started. `variant_of` groups, so it wants one representative per group rather than a chain of pairs. Ticket 01 already refuses an id that points at nothing; this ticket is where the shape of the pointing gets decided.

Reference: TRAINER.md § Appendix (the seven fields), § Glossary (movement pattern); ROADMAP.md § Session 2.

**Blocked by:** 02 — What the eleven patterns mean; 04 — The rows no rule could decide

**Status:** ready-for-agent

- [ ] `variant_of` groups the rows that are the same movement across equipment, with one representative per group rather than a chain
- [ ] `regression_of` points from the easier version to the harder one, in one direction, and a cycle is refused rather than stored
- [ ] The relation is decided from the ticket 02 definition of when one exercise is a variant rather than a regression, and disagreements with it are a diff on the same committed file the other hand work uses
- [ ] `Arnold Dumbbell Press`, `Standing Military Press` and the two Arnold rows resolve the way TRAINER.md's running example says they do, with a test naming those ids
- [ ] A query can go from one exercise to every id that is the same movement, in one step, because that is what session 5 will ask
- [ ] What cannot be decided stays null, and `--stats` says how much of the catalog is in a group and how much is not
- [ ] `trainer db snapshot` carries the relation without turning one exercise into more than one line

## Comments
