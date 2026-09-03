# 02 — What the eleven patterns mean, and the rules that follow from it

**What to build:** the document that defines every enrichment vocabulary precisely enough that two people applying it get the same answer, and the deterministic pass that applies it. Since this session dropped the models, **this ticket is the enrichment** — everything ticket 04 does afterwards is the residue this one could not decide.

The eleven movement patterns are **this project's taxonomy, not anyone else's.** No public source labels an exercise `core anti-rotation` in the sense TRAINER.md's glossary means, and no amount of research changes that. So the definitions get written rather than looked up, and the code executes them: one document, read by a person and applied by the pass. A vocabulary restated in code is a vocabulary that will drift, and here the drift would be between the rules and the reference set that scores them.

**How much the rules can take is already measured.** A throwaway rule set over `name`, `primary_muscles`, `force` and `mechanic` decided `movement_pattern` for 524 of the 584 strength rows, and its sixty failures were oddities — `Kettlebell Turkish Get-Up`, `Spell Caster`, `Muscle Up`, `Battling Ropes` — not a class of exercise it had no handle on. Several were plain gaps a real pass closes immediately: `Barbell Deadlift`, `Weighted Pull Ups`, `Pull Through`. So 90% is the floor, not the target.

The other fields are cheaper still, because they hang off the pattern rather than off the exercise. `loaded_joints` is a function of pattern and equipment. `spinal_axial_load` is a function of pattern, equipment and whether the load is carried standing. `required_stability` is a function of equipment, support and whether the movement is unilateral. `setup_cost_min` is largely a function of equipment. Each of these is a defensible judgement expressed once in the document, not eight hundred judgements — which is why a rule beats a per-row opinion here even when the judgement itself is arguable.

**The risk moved with the work.** When the run was three models, the danger was a vote nobody could audit. Now the vocabulary *is* the run, and a wrong boundary in this document is a wrong column across hundreds of rows with nothing disagreeing. That is what ticket 03 exists to catch, and why the number this ticket owes the session is per field: how many rows it decided, and how many it left for a person.

Reference: TRAINER.md § Glossary (the eleven patterns), § Appendix (the seven fields); ROADMAP.md § Session 2, § Risks.

**Blocked by:** 01 — The seven enrichment fields

**Status:** ready-for-agent

- [ ] A document defines each of the eleven movement patterns with its boundary cases named — what separates a hinge from a squat, when a press is vertical rather than horizontal, what makes a movement anti-rotation rather than isolation, and where a loaded carry stops being one
- [ ] It defines the other six vocabularies: the seven loaded joints, what `spinal_axial_load` counts as axial, the three stability levels, what `setup_cost_min` measures and what it excludes, and when one exercise is a `regression_of` another rather than a `variant_of`
- [ ] For `required_rom` it names the joints and movements in play and the degree thresholds that matter, citing sources where normative ranges exist and saying plainly where they do not
- [ ] The document lives where a person reads it and the pass executes it, and it is the only copy — a rule whose reason is not in the document is a rule nobody can check
- [ ] `trainer enrich derive` fills every field the rules can decide, across the catalog, recording `rule` as the source
- [ ] Running it twice changes nothing, and it never overwrites a curated value
- [ ] It reports coverage per field: how many rows it decided and how many it left
- [ ] **`movement_pattern` coverage on the strength rows beats 90%** — the measured floor — and the rows it leaves are listed by name, because that list is ticket 04's input
- [ ] A rule that cannot decide leaves the field null. A guess here is worse than a gap: it is indistinguishable from a decision downstream, and it would be trusted as one

## Comments
