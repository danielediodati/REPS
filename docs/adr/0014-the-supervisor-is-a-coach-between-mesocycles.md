# The supervisor is a coach between mesocycles

TRAINER.md designed the supervisor as a drift guard: observations pointing at a measure, injected into the next workout, an engine constraint when ignored twice. Since ADR-0008 the next workout is read from the mesocycle, not planned, so there was nothing to inject into. And what a mesocycle following another lacked was not a guard but a reason to change: the planner was handed the last one and its full log, and nobody told it to vary.

## Decision

1. **The supervisor writes the next mesocycle's direction**, every time one ends, before the planner runs. Not on the first mesocycle, not on a change.
2. **A direction is one theme for the whole mesocycle** and what changes from the last: exercises, reps, rest, or both, inside the methodology's ranges, with a reason. It carries the thread from the directions before it.
3. **It reads the history through tools**, starting from the last mesocycle only. It reads its own past directions; never the planner's or the entrance's prose.
4. **The planner plans from the direction and the mesocycle that ended**; the per-workout log leaves its brief. Following the direction is judgement, measured at a declared bar, never held by the validator (ADR-0010).
5. **The user is told the direction** when the new mesocycle is proposed.
6. **Its model is chosen by ADR-0011's rule.** ADR-0004 item 8's *different model* goes: it bought independence for a guard.
7. **Two methodologies, one per reader.** `methodology.md` is within a mesocycle and the planner reads it; `variation.md` is between mesocycles and the supervisor reads it. The goal's ranges live only in the first, and the supervisor reads them from there.

## Consequences

- **Dropped to after 1.0.0**: observations and their teeth, and the memory gate (marking a conclusion suspect or retiring it). Both belonged to the guard.
- **The supervisor's set** is histories with what the next direction must hold, checked by code, no judge model.
- **`variation.md` is written**, with sources, before the supervisor is built.
