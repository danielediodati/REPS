# 01 — Blocks, and rest that is prescribed rather than imposed

**What to build:** the rework of `engine/duration.py`, which shipped at `9e21b10` costing a flat list of `(exercise, sets, reps)` at a rest value the engine chose. Two things were wrong with it and both are decided: a plan is a sequence of **blocks** (ADR-0002), and **rest is prescribed** by whoever plans, not derived by the engine (ADR-0001).

**A block is one or more exercises, a number of rounds, and the rest after each round.** Its cost is `setup(every exercise in the block, once) + rounds × (Σ work + rest)`. Straight sets are the block holding one exercise, a superset holds two, a triset three, a circuit as many as it has — so the shipped model is a strict subset of this one and nothing downstream has to ask which kind it is looking at.

**This is not a refinement, it is a correctness fix.** Costed as two independent entries the way the shipped code does it, a superset comes out several minutes longer than it is — the rest is counted after each exercise instead of after the pair. And the number looks exactly like every other number the engine produces, which is the failure mode this project keeps naming.

**Rest stops being a function and becomes a field.** `rest_seconds(pattern, reps)` currently returns 180 / 120 / 60, taken at the top of each of TRAINER.md's three bands. That was a law where a prescription belongs: a deliberately short rest is legitimate training, and an engine that overrides it is deciding method. The three bands survive as a **reference a planner may consult** — keep them exported, keep them documented as reference, and make nothing in the costing path call them. The value used is the one on the block.

**Timed work.** A block's exercises are prescribed either in reps or in a duration — a light walk, a carry, a sled push. Reps-based work contributes `reps × 3s`; timed work contributes its declared seconds. This is what makes a warm-up expressible as part of the plan rather than as a constant subtracted from the budget, which is what the user asked for and what nothing in the engine could say before.

**What survives from the shipped version, unchanged in meaning:** `setup_cost_min` is spent once per exercise; an exercise appears at most once in a plan (`check_selection`, now over blocks); an id that is not in the catalog or not enriched is a named error and never a default; `plan_duration` reports whole minutes rounded up and `plan_seconds` the exact figure. The tests for those are in `tests/test_duration.py` and most should survive the reshape — if one does not, say which and why.

**What must not survive:** any code path where the engine picks a rest value. `simulate_cut` was never built and is not going to be — ADR-0001 — so there is nothing to delete, only a shape to avoid leaving behind that a cut could later be hung off.

Reference: TRAINER.md § Engine — analytic / derived (Duration); ADR-0001, ADR-0002; CONTEXT.md (*block*, *round*, *rest*, *timed work*); ROADMAP.md § Session 3.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] `Block` — exercises, rounds, rest — and a plan as an ordered sequence of blocks, replacing the flat `Selection` of `9e21b10`
- [ ] An exercise inside a block is prescribed either in reps or as a duration; both cost correctly and a block may mix them
- [ ] A block costs `setup(each exercise once) + rounds × (Σ work + rest)`, verified against a hand-computed superset that the shipped flat model gets wrong
- [ ] Straight sets go through the same code path as a superset, with no branch on block size
- [ ] The rest used in costing is always the block's prescribed value; no call to the reference bands exists in the costing path
- [ ] The three bands stay exported and documented as a reference for a planner, with a test asserting they hold TRAINER.md's values
- [ ] `setup_cost_min` once per exercise; an exercise appears at most once in a plan
- [ ] Unknown id and unenriched row remain distinct named errors; no default rest, no default duration
- [ ] `plan_duration` (whole minutes, rounded up) and `plan_seconds` (exact) keep their current contract
- [ ] Unit tests cover straight sets, a superset, a triset or circuit, a mixed reps/timed block, and a plan spanning several blocks — no LLM, no network
- [ ] `tests/test_engine_boundary.py` still passes

## Comments
