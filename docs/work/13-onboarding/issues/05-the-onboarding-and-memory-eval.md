# The onboarding and memory eval

Status: ready-for-agent

Blocked by: 02, 04.

Read first: ADR-0010 (legality at 100%, judgement at a declared bar); ADR-0011 (the cheapest configuration that clears its bar); `trainer eval --suite log` as the model to follow.

## What to build

- **`trainer eval --suite onboard`**: scripted users, each a persona whose replies are fixed in advance per field, some covering several fields in one answer, one stopping half-way and resuming.
- **Held at 100%** (code): every field filled and valid; no field asked again once answered; every stored conclusion's quote in a user message.
- **At a declared bar** (judgement): the preferences a persona states are remembered; a declaration change is routed to onboarding and an adaptation is not. The bar is set before the first run, and written down.
- **Onboarding's model and effort** are chosen by ADR-0011's rule on this suite, and the ADR gets its row.

**Spends credits.** Every run is estimated first and runs only on the user's go (CLAUDE.md).

## Acceptance criteria

- [ ] The suite runs against a fixture named in `TRAINER_DB` and `TRAINER_CONFIG`.
- [ ] The chosen configuration clears both bars, with its $ and s per onboarding.
- [ ] ADR-0011 has the onboarding row.
- [ ] Full test suite and mypy green.
