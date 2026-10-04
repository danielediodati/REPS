# Session 15 — The next mesocycle has a reason

**Demo**: after three mesocycles, the fourth arrives with its reason, and what changed is visible in it.

| Question | Answer |
|---|---|
| The supervisor | A coach between mesocycles, not a drift guard (ADR-0014). The guard and the memory gate are after 1.0.0. |
| When it runs | When a mesocycle ends, before the planner. Not on the first mesocycle, not on a change. |
| What it writes | A direction: one theme for every workout of the mesocycle, what changes from the last (exercises, reps, rest, or both), why. No fixed rule such as "rotate half the exercises": ranges, never a template. |
| What it reads | Tools over the history, starting from the last mesocycle; goal, conclusions, its own past directions. Never the planner's or the entrance's prose. |
| Its methodology | `variation.md`, a document of its own; the goal's ranges read from `methodology.md`. The planner's prompt does not change. |
| Loads | Out: a cycle still shows the last load and the user raises it. |
| The planner | Plans from the direction and the mesocycle that ended; the per-workout log leaves its brief. Not bound: following it is measured, not validated. |
| The user | Told the direction in a line when the mesocycle is proposed. |
| Model | ADR-0011's rule; no "different model". |
| The measure | 15-20 scripted histories with what the direction must hold, checked by code; no judge model. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | Between mesocycles, in a methodology of its own | — |
| 02 | The supervisor | 01 |
| 03 | The planner plans from the direction | 02 |
| 04 | The supervisor's set | 02, 03 |
| 05 | Portfolio-ready | 04 |
