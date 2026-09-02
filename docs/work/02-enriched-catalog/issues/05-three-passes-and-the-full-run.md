# 05 — Three passes, measured before they are paid for

**What to build:** the job that actually fills the catalog. Two cheap models from different providers, the strong one called only where they disagree, majority vote. Scored against the ticket 03 reference set **before** it is turned loose, then run over what the rules could not decide, resumably.

**Two providers and not two models from one house.** Models from the same family fail together, so agreement between them means less than it looks — and agreement is the entire signal this design is built to produce. Which two is decided by the keys that exist; ticket 04 leaves that open on purpose.

**Disagreement is the product, not the waste.** Where the three passes do not converge, the row is unreliable and gets marked as such. That list is what tells you which rows to look at, instead of sampling fifty at random and hoping.

**Scope: the 584 rows of `category: strength`,** minus whatever the ticket 02 rules already decided. ROADMAP.md calls that count the multiplier on this session's cost, and no honest value among the eleven patterns exists for a hamstring stretch. The other 292 keep their nulls, and ticket 01 makes that state readable rather than mysterious.

The field to watch is `movement_pattern`. Get it wrong there and every downstream volume count is wrong without anyone noticing, which is why it is scored separately and why ticket 03 exists at all.

Reference: TRAINER.md § Appendix (three passes, majority vote); ROADMAP.md § Session 2, § Risks.

**Blocked by:** 03 — Sixty movements decided by hand; 04 — One exercise through a model

**Status:** ready-for-agent

- [ ] Two cheap models from different providers, the strong one called only on disagreement, and the majority vote recorded as the source of the value
- [ ] Accuracy per field against the ticket 03 reference set is reported **before** the full run, and the run is a deliberate decision taken with that number in hand
- [ ] The full run covers the strength rows the rules left undecided, and states its scope and its cost when it finishes
- [ ] It is resumable: interrupted at any point, rerunning continues rather than restarting, and never pays twice for the same row
- [ ] It never overwrites a curated value
- [ ] A report lists the residual disagreements per field, with the rows named, so the follow-up is a reading list and not a search
- [ ] `trainer catalog --stats` afterwards says what enrichment produced: how much of each field is filled, and by which source
- [ ] `trainer catalog --pattern hinge --max-rom shoulder:flexion:120` answers over the enriched catalog — the command this session is defined by
- [ ] The resulting numbers are recorded where they outlive this ticket

## Comments
