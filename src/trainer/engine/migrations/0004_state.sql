-- Session 2's other table: the state `admissible_set` reads, alongside the
-- catalog. TRAINER.md's Persistent state section names three things here --
-- `profile`, `pattern_state`, and the exclusions each carries -- and this
-- migration gives each its own table rather than folding exclusions into
-- pattern_state, because a **joint** exclusion has no single pattern to live
-- on: `shoulder` cuts across every push and pull pattern at once.
--
-- Nothing here is exercised by volume, trend or pain yet -- those are
-- session 5's `workouts` writing into `pattern_state`. Ticket 05 only needs
-- the shape to exist and the exclusions to be real.

-- One row, always. `profile` holds facts that do not change per session --
-- the goal, what equipment lives at home, standing constraints -- so there
-- is nothing to key it by. The CHECK pins the id, and the seed row means
-- "empty profile" is a state a query can always find, never a table a
-- caller has to check for the absence of.
CREATE TABLE profile (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    primary_goal          TEXT,
    base_equipment        TEXT NOT NULL DEFAULT '[]'
                              CHECK (json_type(base_equipment) = 'array'),
    permanent_constraints TEXT NOT NULL DEFAULT '[]'
                              CHECK (json_type(permanent_constraints) = 'array')
);

INSERT INTO profile (id) VALUES (1);

-- One row per movement pattern, created as a pattern starts being trained --
-- volume and trend are counted from logged workouts, which do not exist
-- until session 5. Empty today, on purpose.
CREATE TABLE pattern_state (
    movement_pattern TEXT PRIMARY KEY,
    weekly_volume    INTEGER,
    load_trend       TEXT,
    pain             TEXT
);

-- The hard engine boundary. `granularity` is exactly the two values
-- TRAINER.md's glossary allows -- a pattern, or everything loading a named
-- joint -- and nothing enforces that `value` is itself real: `exclusions.py`
-- checks it against the catalog's own vocabulary before a row is ever
-- inserted, the same way a rule can never be trusted to have checked a
-- native column for a filter it did not derive.
--
-- `retest_date` is required on every row: TRAINER.md is explicit that an
-- exclusion with no expiry walls off a pattern forever and nobody reopens
-- it. Stored as an ISO-8601 date (`YYYY-MM-DD`), which sorts and compares
-- lexicographically the same way it compares as a date -- no separate
-- column or function needed to ask whether one has passed.
CREATE TABLE exclusions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    granularity  TEXT NOT NULL CHECK (granularity IN ('pattern', 'joint')),
    value        TEXT NOT NULL,
    retest_date  TEXT NOT NULL
);
