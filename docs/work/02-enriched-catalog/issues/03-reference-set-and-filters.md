# 03 — Sixty movements decided by hand, and the filters that read them

**What to build:** a reference set of enrichment values for 60-80 distinct movements, decided by hand against the ticket 02 definitions; the command that scores the database against it; and the two CLI filters this session is defined by, which by the end of this ticket finally have real data to run on.

**Why by hand, and why first.** With the models gone, this is the only independent measurement in the session. The rules are one mind reading the definitions and the catalog; the reference set has to be a second reading, or it measures nothing. Its first job is to score the rules from ticket 02: that number says how much work is left for a person, and it is the first honest signal about quality anyone gets.

**Decided blind.** The values go in *before* the `enrich derive` output is looked at, on any row. A reference set built while the rules' answers are on screen is fitted to them, and every accuracy figure computed against it afterwards is inflated by an amount nobody can estimate. This is the single constraint the credibility of the whole session rests on, and it is cheap to honour and impossible to repair later.

**Why sixty to eighty.** ROADMAP.md's own note on `demo_url` puts the number of distinct exercises one person meets in eight weeks at 40-60. A reference set that size is both a measuring stick and a meaningful share of what will really get prescribed, so the hand work is not spent twice.

The sample has to span the eleven patterns and the equipment range on purpose. Sixty barbell compounds would score the rules on the easy half of the catalog and tell you nothing about the half that needs a person.

**`required_rom` and the cost of `--max-rom`.** The degrees a military press asks of the shoulder is the kind of value that reads plausibly and is wrong, and it is what session 3's exclusions will rest on. Which is why the default this ticket picks — what `--max-rom` does with an exercise that has no recorded requirement — is the largest cost decision left in the session. *Included* means only movements that genuinely constrain something need a value, and the field stays a short curated list. *Excluded* means every one of the 584 rows needs one before the filter is usable at all. Pick it deliberately, on safety grounds and not on convenience, and write the reasoning where session 3 will read it: the admissible set inherits this choice.

Reference: TRAINER.md § Glossary, § Persistent state (the exclusion `WHERE`); ROADMAP.md § Session 2, § Risks.

**Blocked by:** 01 — The seven enrichment fields; 02 — What the eleven patterns mean

**Status:** ready-for-agent

- [ ] 60-80 distinct movements, chosen to span the eleven patterns and the equipment range, every enrichment field decided by hand and recorded as `curated`
- [ ] **The decisions are made before the rules' output on those rows is read**, and the file says so — that is what makes the accuracy figure mean anything
- [ ] The decisions are reviewable as a committed file, not only as rows in a database, so a disagreement about one of them is a diff
- [ ] Where a decision was genuinely uncertain, the file says so — a reference set that hides its own soft spots overstates every accuracy figure computed against it
- [ ] `trainer enrich check` scores whatever is in the database against the reference, per field, and names the rows that disagree
- [ ] Run against the ticket 02 rules it produces the number this session needs: how often the rules get `movement_pattern` right, and where they go wrong. `movement_pattern` is scored on its own, never averaged into the others
- [ ] The choice `--max-rom` makes about an exercise with no recorded requirement is decided on safety grounds and written down where session 3 reads it, together with what it costs
- [ ] `trainer catalog --pattern hinge` filters on movement pattern, composing with every session 1 filter
- [ ] `trainer catalog --max-rom shoulder:flexion:120` excludes exercises requiring more than that at that joint and movement
- [ ] Against a catalog where nothing has a recorded range of motion, `--max-rom` names that state instead of returning an empty result
- [ ] Both filters reject a malformed argument as a malformed argument, and an unknown joint or movement with the vocabulary read from the data

## Comments
