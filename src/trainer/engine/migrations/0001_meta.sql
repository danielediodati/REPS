-- The first migration exists to make the mechanism real, and it records the
-- one thing a database should be able to say about itself: what created it.
-- Domain tables arrive with the tickets that fill them.

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO meta (key, value) VALUES ('created_by', 'trainer');
