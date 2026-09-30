# No configuration starts the interview

Status: ready-for-agent

Blocked by: 02.

Read first: CLAUDE.md, the standing rule on a missing precondition; `engine/config.py` (`NoTrainingConfig`, `NoGoal`, `EXAMPLE_CONFIG_PATH`).

## What to build

- **In the bot**, a missing `training.toml` or a missing goal starts onboarding instead of answering with the missing-config state. A file with some fields and no goal is resumed: onboarding asks only for what is missing.
- **At the CLI**, the missing-config state names the fix as *talk to the bot*, not *copy the example*.
- **`training.example.toml` goes**, with `EXAMPLE_CONFIG_PATH` and every message and test that names it. The comments it carried now come from the file onboarding writes.
- README's setup section says the bot asks, and no longer tells the reader to copy a file.

## Acceptance criteria

- [ ] With no `training.toml`, the first message to the bot gets the first onboarding question.
- [ ] With a file missing only `goal`, onboarding asks only about the goal.
- [ ] `grep -r training.example` finds nothing in `src`, `tests` or README.
- [ ] Full test suite and mypy green.
