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
- First pass, 2026-10-02, 1 repetition: **routed 15/19 (78%, bar 80)**, **held 4/9 (44%, bar 100)**, $0.20, 82 min of wall time (superset alone 40 min: three budget refusals on gpt-oss-120b).

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
