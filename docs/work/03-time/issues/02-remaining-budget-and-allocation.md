# 02 — What is left, and how the minutes are divided

**What to build:** `remaining_budget(connection, partial_plan, budget)` and `allocate(minutes, proportions)`. Both are arithmetic. Neither decides anything about how to train — see ADR-0001, which is the reason this ticket no longer contains `simulate_cut`.

**`remaining_budget` is the primitive the whole approach rests on.** A plan is built against a budget rather than trimmed to one, which only works if whoever is building it can ask *how much room is left* before committing the next block, not after. `budget - plan_duration(connection, partial_plan)`, negative when already over, in whole minutes because that is what a budget is spoken in. It is the single most-called tool in session 4's loop.

**`allocate` divides a workout's minutes among the muscle groups it trains, on proportions it is handed.** `allocate(40, {"chest": 0.6, "arms": 0.4})` is arithmetic; that today is 60-40 and not 70-30 is a decision, and a workout holding three groups makes the pair meaningless anyway. So the function takes arbitrary proportions over any number of groups and never carries a table of its own. Proportions that do not sum to 1 are an error, not something silently normalised — a caller who typed 0.6 and 0.3 meant something and should be told they lost ten percent of the workout.

**There is no cut, and this ticket must not grow one back.** A plan that does not fit is **rejected** by session 4's validator. The old cut order — isolation → secondary patterns → sets on the primaries — is gone along with its `role` field on the plan's items: it existed only to tell the cut what to protect, and nothing else ever read it. TRAINER.md is already corrected; ADR-0001 carries why.

**Rounding, in one direction.** `remaining_budget` uses `plan_duration`, which rounds minutes **up**, so the room reported is never more than the room there is. `allocate` splits whole minutes and the remainder from rounding has to go somewhere — give it to the largest proportion and say so, rather than leaving a minute unassigned or handing the caller fractions.

Reference: TRAINER.md § Engine — analytic / derived, § The tool surface; ADR-0001; CONTEXT.md (*allocation*, *muscle group*); ROADMAP.md § Session 3.

**Blocked by:** 01 — Blocks, and rest that is prescribed rather than imposed

**Status:** ready-for-agent

- [ ] `remaining_budget(connection, partial_plan, budget)` returns `budget - plan_duration(...)` in whole minutes, negative when already over
- [ ] An empty partial plan returns the whole budget; a plan that exactly fills it returns 0
- [ ] `allocate(minutes, proportions)` divides whole minutes over any number of groups, on the proportions given
- [ ] Proportions that do not sum to 1 are a named error, never silently normalised
- [ ] The rounding remainder is assigned deterministically and the allocated minutes always sum to the input
- [ ] Neither function contains a cut, a fallback, or a proportion of its own
- [ ] Unit tests for two groups, three groups, and a single group — no LLM, no network
- [ ] `tests/test_engine_boundary.py` still passes

## Comments
