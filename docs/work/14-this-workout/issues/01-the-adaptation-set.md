# The adaptation set

Status: ready-for-agent

Blocked by: none.

Read first: ADR-0010 (legality at 100%, judgement at a declared bar); `trainer eval --suite onboard` (`onboarding_set.py`, whose routed messages are the model to follow); ADR-0008 item 6.

## What to build

- **`trainer eval --suite adapt`**: user messages against a fixture with an active mesocycle, each with where it must go and, for this workout, what its plan must hold.
- **Held at 100%** (code): an adapted plan holds every exercise asked for, none left out, this workout's equipment and the minutes asked (±5).
- **At a declared bar** (judgement): where the message goes. Asking is the right answer when the words are ambiguous, and acting instead counts double, as in the log set. The bar is written down before the first run.
- Written against today's tool names; ticket 03 renames them.

| # | message | goes to | the plan holds |
|---|---|---|---|
| 0 | oggi niente squat, stacchi rumeni in superset con i bulgari | this workout | no squat; Romanian deadlift and Bulgarian split squat |
| 0b | oggi niente squat, proponi tu | this workout | no squat |
| 1 | oggi ho 30 minuti invece di 45 | this workout | 30 min |
| 2 | oggi niente gambe che stasera gioco a calcio | this workout, another of the cycle's | not the legs workout |
| 3 | mi hanno prestato una kettlebell, usiamola oggi | this workout | declared equipment plus kettlebell |
| 4 | sono in trasferta, solo corpo libero | this workout | body only |
| 5 | oggi ho tempo, metti un esercizio in più per gruppo | this workout | more minutes than the cap, when given |
| 6 | oggi solo manubri, la palestra è piena | this workout | dumbbells only |
| 7 | 20 minuti e niente attrezzi | this workout | 20 min, body only |
| 8 | oggi vorrei fare trazioni | this workout | pull-ups |
| 9 | da ora in poi niente affondi | the mesocycle | — |
| 10 | gli affondi non li sopporto più | the mesocycle | — |
| 11 | ho comprato un bilanciere | the declaration | — |
| 12 | d'ora in poi ho solo 30 minuti | the declaration | — |
| 13 | niente squat | ask | — |
| 14 | oggi non ho voglia di panca | this workout | no bench press |
| 15 | mi fa male la spalla quando spingo sopra la testa | triage | — |
| 16 | oggi stacchi rumeni (hip hinge excluded in the fixture) | refused, naming the exclusion | — |
| 17 | odio la panca | `remember` | — |

The first run is the baseline: it measures today's gap, so failing rows are expected.

**Spends credits.** Every run is estimated first and runs only on the user's go (CLAUDE.md).

## Acceptance criteria

- [ ] The suite runs against a fixture named in `TRAINER_DB`.
- [ ] The bar is written before the first run.
- [ ] A baseline run on the current entrance configuration, with $ and s per message, its failures listed.
- [ ] Full test suite and mypy green.
