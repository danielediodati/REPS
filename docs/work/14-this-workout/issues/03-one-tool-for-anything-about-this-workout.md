# One tool for anything about this workout

Status: ready-for-agent

Blocked by: 02.

Read first: ADR-0008 item 6; ADR-0001 (the engine constrains, never prescribes); CONTEXT.md *Adaptation*, *Exclusion*, *Admissible set*; `entrance.adapt_today` and `plan.adaptation_requested`.

## What to build

- **`adapt_today` becomes `adapt_this_workout`**, everywhere it is named, the onboarding set's routes included.
- **Its fields**, each optional, beside `said`:
  - `minutes`: may exceed the declared cap for this workout; the cap is the usual time, not a limit (`constraints.within_the_cap`).
  - `equipment`: this workout's equipment in full, checked against the catalog. It replaces `without`, so *«solo corpo libero»* and *«ho una kettlebell in prestito»* are one field.
  - `leave_out`: exercises not to do this workout. Not an exclusion: it leaves nothing behind.
  - `ask_for`: exercises to do this workout.
  - `workout`: which of the mesocycle's workouts this one is, when the user asked for another (*«niente gambe oggi»*). The entrance picks it from what the cycle has performed; `adaptation_requested` stops refusing it. `mesocycles.record_adapted` must write the chosen slot into `served`: the cycle counts a workout as the slot recorded there (`state.performed_slots`), and today it writes the next free one.
- **Names to ids**: the entrance resolves exercise names through the catalog; a name it cannot place is asked about, never guessed. The catalog has no Bulgarian split squat: row 0 holds `Split_Squat_with_Dumbbells` instead.
- **An asked-for exercise under an exclusion** is refused before planning, naming the exclusion and its re-test date. The adaptation set scores row 16 by the re-test date, as ISO `YYYY-MM-DD`, in the tool message answering the call.
- **The validator** refuses an adapted plan missing an `ask_for` exercise or holding a `leave_out` one, and sends it back like any refusal. Superset, order and *«one more per group»* stay the planner's, read from `said`.

## Acceptance criteria

- [ ] Rows 0-8, 14 and 16 of the adaptation set produce the right request (unit tests, no model).
- [ ] A plan without an asked-for exercise is refused, and so is one holding a left-out exercise.
- [ ] 70 minutes asked against a 45-minute cap plans 70.
- [ ] Full test suite and mypy green.
