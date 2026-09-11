# Training requirements live in a config file, not in SQLite

The user **declares** four things: cycle length, duration cap, split and volume denominator. They edit them by hand and read them back, so these live in `training.toml`. SQLite keeps what the **system** writes: workouts, volume, exclusions.

The dividing line is who writes the value. A declaration in a file is visible without a query, and `git diff` shows when it changed. The same value in SQLite would sit beside measurements, with nothing to tell the two apart.

Onboarding (session 9) fills the file by talking to the user. Until the agent chooses the split itself, the user declares it.
