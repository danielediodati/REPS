-- What the user declares, one version per change (ADR-0013).
--
-- The version in force is the one with the highest id; nothing is updated or
-- deleted, so when a declaration changed is a query. `split` and `equipment`
-- are JSON arrays, checked by `config.parse` on every read.
CREATE TABLE declarations (
    id                 INTEGER PRIMARY KEY,
    declared_on        TEXT    NOT NULL,
    cycle_length       INTEGER NOT NULL CHECK (cycle_length >= 1),
    duration_cap_min   INTEGER NOT NULL CHECK (duration_cap_min >= 1),
    split              TEXT    NOT NULL,
    volume_denominator TEXT    NOT NULL,
    equipment          TEXT    NOT NULL,
    goal               TEXT    NOT NULL
);
