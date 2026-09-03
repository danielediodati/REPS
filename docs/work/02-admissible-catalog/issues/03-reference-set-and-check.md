# 03 — Sixty movements decided by hand, and the command that scores everything against them

**What to build:** a reference set of enrichment values for 60-80 distinct movements, decided by hand against the ticket 02 definitions; `trainer enrich check`, which scores whatever is in the database against it; and `trainer catalog --pattern`, the first filter that reads an enriched field.

**Why by hand, and why before ticket 04.** This is the only independent measurement in the session. The rules read the columns; ticket 04 reads the prose; the reference set is what says which of them is right where they disagree. Without it, ticket 04 produces a pile of disagreements and no way to adjudicate them.

**Decided blind.** The values go in *before* the `enrich derive` output is looked at, on any row. A reference set built while the rules' answers are on screen is fitted to them, and every accuracy figure computed against it afterwards is inflated by an amount nobody can estimate. This is the single constraint the credibility of the whole session rests on. It is cheap to honour and impossible to repair later.

**Why sixty to eighty.** ROADMAP.md's note on `demo_url` puts the number of distinct exercises one person meets in eight weeks at 40-60. A reference set that size is both a measuring stick and a meaningful share of what will really get prescribed, so the hand work is not spent twice.

The sample has to span the eleven patterns and the equipment range on purpose. Sixty barbell compounds would score the rules on the easy half of the catalog and say nothing about the half that has to be read.

**No `--max-rom`.** The session originally shipped `trainer catalog --max-rom shoulder:flexion:120` alongside `--pattern`, and with it a decision about what to do with an exercise having no recorded requirement. `required_rom` was removed from v1 — TRAINER.md § Appendix carries why — so neither the filter nor the decision exists. `--pattern` is the whole of the new filtering surface here; the joint-level exclusion lands in ticket 05, where it belongs, as part of the admissible set rather than as a catalog filter.

Reference: TRAINER.md § Glossary, § Persistent state; ROADMAP.md § Session 2, § Risks.

**Blocked by:** 01 — The six enrichment fields; 02 — What the eleven patterns mean

**Status:** ready-for-agent

- [ ] 60-80 distinct movements, chosen to span the eleven patterns and the equipment range, every enrichment field decided by hand and recorded as `curated`
- [ ] **The decisions are made before the rules' output on those rows is read**, and the file says so — that is what makes every accuracy figure in this session mean anything
- [ ] The decisions are reviewable as a committed file, not only as rows in a database, so a disagreement about one of them is a diff
- [ ] Where a decision was genuinely uncertain, the file says so — a reference set that hides its own soft spots overstates every figure computed against it
- [ ] `trainer enrich check` scores whatever is in the database against the reference, per field, and names the rows that disagree
- [ ] Run against the ticket 02 rules it produces the number this session needs: how often the rules get `movement_pattern` right, and where they go wrong. `movement_pattern` is scored on its own, never averaged into the others
- [ ] The same command is what ticket 04 is judged by, so its output has to be readable as a before/after and not only as a snapshot
- [ ] `trainer catalog --pattern hinge` filters on movement pattern, composing with every session 1 filter
- [ ] Against an unenriched catalog `--pattern` names that state instead of rejecting a correct value against an empty vocabulary
- [ ] It rejects a malformed argument as malformed, and an unknown pattern with the vocabulary read from the data

## Comments
