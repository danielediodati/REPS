# Session 14 — Anything about this workout

**Demo**: *«oggi niente squat, stacchi rumeni in superset con i bulgari»* and *«oggi niente gambe, stasera gioco a calcio»* each come back as this workout, and the cycle after them is still right.

| Question | Answer |
|---|---|
| Scope | Any request about this workout works. The hypothesis and trial loop is dropped from the design, not postponed. |
| The tool | `adapt_this_workout(said)`: the user's sentence only. The planner reads it; nothing is extracted into fields (ADR-0008 item 6). |
| The declared cap | The usual time, not a limit: this workout may ask for more. |
| Borrowed equipment | Counts for this workout only; keeping it is `change_declaration`. |
| An asked-for exercise under an exclusion | Planned without, and the plan's `note` tells them, with the re-test date. Exclusions are the one thing that binds an adaptation. |
| Which workout of the cycle | Unasked, the first of the cycle not yet performed, read off the log; no stored order. An adapted workout says which one still to do it `counts_as`, so the cycle goes on right after it. |
| This workout or from now on | The entrance decides from context, and asks when the words do not say. |
| The measure | A set of real requests: where each one goes, and what its plan must hold. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | The adaptation set | — |
| 02 | The next workout is the first not yet performed | — |
| 03 | One tool for anything about this workout | 02 |
| 04 | This workout or from now on | 01, 03 |
| 05 | Prompt caching | — |
