# The user's training requirements live in a config file, not in SQLite

How many workouts a cycle holds, how long a workout may run, which split is
being trained, what denominator volume is counted on — these are declared by
the user, changed by hand, and read back by the user. They go in a committed
configuration file. SQLite keeps what the **system** writes: performed
workouts, accumulated volume, exclusions and their re-test dates.

## Why the split matters

Both stores would work. The line is who writes the value. A requirement in a
config file is visible without a query, and `git diff` says when the user
changed their mind about the cycle — which is itself training history worth
having. The same value in SQLite is a row that has to be interrogated to find
out what was decided, sitting beside rows the system produced, with nothing
distinguishing a declaration from a measurement.

TRAINER.md already draws this line once, between LangGraph and SQLite: *no
domain fact in the conversation store, no conversation fact in the domain
store*. This is the same cut one level out — a declaration is not a
measurement, and mixing them is how, at week 20, nobody can tell which store
tells the truth.

## Consequence for the roadmap

Session 3's allocator is a pure function: it is handed the cycle length, the
duration cap and the split, and returns arithmetic. It writes nothing and opens
no database. Session 6 (onboarding) is what fills the config file by talking to
the user, and session 7 is where the agent starts choosing the split at the
mesocycle boundary and recording its reason — until then, the user declares it.
