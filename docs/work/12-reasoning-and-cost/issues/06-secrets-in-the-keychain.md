# Secrets in the keychain, models in a file

Status: needs-triage

Blocked by: 05, whose defaults this file holds.

## Why

`.env` mixes two kinds of setting that want different homes, and it is found from the working directory (`find_dotenv(usecwd=True)` in `cli.py`) while everything else the machine writes is in `TRAINER_HOME`.

| Kind | Today | Here |
|---|---|---|
| **Secrets**: `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN` | plain text in `.env` | the OS keychain, through `keyring` (Windows Credential Manager, macOS Keychain) |
| **Model settings**: `*_MODEL`, `*_REASONING`, `OPENROUTER_PROVIDER`, `LLM_BACKEND` | `.env`, defaults in `models.py` | a TOML file in `TRAINER_HOME`, defaults in code |
| **Paths and ids**: `TRAINER_*`, `TELEGRAM_OWNER_ID`, Ollama's | `.env` or the environment | unchanged |

## What to build

- **Precedence, one rule everywhere**: the environment wins, then the file (or the keychain, for a secret), then the default in code. CI and the eval keep working on environment variables alone.
- **A command that stores a secret**, e.g. `trainer secret set openrouter`, prompting without echo. `trainer secret list` names which are set and never prints one.
- **A missing secret is reported as a state** (CLAUDE.md): which one, and the command that sets it.
- **`.env` is still read**, as the environment's override, so nothing breaks on upgrade; `.env.example` shrinks to what is left in it.
- **The no-credentials guarantee holds**: `conftest.py` must keep the keychain out of the suite as it keeps `.env` out, or a test passes on the machine and fails in CI.

## Open for triage

- One file or two: the model settings in `training.toml` (the user's), or a file of their own (the machine's). `training.toml` is what the onboarding of session 13 writes.
- Whether this belongs to session 12 or opens a later one.

## Acceptance criteria

- [ ] `trainer bot` starts with no `.env`, the secrets in the keychain and the models from the file.
- [ ] An environment variable still overrides both.
- [ ] A missing secret names the command that sets it.
- [ ] The suite runs with a keychain holding real secrets and reads none of them.
