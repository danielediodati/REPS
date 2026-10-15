# The recorded demo

Status: ready-for-agent

Blocked by: 01, 02, 03, 04.

Read first: `spec.md` (Carried from 15.5); README "The demo".

Budget: $1.00 for the whole ticket, approved by the user on 2026-10-15 (raised from $0.50 after two attempts, ~$0.62).

## What to build

The session's demo, recorded in English (Telegram's app set to English, ticket 03) on a home built by `trainer demo`:

1. Today's workout is asked for and reported: the third mesocycle ends, and the fourth arrives with its direction in a line.
2. Once the fourth mesocycle is accepted, today's workout is adapted (*"today I only have dumbbells"*), and *"actually, I only have 30 minutes"* is sent while it is written: the 30-minute dumbbell plan arrives instead. Asked of a mesocycle still waiting on its answer, the same words rewrite the whole mesocycle.

- A GIF of it in the README's "The demo", replacing the line that says it lands with `1.0.0`; the script stays below it for anyone who wants to run it.
- The draft's last line stays above a message the bot has just sent, with its dots, until Telegram expires it about 30 seconds later (seen on the user's client in the 15c.4 rehearsal; the Bot API has no call to clear it). Wait it out or cut there.
- Whatever the recording shows wrong is either fixed here or written down as a declined finding; a fix that is a session of its own goes under After 1.0.0, with the user.

## Acceptance criteria

- [ ] The recording shows both scenes, end to end, with no message the user did not expect.
- [ ] The README's GIF renders on GitHub, in both themes.
- [ ] Every recording attempt is paid: estimated and approved first, with the running total shown.
