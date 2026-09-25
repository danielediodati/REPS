# Training requirements live in a config file, not in SQLite

The user **declares** six things: cycle length, duration cap, split, volume denominator, the equipment they have and the goal. They edit them by hand and read them back, so these live in `training.toml`. SQLite keeps what the **system** writes: workouts, volume, exclusions.

The dividing line is a file you read and edit by hand, against rows you query. A declaration is visible without a query; the same value in SQLite would sit beside measurements, with nothing to tell the two apart.

It is not *who writes the value*, which was the line until session 8. Onboarding (session 13) fills the file by talking to the user, so the system writes it too; until the agent chooses the split itself, the user declares it, and after that they still read it back and change it.

**The file lives in `TRAINER_HOME`, not in the repository** (session 8). It held the user's own cap, split and equipment in a repository meant to be published, and anyone cloning it got the author's declarations. The `git diff` on it was training history -- *when did the cycle change* -- and losing that is the accepted cost of the move. `src/trainer/data/training.example.toml` stays committed as the example the missing-config state names, until onboarding writes the file itself.

Equipment joined the four in session 7, because the bot has to answer *«what am I doing today?»* with no arguments and something has to say what there is to train with. It is a **default and not a cap**: today's equipment travels with the request, and a door that names it wins. Its values are the catalog's, and they are checked where the catalog is open -- `admissible_set` names the ones that exist -- never against a list copied into `config.py`.

The goal joined in session 11: one per mesocycle, and its values are the goal columns of [the methodology](../../src/trainer/data/methodology.md), read from the file. A file without one predates it, and is reported as that state with the line to add.
