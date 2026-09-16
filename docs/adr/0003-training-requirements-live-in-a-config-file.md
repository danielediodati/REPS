# Training requirements live in a config file, not in SQLite

The user **declares** five things: cycle length, duration cap, split, volume denominator and the equipment they have. They edit them by hand and read them back, so these live in `training.toml`. SQLite keeps what the **system** writes: workouts, volume, exclusions.

The dividing line is who writes the value. A declaration in a file is visible without a query, and `git diff` shows when it changed. The same value in SQLite would sit beside measurements, with nothing to tell the two apart.

Onboarding (session 9) fills the file by talking to the user. Until the agent chooses the split itself, the user declares it.

Equipment joined the four in session 7, because the bot has to answer *«what am I doing today?»* with no arguments and something has to say what there is to train with. It is a **default and not a cap**: today's equipment travels with the request, and a door that names it wins. Its values are the catalog's, and they are checked where the catalog is open -- `admissible_set` names the ones that exist -- never against a list copied into `config.py`.
