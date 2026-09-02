# 04 — One exercise through a model, and nothing that does not validate

**What to build:** the smallest complete path from an unenriched exercise to a validated set of enrichment values. A prompt that quotes the ticket 02 definitions, a typed output, and a whole-hearted rejection of anything that does not fit the vocabularies. One model, one exercise, nothing written to the database.

**This is the ticket that brings a network and a model into the project for the first time.** The engine is a pure library by construction — no LLM, no network, no knowledge of any client — and a test enforces that rather than trusting the convention. So this ticket decides where the calling code lives, and how a suite that runs with no network and no credentials (both are removed in `conftest.py`) goes on testing it.

Validation is not politeness. A model that returns `hip_hinge` when the vocabulary says `hip hinge`, or invents a twelfth pattern, has produced a value that will fail silently at the point where session 3 counts volume on a pattern. Anything that does not validate is rejected whole: a partially written row is worse than an empty one, because it looks enriched.

`demo_url` is never in the output. Asked for a video link a model returns a well-formed dead one — the plausible-and-wrong failure at its most silent — and ROADMAP.md already assigns that field to human curation for exactly this reason.

Reference: TRAINER.md § Appendix (the enrichment procedure), README § Layout (the engine boundary); ROADMAP.md § Declared deviations.

**Blocked by:** 01 — The seven enrichment fields; 02 — What the eleven patterns mean; 03 — Sixty movements decided by hand

**Status:** ready-for-agent

- [ ] `trainer enrich one --id <id>` prints what a model returned for one exercise, and writes nothing
- [ ] The output is typed and validated: `movement_pattern` one of the eleven, `loaded_joints` a subset of the seven, `required_stability` one of three, `setup_cost_min` a number, `required_rom` a list of well-formed triples
- [ ] Anything that does not validate is rejected whole and reported as a rejection, never partially stored
- [ ] The prompt quotes the ticket 02 definitions rather than restating them — one document governs the humans and the model, or the two will drift apart without anyone noticing
- [ ] `demo_url` cannot appear in the output
- [ ] The model-calling code lives outside `engine/`, and the boundary test that enforces engine purity covers the new package too rather than only the old one
- [ ] The suite still passes with no network and no credentials; a test that needs a model response uses a recorded one
- [ ] Nothing binds the code to a single provider's SDK — ticket 05 needs two, and which two depends on the keys that exist
- [ ] Run over the ticket 03 reference set, it reports how often one model alone agrees with the hand-decided values. That number is what says whether three passes are worth their cost

## Comments
