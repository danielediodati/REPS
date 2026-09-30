# Declarations live in the database

Status: ready-for-agent

Blocked by: 02, 04.

Read first: ADR-0013 (all of it); CLAUDE.md, the standing rules on a missing precondition and on the schema version in tests; `engine/config.py`.

## What to build

- **A migration** adding the declarations table: one dated row per version, the latest in force.
- **`config.load(connection)`** reads the version in force; every caller passes the connection it already has. No version is `NoTrainingConfig`, a state.
- **Onboarding writes a version** (first interview and change) in the transaction that writes its exclusions. `onboarding.rewritten` and `_span` go.
- **The bot**: no version makes the first message start the interview. The CLI's state names the bot as the fix.
- **`trainer config`** prints the version in force, ASCII.
- **A `training.toml` found at the old path** is imported once, when the table is empty and the declarations are read.
- **Gone**: `TRAINER_CONFIG`, `training.example.toml`, `EXAMPLE_CONFIG_PATH`, `config_path()`, and every message, test and README line naming them. The `declared_training` fixture writes a version into the test database instead.

## From 04

- A change is `onboarding.changing(said, today, words, before)`; `before` comes from `onboarding.declarations()`, which reads the file raw today. It becomes the version in force.
- `mesocycle_requested`, `requested`, `constraining_today` and `within_the_cap` take an optional `declared`; keep that seam, since `open_paths` validates against declarations not yet written.

## Acceptance criteria

- [ ] With no version, the first message to the bot gets the first onboarding question.
- [ ] A change adds a version and leaves the previous one readable, with its date.
- [ ] An existing `training.toml` is imported once and the plan it gives is unchanged.
- [ ] `trainer config` prints the version in force.
- [ ] `grep -rE "training.example|TRAINER_CONFIG"` finds nothing in `src`, `tests` or README.
- [ ] Full test suite and mypy green.
