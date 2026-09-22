-- Which prescribed workout a mesocycle's slot became when it was served
-- (ADR-0008 item 4).
--
-- `served_after` is how many workouts had been performed when it was served.
-- Served again before anything else is performed, the count is the same and
-- so is the workout: the unique key is what makes serving twice one
-- prescription and not two.
CREATE TABLE served (
    workout_id   INTEGER PRIMARY KEY REFERENCES workouts (id) ON DELETE CASCADE,
    mesocycle_id INTEGER NOT NULL REFERENCES mesocycles (id) ON DELETE CASCADE,
    slot         INTEGER NOT NULL CHECK (slot >= 1),
    served_after INTEGER NOT NULL CHECK (served_after >= 0),
    UNIQUE (mesocycle_id, served_after)
);
