-- The workout, in its two states, and the two child tables that carry a
-- phase.
--
-- CONTEXT.md § The unit of training settles the states: a workout is
-- `prescribed` when a plan is emitted for it and `performed` once it has been
-- reported. `unreported` is deliberately not a third value -- it is a
-- *reading* of a prescribed workout that a later one has overtaken, and
-- storing it would mean something has to go and set it, which nothing does.
-- A view computes it in session 5's issue 03; no column here can go stale.
--
-- A workout transitions in place. Its children do not: `workout_blocks` and
-- `workout_exercises` hold **both phases side by side**, because deviation is
-- the difference between them. Overwrite the prescribed rows when a report
-- arrives and the deviation stops being computable the moment it is recorded.
-- A workout nobody planned has only performed rows; a workout never reported
-- has only prescribed ones.
--
-- What is deliberately not here: `location` and `equipment overrides`, which
-- TRAINER.md § Persistent state lists on `workouts` and nothing in session 5
-- reads or writes; and the plan's `despite` acknowledgements, because a
-- preference has nowhere to live until `conclusions` in session 8 -- `plan.py`
-- already states that preferences are per run for exactly that reason.

-- One row per workout. `prescribed_on` and `performed_on` are ISO-8601 dates
-- (`YYYY-MM-DD`), which sort and compare lexicographically the way they
-- compare as dates -- the same choice `exclusions.retest_date` already made.
--
-- The three CHECKs make `state` a reading of the dates rather than a second,
-- independently settable fact:
--
--   * performed <=> there is a date it was performed on;
--   * a prescribed workout was prescribed on some day;
--   * a performed workout need not have been -- training nobody planned is
--     still training, and it arrives with `prescribed_on` NULL.
--
-- `report` is the user's own words, verbatim, and the only prose this schema
-- keeps. It is what session 5's issue 02 writes; a prescribed workout has
-- nothing to say yet, so the CHECK keeps it empty there.
CREATE TABLE workouts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    state         TEXT NOT NULL CHECK (state IN ('prescribed', 'performed')),
    prescribed_on TEXT,
    performed_on  TEXT,
    report        TEXT,
    CHECK ((state = 'performed') = (performed_on IS NOT NULL)),
    CHECK (state = 'performed' OR prescribed_on IS NOT NULL),
    CHECK (state = 'performed' OR report IS NULL)
);

CREATE INDEX workouts_performed_on ON workouts (performed_on);

-- One block, in one phase, mirroring the plan document's own shape: the
-- exercises it holds (in `workout_exercises`), how many rounds it is
-- performed for, and the rest taken **after each round**. ADR-0002: one
-- exercise is straight sets, two a superset, more a circuit, and nothing
-- records which -- the shape is already described by how many exercises the
-- block holds.
--
-- `reason` is the agent's justification, required on the wire (`PlanBlock`)
-- and required here too, so a persisted plan is still the document that was
-- rendered: a stored block with no reason reads back as a plan whose *why*
-- line is empty, which is the prose-beside-the-plan failure the wire shape
-- exists to prevent, arriving a week later through the database. A performed
-- block has none instead: nobody justifies what already happened.
--
-- Provenance is per field, the way migration 0003 does it for enrichment: a
-- `_source` column beside the value it describes, holding `reported`,
-- `assumed` or `asked` and nothing else. It is NULL on the prescribed phase,
-- where nothing has been reported yet, and required on the performed phase,
-- where every value got there one of exactly those three ways. That biconditional
-- is what makes «assume adherence and flag the uncertainty» a query rather
-- than a slogan: `WHERE rounds_source = 'assumed'` is the list of numbers the
-- user never actually said.
--
-- RPE is nullable and carries no `_source`. It is never asked for -- if the
-- user says it, it is recorded; if they do not, the column stays empty -- so
-- `assumed` and `asked` cannot arise for it and a provenance column would
-- have one legal value. Session 7's autoregulated scheme is its only
-- consumer, and a column that is empty most of the time is information about
-- which schemes are available, not a fault.
--
-- `UNIQUE (id, phase)` exists for the composite foreign key below, not for
-- this table: it is what lets an exercise row's phase be proven equal to its
-- block's rather than merely written that way.
CREATE TABLE workout_blocks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id    INTEGER NOT NULL REFERENCES workouts (id) ON DELETE CASCADE,
    phase         TEXT NOT NULL CHECK (phase IN ('prescribed', 'performed')),
    position      INTEGER NOT NULL CHECK (position >= 1),
    rounds        INTEGER NOT NULL CHECK (rounds >= 1),
    rounds_source TEXT CHECK (rounds_source IS NULL
                              OR rounds_source IN ('reported', 'assumed', 'asked')),
    rest          INTEGER NOT NULL CHECK (rest >= 0),
    rest_source   TEXT CHECK (rest_source IS NULL
                              OR rest_source IN ('reported', 'assumed', 'asked')),
    reason        TEXT,
    rpe           REAL CHECK (rpe IS NULL OR (rpe >= 1 AND rpe <= 10)),
    UNIQUE (workout_id, phase, position),
    UNIQUE (id, phase),
    CHECK (phase = 'performed'
           OR (rounds_source IS NULL AND rest_source IS NULL AND rpe IS NULL
               AND reason IS NOT NULL)),
    CHECK (phase = 'prescribed'
           OR (rounds_source IS NOT NULL AND rest_source IS NOT NULL AND reason IS NULL))
);

CREATE INDEX workout_blocks_workout ON workout_blocks (workout_id, phase);

-- One exercise inside a block, and how much of it: an amount and the unit it
-- counts, never a `reps` beside a `seconds`. `duration.BlockItem` refuses both
-- and neither, and `plan.Prescription` is already shaped this way on the wire
-- -- *«3 rounds of 10 reps of walking»* means nothing, and a schema that
-- cannot express it needs no rule saying so.
--
-- `phase` is repeated here rather than read off the parent block because a
-- CHECK cannot reach into another table, and the provenance rule below is the
-- one this ticket is judged on. The composite foreign key is what keeps the
-- repetition honest: `(block_id, phase)` has to match a block's own
-- `(id, phase)`, so a performed exercise cannot be filed under a prescribed
-- block.
--
-- `load_kg` is nullable in both phases: a plan does not prescribe load, and a
-- pull-up performed does not have one. Its `_source` is tied to the value
-- rather than to the phase -- a provenance describing nothing is not a
-- provenance -- while a load that *was* performed always says how it got here.
CREATE TABLE workout_exercises (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id       INTEGER NOT NULL,
    phase          TEXT NOT NULL CHECK (phase IN ('prescribed', 'performed')),
    position       INTEGER NOT NULL CHECK (position >= 1),
    exercise_id    TEXT NOT NULL REFERENCES exercises (id),
    unit           TEXT NOT NULL CHECK (unit IN ('reps', 'seconds')),
    amount         INTEGER NOT NULL CHECK (amount >= 1),
    amount_source  TEXT CHECK (amount_source IS NULL
                               OR amount_source IN ('reported', 'assumed', 'asked')),
    load_kg        REAL CHECK (load_kg IS NULL OR load_kg >= 0),
    load_kg_source TEXT CHECK (load_kg_source IS NULL
                               OR load_kg_source IN ('reported', 'assumed', 'asked')),
    UNIQUE (block_id, position),
    FOREIGN KEY (block_id, phase) REFERENCES workout_blocks (id, phase) ON DELETE CASCADE,
    CHECK (phase = 'performed'
           OR (amount_source IS NULL AND load_kg_source IS NULL)),
    CHECK (phase = 'prescribed' OR amount_source IS NOT NULL),
    CHECK ((load_kg IS NULL AND load_kg_source IS NULL)
           OR (load_kg IS NOT NULL AND (phase = 'prescribed' OR load_kg_source IS NOT NULL)))
);

CREATE INDEX workout_exercises_exercise ON workout_exercises (exercise_id);

-- Nothing will ever write it.
--
-- `pain` was on this table from migration 0004, when TRAINER.md still had a
-- medical trigger reading an accumulated pain state. ROADMAP.md § Declared
-- deviations carries the reversal: a 0-10 scale is the `required_rom` failure
-- applied to the most delicate thing the system touches -- nobody's 4 is
-- anybody else's, or their own next month -- and an escalation threshold built
-- on it is false precision used as a safety boundary. Pain is prose the agent
-- reads, and its only structured outcome is an **exclusion** the user
-- confirms, which `exclusions` already holds at both the granularities that
-- matter.
--
-- Dropped rather than left empty: session 5's issue 03 turns `pattern_state`
-- into a view over the rows above, and a column no view could compute would
-- have to be invented there or quietly disappear without anyone deciding.
ALTER TABLE pattern_state DROP COLUMN pain;
