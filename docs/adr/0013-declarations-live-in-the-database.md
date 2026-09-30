# Declarations live in the database

ADR-0003 kept the six declarations in `training.toml`, a file the user reads and edits by hand. Since session 13 onboarding writes them and changes them (ADR-0012), and the user talks to the bot, not to the file.

## Decision

1. **The declarations are rows in SQLite**, one version per change, dated. The one in force is the latest. Nothing is overwritten.
2. **Onboarding is the one door that writes them**: the first interview and every change (ADR-0012). A version is written in the same transaction as the exclusions the interview confirmed.
3. **`trainer config` reads them** and prints the version in force. It does not change them: a change goes through the bot, which checks the paths open to the running mesocycle.
4. **No declarations is a state, not an error**: the bot starts the interview, and the CLI names the bot as the fix.
5. **An existing `training.toml` is imported once**, the first time the declarations are read and the table is empty. The file is then ignored.

## Consequences

- **Supersedes ADR-0003.** `TRAINER_CONFIG`, `training.example.toml` and the TOML patching behind a change (`onboarding.rewritten`) go.
- **Reading a declaration needs a connection**, as every other state already does.
- **History comes back**: *when did the goal change* is a query, which the file lost when it left the repository.
