# A plan is a sequence of blocks, not a list of exercises

A **block** is one or more exercises, a number of rounds, and the rest taken
after each round. Straight sets are a block holding one exercise; a superset
holds two, a triset three, a circuit as many as it has. Its cost is
`setup(every exercise in the block, once) + rounds x (Σ work + rest)`.

## Why not a flat list

The first version of the duration model made a plan a flat sequence of
`(exercise, sets, reps)` and costed each entry independently:
`Σ [ setup + sets x (work + rest) ]`. That formula assumes every entry is
performed to completion before the next one starts, and a superset is exactly
the case where it is not — two exercises alternate and the rest falls after the
pair, not after each. Costed as two independent entries, a superset comes out
several minutes longer than it is, and the error is invisible: the number looks
like every other number the engine produces.

The block shape is not a special case bolted on for supersets. Straight sets
are the one-exercise block, so the old model is a strict subset of this one and
nothing has to know which kind it is holding.

## What it deliberately does not cover

Drop sets, rest-pause and EMOM/AMRAP each need a field the block does not have
— a load progression within the set, an intra-set pause, or a fixed time
container that makes the work the dependent variable rather than the result.
They are out of v1 by decision, not by oversight. They arrive when someone
actually trains that way, because a plan that cannot express what was performed
forces the user to misreport it, and every number downstream inherits the lie.

Note that this vocabulary describes structure only. Which approach to use, and
when, is the agent's call — see ADR-0001.
