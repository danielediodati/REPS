# 03 — The rest period is not a knob

**What to build:** the test suite that holds ticket 02's one non-negotiable property — on every branch of `simulate_cut`, the rest value attached to every surviving set is byte-identical to what `plan_duration` would have assigned it before the cut. Nothing in this ticket is new production code; it exists because this property is easy to get right by accident today and easy to break by accident later, and TRAINER.md is explicit that this is the one direction a cut must never take.

**Why this is its own ticket and not three assertions bolted onto ticket 02.** *«Shortening rest does not make the workout shorter, it changes the stimulus, and the engine would keep progressing as if nothing had happened»* — TRAINER.md states this as a standalone guarantee, not a side effect of the cut order, and a guarantee that important gets a test suite whose only job is to fail loudly the day someone "optimises" the cut by trimming a few seconds of rest instead of a set. A property folded into another ticket's checklist gets read once and then forgotten; a ticket named for the property gets found by whoever breaks it.

**The property has to be checked on every branch, not just the happy path.** Three branches exist in ticket 02's cut order — isolation dropped, secondary pattern dropped, primary sets reduced — and each one is a place a future change could quietly touch rest instead of volume. A selection engineered to pass through all three in one cut is the fixture this suite needs, not three separate selections that each only exercise one branch.

**What "unchanged" means, precisely.** For every `SelectionItem` still present after the cut, its rest bucket — as ticket 01 defines it, from `movement_pattern` and reps — is the same value it would get computed fresh, on that same item, outside the cut entirely. The cut is allowed to remove items and remove sets; it is never allowed to change what reps or pattern implies about rest, on the items it keeps.

Reference: TRAINER.md § Engine — analytic / derived (Duration); ROADMAP.md § Session 3.

**Blocked by:** 02 — What gets cut when it doesn't fit

**Status:** ready-for-agent

- [ ] A fixture selection large enough to trigger all three cut stages in one call to `simulate_cut`
- [ ] For every surviving item after the cut, its rest bucket matches what ticket 01's rules would assign it computed independently of the cut
- [ ] The same check repeated for a cut that only reaches the isolation stage, one that reaches the secondary-pattern stage, and one that reaches the primary-sets stage
- [ ] A mutation test or an explicit negative case: a deliberately broken `simulate_cut` that shortens rest during the primary-sets stage is caught by this suite, not waved through
- [ ] No LLM, no network

## Comments
