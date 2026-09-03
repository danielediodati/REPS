# 02 — What gets cut when it doesn't fit

**What to build:** `remaining_budget(connection, partial_selection, budget)`, which is `plan_duration` turned around — how many minutes are left once a partial selection is already committed — and `simulate_cut(connection, selection, minutes)`, which trims a selection that overflows `minutes` until it fits, always in the same order: **isolation → secondary patterns → sets on the primaries**. Never anything else, never a different order.

**The order is the whole point, and TRAINER.md fixes it for a reason.** Cutting isolation work first costs the least of the plan's actual training effect; cutting sets on a primary lift last protects the one thing a workout exists to progress. An agent that could choose its own cut order could quietly protect its favourite exercise instead of the plan's actual priority — this is one of the boundaries session 4's agent is not allowed to move, the same way it cannot see outside `admissible_set`.

**`simulate_cut` needs to know which patterns are primary, and ticket 01 does not carry that.** `Selection`/`SelectionItem` from ticket 01 has no opinion about which pattern a given workout is built around — that is a per-workout call nobody but the caller (session 4's agent, later) can make. Extend `SelectionItem` with a `role` of `primary` or `secondary`, decided by whoever builds the selection, not derived here. This ticket does not invent a rule for *which* patterns are primary on a given day — it only respects whatever the caller already declared.

**The cut stops as soon as it fits — it does not over-cut looking for margin.** After each step, recompute with `plan_duration` and check against `minutes`; the moment it fits, stop. Isolation items are dropped whole, one at a time, in the order they appear in the selection; once isolation is exhausted, secondary-pattern items are dropped whole, one at a time; once those are exhausted, sets are removed one at a time from primary items, cheapest reduction first — never dropping a primary item outright while it still has sets left, since removing it entirely would drop the pattern's volume to zero rather than reduce it.

**`remaining_budget` is not `simulate_cut` in miniature — it answers a different question.** `remaining_budget` tells the caller how much room is left before anything is decided about a cut; `simulate_cut` is what runs once the caller already knows the answer is negative. Building the selection incrementally (session 4's agent adding one exercise at a time) needs the first; fitting a finished, over-length selection needs the second.

**What comes back describes the cut, not just the surviving selection.** A caller — and eventually the user, reading *«dropped: ab-wheel rollout, cable chop; reduced: bench press to 3 sets»* — needs to see what left and why, not just infer it by diffing two lists. Return the trimmed selection alongside what was removed, tagged with which stage removed it.

Reference: TRAINER.md § Engine — analytic / derived (Duration: *«the cut order is... never the rest periods»*), § The tool surface; ROADMAP.md § Session 3.

**Blocked by:** 01 — How long does this actually take

**Status:** ready-for-agent

- [ ] `SelectionItem` carries a `role` of `primary` or `secondary`, set by the caller
- [ ] `remaining_budget(connection, partial_selection, budget)` returns `budget - plan_duration(connection, partial_selection)`, negative when already over
- [ ] `simulate_cut(connection, selection, minutes)` returns a selection that fits `minutes` (or the smallest it can reach, if even every primary reduced to one set does not fit) plus a record of what was removed and at which stage
- [ ] Cut order is exactly isolation items whole, then secondary-pattern items whole, then sets removed one at a time from primary items — verified with a selection that has all three kinds present
- [ ] A selection already inside the budget is returned unchanged, with nothing removed
- [ ] A primary item is never dropped outright while any of its sets remain
- [ ] Unit tests exercise each stage in isolation and the full order together, with no LLM and no network
- [ ] `tests/test_engine_boundary.py` still passes

## Comments

**From ticket 01 — two things about the number this ticket spends.**

`duration` exposes the total twice. `plan_duration` returns **whole minutes, rounded up**, which is what a budget is spoken in and what `remaining_budget` and the "does it fit" check should both use — rounding up is deliberate, so a selection can never be reported as fitting when it does not. `plan_seconds` returns the exact figure. Use `plan_seconds` for *«cheapest reduction first»* when choosing between primary items: two candidate cuts thirty seconds apart are the same number of minutes, and comparing the rounded value would make that choice arbitrary.

**An exercise appears at most once in a selection**, enforced by `duration.check_selection` and raised as a `DurationError`. A workout has one line per exercise: three sets of five and two of twelve on the same bar is one entry whose sets differ, not two entries. This ticket's cut has to preserve the invariant — dropping items and removing sets both do, but call `check_selection` on whatever is returned rather than assuming it. It is also what makes `setup_cost_min` unambiguous: once per item and once per exercise are the same sentence, so removing an item always removes its setup and the total is monotone, which this ticket's stop condition relies on.
