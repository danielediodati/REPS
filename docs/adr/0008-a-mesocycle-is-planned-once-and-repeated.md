# A mesocycle is planned once and repeated

Until session 9 every workout was planned from nothing. The split fixed which groups a workout trains; the exercises were new each time. Ticket 9.4 would have planned the next workout after every report, and that is how nobody trains: a programme is chosen once and repeated for several cycles, with only the loads moving.

## Decision

1. **A mesocycle is a workout for each slot of the cycle, with fixed exercises, repeated for a number of cycles.** The planner emits it whole; the validator checks each workout in it as it checks one today.
2. **How many cycles it lasts is the agent's choice, with a reason**, like a block's rest. The engine checks there is a number and a reason, and nothing else (ADR-0001).
3. **Between workouts nothing is planned.** Today's workout is read off the mesocycle: the first of the cycle not yet performed, with the last load performed beside each exercise. Raising it is the user's call until progression lands (after 1.0).
4. **A mesocycle is accepted once.** Each of its workouts becomes *prescribed* when it is served as today's, not when the mesocycle is accepted: ADR-0005's reason holds, an outstanding prescription for a future workout would corrupt the volume deficit.
5. **Three things open a negotiation for a mesocycle**, all through the same accept / turn down loop (ADR-0007):
   - the last cycle ends, and the next one is prepared without being asked for;
   - the user asks for a new one;
   - the user asks for a change to it.
6. **A change and an adaptation are different things.** A change (*"no more lunges"*) rewrites the mesocycle for the cycles left. An adaptation (*"only 30 minutes today"*, *"no dumbbells today"*, *"no legs today, I play football tonight"*) plans this workout from one of the mesocycle's, which the agent picks when asked, and leaves the mesocycle as it was. The entrance tells them apart from the user's words, and asks when it cannot.
   - **An adaptation answers to the user's words first.** The entrance hands over only their sentence; the planner reads it. Nothing of the mesocycle binds it: not the slot's groups, the declared equipment or the usual time. Only the exclusions do, and the plan says which of the cycle's workouts still to do it counts as. What it could not do is a `note` to the user, not a refusal before planning.
7. **The accepted mesocycle is kept in SQLite.** It is something the system writes and the engine reads, not a declaration (ADR-0003).

## Why

- **Re-planning every workout is noise, not coaching.** The same slot came back with different exercises each cycle, so no load could be compared and nothing could progress.
- **The model's minutes move to where they buy something.** A plan is minutes on the local model. Spent once per mesocycle and prepared in the background, it stops being a wait in front of every workout.
- **Loads beside the exercise, not raised by the machine.** Raising them needs a progression scheme, and writing one is the methodology after 1.0. Showing the last load is what the engine can already answer.

## Consequences

- **Amends ADR-0005**: what is accepted is a mesocycle; what is prescribed is still one workout, on the day it is served.
- **CONTEXT.md**: *Mesocycle* is redefined in cycles, not weeks; *Negotiation* is asking for a mesocycle, a change, or an adaptation.
- **ROADMAP.md**: ticket 9.4 is withdrawn, session 9 closes on 9.5, and *The mesocycle* becomes session 10. Every later session moves down one.
- **A mesocycle costs several plans' worth of model time.** Its wall time on the local model is measured as soon as the planner emits one.
