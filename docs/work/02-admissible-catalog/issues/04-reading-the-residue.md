# 04 — The rows the columns cannot answer, read from the instructions

**What to build:** the end of the catalog. The rows ticket 02 left null get decided by reading the exercise's own `instructions`, a spot-check goes back over what the rules claimed, the `variant_of` / `regression_of` graph gets built, and all of it lands in a committed file with the evidence beside each value.

**Why these rows resist a rule, and what does answer them.** `Spell Caster` is `abdominals / pull / compound / dumbbell`, and its name says nothing at all. Its own instructions say: *«pull both of the dumbbells to one side next to your hip, rotating your torso... rotate your torso to swing the weights to the opposite side»*. That is trunk rotation, and it takes one reading. `Cocoons` says *«tuck the knees toward your chest, rotating your pelvis... flex the spine, bringing your arms back over your head»* — spinal flexion. **The catalog describes every movement in prose, and no rule can read prose.** The residue is not a hard problem, it is a different kind of problem: fifty rows that need reading rather than matching.

**Each decision quotes the sentence it rests on.** This is the acceptance criterion that matters most, and it is what makes this ticket better than any pipeline that could have bought the same labels. A value with the line that produced it is checkable a year later by someone who was not here, in seconds, without opening the source data. A label on its own has to be taken on trust or redone from scratch.

**The spot-check is the second half.** The rules decided 90% by looking at `force`, `mechanic` and `primary_muscles`. Reading a sample of those rows' instructions is a genuinely independent second look — prose against columns — and it is the only thing in the session that can catch a rule that is confidently and uniformly wrong. Ticket 03's reference set catches that too, on the rows it covers; this catches it on rows it does not. Where the reading disagrees with the rule, the row is named and the rule in ticket 02's document is the thing that gets fixed, not the row.

**Where honesty has to be.** These decisions have one reader and no second opinion behind them. An uncertain one is marked uncertain rather than smoothed over, and a row with no honest answer among the eleven patterns keeps its null — `Battling Ropes` may well be one of those, and a null is a state ticket 01 made readable. A wrong pattern is a volume count that stays wrong forever without anyone noticing.

**The 292 non-strength rows keep their nulls.** No honest value among the eleven patterns exists for a hamstring stretch.

**If the session overruns, the graph is the cut.** ROADMAP.md § Risks names it: `variant_of` / `regression_of` has no consumer until substitution in session 4, and it slides there intact. The residue does not slide — ticket 05 needs a `movement_pattern` on every strength row.

Reference: TRAINER.md § Appendix (the enrichment procedure), § Glossary; ROADMAP.md § Session 2, § Risks.

**Most of this ticket is already written.** `docs/enrichment/residue.md` holds all 60 rows decided, each with the sentence from its own instructions, 21 marked uncertain, 2 left null and the six boundary rules the reading forced. What is left here is to re-run it against the *real* rules rather than the throwaway ones — the residue will be smaller, because plain gaps like `Barbell Deadlift` and `Weighted Pull Ups` will have been caught by a rule — to reconcile it with whatever ticket 02's document decided about B1-B6, to load it into the database with `curated` provenance, and to do the spot-check and the graph.

**Blocked by:** 02 — What the eleven patterns mean; 03 — Sixty movements decided by hand

**Status:** ready-for-agent

- [ ] Every strength row the rules left undecided is either decided against the ticket 02 definitions and recorded as `curated`, or left null on purpose with the reason written down
- [ ] `docs/enrichment/residue.md` is reconciled against the real `enrich derive` output and against ticket 02's ruling on B1-B6: rows that a rule now reaches leave the file, rows a boundary ruling changed are re-decided, and the file says which
- [ ] **Every decision quotes the sentence from the exercise's `instructions` that produced it.** A value with no citation does not go in the file
- [ ] The decisions live in a committed file in the same form as the ticket 03 reference set, so the two are read and diffed the same way
- [ ] An uncertain decision is marked uncertain — one reader, no second opinion, and pretending otherwise is what makes a bad value permanent
- [ ] **The spot-check**: a sample of the rows the rules *did* decide is read against their instructions, and every disagreement is named. A disagreement is a bug in ticket 02's document first and in the row second
- [ ] `trainer enrich check` against the ticket 03 reference set is run **before and after**, so the session can say what this ticket changed and whether it changed it for the better
- [ ] `variant_of` groups the rows that are the same movement across equipment, one representative per group rather than a chain; `regression_of` points from easier to harder, in one direction, and a cycle is refused
- [ ] `Arnold Dumbbell Press`, `Standing Military Press` and the two Arnold rows resolve the way TRAINER.md's running example says they do, with a test naming those ids
- [ ] The 292 non-strength rows are untouched, and `--stats` shows that as a state rather than as a gap
- [ ] Nothing in this ticket opens a socket or calls a model, and the suite still passes with no network and no credentials
- [ ] The final numbers — coverage per field, per source, and accuracy against the reference set — are recorded where they outlive this ticket

## Comments
