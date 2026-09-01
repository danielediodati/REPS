# 05 — `trainer catalog stats`: what is actually in the catalog

**What to build:** a command that reports what the catalog actually contains, so the session ends with a number instead of a list.

"~800 exercises" is the headline, but `category` includes stretching, cardio, plyometrics, powerlifting and strongman — so the count of things that are actually strength work is smaller and currently unknown. That number matters twice over: it is the real size of the pool the admissible set will be drawn from, and it is the multiplier on session 2's enrichment, which is the only step in the project with a real external cost.

The same command stays useful after session 2: rerun it against the enriched catalog and the aggregates say what enrichment produced.

Reference: ROADMAP.md § Session 2 (the enrichment cost), TRAINER.md § Appendix.

**Blocked by:** 02 — Import the free-exercise-db catalog

**Status:** ready-for-agent

- [ ] The command reports counts broken down by `category`, `equipment`, `level`, `mechanic` and `force`
- [ ] It reports how many records have a null `force` and a null `mechanic` — the fields the appendix already judges insufficient, so their coverage is worth knowing before relying on them
- [ ] It reports how many records are `category: strength` against everything else
- [ ] The aggregates are computed by the engine library; the CLI only formats them
- [ ] Totals reconcile: every breakdown sums to the total row count, nulls included
- [ ] The resulting numbers are recorded in this ticket's Comments when it closes

## Comments
