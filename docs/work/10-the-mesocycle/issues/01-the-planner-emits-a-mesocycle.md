# The planner emits a mesocycle, and an accepted one is kept

Status: ready-for-agent

Blocked by: nothing.

Today the planner emits one `WorkoutPlan` for today's slot. ADR-0008 item 1: it emits a workout for every slot of the cycle, how many cycles it lasts, and why. See `../spec.md` for the decisions this ticket builds on.

## What to build

- **`plan.Mesocycle`**: `workouts` (one `WorkoutPlan` per slot, in split order, exactly `cycle_length` long), `cycles` (int, ≥ 1) and `why` (non-blank). Strict schema like `WorkoutPlan`.
- **A per-slot `Request`**: `plans.requested` with `Asked(workout=slot)` for each slot, so every workout is checked against what that slot would have been asked on its own.
- **Validation**: `plans.validate` per workout against its slot's request; a violation names the slot (`workout 2: …`). The mesocycle-level rules are only `cycles` and `why`. Refusals go back to the model as today, within `planner.ATTEMPTS`.
- **The planner graph in mesocycle mode**: the brief lists every slot's groups, minutes and equipment; the model uses the same tools; one emission. The single-workout mode stays as it is.
- **Proposal and acceptance** through the existing interrupt (ADR-0005, ADR-0007). What is shown is the whole mesocycle, one workout per slot, and the cycles with their reason.
- **Kept in SQLite** on acceptance: a migration for the mesocycle, its workouts and blocks, and the performed count at acceptance. Accepting a new one ends the active one. Nothing is prescribed yet (ADR-0008 item 4).
- **A door**: `trainer plan --mesocycle` asks for one. The bot is 02's.

## References

- ADR-0001, ADR-0002, ADR-0005, ADR-0007, ADR-0008
- CONTEXT.md: Cycle, Mesocycle, Split, Negotiation
- `src/trainer/plan.py` (`WorkoutPlan`, `Request`, `requested`, `validate`), `src/trainer/coach/planner.py`, `src/trainer/engine/state.py` (`rotation`), `src/trainer/engine/migrations/`

## Acceptance criteria

- [ ] A scripted planner emitting a four-slot mesocycle against a four-workout split is validated slot by slot, and a violation in slot 3 comes back to the model naming slot 3.
- [ ] A mesocycle with the wrong number of workouts, `cycles: 0` or a blank `why` is refused.
- [ ] Accepted, it is in the database with the performed count it was accepted at; accepting a second ends the first; no workout is prescribed by either.
- [ ] `trainer plan --mesocycle` on a real provider proposes a mesocycle; its wall time on the local model is written here.
- [ ] Tests derive the expected schema version from the migration set.
- [ ] Full test suite and mypy green.
