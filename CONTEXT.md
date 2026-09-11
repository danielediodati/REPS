# REPS — glossary

The only glossary. Every load-bearing term is defined here, once, and the other documents use these words without redefining them.

## The unit of training

**Workout**: one training session. It is **prescribed** when a plan is emitted for it and **performed** once it is reported. A performed workout need not have been prescribed.
_Avoid_: session, which in ROADMAP.md means a unit of development work.

**Unreported**: a prescribed workout with no report after a later workout has been performed. It contributes no volume and is never assumed done. Whether to ask about it is the agent's call.

**Cycle**: one complete rotation through the workouts being trained. The user declares its length. It advances when a workout is performed, never when a date passes.
_Avoid_: week; mesocycle.

**Mesocycle**: 4-6 weeks with a fixed progression scheme and a fixed goal. It is the unit a split holds for.

**Ramp-in**: a workout on the normal scheme with reduced volume and loads chosen by feel, used when returning from a break.

## The structure of a workout

**Muscle group**: one of the six units a workout's time is divided among: chest, back, shoulders, arms, legs, core. Each is a curated grouping of the catalog's seventeen muscles, defined only in `src/trainer/data/muscle-groups.md`. It allocates time and nothing else; volume is never counted on it.
_Avoid_: muscle, which means one of the seventeen raw values.

**Split**: how the muscle groups are distributed across the workouts of a cycle. It is chosen, with a reason, and never computed.
_Avoid_: routine, programme.

**Allocation**: how one workout's minutes are divided among its groups. Chosen per workout; there are no fixed ratios.
_Avoid_: budget, which is the time available before it is divided.

## What a plan is made of

**Block**: one or more exercises performed together for a number of rounds, with rest after each round. A plan is a sequence of blocks.
- One exercise: straight sets.
- Two exercises: a superset.
- More: a circuit.

_Avoid_: set, which is one round of one exercise.

**Round**: one pass through every exercise in a block.

**Rest**: the recovery **prescribed** after a round. It travels in the plan and is recorded. The bands in TRAINER.md are a reference, never imposed.

**Timed work**: work prescribed as a duration rather than reps, such as a carry, a walk or a plank.
_Avoid_: cardio, which is a catalog `category`.

## What a report says

**Report**: what the user says about a workout they performed, in their own words.

**Adherence**: the assumption that anything a report does not mention was done as prescribed. It holds inside one report only.

**Deviation**: the difference between what was prescribed and what was done. It is all a report has to carry.

**Skipped**: an exercise the user says they did not do. The document cannot express this yet, because a block has at least one round. So the honest emission is empty, and adherence fills it in. Log-set row U7 checks only that nothing is invented.

**Provenance**: how a performed value got there, recorded per field.
- *reported*: the user said it.
- *assumed*: filled in by adherence, so it must equal the prescription.
- *asked*: confirmed by a question.

**Flag**: something the engine noticed about a performed workout and recorded anyway. Examples: an exercise nobody prescribed, an exercise under an active exclusion, an unplanned workout, an unexplained jump in load. Flags are computed when the workout is read, never stored. A report is a fact, and it is never refused for what the user did.
_Avoid_: warning, error.

**Pending question**: an `interrupt()` waiting for the user's answer. It can wait for days without losing the thread.

## What volume is counted on

**Movement pattern**: the class of movement, not the exercise. There are twelve: horizontal push, vertical push, horizontal pull, vertical pull, squat, hip hinge, single-leg, core anti-extension, core rotation, core lateral flexion, carry, isolation. The three core patterns:
- `core anti-extension` resists lumbar extension: plank, ab-wheel rollout.
- `core rotation` produces or resists rotation: cable chop, Pallof press.
- `core lateral flexion` produces or resists a sideways lean: windmill, side plank, suitcase carry.

**Muscle**: one of the catalog's seventeen `primary_muscles` values. It is the finer volume axis, and the only one that can tell an arm workout of curls from a balanced one.

**Volume**: **rounds performed**. A round counts whole toward the exercise's pattern and toward each of its primary muscles. A block of two exercises for four rounds counts as four rounds of each.

**Volume deficit**: planned volume minus performed volume over a cycle, on both axes. It is the signal that a plan is degenerating (ADR-0001).

## What limits a plan

**Constraint**: anything that limits a plan: a preference, time, equipment, boredom, a niggle. Most constraints are not medical.

**Exclusion**: a hard boundary, used only for safety. It removes a movement pattern, or every exercise loading a given joint, until a re-test date. A preference never becomes an exclusion.
_Avoid_: excluding an exercise id. There is no third granularity.

**Preference**: something the user would rather not do. It stays in the admissible set, but a plan that includes it has to say so.

**Admissible set**: the exercises compatible with the exclusions, today's equipment, the time available and the muscle groups. The agent chooses inside it and never widens it.

**Triage**: the interview about movements, never about symptoms. It produces exclusions, not diagnoses.

## What the system learns

**Hypothesis**: a falsifiable statement about the user. It is admissible only if a trial exists that can discriminate it.

**Trial**: a change to the plan that holds everything fixed except one variable. It has a duration, and its outcome comes back in.

**Conclusion**: a fact about this person that has a source: something they said, or a trial outcome. It has a state and can be retired.

**Observation**: a fact about the agent, written by the supervisor from the trajectory. It points at a measure.
