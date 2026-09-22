# The next mesocycle is prepared when the last cycle ends

Status: ready-for-agent

Blocked by: 02.

ADR-0008 item 5: when the active mesocycle's last cycle is performed, the next one is prepared without being asked for and waits in the chat.

## What to build

What ticket 9.4 established still holds (ROADMAP § Session 10 item 4):

- a negotiation nobody asked for is still one, and `trainer runs list` tells it apart from one the user opened;
- left unanswered it reads *waiting*, with how long, never *abandoned* (ADR-0007 item 8);
- it runs outside the turn-taking queue, so a message arriving meanwhile is answered, and it opens no draft;
- it starts its run with `planner.starting` alone, on `bot.under(thread, PLANNING)`, so a user request while it waits gets the prepared one and never a second.

Triggered by the report that completes the last cycle. The brief carries the mesocycle that ended and what was performed against it.

## Left by 02

- After the last cycle `mesocycles.today` raises *finished its N cycles*, `entrance.reading_today` answers `NO_MESOCYCLE`, and the entrance offers to plan one. Once the next is prepared, that answer should point at the one waiting, not offer a new one.
- 03 made `entrance.startable` answer `adapt_today` and `change_mesocycle` with the same `NO_MESOCYCLE` after the last cycle; the same fix applies there.
- Accepting a mesocycle withdraws the ended one's serving nobody performed (`mesocycles.record_mesocycle`). After the last cycle there is none, so the prepared one's acceptance takes nothing back.

## References

- ADR-0007, ADR-0008; CONTEXT.md: Negotiation
- `src/trainer/coach/bot.py`, `src/trainer/coach/runs.py`, `src/trainer/coach/planner.py`

## Acceptance criteria

- [ ] The report that completes the last cycle starts one planning run, and only one.
- [ ] A message sent while it runs is answered; asking for a mesocycle meanwhile gets the prepared one.
- [ ] `trainer runs list` shows it as opened by the machine, and as *waiting* while unanswered.
- [ ] Full test suite and mypy green.
