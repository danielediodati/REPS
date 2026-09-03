# 04 — The rows no rule could decide, and the ranges of motion that matter

**What to build:** the end of the catalog. The rows ticket 02 left null get decided by hand, `required_rom` gets filled on the movements that actually constrain something, and both land in a committed file rather than only in the database.

**This is the ticket that replaced the models.** The original session bought this residue from two cheap models with a majority vote. The measurement in ROADMAP.md § Session 2 is what removed them: the rules take at least 90% of `movement_pattern`, and the rows they leave are `Kettlebell Turkish Get-Up`, `Spell Caster`, `Cocoons`, `Battling Ropes`, `Landmine 180's` — exactly the rows on which a cheap model is least reliable and a person reading the instructions is most. The residue is under fifty rows. Deciding it by hand is less work than the machinery for buying it would have been, and the output is reviewable.

**Reviewable is the whole point.** A vote is a number nobody can rejoin an argument with. A file is a diff: the user can read fifty decisions in the vocabulary of the ticket 02 document, disagree with six of them, and the disagreement is a line. That is the human in the loop the vote was standing in for, and in a single-user project where the user is the domain expert, it is the stronger of the two.

**Where the honesty has to be.** These decisions are made by one reader with no second opinion behind them. So an uncertain one is marked uncertain rather than smoothed over, and a row that genuinely has no honest answer among the eleven patterns keeps its null. `Battling Ropes` may be one of those. A null is a state ticket 01 made readable; a wrong pattern is a volume count that is wrong forever without anyone noticing.

**`required_rom` follows the ticket 03 decision.** If `--max-rom` includes exercises with no recorded requirement, this ticket fills the movements that actually constrain a joint — overhead flexion, deep knee and hip flexion, shoulder extension under load — and stops. If it excludes them, the scope is every strength row and this ticket is the largest in the session. Ticket 03 makes that call; this one executes it and states which it executed.

**The 292 non-strength rows keep their nulls.** No honest value among the eleven patterns exists for a hamstring stretch, and ticket 01 makes that state readable rather than mysterious.

Reference: TRAINER.md § Glossary, § Appendix; ROADMAP.md § Session 2 (why the models were removed), § Declared deviations (`demo_url` is not filled here either).

**Blocked by:** 02 — What the eleven patterns mean; 03 — Sixty movements decided by hand

**Status:** ready-for-agent

- [ ] Every strength row the rules left undecided is either decided by hand and recorded as `curated`, or left null on purpose with the reason written down
- [ ] The decisions live in a committed file in the same form as the ticket 03 reference set, so the two are read and diffed the same way
- [ ] An uncertain decision is marked as uncertain in the file — one reader, no second opinion, and pretending otherwise is what makes a bad value permanent
- [ ] `required_rom` is filled to the scope ticket 03's `--max-rom` decision requires, and the ticket states which scope that was
- [ ] The 292 non-strength rows are untouched, and `--stats` shows that as a state rather than as a gap
- [ ] `trainer enrich check` against the ticket 03 reference set still passes: this ticket never edits a reference value to agree with itself
- [ ] `trainer catalog --stats` reports the finished coverage per field and per source
- [ ] `trainer catalog --pattern hinge --max-rom shoulder:flexion:120` answers over the enriched catalog — the command this session is defined by
- [ ] The final numbers — coverage per field, rule against curated, the rules' accuracy on `movement_pattern` — are recorded where they outlive this ticket

## Comments
