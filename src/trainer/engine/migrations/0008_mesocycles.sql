-- The accepted mesocycle (ADR-0008): a workout for each slot of the cycle,
-- repeated for `cycles` cycles, with the agent's reason.
--
-- Its blocks and exercises have the shape of a prescribed workout's, and are
-- not prescribed workouts: a workout is prescribed when it is served, so a
-- mesocycle's slots are templates the engine reads from.
--
-- `accepted_after` is how many workouts had been performed when it was
-- accepted: its cycles are counted from there, never from dates. `ended_on`
-- is set when another mesocycle is accepted; at most one row has none.
CREATE TABLE mesocycles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    accepted_on    TEXT NOT NULL,
    accepted_after INTEGER NOT NULL CHECK (accepted_after >= 0),
    cycles         INTEGER NOT NULL CHECK (cycles >= 1),
    why            TEXT NOT NULL CHECK (length(trim(why)) > 0),
    ended_on       TEXT
);

CREATE UNIQUE INDEX mesocycles_one_active ON mesocycles ((ended_on IS NULL))
    WHERE ended_on IS NULL;

CREATE TABLE mesocycle_blocks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mesocycle_id INTEGER NOT NULL REFERENCES mesocycles (id) ON DELETE CASCADE,
    slot         INTEGER NOT NULL CHECK (slot >= 1),
    position     INTEGER NOT NULL CHECK (position >= 1),
    rounds       INTEGER NOT NULL CHECK (rounds >= 1),
    rest         INTEGER NOT NULL CHECK (rest >= 0),
    reason       TEXT NOT NULL,
    UNIQUE (mesocycle_id, slot, position)
);

CREATE TABLE mesocycle_exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id    INTEGER NOT NULL REFERENCES mesocycle_blocks (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL CHECK (position >= 1),
    exercise_id TEXT NOT NULL REFERENCES exercises (id),
    unit        TEXT NOT NULL CHECK (unit IN ('reps', 'seconds')),
    amount      INTEGER NOT NULL CHECK (amount >= 1),
    UNIQUE (block_id, position)
);
