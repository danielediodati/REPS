-- `pattern_state` stops being a table, and the muscle axis gets its
-- counterpart. Both are views, and so is everything else this migration adds.
--
-- **Why a view and not an aggregate.** Two reasons, both already written down.
-- `pattern_history(pattern, cycles)` takes a window of cycles, and one
-- aggregate row per pattern has no cycle dimension to narrow over -- which is
-- what `state.volume_history`'s own docstring said session 5's rows would
-- give it. And `cycle_length` lives in `training.toml`, a file the user edits:
-- change it from 4 to 3 and every historical cycle boundary moves. A view gets
-- that right on the next read; a stored aggregate gets it silently wrong
-- forever, because nothing in the engine watches that file.
--
-- **Nothing here can go stale**, which is the same argument migration 0006
-- made for not storing `unreported` and `log.flags` makes for not storing a
-- flag. A view recomputed against today's rows is the truthful one.
--
-- No row is moved. `pattern_state` has never held one -- session 2 created it
-- empty and nothing has written to it since -- so the table is dropped rather
-- than migrated out of.

DROP TABLE pattern_state;

-- CONTEXT.md § Unreported, executable: a prescribed workout is unreported once
-- a later one has been performed and it still has no report.
--
-- Deliberately not a third value of `workouts.state` -- migration 0006 says
-- why: storing it would mean something has to go and set it, and nothing
-- does. Read here, it is right on the day it becomes true and needs nobody to
-- have run anything.
--
-- Nothing closes it and nothing assumes it happened. It contributes no volume
-- (its rows are `prescribed`, and the performed side of the deficit counts
-- only performed ones), which is the one direction the error must never run:
-- assuming adherence here would fabricate workouts at exactly the moment
-- training stopped.
CREATE VIEW unreported_workouts AS
SELECT
    w.id            AS workout_id,
    w.prescribed_on AS prescribed_on
FROM workouts AS w
WHERE w.state = 'prescribed'
  AND EXISTS (
      SELECT 1 FROM workouts AS later
      WHERE later.state = 'performed'
        AND later.performed_on > w.prescribed_on
  );

-- The one join, written once: a workout, its blocks, the exercises in them,
-- and the catalog row each exercise is. Every view below is a projection of
-- this one, so the day a phase, a table or a key column moves, it moves here.
--
-- **Both phases, on purpose.** The volume deficit is the difference between
-- what was planned and what was done (ADR-0001), so a view that kept only the
-- performed rows could not answer it -- and two views over the same join,
-- one per phase, would be the second contract this session was promised it
-- would not need. `phase` is a column; every reader says which phase it means.
--
-- `dated_on` is the day the row belongs to: when it was performed, or, for a
-- workout that never was, the day it was prescribed for. It is what every
-- window is drawn against, and `COALESCE` is safe in both directions because
-- migration 0006's CHECKs make one of the two dates present in every state.
--
-- `rounds` sits on the block and is repeated on each of its exercises,
-- deliberately: CONTEXT.md § Volume counts a round whole to every exercise in
-- the block. Two exercises for four rounds is four rounds of *each*.
CREATE VIEW workout_volume AS
SELECT
    w.id                                      AS workout_id,
    b.phase                                   AS phase,
    COALESCE(w.performed_on, w.prescribed_on) AS dated_on,
    b.position                                AS block_position,
    x.position                                AS position,
    x.exercise_id                             AS exercise_id,
    e.movement_pattern                        AS movement_pattern,
    e.primary_muscles                         AS primary_muscles,
    b.rounds                                  AS rounds,
    x.load_kg                                 AS load_kg,
    -- Whether this row is still waiting to happen: a workout prescribed and
    -- neither performed nor overtaken. It is the one prescribed row that is
    -- **not** a deficit -- nobody has failed to do a workout they are about
    -- to do -- and `trainer plan` writes one every time it runs, so counted
    -- as one the planner would see its own last prescription as a shortfall
    -- and add volume to make up for volume already scheduled.
    --
    -- Read off `unreported_workouts` rather than restated, so *the workout
    -- has had its chance* has one definition and the deficit and the
    -- unreported list can never disagree about which rows it covers.
    CASE
        WHEN w.state = 'performed' THEN 0
        WHEN EXISTS (SELECT 1 FROM unreported_workouts AS u
                     WHERE u.workout_id = w.id) THEN 0
        ELSE 1
    END                                       AS outstanding
FROM workouts AS w
JOIN workout_blocks AS b ON b.workout_id = w.id
JOIN workout_exercises AS x ON x.block_id = b.id AND x.phase = b.phase
JOIN exercises AS e ON e.id = x.exercise_id;

-- The coarser of the two axes ADR-0001 counts volume on, keeping the name the
-- table had: `state._SOURCES` names a table and a key column, and a view drops
-- into both.
--
-- An exercise the enrichment has no pattern for contributes to no pattern,
-- rather than to a `(none)` bucket nobody can act on. That is a real state and
-- not an oversight: the catalog's stretching and cardio rows are never
-- enriched, and `enrich check` is what reports the strength rows that are
-- still missing one.
CREATE VIEW pattern_state AS
SELECT
    movement_pattern AS movement_pattern,
    phase            AS phase,
    workout_id       AS workout_id,
    dated_on         AS dated_on,
    block_position   AS block_position,
    position         AS position,
    exercise_id      AS exercise_id,
    rounds           AS rounds,
    load_kg          AS load_kg,
    outstanding      AS outstanding
FROM workout_volume
WHERE movement_pattern IS NOT NULL;

-- The finer axis, and the only one that can tell an arm workout of curls from
-- a balanced one -- biceps, triceps and forearms are all `isolation` on the
-- pattern axis (ADR-0001).
--
-- One row per muscle per exercise: a round counts whole to *each* of the
-- exercise's primary muscles, nothing is divided, because the question is what
-- is accumulating and not how the effort splits. `primary_muscles` is the
-- catalog's own JSON array, exploded the way `admissible_set` explodes
-- `loaded_joints` -- never a copy of the seventeen values kept anywhere.
--
-- Secondary muscles are not counted. CONTEXT.md's axis is `primary_muscles`,
-- and counting a bench press as chest *and* triceps at full weight would put
-- more volume in the ledger than the body did.
CREATE VIEW muscle_state AS
SELECT
    muscle.value AS muscle,
    v.phase      AS phase,
    v.workout_id AS workout_id,
    v.dated_on   AS dated_on,
    v.block_position AS block_position,
    v.position   AS position,
    v.exercise_id AS exercise_id,
    v.rounds     AS rounds,
    v.load_kg    AS load_kg,
    v.outstanding AS outstanding
FROM workout_volume AS v
JOIN json_each(v.primary_muscles) AS muscle;

-- Where `state.last_performed_load` reads. It is a view rather than the base
-- one because two things have to be true of every row it sees and neither is
-- expressible in `_LoadSource`'s column names: the row is performed --
-- a plan prescribes no load, and a prescribed row read as one would answer
-- with a number nobody lifted -- and it carries a load at all, so that a
-- bodyweight session does not hide the last workout that did.
--
-- `performed_on` is `dated_on` renamed, because on a performed row they are
-- the same column and the name a caller reads should say which it is.
-- `workout_id` is carried for the tie-break: two workouts on one day are
-- ordered by which was written second, so *the last load* is a fact and not a
-- coin toss.
CREATE VIEW performed_loads AS
SELECT
    exercise_id  AS exercise_id,
    load_kg      AS load_kg,
    dated_on     AS performed_on,
    workout_id   AS workout_id
FROM workout_volume
WHERE phase = 'performed' AND load_kg IS NOT NULL;
