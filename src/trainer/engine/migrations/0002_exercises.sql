-- The catalog, as published. Enrichment adds its seven fields in session 2;
-- nothing here anticipates them.
--
-- The source's own string id is the primary key. It is stable, readable and
-- already unique across the dataset, and inventing a surrogate beside it would
-- mean carrying two identities for the same thing forever.
--
-- The four list-valued fields are stored as JSON arrays -- checked as arrays,
-- not merely as valid JSON, since json_valid() also accepts an object or a
-- bare number and _from_row would turn those into nonsense. One row is one source
-- record, so an exercise comes back whole; json_each() reaches inside when a
-- query needs to.

CREATE TABLE exercises (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    force             TEXT,
    level             TEXT NOT NULL,
    mechanic          TEXT,
    equipment         TEXT,
    category          TEXT NOT NULL,
    primary_muscles   TEXT NOT NULL CHECK (json_type(primary_muscles) = 'array'),
    secondary_muscles TEXT NOT NULL CHECK (json_type(secondary_muscles) = 'array'),
    instructions      TEXT NOT NULL CHECK (json_type(instructions) = 'array'),
    images            TEXT NOT NULL CHECK (json_type(images) = 'array')
);

CREATE INDEX exercises_equipment ON exercises (equipment);
CREATE INDEX exercises_category ON exercises (category);
CREATE INDEX exercises_level ON exercises (level);

-- `force` and `mechanic` are nullable on purpose: the source leaves them empty
-- for 30 and 87 records, and that absence is data. The appendix already judges
-- these two fields insufficient, so how far they reach is worth being able to
-- ask.
