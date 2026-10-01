# This workout or from now on

Status: ready-for-agent

Blocked by: 01, 03.

Read first: ADR-0006 (the entrance is a conversation); ADR-0008 item 6; ADR-0011 (the cheapest configuration that clears its bar).

## What to build

- **The entrance tells apart** this workout (`adapt_this_workout`), the mesocycle (`change_mesocycle`), the declaration (`change_declaration`) and a fact about the user (`remember`), from the words and the conversation. The tools' descriptions carry the difference; no classifier, no keyword list.
- **When the words do not say** (*«niente squat»*), it asks whether this workout or from now on, and acts on the answer.
- **The demo** runs in Telegram: rows 0 and 2 of the adaptation set, then the next workout served after them.

**Spends credits.** The closing pass of `trainer eval --suite adapt` is estimated first and runs only on the user's go (CLAUDE.md).

## Acceptance criteria

- [ ] The adaptation set at 100% on what code holds, and at its bar on where messages go, with $ and s per message.
- [ ] If the entrance's model no longer clears its bar, ADR-0011's rule picks another and the ADR gets the row.
- [ ] Full test suite and mypy green.
