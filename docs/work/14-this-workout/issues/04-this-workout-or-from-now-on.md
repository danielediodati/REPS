# This workout or from now on

Status: ready-for-agent

Blocked by: 01, 03.

Read first: ADR-0006 (the entrance is a conversation); ADR-0008 item 6; ADR-0011 (the cheapest configuration that clears its bar).

## What to build

- **The entrance tells apart** this workout (`adapt_this_workout`), the mesocycle (`change_mesocycle`), the declaration (`change_declaration`) and a fact about the user (`remember`), from the words and the conversation. The tools' descriptions carry the difference; no classifier, no keyword list.
- **When the words do not say** (*«niente squat»*), it asks whether this workout or from now on, and acts on the answer.
- **An ache** (row 15, `triage`) has no handoff from the entrance: triage runs only inside the first interview. The set scores it as nothing started and a question asked.
- **The demo** runs in Telegram: rows 0 and 2 of the adaptation set, then the next workout served after them.

**Spends credits.** The closing pass of `trainer eval --suite adapt` is estimated first and runs only on the user's go (CLAUDE.md).

## From ticket 03

- A refused `adapt_this_workout` comes back as *«That was not started: ... call it again put right, or ask them»*. Two refusals want different turns: row 8 (pull-ups on the legs day) names the workout's groups and should be called again with `workout`; row 16 names the exclusion and its re-test date and should be relayed, not retried.
- `TALKING` and the tool's docstring already say exercise ids come from `search_exercises`; the routing between the four destinations is still this ticket's.

## Acceptance criteria

- [ ] The adaptation set at 100% on what code holds, and at its bar on where messages go, with $ and s per message.
- [ ] If the entrance's model no longer clears its bar, ADR-0011's rule picks another and the ADR gets the row.
- [ ] Full test suite and mypy green.

## Comments

- Built (`d84e61a`): the prompt sorts a change by how long it is for, plus a dislike (remember) and an ache (ask); its examples are no longer the set's rows. `plans.Excluded` is relayed, never retried; a group refusal names the workouts still to do by number.
- First pass, 2026-10-02, 1 repetition, **off ADR-0011** (`.env` named qwen3.8-27b on the entrance and gpt-oss-120b on the planner, unpinned): **routed 15/19 (78%, bar 80)**, **held 4/9 (44%, bar 100)**, $0.20, 82 min of wall time (superset alone 40 min: three budget refusals on gpt-oss-120b).

| row | what happened |
|---|---|
| twenty-bare | asked «solo oggi o d'ora in poi?» -- the words carry no «oggi» |
| pull-ups | asked which pull-up variant |
| lunges-again | remembered, then asked mesocycle or this workout |
| hinge-excluded | `log_workout`: «oggi stacchi rumeni» read as a report |
| superset, football, one-more plans | over the budget, 53-59 min against 45-50 |
| football | called without `workout`: the entrance cannot know which number is not legs, so the plan is held to legs |
| you-choose plan | `Dumbbell_Squat` kept: `leave_out` takes ids, «niente squat» is a pattern |
| no-bench plan | a block of 0 rounds |
- Second pass, 2026-10-02, 1 repetition, on ADR-0011's choices: **routed 13/19 (68%)**, **held 5/8 (62%)**, $0.44, 23 s a run. The planner is no longer the problem: every failing plan was started with only `said`.

| row | what happened |
|---|---|
| superset, football, dumbbells, hinge-excluded | `adapt_this_workout` called with `said` alone: no `ask_for`, `workout`, `equipment`, so code holds nothing and the exclusion is never checked |
| thirty | `change_declaration` for «oggi ho 30 minuti invece di 45» |
| pull-ups | `todays_workout`, then «ti mando le trazioni» |
| bought-barbell | `remember` only, then «aggiorno la tua dichiarazione» with nothing started (the fixture already declares a barbell) |
| no-bench, lunges-again | asked instead of acting |

- Next, per this ticket's second criterion: the entrance (`gpt-oss-120b` low, chosen with no suite) does not clear the bar; ADR-0011's rule picks another on this set.
- Fourth pass, 2026-10-02, after `1057b2a` (the planner reads the words) and `dcf3be3`: **routed 15/19 (78%)**, **held 8/10 (80%)**, $0.44, 8 s a run. Football, the exclusion's note and every time row now hold.

| row | what happened |
|---|---|
| superset plan | `Elevated_Back_Lunge` for «i bulgari»: a rear-foot-elevated split squat, which the row's single id does not accept |
| dumbbells plan | a `Plank` in «solo manubri» |
| pull-ups | `todays_workout`, «le trazioni sono programmate» (they are not) |
| no-bench, lunges-again, bought-barbell | asked instead of acting |
- The entrance's matrix, 2026-10-02, on `2b16134`: deepseek-v4-flash high on Parasail is the only row over both bars (routed 17/19, plans 11/11), and the cheapest; it is the entrance's choice in ADR-0011. Left: «oggi vorrei fare trazioni» goes to `todays_workout` on every model, and the demo in Telegram.
