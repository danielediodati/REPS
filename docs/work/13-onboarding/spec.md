# Session 13 — Onboarding and memory

**Demo**: an onboarding conversation, resumed after a day away, ending in a first mesocycle; weeks later, *"I hate pressing"* still holds.

| Question | Answer |
|---|---|
| Who leads the interview | The agent, from a prompt, in its own words. No script, no fixed count. Code holds only that it cannot end while a field of `training.toml` is missing. |
| Triage | Part of onboarding, not a node: the agent asks about movements, never symptoms, and proposes an exclusion through a tool. The user confirms it, as with the logger today. |
| Medical trigger | Dropped. No pain scale, no health check-in, no referral. |
| What enters memory | A conclusion carrying the user's sentence verbatim; code refuses it unless that sentence is in one of the user's messages (TRAINER.md § Memory). |
| Who decides to remember | The node already reading the turn (onboarding, entrance, logger), through a `remember` tool. No node of its own. |
| A declaration changed later | Onboarding again, asking only about what changed; code lists the paths open for the running mesocycle, the agent picks one, the user accepts (ADR-0012). |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | Memory with a source | — |
| 02 | The onboarding conversation | 01 |
| 03 | No configuration starts the interview | 02 |
| 04 | A declaration changes through onboarding | 02 |
| 05 | The onboarding and memory eval | 02, 04 |
