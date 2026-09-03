# 04 — The model reads the instructions: the residue, the audit, and the graph

**What to build:** the first model in the project. It does three things the rules cannot, in one pass: it decides the rows they left null, it re-decides the rows they filled so the two can be compared, and it builds the `variant_of` / `regression_of` graph.

**Why a model at all, once the rules take 90%.** Because of what the leftovers look like. `Spell Caster` is `abdominals / pull / compound / dumbbell` and its name says nothing whatsoever — but its own `instructions` column says *«pull both dumbbells to one side, rotating your torso... rotate your torso to swing the weights to the opposite side»*. That is a rotation, and it takes three seconds to see. `Cocoons`: *«tuck the knees toward your chest, rotating your pelvis... flex the spine, bringing your arms back over your head»* — spinal flexion. **The catalog describes every movement in prose, and no rule can read prose.** That is the model's job here, and it is a job it is good at, unlike the one the original three-pass design gave it: guessing a range of motion in degrees.

**The audit is the second half, and it is the part that replaces the vote.** Running the model over the rows the rules already decided costs the same call and produces the signal the three-pass design was trying to buy: *which rows are unreliable*. But rule-versus-model is a sharper instrument than two cheap models of the same generation voting, because the two readings are genuinely independent — one over `force`, `mechanic` and `primary_muscles`, the other over a paragraph of English. Where they agree, the row is settled twice over. Where they disagree, the row goes on a list, and the ticket 03 reference set says who was right on the part of the list it covers.

**Validation is not politeness.** A model returning `hip_hinge` when the vocabulary says `hip hinge`, or inventing a twelfth pattern, has produced a value that fails silently where session 5 counts volume on a pattern. Anything that does not validate is rejected whole: a partially written row is worse than an empty one, because it looks enriched. The prompt quotes the ticket 02 document rather than restating it — one document governs the rules, the humans and the model, or they drift apart with nobody noticing.

**This is where the network enters the project.** The engine is a pure library by construction — no LLM, no network, no knowledge of any client — and a test enforces it rather than trusting the convention. So this ticket decides where the calling code lives, and how a suite that runs with no network and no credentials (both are removed in `conftest.py`) goes on testing it.

**`demo_url` is never in the output.** Asked for a video link a model returns a well-formed dead one, and ROADMAP.md assigns that field to human curation for exactly this reason.

**If the session overruns, the graph is the cut.** ROADMAP.md § Risks names it: `variant_of` / `regression_of` has no consumer until substitution in session 4, and it slides there intact. The residue and the audit do not slide — ticket 05 needs a `movement_pattern` on every strength row.

Reference: TRAINER.md § Appendix (the enrichment procedure), README § Layout (the engine boundary); ROADMAP.md § Session 2, § Risks, § Declared deviations.

**Blocked by:** 02 — What the eleven patterns mean; 03 — Sixty movements decided by hand

**Status:** ready-for-agent

- [ ] `trainer enrich model --id <id>` prints what the model returned for one exercise and writes nothing — the smallest path, testable before anything runs in batch
- [ ] The exercise's `instructions` are in the prompt. That is the whole reason the model is here, and a prompt built from the name alone would be a worse rule
- [ ] The output is typed and validated: `movement_pattern` one of the eleven, `loaded_joints` a subset of the seven, `required_stability` one of three, `setup_cost_min` a number. Anything that does not validate is rejected whole and reported as a rejection, never partially stored
- [ ] The prompt quotes the ticket 02 definitions rather than restating them
- [ ] `demo_url` cannot appear in the output
- [ ] The batch run fills every strength row the rules left null, recording `model` as the source, and is **resumable**: interrupted at any point, rerunning continues rather than restarting
- [ ] It never overwrites a curated value, and it records rather than overwrites where it disagrees with a rule
- [ ] **The audit**: run over the rows the rules decided, it produces the list of disagreements per field, with the rows named. That list is the confidence map over the whole catalog, and it is the deliverable, not a by-product
- [ ] `trainer enrich check` against the ticket 03 reference set is run **before and after**, so the session can say what the model changed and whether it changed it for the better
- [ ] `variant_of` groups the rows that are the same movement across equipment, one representative per group rather than a chain; `regression_of` points from easier to harder, in one direction, and a cycle is refused
- [ ] `Arnold Dumbbell Press`, `Standing Military Press` and the two Arnold rows resolve the way TRAINER.md's running example says they do, with a test naming those ids
- [ ] The model-calling code lives outside `engine/`, and the boundary test that enforces engine purity covers the new package too rather than only the old one
- [ ] The suite still passes with no network and no credentials; a test that needs a model response uses a recorded one
- [ ] Nothing binds the code to a single provider's SDK
- [ ] The final numbers — coverage per field, per source, rule-versus-model agreement, and accuracy against the reference set — are recorded where they outlive this ticket

## Comments
