# A plan is a sequence of blocks

A **block** is one or more exercises, a number of rounds, and the rest taken after each round. Straight sets hold one exercise, a superset two, a circuit more. A block costs `setup(each exercise, once) + rounds × (Σ work + rest)`.

- **Not a flat list.** Costing `(exercise, sets, reps)` entries one by one silently makes a superset several minutes longer than it really is. Straight sets are simply the one-exercise block, so the block model loses nothing.
- **The rest after the last round is charged.** This overcounts at most one interval, three minutes per plan. The figure decides whether a plan fits the budget, and it must never say a plan fits when it does not.
- **An exercise appears at most once per plan.** Two entries on the same bar leave the setup cost with no honest answer. The accepted cost: ramp-up sets cannot be written as a light block followed by a working block. Reopen this decision if they need to be.
- **Out of v1:** drop sets, rest-pause, EMOM and AMRAP. Each needs a field a block does not have. They come when someone actually trains that way.

Which structure to use is the agent's call (ADR-0001).
