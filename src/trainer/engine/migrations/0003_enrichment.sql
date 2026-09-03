-- The six enrichment fields from TRAINER.md's appendix, plus demo_url. Nothing
-- gets enriched here: every column is nullable (or defaults to an empty set)
-- on the 876 rows already in the table.
--
-- A seventh field, required_rom, is deliberately absent. TRAINER.md § Appendix
-- and ROADMAP.md § Session 2 carry why: it needs a degree value on the catalog
-- side that no source publishes and a degree value on the user side that no
-- user knows. Exclusion works at two granularities instead -- movement_pattern
-- and loaded_joints -- both below.
--
-- Provenance is per field, not per row: a `_source` column beside each
-- enrichable value, holding 'rule' or 'curated' and nothing else. The
-- CHECK constraints enforce the closed vocabulary; the triggers at the bottom
-- of this file enforce that a rule can never overwrite a curated value.
--
-- movement_pattern stays one column even though a few movements genuinely load
-- two patterns -- a thruster is a squat and an overhead press, a muscle-up is
-- a vertical pull and a dip. docs/enrichment/residue.md § B4 names the rows
-- this affects and the rule that resolves them (the pattern the load ends in).
-- A second column to carry the other pattern would spread across every query
-- in the engine to serve a handful of rows.

ALTER TABLE exercises ADD COLUMN movement_pattern TEXT;
ALTER TABLE exercises ADD COLUMN movement_pattern_source TEXT
    CHECK (movement_pattern_source IS NULL OR movement_pattern_source IN ('rule', 'curated'));

-- loaded_joints is a set, not a scalar -- one exercise can load several joints
-- -- and it is stored the way primary_muscles and secondary_muscles already
-- are: a JSON array column, queried with json_each() rather than parsed as a
-- string. Unlike those two native fields it defaults to '[]' rather than being
-- required at insert time, since every one of the 876 rows starts unenriched;
-- the _source column is what tells an empty set apart from one a rule
-- genuinely decided was empty.
ALTER TABLE exercises ADD COLUMN loaded_joints TEXT NOT NULL DEFAULT '[]'
    CHECK (json_type(loaded_joints) = 'array');
ALTER TABLE exercises ADD COLUMN loaded_joints_source TEXT
    CHECK (loaded_joints_source IS NULL OR loaded_joints_source IN ('rule', 'curated'));

ALTER TABLE exercises ADD COLUMN spinal_axial_load TEXT;
ALTER TABLE exercises ADD COLUMN spinal_axial_load_source TEXT
    CHECK (spinal_axial_load_source IS NULL OR spinal_axial_load_source IN ('rule', 'curated'));

ALTER TABLE exercises ADD COLUMN required_stability TEXT;
ALTER TABLE exercises ADD COLUMN required_stability_source TEXT
    CHECK (required_stability_source IS NULL OR required_stability_source IN ('rule', 'curated'));

ALTER TABLE exercises ADD COLUMN setup_cost_min INTEGER;
ALTER TABLE exercises ADD COLUMN setup_cost_min_source TEXT
    CHECK (setup_cost_min_source IS NULL OR setup_cost_min_source IN ('rule', 'curated'));

-- Self-referencing: a regression or a variant points at another row of this
-- same table. Enforced by PRAGMA foreign_keys (on for every connection this
-- project opens), so a value pointing at nothing is refused at write time
-- rather than stored and discovered later.
ALTER TABLE exercises ADD COLUMN regression_of TEXT REFERENCES exercises (id);
ALTER TABLE exercises ADD COLUMN regression_of_source TEXT
    CHECK (regression_of_source IS NULL OR regression_of_source IN ('rule', 'curated'));

ALTER TABLE exercises ADD COLUMN variant_of TEXT REFERENCES exercises (id);
ALTER TABLE exercises ADD COLUMN variant_of_source TEXT
    CHECK (variant_of_source IS NULL OR variant_of_source IN ('rule', 'curated'));

-- A link, never hosted media -- linking is not distribution. Filled by hand
-- from session 4 onward; no rule and no model ever writes it, which is why it
-- carries no _source column of its own: when it holds a value, that value is
-- always curated.
ALTER TABLE exercises ADD COLUMN demo_url TEXT;

-- One trigger per enrichable field: a write that would move a field's source
-- from 'curated' to 'rule' is rejected outright. This is the one guarantee in
-- this migration that must not depend on every future caller remembering to
-- check it themselves -- a hand decision does not regenerate, and a rule
-- silently overwriting one is the failure this session cannot afford.
CREATE TRIGGER exercises_protect_movement_pattern
BEFORE UPDATE OF movement_pattern, movement_pattern_source ON exercises
WHEN OLD.movement_pattern_source = 'curated' AND NEW.movement_pattern_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite a curated movement_pattern');
END;

CREATE TRIGGER exercises_protect_loaded_joints
BEFORE UPDATE OF loaded_joints, loaded_joints_source ON exercises
WHEN OLD.loaded_joints_source = 'curated' AND NEW.loaded_joints_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite curated loaded_joints');
END;

CREATE TRIGGER exercises_protect_spinal_axial_load
BEFORE UPDATE OF spinal_axial_load, spinal_axial_load_source ON exercises
WHEN OLD.spinal_axial_load_source = 'curated' AND NEW.spinal_axial_load_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite a curated spinal_axial_load');
END;

CREATE TRIGGER exercises_protect_required_stability
BEFORE UPDATE OF required_stability, required_stability_source ON exercises
WHEN OLD.required_stability_source = 'curated' AND NEW.required_stability_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite a curated required_stability');
END;

CREATE TRIGGER exercises_protect_setup_cost_min
BEFORE UPDATE OF setup_cost_min, setup_cost_min_source ON exercises
WHEN OLD.setup_cost_min_source = 'curated' AND NEW.setup_cost_min_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite a curated setup_cost_min');
END;

CREATE TRIGGER exercises_protect_regression_of
BEFORE UPDATE OF regression_of, regression_of_source ON exercises
WHEN OLD.regression_of_source = 'curated' AND NEW.regression_of_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite a curated regression_of');
END;

CREATE TRIGGER exercises_protect_variant_of
BEFORE UPDATE OF variant_of, variant_of_source ON exercises
WHEN OLD.variant_of_source = 'curated' AND NEW.variant_of_source = 'rule'
BEGIN
    SELECT RAISE(ABORT, 'a rule cannot overwrite a curated variant_of');
END;
