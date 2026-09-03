# 02 — What the eleven patterns mean, and the rules that follow from it

**What to build:** the document that defines every enrichment vocabulary precisely enough that two people applying it get the same answer, and the deterministic pass that applies it. **This ticket is most of the enrichment** — ticket 04's model only sees what this one could not decide, plus whatever it decided wrongly.

The eleven movement patterns are **this project's taxonomy, not anyone else's.** No public source labels an exercise `core anti-rotation` in the sense TRAINER.md's glossary means, and no amount of research changes that. So the definitions get written rather than looked up, and the code executes them: one document, read by a person, executed by the pass, and quoted by ticket 04's prompt. A vocabulary restated in code is a vocabulary that will drift, and here it would drift between the rules, the reference set that scores them and the model that audits them.

**How much the rules can take is already measured.** A throwaway rule set over `name`, `primary_muscles`, `force` and `mechanic` decided `movement_pattern` for 524 of the 584 strength rows. Its sixty failures were oddities — `Kettlebell Turkish Get-Up`, `Spell Caster`, `Muscle Up`, `Battling Ropes` — not a class of exercise it had no handle on, and several were plain gaps a real pass closes at once: `Barbell Deadlift`, `Weighted Pull Ups`, `Pull Through`. So 90% is the floor, not the target. One rule alone carries a third of the catalog: `mechanic = isolation` is 244 of the 584 rows.

The other fields are cheaper still, because they hang off the pattern rather than off the exercise. `loaded_joints` is a function of pattern and equipment. `spinal_axial_load` is a function of pattern, equipment and whether the load is carried standing. `required_stability` is a function of equipment, support and whether the movement is unilateral. `setup_cost_min` is largely a function of equipment. Each is one defensible judgement written once in the document, not 584 judgements — which is why a rule beats a per-row opinion here even where the judgement itself is arguable.

**The risk moved with the work.** When the run was three models voting, the danger was a vote nobody could audit. Now the vocabulary *is* the run, and a wrong boundary in this document is a wrong column across hundreds of rows. Two things catch that, and neither is in this ticket: the reference set in 03 and the model audit in 04. What this ticket owes them is a number per field — how many rows it decided, and which ones it left.

Reference: TRAINER.md § Glossary (the eleven patterns), § Appendix (the fields); ROADMAP.md § Session 2, § Risks.

**Blocked by:** 01 — The six enrichment fields

**Status:** ready-for-agent

- [ ] A document defines each of the eleven movement patterns with its boundary cases named — what separates a hinge from a squat, when a press is vertical rather than horizontal, what makes a movement anti-rotation rather than isolation, and where a loaded carry stops being one
- [ ] It defines the other five vocabularies: the seven loaded joints, what `spinal_axial_load` counts as axial, the three stability levels, what `setup_cost_min` measures and what it excludes, and when one exercise is a `regression_of` another rather than a `variant_of`
- [ ] The document lives where a person reads it, the pass executes it and ticket 04's prompt quotes it, and it is the only copy — a rule whose reason is not in the document is a rule nobody can check
- [ ] `trainer enrich derive` fills every field the rules can decide, across the catalog, recording `rule` as the source
- [ ] Running it twice changes nothing, and it never overwrites a model or curated value
- [ ] It reports coverage per field: how many rows it decided and how many it left
- [ ] **`movement_pattern` coverage on the strength rows beats 90%** — the measured floor — and the rows it leaves are listed by name, because that list is ticket 04's input
- [ ] A rule that cannot decide leaves the field null. A guess here is worse than a gap: downstream it is indistinguishable from a decision, and it would be trusted as one

## Comments
