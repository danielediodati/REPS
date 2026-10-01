# Session 14 — Anything about this workout

**Demo**: *«oggi niente squat, stacchi rumeni in superset con i bulgari»* and *«oggi niente gambe, stasera gioco a calcio»* each come back as this workout, and the cycle after them is still right.

| Question | Answer |
|---|---|
| Scope | Any request about this workout works. The hypothesis and trial loop is dropped from the design, not postponed. |
| The tool | `adapt_today` becomes `adapt_this_workout`: the user's sentence, plus the fields code can check (minutes, this workout's equipment in full, exercises left out, exercises asked for, which of the cycle's workouts). A superset, *«one more per group»*, *«you choose»* stay prose for the planner. |
| The declared cap | The usual time, not a limit: this workout may ask for more. |
| Borrowed equipment | Counts for this workout only; keeping it is `change_declaration`. |
| An asked-for exercise under an exclusion | Refused before planning, naming the exclusion and its re-test date. An asked-for exercise never widens the admissible set. |
| Which workout of the cycle | Unasked, the first of the cycle not yet performed, read off the log; no stored order. Asked (*«niente gambe oggi»*), the agent picks one of the mesocycle's. |
| This workout or from now on | The entrance decides from context, and asks when the words do not say. |
| The measure | A set of real requests: where each one goes, and what its plan must hold. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | The adaptation set | — |
| 02 | The next workout is the first not yet performed | — |
| 03 | One tool for anything about this workout | 02 |
| 04 | This workout or from now on | 01, 03 |
