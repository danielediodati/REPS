# Session 15b — A message mid-plan is read, not queued

**Demo** (recorded at `1.0.0`, session 15c): *«anzi, ho solo 30 minuti»* sent while a plan is being written stops it, and the 30-minute plan arrives instead.

| Question | Answer |
|---|---|
| Order | Refactors with no behaviour change (01, 02, 04), and one behaviour change built on 02 (03). |
| 01, the eval runner | The five suites each rebuild fixture, run, quota stop, record and bars. One runner owns them; each suite keeps its set, its fixture's contents and how it scores one run. |
| 02, the negotiation | "At most one plan per negotiation" lives in Telegram code (`bot.py`) and its only test drives a fake chat. One Negotiation module owns it; bot and CLI are its two adapters. |
| 03, mid-plan | Today a message arriving while the planner works is queued blindly. The entrance reads it: a question is answered at once, a correction or a new ask stops the run in flight. |
| 04, the node models | Which model each node runs on is written in five places, and two of them fall back differently. One roster in `models.py`, read by everyone. |
| Credits | 01, 02 and 04: none, closed on scripted models. 03: estimated before any paid run, on the user's go. |
| 05, the front page | MIT licence, a logo, a README worth opening, badges. The repository stays private until `1.0.0`, so the live badges show only to its owner until then. |
| Version | `1.0.0rc1`. `1.0.0` is session 15c: the recorded demo, the repository made public, and the fixes found using the rc. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | One suite runner (done) | — |
| 02 | One Negotiation, two doors (done) | — |
| 03 | The entrance reads a message mid-plan | 02 |
| 04 | One roster of node models | — |
| 05 | The front page | 01-04 |
