# The onboarding conversation

Status: ready-for-agent

Blocked by: 01.

Read first: TRAINER.md § Agent and the onboarding line under the user's loop; ADR-0003 (the six declarations); ADR-0004 item 4 (`interrupt()`); `engine/config.py`.

## What to build

- **An onboarding subgraph**, led by the agent from a prompt: what it must know by the end, never a list of questions. Goal first and aches last is guidance, not order. One question per `interrupt()`; an answer that covers several fields covers them.
- **It resumes.** The thread is checkpointed: a user who stops at the fourth answer and writes the next day picks up where they left, nothing asked twice.
- **It cannot end with a field missing.** Code checks the six declarations of ADR-0003 against the same validation `config.load` applies, and sends what is missing back to the model. Vocabulary (equipment, groups, goals) is read from the data.
- **Triage is a tool**, `propose_exclusion(pattern or joint, re-test date, why)`, with the patterns and joints read from the catalog (ADR-0009 item 4). The user confirms or declines, through the same path the logger's proposed exclusion takes today (`coach/bot.py`).
- **It has `remember`** from 01: *"I hate pressing"* said here is a conclusion with its quote.
- **It writes `training.toml`** in `TRAINER_HOME`, with a comment per field as the example has, then starts the planner for a first mesocycle through the existing accept / turn down loop.
- **Reachable from the chat**: the entrance hands off to it when the user asks to set up. 03 makes it start on its own.

## Acceptance criteria

- [ ] A scripted conversation fills all six fields, and `trainer config` (or `config.load`) reads the file it wrote.
- [ ] An answer covering equipment and minutes at once leaves neither asked again (test).
- [ ] The model trying to end with the goal missing is sent back (test).
- [ ] Stopped mid-way and the bot restarted, the next message resumes the interview.
- [ ] A confirmed exclusion is in `exclusions`; a declined one is not.
- [ ] It ends in a mesocycle offered in the chat.
- [ ] Full test suite and mypy green.
