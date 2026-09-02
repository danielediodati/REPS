# 02 — What the eleven patterns mean, and the rules that follow from it

**What to build:** the document that defines every enrichment vocabulary precisely enough that two people applying it get the same answer, and the deterministic pass that applies the part of it the catalog already decides.

The eleven movement patterns are **this project's taxonomy, not anyone else's.** No public source labels an exercise `core anti-rotation` in the sense TRAINER.md's glossary means, and no amount of research changes that. So the definitions get written rather than looked up, and everything downstream reads them: ticket 03 applies them by hand, ticket 04's prompt quotes them, and the rules here encode the part that needs no judgement at all.

Then the rules. A good share of the seven fields is already implied by columns the catalog holds. `spinal_axial_load` follows from equipment and pattern — a barbell back squat loads the spine axially, a leg press does not. `setup_cost_min` is largely a function of equipment. `movement_pattern` itself falls out of `force`, `mechanic` and `primary_muscles` for a large fraction of the catalog. **Whatever a rule can decide is never bought from a model:** rules are auditable, free, and regenerate identically when the dataset is re-vendored, which is three properties a majority vote does not have.

The number this ticket owes the session is how much is left over. That is what ticket 05 is going to pay for.

Reference: TRAINER.md § Glossary (the eleven patterns), § Appendix (the seven fields).

**Blocked by:** 01 — The seven enrichment fields

**Status:** ready-for-agent

- [ ] A document defines each of the eleven movement patterns with its boundary cases named — what separates a hinge from a squat, when a press is vertical rather than horizontal, what makes a movement anti-rotation rather than isolation
- [ ] It defines the other six vocabularies: the seven loaded joints, what `spinal_axial_load` counts as axial, the three stability levels, what `setup_cost_min` measures and what it excludes, and when one exercise is a `regression_of` another rather than a `variant_of`
- [ ] For `required_rom` it names the joints and movements in play and the degree thresholds that matter, citing sources where normative ranges exist and saying plainly where they do not
- [ ] The document lives where both a person and a prompt can read it, and it is the only copy — a vocabulary restated in code is a vocabulary that will drift
- [ ] `trainer enrich derive` fills every field the rules can decide, across the catalog, recording the rule as the source
- [ ] Running it twice changes nothing, and it never overwrites a value written by hand or by a vote
- [ ] It reports coverage per field: how many rows it decided and how many it left for a model
- [ ] A rule that cannot decide leaves the field null. A guess here would be indistinguishable from enrichment downstream, and would be trusted more than it deserves

## Comments
