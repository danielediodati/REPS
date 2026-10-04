-- The direction a mesocycle was planned from (ADR-0014): one theme for all of
-- it, what changed from the last, and why. Written by the supervisor, kept
-- with the mesocycle it shaped. The first mesocycle and a change have none.
CREATE TABLE directions (
    mesocycle_id INTEGER PRIMARY KEY REFERENCES mesocycles (id) ON DELETE CASCADE,
    theme        TEXT NOT NULL CHECK (length(trim(theme)) > 0),
    changes      TEXT NOT NULL CHECK (length(trim(changes)) > 0),
    why          TEXT NOT NULL CHECK (length(trim(why)) > 0)
);
