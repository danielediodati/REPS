# Session 10 — The mesocycle

**Demo**: you ask for a mesocycle and accept it once. On each of the next workouts the bot answers at once with the next one from it, the last load beside each exercise. After the last cycle the next mesocycle is waiting in the chat.

ADR-0008 is the decision. This spec fixes what it leaves open.

| Question | Answer |
|---|---|
| Shape | `plan.Mesocycle`: one `WorkoutPlan` per slot of the cycle, in split order, plus `cycles` and `why`. |
| Which slot is which | Slot *n* is split entry *n*. Today's slot is `state.rotation().position`, as today; accepting a mesocycle never resets the rotation. |
| How each workout is checked | Against the `Request` its slot would get on its own: that slot's groups and allocation, the declared cap and equipment, today's exclusions. The six invariants run per workout. Across the mesocycle, only that `cycles ≥ 1` and `why` is not blank (ADR-0001); a change's `cycles` is at least the cycle it is in. |
| When it ends | After `cycles` complete cycles counted from the performed workouts at acceptance, not from dates. A change keeps the count of the one it rewrites, and its `cycles` is the total. |
| Where it lives | SQLite, one migration: the accepted mesocycle, its workouts and blocks in the same shape a prescribed workout has, and the performed count it was accepted at. One active mesocycle at a time; a new acceptance ends the old one. |
| Who emits it | The planner graph, in one emission, in a *mesocycle* mode beside the existing *one workout* mode. One workout is still what an adaptation plans (10.3). |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | The planner emits a mesocycle, and an accepted one is kept | — |
| 02 | Today's workout is read, not planned | 01 |
| 03 | A change and an adaptation | 02 |
| 04 | The next mesocycle is prepared when the last cycle ends | 02 |
| 05 | The plan eval suite on a mesocycle | 01 |
