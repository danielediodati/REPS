# One directory for everything the machine writes

Status: ready-for-agent

Blocked by: none -- can start immediately.

Today the training database, the checkpointer, `eval-runs/` and `training.toml` are each resolved against the working directory. Launched from two directories, `trainer` is two installations with two histories, and nothing says so. There is also nothing to copy when the laptop is replaced: the four live in four places.

**`TRAINER_HOME` is that one place, and it defaults to `~/.reps`.** The per-artifact variables stay as overrides, and an override always wins:

| what | variable | where it lands |
|---|---|---|
| training database | `TRAINER_DB` | `$TRAINER_HOME/trainer.sqlite` |
| checkpointer | `TRAINER_CHECKPOINTS` | `$TRAINER_HOME/checkpoints.sqlite` |
| eval records | (new) | `$TRAINER_HOME/eval-runs/` |
| declarations | `TRAINER_CONFIG` | `$TRAINER_HOME/training.toml` |

## `training.toml` moves too, and ADR-0003 changes with it

The roadmap says `training.toml` is the exception and stays in the repository, because ADR-0003 makes the diff on it training history. **That is wrong and this ticket corrects it**, for three reasons:

- from session 11 the onboarding subgraph writes the file by talking to the user, which ADR-0003 already says -- so it is not only hand-written;
- it is tracked in a repository that becomes a public portfolio, and the cap, the split and the equipment are the user's own data;
- anyone who clones the repository gets the author's declarations instead of their own.

**The `git diff` history is a loss, and the user has accepted it.** ADR-0003's dividing line stops being *who writes the value* and becomes *a file you read and edit by hand, against rows you query*. The committed example stays where it is, at `src/trainer/data/training.example.toml`.

## What to build

- **`TRAINER_HOME`**, resolved in one place, that every one of the four paths above is built from. `eval-runs/` gets a variable of its own while it is there, so that the table has no hole in it.
- **The files that exist are moved, not recreated.** Move `trainer.sqlite`, `checkpoints.sqlite` and `training.toml` into the home yourself, in this ticket, and verify the bot and `trainer state` read them afterwards. No migration command and no state for it: there is exactly one installation and it is this one.
- **`training.toml` leaves git**: `git rm --cached`, and `.gitignore` gains it. It stays on disk, in the home.
- **ADR-0003 is amended**: the dividing line, the accepted loss of the diff history, and the onboarding session is 11 and not 10.
- **ROADMAP.md**: the sentence making `training.toml` the exception goes.
- **README**: the `cp` line in Getting started and the paragraph on `TRAINER_DB` and `TRAINER_CHECKPOINTS` describe the home.

## Acceptance criteria

- [ ] With no variable set, `trainer state` run from two different directories reads the same database.
- [ ] Each of the four overrides still wins over the home when it is set.
- [ ] The three existing files are in the home, with their content: the workouts and the threads from before the move are readable, and `trainer state` shows the same history as it did before.
- [ ] `git status` is clean and `training.toml` no longer appears in `git ls-files`.
- [ ] ADR-0003, ROADMAP.md and README agree with the code.
- [ ] The full test suite and mypy are green.
