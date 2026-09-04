# REPS

The language this project reasons in. TRAINER.md § Glossary is the source for
the terms that were settled before this file existed — *movement pattern*,
*admissible set*, *exclusion*, *hypothesis*, *trial*, *conclusion*,
*observation*, *mesocycle*, *volume deficit*, *ramp-in*. What follows is the
vocabulary of time and structure, settled after it.

## Language

### The unit of training

**Workout**:
One training session performed by the user.
_Avoid_: session — in ROADMAP.md that word means a unit of development work,
and the two appear in the same sentence too often to share a name.

**Cycle**:
One complete rotation through the workouts the user trains on. The user
declares how many workouts a rotation holds; it advances when a workout is
performed, never when a date passes.
_Avoid_: week — a week counts days, and a user who trains when they have time
completes a rotation in a span no calendar decides. Also avoid confusing it
with **mesocycle**, which is 4-6 weeks holding a fixed progression scheme and
spans many cycles.

### The structure of a workout

**Muscle group**:
One of the six units a workout's time is allocated to: **chest**, **back**,
**shoulders**, **arms**, **legs**, **core**. Each is a curated grouping of the
catalog's own `primary_muscles` values, decided once and written down —
`lower back` belongs to core, not to back, because it is trunk musculature.
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

**Volume deficit**:
Unchanged from TRAINER.md, with the denominator settled: the difference
between planned and performed volume on a movement pattern, measured over a
**cycle**. It is the signal that a plan is degenerating — an under-served
pattern shows up here rather than being forbidden in advance.

**Movement pattern**:
Unchanged from TRAINER.md — one of the twelve ways a body can be loaded. It
remains the axis **volume** is counted on, and the axis a split's coverage is
stated in. A muscle group answers *what am I training today*; a movement
pattern answers *what is my body accumulating*. They are different questions
and an exercise carries both labels already.
