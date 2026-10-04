-- What a direction varies, as the supervisor names it: a JSON list drawn from
-- exercises, reps and rest. A column, so whether the planner followed it is
-- looked up rather than read out of `changes` (ticket 15.4).
ALTER TABLE directions ADD COLUMN varies TEXT NOT NULL DEFAULT '[]';
