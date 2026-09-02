# 03 — Sixty movements decided by hand, and the filters that read them

**What to build:** a reference set of enrichment values for 60-80 distinct movements, decided by hand against the ticket 02 definitions; the command that scores anything else in the database against it; and the two CLI filters this session is defined by, which by the end of this ticket finally have real data to run on.

**Why by hand, and why first.** The original plan for this session measured enrichment quality only after the full run — that is, after the one external spend in the project had already happened. The reference set moves the measurement in front of the money. Its first job is to score the rules from ticket 02: that number says how much work is actually left for a model, and it is the first honest signal about quality anyone gets.

**Why sixty to eighty.** ROADMAP.md's own note on `demo_url` puts the number of distinct exercises one person meets in eight weeks at 40-60. A reference set that size is both a measuring stick and a meaningful share of what will really get prescribed, so the hand work is not spent twice.

`required_rom` is filled here with real research. The degrees a military press asks of the shoulder is exactly the kind of value a model returns plausibly and wrong, and it is the field session 3's exclusions will rest on.

The sample has to span the eleven patterns and the equipment range on purpose. Sixty barbell compounds would score the rules on the easy half of the catalog and tell you nothing about the half that needs a model.

Reference: TRAINER.md § Glossary, § Persistent state (the exclusion `WHERE`); ROADMAP.md § Session 2.

**Blocked by:** 01 — The seven enrichment fields; 02 — What the eleven patterns mean

**Status:** ready-for-agent

- [ ] 60-80 distinct movements, chosen to span the eleven patterns and the equipment range, every enrichment field decided by hand and recorded as curated
- [ ] The decisions are reviewable as a committed file, not only as rows in a database, so a disagreement about one of them is a diff
- [ ] Where a decision was genuinely uncertain, the file says so — a reference set that hides its own soft spots overstates every accuracy figure computed against it
- [ ] `trainer enrich check` scores whatever is in the database against the reference, per field, and names the rows that disagree
- [ ] Run against the ticket 02 rules it produces the number this session needs: how often the rules get `movement_pattern` right, and where they go wrong
- [ ] `trainer catalog --pattern hinge` filters on movement pattern, composing with every session 1 filter
- [ ] `trainer catalog --max-rom shoulder:flexion:120` excludes exercises requiring more than that at that joint and movement
- [ ] `--max-rom` **states what it does with an exercise that has no recorded requirement** — included or excluded — and the reasoning is written where session 3 will read it, because the admissible set inherits this choice and it is a safety boundary, not a convenience
- [ ] Against a catalog where nothing has a recorded range of motion, `--max-rom` names that state instead of returning an empty result
- [ ] Both filters reject a malformed argument as a malformed argument, and an unknown joint or movement with the vocabulary read from the data

## Comments
