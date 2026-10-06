# Session 15b — A message mid-plan is read, not queued

**Demo** (recorded after the session): *«anzi, ho solo 30 minuti»* sent while a plan is being written stops it, and the 30-minute plan arrives instead.

| Question | Answer |
|---|---|
| Order | Refactors with no behaviour change (01, 02, 04), and one behaviour change built on 02 (03). |
| 01, the eval runner | The five suites each rebuild fixture, run, quota stop, record and bars. One runner owns them; each suite keeps its set, its fixture's contents and how it scores one run. |
| 02, the negotiation | "At most one plan per negotiation" lives in Telegram code (`bot.py`) and its only test drives a fake chat. One Negotiation module owns it; bot and CLI are its two adapters. |
| 03, mid-plan | Today a message arriving while the planner works is queued blindly. The entrance reads it: a question is answered at once, a correction or a new ask stops the run in flight. |
| 04, the node models | Which model each node runs on is written in five places, and two of them fall back differently. One roster in `models.py`, read by everyone. |
| Credits | 01, 02 and 04: none, closed on scripted models. 03: estimated before any paid run, on the user's go. |
| Version | `1.0.1`, the user's call. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | One suite runner | — |
| 02 | One Negotiation, two doors | — |
| 03 | The entrance reads a message mid-plan | 02 |
| 04 | One roster of node models | — |
