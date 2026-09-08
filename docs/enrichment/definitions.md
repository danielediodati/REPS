# Enrichment definitions

What every enrichment vocabulary means, precisely enough that two people
applying it by hand get the same answer. `src/trainer/engine/enrichment.py`
executes the parts a rule can decide; `docs/enrichment/residue.md` applies
the same definitions by hand to the rows it cannot. This is the only copy —
a rule whose reason is not written here is a rule nobody can check, and a
hand decision that disagrees with this document is wrong, not the document.

## Movement pattern

Twelve values. The level at which the engine programs, excludes and counts
— CONTEXT.md — so a boundary drawn wrong here is wrong for every
row that falls on the wrong side of it, silently.

**`horizontal push`** — the load moves away from the torso on a path roughly
parallel to the floor: a bench press, a push-up. **`vertical push`** — the
load moves overhead: a military press, a handstand push-up. A dip sits with
vertical push: the torso stays upright and the load still travels up, not
away from it.

**`horizontal pull`** — the load moves toward the torso on a horizontal
path: a row. **`vertical pull`** — the load moves down toward the torso
from overhead, or the torso moves up to the load: a pulldown, a pull-up, a
rope climb.

**`squat`** — knee-dominant, both legs, descending and rising roughly in
place: a back squat, a leg press, a wall sit. **`hip hinge`** — hip-dominant,
both legs, the torso hinging forward while the knees stay soft: a deadlift,
a good morning, a kettlebell swing, a clean or a snatch (the pull is hip
extension, not the arm — the whole olympic-lift family in this catalog is
hip hinge, regardless of what a naive reading of "the bar ends up overhead"
would suggest). **`single-leg`** — either pattern performed on one leg at a
time, or with the legs staggered so the load is not shared evenly: a lunge,
a split squat, a step-up, a pistol squat.

**`carry`** — a load held while travelling, full stop. Holding a static
position is not a carry, however heavy: a farmer's walk is, a static hold is
`isolation` or a core pattern depending on what it demands. `B5`: `Sled
Overhead Backward Walk` qualifies — a load is held overhead while walking.
`Monster Walk` does not — a band resists the step, nothing is carried.

**`isolation`** — one joint, one muscle group, nothing else in the chain
under meaningful load: a curl, a leg extension, a lateral raise, a calf
raise. The catalog's own `mechanic: isolation` gets this right for 244 of
the 584 strength rows checked by hand against this document, and is trusted
except where a name says otherwise outright — see `B2` below, where
`mechanic: isolation` is wrong for a movement this taxonomy does not
consider isolation at all.

### The trunk: three patterns, not one

**`core anti-extension`** — the trunk holds a fixed position, resisting
lumbar extension, while the limbs or the implement move: a plank, an
ab-wheel rollout, a stir-the-pot. `B3`: a plank held while the limbs move
(a ball pull-in, a spider crawl) is still anti-extension — the demand is
continuous resistance, even though something in the picture is moving.
`B1`: a movement that *produces* spinal flexion (a crunch, a sit-up, a leg
raise brought up dynamically) is not anti-extension, because the trunk is
not resisting anything — it is `isolation`, and it is the largest single
family this document has to place.

`B3` has the same source disagreement `B2` has: `Plank` and
`Suspended_Fallout` are both `mechanic: isolation` in the catalog, and
neither is — a plank is the textbook anti-extension hold. The rule is the
same one: a name that says `plank`, `rollout` or `fallout` outright wins
over a `mechanic` column that was never going to be right for a pattern
this taxonomy does not call isolation.

**`core rotation`** — the trunk produces or resists rotation in the
transverse plane: a cable chop, a Pallof press, a landmine 180, a judo
flip, swinging a kettlebell around the body. `B2a`.

**`core lateral flexion`** — the trunk produces or resists a lean in the
frontal plane, not a turn: a kettlebell windmill, a side plank, a suitcase
carry held on one side, the loaded lean phase of a Turkish get-up. `B2b`.

These two were one pattern for most of this session, first called
`core anti-rotation` and then a merged `core rotation`. Splitting them was
forced by the catalog, not chosen for elegance: `Spell Caster` and
`Landmine 180's` visibly rotate the torso, while `Kettlebell Windmill` and
`Side Bridge` visibly do not — nothing rotates, the body bends sideways. A
name that has to cover both fails half its members, and `movement_pattern`
is prompt surface for the agent from session 4 on, so the difference has to
be visible in the name. TRAINER.md § Appendix carries the same argument.

`B2` also settled a real disagreement with the source data:
`Advanced Kettlebell Windmill` is `mechanic: isolation`, and it is not —
it is a compound trunk-stability movement the source mislabeled. Where a
name says `windmill`, `get-up`, `chop` or `Pallof` outright, that name wins
over a `mechanic` column that was never going to be right for a pattern
this taxonomy does not call isolation.

### Two boundaries that do not get their own pattern

**`B4` — a movement that loads two patterns.** A thruster is a squat and an
overhead press. A muscle-up is a vertical pull and a dip. `movement_pattern`
is one column, so one pattern is picked and the other is lost — a real
limitation, not a design this document is proud of. The rule: **the pattern
the load ends in**, which keeps volume counting honest for the joint that
took the load last. Two exceptions, both overriding the naive reading on
purpose: a kettlebell clean or snatch is `hip hinge` (the hips did the
work; nothing is pressed), and a muscle-up is `vertical pull` (the primary
muscle is `lats`, and the pulling portion is what defines the movement,
against a literal "the dip is the terminal pattern" reading). A second
column to carry the other pattern would spread across every query in the
engine to serve a handful of rows — left as a limitation, deliberately.

**`B6` — no honest answer.** `Battling Ropes` is conditioning and none of
the twelve patterns fits. The field stays null, with the reason on record.
A guessed pattern is worse than a gap: downstream, a null is a state the
schema makes readable, while a wrong pattern is a volume count that stays
wrong and nobody notices.

## Loaded joints

Seven values: `shoulder`, `elbow`, `wrist`, `lumbar spine`, `hip`, `knee`,
`ankle`. A joint is loaded when it bears the resistance through a
meaningful range under load, not merely braced — a plank loads the lumbar
spine (resisting extension is the whole demand) but not the wrist, even
though the wrist is bearing bodyweight, because nothing about the wrist's
range of motion is under load.

For a compound pattern, the joints follow the pattern: every horizontal or
vertical push or pull loads shoulder and elbow; a squat or single-leg
movement loads hip, knee and ankle; a hip hinge loads hip and lumbar spine
(the knee stays soft by definition, so it is not counted); any of the three
trunk patterns loads the lumbar spine and nothing else; a carry loads
shoulder, wrist and lumbar spine (the grip and the trunk are what is really
under demand on a walk, not the legs, which are doing what they always do).

For `isolation`, the joint follows the primary muscle rather than the
pattern, since isolation by definition has no fixed joint set of its own:
chest, shoulders, lats, middle back and traps isolate the shoulder;
triceps and biceps isolate the elbow; forearms isolate the wrist;
abdominals and lower back isolate the lumbar spine; quadriceps isolates the
knee; hamstrings crosses both knee and hip; glutes, adductors and abductors
isolate the hip; calves isolate the ankle. `neck` isolation work loads none
of the seven — none of the seven names the joint a neck movement uses, and
claiming one would be a wrong answer dressed as a right one, so it is left
empty rather than guessed.

## Spinal axial load

Yes or no. Yes when a real external load bears down through the spine
while the lifter is standing and unsupported: a barbell back squat, a
barbell or trap-bar deadlift, a standing overhead press, a loaded carry.
No otherwise — lying, seated, machine-supported or cable work, and every
isolation movement, none of which route a compressive load through the
spine in this catalog's typical entries.

This is a coarse rule and a stated one, not a claim of biomechanical
precision applied row by row: a barbell hip thrust technically loads the
spine while lying, and this document calls it `no` anyway, because the
rule is deliberately keyed on pattern, equipment and standing-or-not — the
three inputs cheap enough to be worth one written judgement rather than 584.

**Known gap, found by the reference set.** "Standing and unsupported"
resolves cleanly for the five upright patterns the rule checks (squat, hip
hinge, single-leg, carry, vertical push) but says nothing about a standing,
unsupported, really-loaded row (`Bent_Over_Barbell_Row`) or a standing
rotational movement (`Spell_Caster`, `Landmine_180's`) — bent-over and
rotational postures the named examples never cover. `trainer enrich derive`
answers `no` for both today, by omission rather than by a considered
reading of this rule; docs/enrichment/reference-set.md marks its own
answers on these rows `?` for the same reason. Left open rather than
guessed at further — a real decision, not a bug, and one for whoever
extends this rule next to make deliberately.

## Required stability

Three values: `high`, `medium`, `low`. High for anything performed on one
leg or one arm, and for any carry — a load in motion under a narrow base of
support. Low for anything a machine or a fixed cable path supports through
its own structure, and for anything performed lying or seated on a bench.
Medium is standing, bilateral, free-weight work in between: a barbell back
squat is more demanding of balance than a leg press and less than a
single-leg deadlift.

**Known gap, found by the reference set.** This document says "one leg *or
one arm*", but `trainer enrich derive` only checks the `single-leg`
*pattern* — it has no way to tell a two-arm row from a one-arm row, because
that distinction is not in any native or enriched column, only in the
name. `Kettlebell_Windmill`, `One-Arm_Dumbbell_Row` and
`One-Legged_Cable_Kickback` are all genuinely unilateral and the rule
answers `medium` for them regardless, disagreeing with the reference set on
thirteen of its seventy rows — most of this field's disagreements trace
to this one gap. A second cause, smaller: `horizontal push`/`horizontal
pull` are ruled `low` unconditionally, which is right for a bench or a
cable but wrong for unsupported bodyweight or free-weight work performed
standing (`Pushups`, `Bent_Over_Barbell_Row` again) — the equipment was not
checked before the pattern decided the answer. Neither is fixed here:
closing them needs either a name-keyword pass for "one-arm"/"one-leg" or a
narrower joints/equipment cross-check, and either is real rule work for
whoever picks this up next, not a one-line patch.

## Setup cost (minutes)

What it takes to get the equipment ready for the set, not how long the set
itself takes. A barbell needs plates found and a rack adjusted (3 minutes).
A machine is close to ready, left loaded by whoever used it last (1
minute). Dumbbells, kettlebells, bands, an exercise ball or a medicine ball
need picking up and nothing more (1 minute). A cable stack needs its pin
moved and often its handle swapped (2 minutes). Bodyweight needs nothing
(0 minutes). An e-z curl bar is a small loaded barbell (2 minutes); `other`
-- sleds, suspension straps, weighted belts, gymnastics rings, ropes -- is
the one bucket with no single real answer, and gets 2 minutes as a rough
middle ground rather than a considered one. This is a coarse,
equipment-keyed estimate, not a per-exercise measurement — TRAINER.md's
duration model (`Σ [ setup + sets × (work + rest) ]`) needs a number in the
right neighbourhood for every row, not a perfect one for a few. The
reference set's own guesses for `other`-equipment rows range from 1 to 3
minutes depending on the specific implement, which is the honest shape of
this bucket: right on average, off on any one row.

## `regression_of` versus `variant_of`

Both point at another exercise id. `variant_of` is symmetric in spirit —
two exercises are the *same movement* under different equipment or a minor
stance change, interchangeable for most purposes: `Arnold Dumbbell Press`
and `Standing Military Press` share `force`, `mechanic` and `category` and
differ only on how the shoulder is loaded through the press, which is
exactly what TRAINER.md's running example calls interchangeable; the Arnold
also exists twice, dumbbell and kettlebell, and both point at one another
as variants. `regression_of` is directional — the row it is set on is
*easier* than the row it points at, usable as a substitution when the
harder version is not available today: a knee push-up is a `regression_of`
a push-up, an assisted pull-up is a `regression_of` a pull-up. A cycle is
never correct: if A is a regression of B, B is not a regression of A, and
no chain of regressions returns to where it started.

Neither field is decided by a rule. Recognising that two named movements
are the same, or that one is easier than the other, needs reading and
judgement a single row's columns cannot supply — `trainer enrich derive`
leaves both null on every row, and the graph is built by hand, from
`instructions`, in ticket 04.

## Provenance

Every field above is written by exactly one of two sources, recorded per
field per exercise: `rule` when `trainer enrich derive` decided it against
the definitions above, `curated` when a person decided it by reading. A
value with no source is a field nothing has enriched yet. `src/trainer/
engine/migrations/0003_enrichment.sql` enforces the vocabulary in SQL, and
enforces that a rule can never overwrite a curated value — a decision made
by reading does not regenerate, and a rule silently overwriting one is the
one failure session 2 cannot afford.
