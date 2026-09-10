# REPS

The language this project reasons in — **the** glossary, and the only one.
Every term the project uses in a load-bearing sense is defined here once;
TRAINER.md and ROADMAP.md use these words and never redefine them. Where a term
carries an argument longer than its definition, the definition stays here and
the argument stays where it is made: the twelve movement patterns are
enumerated here and argued in TRAINER.md § Appendix, the two axes volume is
counted on in ADR-0001.

## Language

### The unit of training

**Workout**:
One training session, in one of two states. It is **prescribed** when a plan is
emitted for it, and **performed** once it has been reported. A performed
workout need not have been prescribed — training nobody planned is still
training, and it is recorded like any other.
_Avoid_: session — in ROADMAP.md that word means a unit of development work,
and the two appear in the same sentence too often to share a name.

**Unreported**:
What a prescribed workout is called once a later one has been performed and it
still has no report. Nothing closes it automatically and nothing assumes it
happened: it contributes no volume, the engine states the fact, and whether to
ask about it is the agent's call.
_Avoid_: treating it as adherence — assuming a silent workout was performed
inflates the volume at exactly the moment training stopped, which is the one
direction the error must never run.

**Cycle**:
One complete rotation through the workouts the user trains on. The user
declares how many workouts a rotation holds; it advances when a workout is
performed, never when a date passes.
_Avoid_: week — a week counts days, and a user who trains when they have time
completes a rotation in a span no calendar decides. Also avoid confusing it
with **mesocycle**, below, which spans many cycles.

**Mesocycle**:
4-6 weeks with a fixed progression scheme and a fixed goal. It is the boundary
at which the agent re-evaluates its policies, and the unit a **split** holds
for.

**Ramp-in**:
A workout on the normal scheme with reduced volume and loads guided by feel,
used on returning from a break to realign the loads without estimating them.

### The structure of a workout

**Muscle group**:
One of the six units a workout's time is allocated to: **chest**, **back**,
**shoulders**, **arms**, **legs**, **core**. Each is a curated grouping of the
catalog's own `primary_muscles` values, decided once and written down in
`src/trainer/data/muscle-groups.md`, which carries the reason for every one of
the seventeen assignments — `lower back` belongs to core, not to back, because
it is trunk musculature, and `neck` belongs to no group at all. **That file is
the only place the six names exist**: everything that needs the vocabulary
reads it from there, never from a copy.
Allocating time is **all** it does: volume is never counted on this axis,
because `arms` erases exactly the biceps/triceps distinction the muscle axis
exists to keep.
_Avoid_: body part, muscle — a *muscle* is one of the catalog's seventeen raw
values, a *muscle group* is one of these six.

**Split**:
How the muscle groups are distributed across the workouts of one cycle.
**Chosen** and recorded with the reason it was chosen — never computed from the
cycle's length. It holds for a whole mesocycle; nobody re-chooses it per
workout.
_Avoid_: routine, programme.

**Allocation**:
How one workout's minutes are divided among the muscle groups it trains. The
proportions are chosen for that workout, not fixed by the number of groups —
*60-40* is what one two-group workout might look like, not a rule, and it means
nothing once a workout holds three.
_Avoid_: budget — that word is the time available, before anything is divided.

### What a plan is made of

**Block**:
One or more exercises performed together for a number of rounds, with the rest
taken **after each round**. A block holding one exercise is straight sets; two
is a superset, three a triset, more a circuit. It is the unit a plan is a
sequence of, and the unit duration is computed over.
_Avoid_: set — a set is one round of one exercise inside a block.

**Round**:
One pass through every exercise in a block. For straight sets a round is a set;
for a superset it is one trip through both exercises.
_Avoid_: rep, lap.

**Rest**:
The recovery **prescribed** after a round, carried in the plan and recorded
with the performed workout. TRAINER.md's three bands — strength 2.5-3 min,
hypertrophy 90-120 s, isolation 60 s — are a reference whoever plans may
consult, never a value the engine imposes: a deliberately short rest is a
legitimate prescription, and the point of recording it is that progression
knows what it was measured against.
_Avoid_: recovery, pause.

**Timed work**:
Work whose prescription is a duration rather than a number of reps — a light
walk, a carry, a sled push. It is an exercise like any other and it lives in a
block like any other; only its work term differs.
_Avoid_: cardio — that is one of the catalog's own `category` values and names
where a row came from, not how it is prescribed.

### What a report says

**Report**:
What the user says about a workout they performed. It is prose, in whatever
words they used, and it is the only thing the system asks of them after
training.

**Adherence**:
The assumption that whatever a report does not mention was performed as
prescribed. It holds **inside one report** and nowhere else.
_Avoid_: stretching it across workouts — a prescribed workout with no report
is unreported, never adherent.

**Deviation**:
The difference between what was prescribed and what was done, which is all a
report actually has to carry. Logging is by deviation: adherence is the
default and only the difference is said.

**Provenance**:
Which of three ways a value in a performed workout got there — *reported* (the
user said it), *assumed* (the adherence default), or *asked* (confirmed in a
clarifying turn). It is carried per field, which is what makes *«assume
adherence and flag the uncertainty»* a column rather than a slogan. The same
discipline the enrichment fields already use, where a value a rule derived and
a value a person decided are not worth the same.
*assumed* means **as prescribed**, so a document is refused for marking a value
*assumed* that the prescription does not say — there being no prescription
behind the workout at all, or the number simply not being the prescribed one.
Both are statements about the document rather than about the training: the
column exists to separate a number the user gave from one the system supplied,
and a wrong *assumed* is that column lying in the one direction nothing
downstream can catch.

**Flag**:
Something the engine noticed about a performed workout and **recorded
anyway**: an exercise nobody prescribed, an exercise under an active
exclusion, a workout with no prescribed counterpart, a load that moved further
than the recorded history explains. It is the whole of what a report can be
told about what the user *did*, because a report is a fact and a fact is never
refused — what a report is refused for is only ever a statement about the
document, like an exercise id the catalog does not have.
It is computed when the report is read and printed beside the row it is about;
it is not a column. Nothing stored can go stale, and a flag recomputed
tomorrow against tomorrow's exclusions is the truthful one.
_Avoid_: warning, error — neither is a thing that gets written to the
database, and both read as something the user should have done differently.

### What volume is counted on

**Movement pattern**:
The class of movement, not the exercise. Twelve values: horizontal push,
vertical push, horizontal pull, vertical pull, squat, hip hinge, single-leg,
core anti-extension, core rotation, core lateral flexion, carry, isolation. It
is the level at which you program, exclude and count, and the coarser of the
two axes volume is counted on.

- `core anti-extension` — the trunk holds a fixed position while resisting
  lumbar extension: a plank, an ab-wheel rollout.
- `core rotation` — the trunk produces or resists rotation in the transverse
  plane: a cable chop, a Pallof press, a landmine 180.
- `core lateral flexion` — the trunk produces or resists a lean in the frontal
  plane: a kettlebell windmill, a side plank, a suitcase carry held on one
  side.

Why those three are three and not two is TRAINER.md § Appendix.

A muscle group answers *how is today's time divided*; a movement pattern and a
muscle each answer *what is my body accumulating*, at different resolutions.
An exercise carries all three labels already.

**Muscle**:
One of the catalog's own seventeen `primary_muscles` values — `biceps`,
`quadriceps`, `lower back`. The finer of the two axes volume is counted on,
and the only one that can tell an arm workout of curls from a balanced one.
_Avoid_: muscle group — that is one of the six, and it is for allocating time,
not for measuring.

**Volume**:
What a body has accumulated, counted in **rounds performed** — the unit the
word already means in strength programming. Not reps, not rounds times reps,
not tonnage: a round needs no load, so bodyweight work counts like everything
else, and timed work needs no special case. A block of two exercises for four
rounds is four rounds of *each*, not two. Every round counts whole to the
exercise's movement pattern and whole to each of its primary muscles; nothing
is divided, because the question is what is accumulating and not how the
effort splits.

**Volume deficit**:
The difference between planned and performed volume, measured over a **cycle**,
on two axes — per movement pattern and per muscle. It absorbs four different
mechanisms — substitution, a cut for time, a shortened workout, a skipped
workout — into a single quantity, and it is the signal that a plan is
degenerating: an under-served pattern or muscle shows up here rather than being
forbidden in advance. Two axes because neither catches the other's failure —
see ADR-0001.

### What limits a plan

**Constraint**:
Anything that limits the plan: preference, time, equipment, boredom, a niggle.
Most of it is not medical.

**Exclusion**:
A **hard** engine boundary, reserved for safety: a movement pattern, or
everything loading a named joint, that cannot be prescribed, with a re-test
date. Those are the two granularities a person can actually report at. A
preference never becomes an exclusion — otherwise you wall off a pattern
forever and nobody will be able to reopen it.
_Avoid_: an exclusion on an exercise id — there is no third granularity.

**Admissible set**:
The answer to a question the agent chose to ask the engine: the exercises
compatible with the exclusions, today's equipment and the time available. The
agent chooses inside it; it never widens it.

**Triage**:
The interview about *movements*, never about clinical symptoms: *does it hurt
when you press overhead? at what range? under load or unloaded too?* It
produces exclusions, not diagnoses. It is one of the inputs, not the main one.

### What the system learns

**Hypothesis**:
A falsifiable statement about this user, formulated by the agent. Admissible
only if a trial exists that discriminates it.

**Trial**:
A modification to the plan designed to knock down a hypothesis: it holds every
variable fixed but one, it has a duration, and it has an outcome that comes
back in.

**Conclusion**:
A fact **about this person**, with a source — something they said, or the
outcome of a trial. It has a state, and it can be retired.

**Observation**:
A fact **about the agent**, written by the supervisor looking at the
trajectory.
