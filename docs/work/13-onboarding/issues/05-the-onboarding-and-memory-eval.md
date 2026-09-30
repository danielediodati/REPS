# The onboarding and memory eval

Status: ready-for-agent

Blocked by: 02, 03, 04.

Read first: ADR-0010 (legality at 100%, judgement at a declared bar); ADR-0011 (the cheapest configuration that clears its bar); `trainer eval --suite log` as the model to follow.

## What to build

- **`trainer eval --suite onboard`**: scripted users, each a persona whose replies are fixed in advance per field, some covering several fields in one answer, one stopping half-way and resuming.
- **Held at 100%** (code): every field filled and valid; no field asked again once answered; every stored conclusion's quote in a user message.
- **At a declared bar** (judgement): the preferences a persona states are remembered; a declaration change is routed to onboarding and an adaptation is not. The bar is set before the first run, and written down.
- **Onboarding's model and effort** are chosen by ADR-0011's rule on this suite, and the ADR gets its row.

**Spends credits.** Every run is estimated first and runs only on the user's go (CLAUDE.md).

## From 02

- Onboarding runs on the entrance's model (`bot.graphs` passes `front`; `onboarding.studio` uses `models.entrance()`). There is no `ONBOARDING_MODEL` yet: this ticket adds it with its choice.
- The graph is driven turn by turn with `Command(resume=...)` on a checkpointed thread; `tests/test_onboarding.py` shows the shape a scripted persona needs.

## From 04

- The entrance routes a declaration change through `change_declaration(said)`; an adaptation stays `adapt_today`. That routing is the judgement above.
- A change starts with `onboarding.changing(said, today, words, before)`, seeded from `onboarding.declarations()`. It ends with `choose(path, why)` over `onboarding.open_paths`, or with `finish` alone when no mesocycle is running. Pass `opening=` to `onboarding.build` to fix the paths in a persona.
- Held at 100% for a change: `chosen` is among the open paths, and only the changed fields differ in the new version.

## From 03

- Declarations are in the database (ADR-0013): a persona's starting declarations are a version written into its `TRAINER_DB` fixture; there is no `TRAINER_CONFIG`.

## Acceptance criteria

- [ ] The suite runs against a fixture named in `TRAINER_DB`.
- [ ] The chosen configuration clears both bars, with its $ and s per onboarding.
- [ ] ADR-0011 has the onboarding row.
- [ ] Full test suite and mypy green.
