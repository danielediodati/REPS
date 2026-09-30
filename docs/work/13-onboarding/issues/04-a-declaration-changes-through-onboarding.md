# A declaration changes through onboarding

Status: ready-for-agent

Blocked by: 02.

Read first: ADR-0012 (all of it); ADR-0008 item 6; ADR-0007 (the negotiation loop).

## What to build

- **The entrance tells three requests apart**: an adaptation (today only), a change to the mesocycle, a change to a declaration. It asks when it cannot (*"only 30 minutes"*: today, or from now on?). An adaptation stays fast: no onboarding, no file written.
- **A change to a declaration runs onboarding** on what changed alone, and rewrites `training.toml`, keeping the other fields and comments.
- **Code lists the open paths** for the running mesocycle, per ADR-0012 item 2. Legality is the validator run on the mesocycle's workouts against the new declarations.
- **The agent picks one and says why**; the user accepts or turns it down through the mesocycle's loop. Keeping it to its end writes nothing else: the next mesocycle reads the file.

## From 02

- `onboarding.written` renders the whole file from `settled(declared)` and overwrites it, and `set_up` starts from nothing. Rewriting one field means seeding `declared` from the current file and telling the interview which field changed.
- A declaration change must not end in `bot.interviewed`'s first-mesocycle path: that plans a new mesocycle unconditionally.

## Acceptance criteria

- [ ] *"I bought a barbell"* rewrites `equipment` and nothing else in the file.
- [ ] Equipment removed that the mesocycle uses: *keep it* is not among the paths offered to the agent (test).
- [ ] A changed goal never offers *rewrite the cycles left* (test).
- [ ] *"only 30 minutes today"* is an adaptation and leaves the file untouched (test).
- [ ] Full test suite and mypy green.
