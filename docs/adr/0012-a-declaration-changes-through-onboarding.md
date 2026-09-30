# A declaration changes through onboarding

Onboarding fills `training.toml` the first time (ADR-0003). A declaration also changes later: a barbell bought, minutes cut, a new goal. ADR-0008 has two doors for a change the user asks for, and neither of them writes the file.

## Decision

1. **Three kinds of request**, told apart by the entrance, which asks when it cannot:

   | request | example | door |
   |---|---|---|
   | adaptation | *"only 30 minutes today"* | the planner, today only, as ADR-0008 item 6; `training.toml` is not touched |
   | change to the mesocycle | *"no more lunges"* | the planner, the cycles left, as ADR-0008 item 6 |
   | change to a declaration | *"I bought a barbell"*, *"from now on 30 minutes"*, *"switching to strength"* | onboarding, asking only about what changed, then rewriting `training.toml` |

2. **After a declaration changes, code says which paths are open for the running mesocycle:**

   | the running mesocycle | open paths |
   |---|---|
   | illegal under the new declarations | rewrite the cycles left, or a new mesocycle now |
   | still legal | keep it to its end, rewrite the cycles left, or a new mesocycle now |
   | the goal changed | a new mesocycle now, or at the end of this one; never rewritten under a new goal |

3. **The agent picks one open path and says why**; the user accepts or turns it down through the mesocycle's loop (ADR-0007).
4. **Keeping it to its end needs no memory.** The new declaration is already in `training.toml`, and the next mesocycle reads it from there.

## Consequences

- **Amends ADR-0008 item 6**: a change naming a declaration goes to onboarding, not the planner.
- **Legality of the running mesocycle** is the validator run on its workouts against the new declarations, not a new rule.
