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

## The rest after the last round is charged on purpose

Every round is charged its rest, the final one included. Between blocks that
rest is real — nobody goes from their last squat straight into the next
exercise — so the only interval overcounted is the one after the very last
round of the very last block, at most three minutes on a whole plan. It stays
charged because this number decides whether a plan fits a declared budget and
there is no cut to catch a plan that turns out longer than promised: the one
direction it must never err in is saying something fits when it does not.

## An exercise appears at most once in a plan

One line per exercise, across the whole plan and not merely within a block.
Two entries on the same bar leave `setup_cost_min` with no honest answer —
charged once it undercounts the exercise that genuinely returns later, charged
twice it overcounts the back-off set that never left — and nothing in a plan
tells those two apart.

The cost is real and was accepted knowingly: **ramp-up sets on the same lift
cannot be written as a light block followed by a working block.** Blocks do
make a third answer possible — charge the setup once per plan, to whichever
block reaches the bar first — and it was put and declined. The warm-up that
timed work exists for is a different exercise (external rotations, a light
walk), so the case this session was built to enable is unaffected; the day
ramp-up sets have to be expressible, this is the paragraph to reopen.

## What it deliberately does not cover

Drop sets, rest-pause and EMOM/AMRAP each need a field the block does not have
— a load progression within the set, an intra-set pause, or a fixed time
container that makes the work the dependent variable rather than the result.
They are out of v1 by decision, not by oversight. They arrive when someone
actually trains that way, because a plan that cannot express what was performed
forces the user to misreport it, and every number downstream inherits the lie.

Note that this vocabulary describes structure only. Which approach to use, and
when, is the agent's call — see ADR-0001.
