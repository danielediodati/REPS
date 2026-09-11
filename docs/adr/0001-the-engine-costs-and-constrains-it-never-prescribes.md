# The engine costs and constrains; it never prescribes method

Rules define what is **possible**: the admissible set, the time available, the exclusions.

The agent decides what is **good**:
- the split;
- the workout's structure;
- the rest;
- which exercise;
- a full workout or a reduced one.

An engine function that answers *what is good* is a rule standing where deliberation belongs.

## Rules out

- **An automatic cut.** Time is allocated before the plan is built. A plan that does not fit is refused, never repaired by the engine, because a silent repair would hide the arithmetic error from the agent. Since ADR-0004 the refusal goes back to the agent, which fixes the plan knowing why it was refused.
- **A fixed rest value.** The agent prescribes the rest and it is recorded. The bands are a reference.
- **Split menus, coverage rules, time ratios.** The engine only does arithmetic over the proportions it is given.

## Degeneration is measured, not forbidden

The volume deficit replaces a coverage rule. It is counted on two axes, because each catches what the other misses:

| axis | catches | example |
|---|---|---|
| **movement pattern** | a workout missing whole movements | a leg day of calf raises shows no squat or hinge |
| **muscle** | a workout that trains one muscle within a pattern | an arm day of only curls is invisible per pattern, because biceps, triceps and forearms are all `isolation` |

Muscle groups only allocate time. Used as a volume axis, `arms` would erase exactly the distinction the muscle axis keeps.

## Left in the engine

Plan duration, remaining budget, the admissible set and the volume deficit. All four are arithmetic or set operations, and none of them decides how to train.
