# The residue: the rows the columns cannot answer

The `category: strength` rows `enrichment.derive_movement_pattern` leaves undecided,
decided by reading each exercise's own `instructions`. **Every decision quotes the
sentence that produced it.** That is the whole point of the file: a year from now a
value here can be checked in seconds by someone who was not present, without opening
the source data.

**Reconciled against the real rules, not the throwaway ones that first measured this
residue.** The draft that scoped this ticket read 60 rows by hand against a throwaway
rule set over `name`, `primary_muscles`, `force` and `mechanic`. `enrichment.py`'s real
rules — the ones ticket 02 shipped — close 22 of those 60 outright: `Barbell_Deadlift`,
`Weighted_Pull_Ups` and the rest of ROADMAP.md's named gaps, plus every kettlebell
clean/snatch, both windmills, `Cable_Internal_Rotation`, `Muscle_Up` and its kipping
variant, `Reverse_Hyperextension`, `Rope_Climb`, `Seated_Leg_Tucks` and `Side_Bridge`.
Every one of the 22 lands on **exactly the pattern this file already gave it** — no
boundary ruling changed between the draft and `docs/enrichment/definitions.md` — so
none of the twenty-two needed re-deciding, only removing. `docs/enrichment/definitions.md`
already carries the boundary rules those 22 rows and the 38 below both read from (B1-B6);
nothing here overrides it.

**38 rows are left**, all of them already decided in the draft. This file keeps their
decisions and drops the 22 the rule now reaches — `enrich derive` never leaves a row
this file also claims, so a rule and a curated value are never fighting over the same
id.

The table below is in `docs/enrichment/reference-set.md`'s own format — `id | name |
equipment | pattern | joints | axial | stability | setup | +/- | note` — rather than
the narrower one this file first shipped with, so `trainer enrich curated` can load it
with the exact parser `trainer enrich check` already uses for the reference set. Only
`movement_pattern` was read from prose; `loaded_joints`, `spinal_axial_load`,
`required_stability` and `setup_cost_min` are what `enrichment.derive_loaded_joints` /
`derive_spinal_axial_load` / `derive_required_stability` / `derive_setup_cost_min`
compute from that pattern and the row's own equipment — `docs/enrichment/
definitions.md` is explicit that those four are "functions of pattern and equipment
once the pattern is fixed," never a second independent reading, and `trainer enrich
curated` writes all five with `curated` provenance so a rule never touches these rows
again (`enrichment.run` skips a row entirely the moment its `movement_pattern_source`
is `curated` — it does not fall through to the other four).

`uncertain` means the twelve patterns do not cleanly contain the movement and the value
is the closest of twelve, not a confident answer. None of these 38 rows are in
`docs/enrichment/reference-set.md`, so nothing else in session 2 scores them — the
`?` column is the only review list they get.

## Boundary rules the reading forced

These are decisions about the taxonomy, not about single rows, and each one settles a
whole family. `docs/enrichment/definitions.md` carries all six as the authoritative
copy; they are repeated here only as the key to reading the `note` column below.

| # | boundary | ruling | why |
|---|---|---|---|
| B1 | dynamic spinal flexion — crunch, sit-up, reverse crunch, leg pull-in, hanging knee raise | **`isolation`** | `core anti-extension` resists a movement rather than producing one, and none of the other patterns fit a movement that dynamically flexes the spine either |
| B2a | trunk work that turns the body — chops, judo-flips, landmine swings, pirate-ship swings | **`core rotation`** | the trunk produces or resists motion in the transverse plane |
| B2b | trunk work that leans the body under a fixed or shifting load — windmills, side planks, the loaded lean phase of a get-up | **`core lateral flexion`** | the trunk produces or resists motion in the frontal plane, not the transverse one |
| B3 | plank-based, with the limbs moving — ab rollout, ball pull-in, spider crawl, butt-ups | **`core anti-extension`** | the trunk is holding a plank throughout and the limbs are what moves |
| B4 | a movement that loads two patterns — thruster, muscle-up, jammer, split snatch | **the pattern the load ends in**, with a note | `movement_pattern` is one column; picking the terminal pattern keeps volume counting honest for the joint that took the load last |
| B5 | a loaded carry | **`carry` requires holding a load while travelling** | a band or a static hold does not qualify |
| B6 | no honest answer | **null, with the reason** | a wrong pattern is a volume count that stays wrong and nobody notices; a null is a state the schema makes readable |

## The decisions

### Isolation (16)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Air_Bike` | Air Bike | body only | isolation | lumbar spine | N | M | 0 | | *"Bring your right elbow close to your left knee by crunching to the side"* — B1 |
| `Bottoms_Up` | Bottoms Up | body only | isolation | lumbar spine | N | M | 0 | | *"tuck the knees toward your chest... Rotate and elevate your pelvis to raise your glutes from the floor"* — B1, a dynamic reverse-crunch/hip-raise |
| `Cocoons` | Cocoons | body only | isolation | lumbar spine | N | M | 0 | | *"flex the spine, bringing your arms back over your head to perform a simultaneous crunch motion"* — B1 |
| `Elbow_to_Knee` | Elbow to Knee | body only | isolation | lumbar spine | N | M | 0 | ? | *"flexing the spine and rotating your torso to bring the left elbow to the right knee"* — B1 and B2a both reach for it; flexion is the larger half, and `Air_Bike` above is the same movement decided the same way |
| `Flat_Bench_Leg_Pull-In` | Flat Bench Leg Pull-In | body only | isolation | lumbar spine | N | M | 0 | | *"Bend your knees and pull your upper thighs into your midsection"* — B1 |
| `Flutter_Kicks` | Flutter Kicks | body only | isolation | hip | N | M | 0 | | *"Squeeze your glutes and hamstrings and straighten the legs until they are level with the hips"* — single-joint hip extension held near static, no pattern of the twelve but isolation fits the joint table |
| `Glute_Kickback` | Glute Kickback | body only | isolation | hip | N | M | 0 | | *"lift up your right leg until the hamstrings are in line with the back"* — one joint, glutes isolate hip |
| `Hanging_Pike` | Hanging Pike | body only | isolation | lumbar spine | N | M | 0 | ? | *"Pull your legs up as you exhale until you almost touch your shins with the bar"* — B1. The lats hold an isometric that B3 would notice |
| `Hip_Extension_with_Bands` | Hip Extension with Bands | bands | isolation | hip | N | M | 1 | | *"move the resisted leg back as far as you can while keeping the knee straight"* — single-joint hip extension against a band |
| `Hip_Flexion_with_Band` | Hip Flexion with Band | bands | isolation | knee | N | M | 1 | | *"raise your knee up to 90 degrees and pause"* — single-joint hip flexion; the source's own `primary_muscles: quadriceps` puts the joint at knee per the isolation table, a coarse rule this row does not override |
| `Kettlebell_Halo` | Kettlebell Halo | kettlebells | isolation | shoulder | N | M | 1 | ? | *"move the kettlebell up past one ear and around behind your head"*, trunk held still throughout — shoulder-girdle work; nothing else of the twelve applies |
| `Leg_Pull-In` | Leg Pull-In | body only | isolation | lumbar spine | N | M | 0 | | *"Bend your knees and pull your upper thighs into your midsection"* — B1, same movement as `Flat_Bench_Leg_Pull-In` |
| `One-Arm_Medicine_Ball_Slam` | One-Arm Medicine Ball Slam | medicine ball | isolation | lumbar spine | N | M | 1 | ? | *"flex the shoulders, spine, and hips to throw the ball hard into the ground"* — B1 by the spine, but the movement is a throw and fits none of the twelve well |
| `Otis-Up` | Otis-Up | other | isolation | lumbar spine | N | M | 2 | | *"flexing the hips and spine to raise your torso up from the ground"* — B1, a weighted sit-up; the source's own `primary_muscles: abdominals` (not `shoulders`/`triceps`, unlike `Kettlebell_Halo_With_Overhead_Extension` below) says the sit-up dominates the incidental overhead reach |
| `Seated_Flat_Bench_Leg_Pull-In` | Seated Flat Bench Leg Pull-In | body only | isolation | lumbar spine | N | L | 0 | | *"Bring the knees in toward you as you move your torso closer to them"* — B1, same movement as `Flat_Bench_Leg_Pull-In`; **byte-identical instructions to `Seated_Leg_Tucks`**, which `docs/enrichment/graph.md` records as a `variant_of` pair |
| `Wind_Sprints` | Wind Sprints | body only | isolation | lumbar spine | N | M | 0 | | *"Begin by quickly raising one knee as high as you can"*, hanging from a bar — B1 despite the name |

### Core rotation (7)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Cable_Judo_Flip` | Cable Judo Flip | cable | core rotation | lumbar spine | N | L | 2 | | *"Twist your body away from the pulley as you bring the rope over your shoulder"* — B2a |
| `Kettlebell_Figure_8` | Kettlebell Figure 8 | kettlebells | core rotation | lumbar spine | N | M | 1 | ? | *"pass it to your other hand between your legs. The receiving hand should reach from behind the legs"* — B2a, weakly: the hinge is the position, passing the bell hand to hand is the work, closer to rotation than to a lean |
| `Kettlebell_Pass_Between_The_Legs` | Kettlebell Pass Between The Legs | kettlebells | core rotation | lumbar spine | N | M | 1 | ? | *"pass it to your other hand between your legs, in the fashion of a 'W'"* — B2a, the same weak case as `Kettlebell_Figure_8` |
| `Kettlebell_Pirate_Ships` | Kettlebell Pirate Ships | kettlebells | core rotation | lumbar spine | N | M | 1 | | *"Initiate the movement by turning to one side, swinging the kettlebell to head height"* — B2a |
| `Landmine_180s` | Landmine 180's | barbell | core rotation | lumbar spine | N | M | 3 | | *"rotating the trunk and hips as you swing the weight all the way down to one side"* — B2a, `docs/enrichment/definitions.md`'s own named example |
| `Spell_Caster` | Spell Caster | dumbbell | core rotation | lumbar spine | N | M | 1 | | *"rotate your torso to swing the weights to your opposite side"* — B2a, `docs/enrichment/definitions.md`'s own named example |
| `Standing_Cable_Lift` | Standing Cable Lift | cable | core rotation | lumbar spine | N | L | 2 | | *"pull the handle up and across your body until your arms are in a fully-extended position above your head"* — the low-to-high mirror of `Standing_Cable_Wood_Chop`'s high-to-low chop, same B2a family |

### Core anti-extension (4)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Ab_Roller` | Ab Roller | other | core anti-extension | lumbar spine | N | M | 2 | | *"Slowly roll the ab roller straight forward, stretching your body into a straight position"* — B3, the same rollout `Barbell_Ab_Rollout_-_On_Knees` performs with a loaded bar |
| `Butt-Ups` | Butt-Ups | body only | core anti-extension | lumbar spine | N | M | 0 | ? | *"Begin a pushup position but with your elbows on the ground"* — B3. Borderline: the hips pike deliberately rather than being held still |
| `Exercise_Ball_Pull-In` | Exercise Ball Pull-In | exercise ball | core anti-extension | lumbar spine | N | M | 1 | | *"keeping your back completely straight and the upper body stationary, pull your knees in towards your chest"* — B3, `docs/enrichment/definitions.md`'s own named example |
| `Spider_Crawl` | Spider Crawl | body only | core anti-extension | lumbar spine | N | M | 0 | | *"Support your weight on your hands and toes... bring the knee toward your elbow"* — B3, `docs/enrichment/definitions.md`'s own named example |

### Vertical push (4)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Bent_Press` | Bent Press | kettlebells | vertical push | shoulder, elbow | Y | M | 1 | ? | *"press the weight vertically be extending through the elbow, keeping your arm perpendicular to the ground"* — a real press, unlike the windmill it otherwise resembles |
| `Kettlebell_Halo_With_Overhead_Extension` | Kettlebell Halo with Overhead Extension | kettlebells | vertical push | shoulder, elbow | Y | M | 1 | | *"extend your elbows to press the kettlebell up and overhead until your arms are straight"* — B4; the source's own `primary_muscles: [shoulders, triceps]` (unlike the plain `Kettlebell_Halo`'s `shoulders` alone) says the added press, not the halo circle, is what the row is about |
| `Landmine_Linear_Jammer` | Landmine Linear Jammer | barbell | vertical push | shoulder, elbow | Y | M | 3 | ? | *"extending the elbows to straighten the arms"* out of a squat — B4; the bar travels up and forward, and vertical is the nearer of the two presses |
| `Single-Arm_Linear_Jammer` | Single-Arm Linear Jammer | barbell | vertical push | shoulder, elbow | Y | M | 3 | | *"Perform the movement by extending the elbow, pressing the weight up"* — B4, same family as `Landmine_Linear_Jammer` |

### Core lateral flexion (2)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Kettlebell_Turkish_Get-Up_Lunge_style` | Kettlebell Turkish Get-Up (Lunge style) | kettlebells | core lateral flexion | lumbar spine | N | M | 1 | ? | *"Keeping the kettlebell locked out at all times, pivot to the opposite side"* — B2b, resisting a lean under the locked-out load. Uncertain for a B4 reason, not a B2b one: the legs drive a lunge transition throughout, and the single column can only record the trunk demand or the leg one |
| `Kettlebell_Turkish_Get-Up_Squat_style` | Kettlebell Turkish Get-Up (Squat style) | kettlebells | core lateral flexion | lumbar spine | N | M | 1 | ? | *"While looking up at the kettlebell, slowly stand up"* — B2b, the same reading and the same B4 conflict with the squat it stands up out of |

### Hip hinge (1)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Physioball_Hip_Bridge` | Physioball Hip Bridge | exercise ball | hip hinge | hip, lumbar spine | N | M | 1 | | *"extending the hips using your glutes and hamstrings, raising your hips upward as you bridge"* — the same hip-extension-driven bridge/thrust family `enrichment.py`'s `_HIP_HINGE` keywords already catch under the name "glute bridge" or "hip thrust"; "hip bridge" is the one wording the keyword list misses |

### Horizontal pull (1)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `London_Bridges` | London Bridges | other | horizontal pull | shoulder, elbow | N | L | 2 | ? | *"Keeping your body straight, lean back and lower your body by slowly going hand over hand"* along a hanging rope, then reversing hand over hand back up. Genuinely ambiguous between the two pull patterns — the rope is closer to overhead than horizontal for most of the motion — kept horizontal for the pulling-toward-the-torso reading, marked uncertain rather than picked with false confidence |

### Carry (1)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Sled_Overhead_Backward_Walk` | Sled Overhead Backward Walk | other | carry | shoulder, wrist, lumbar spine | Y | H | 2 | | *"Walk backwards, keeping your arms raised above your head"* — B5, `docs/enrichment/definitions.md`'s own worked example and the only true carry in the residue |

### No honest pattern — B6 and no source (2)

| id | name | equipment | pattern | joints | axial | stability | setup | +/- | note |
|---|---|---|---|---|---|---|---|---|---|
| `Battling_Ropes` | Battling Ropes | other | *(null)* | | | | | | *"whipping the ropes up and down as fast as you can"* — B6. Conditioning; no honest value among the twelve |
| `Iron_Cross` | Iron Cross | dumbbell | *(null)* | | | | | | **No instructions in the source.** The name is used both for a gymnastic ring hold and for a dumbbell raise variant, and nothing in the row separates them |

## Counts

| pattern | rows |
|---|---|
| isolation | 16 |
| core rotation | 7 |
| core anti-extension | 4 |
| vertical push | 4 |
| core lateral flexion | 2 |
| hip hinge | 1 |
| horizontal pull | 1 |
| carry | 1 |
| **null** | 2 |
| | **38** |
| **uncertain** | **12 of 36 decided** |

Three of the twelve patterns have no member here — `horizontal push`, `squat`,
`single-leg` — the same three the draft already found empty: those are the patterns a
rule reads straight off `primary_muscles` and a name, so almost none of them reaches
the residue.

## The spot-check

A sample of 21 rows the rules *did* decide — two per pattern that has more than one,
picked at random, none of them in `docs/enrichment/reference-set.md` or in the table
above — read against their own `instructions` independently of the columns that
decided them. **Zero disagreements.** Every one of the 21 lands on the same pattern a
person reading the prose would give it:

`Barbell_Ab_Rollout_-_On_Knees`, `Barbell_Rollout_from_Bench` (core anti-extension);
`Barbell_Side_Bend`, `Dumbbell_Side_Bend` (core lateral flexion); `Pallof_Press_With_Rotation`
(core rotation); `Dumbbell_Clean`, `Double_Kettlebell_Alternating_Hang_Clean` (hip hinge);
`Bent_Over_Two-Arm_Long_Bar_Row`, `Barbell_Rear_Delt_Row` (horizontal pull);
`Incline_Push-Up`, `Leverage_Incline_Chest_Press` (horizontal push);
`Standing_Towel_Triceps_Extension`, `Dumbbell_One-Arm_Triceps_Extension` (isolation);
`Suspended_Split_Squat`, `Barbell_Side_Split_Squat` (single-leg);
`Front_Barbell_Squat`, `Narrow_Stance_Squats` (squat);
`Underhand_Cable_Pulldowns`, `Kipping_Muscle_Up` (vertical pull);
`Double_Kettlebell_Jerk`, `Bradford_Rocky_Presses` (vertical push).

`carry` has no second member to sample — `Sled_Overhead_Backward_Walk` above is still
the only carry row in the whole catalog. This spot-check is independent of, and in
addition to, ticket 03's own reference set, which already re-read 69 of the rule-decided
rows blind and measured `movement_pattern` at 94.2% with zero disagreements on the 68 it
reached (see `docs/enrichment/reference-set.md`).

## What the reading found, beyond the values

**A movement can load two patterns and the schema has one column.** `Kettlebell
Thruster` is a squat and an overhead press; `Muscle Up` is a vertical pull and a dip;
the two linear jammers and the two Turkish get-ups above are the same shape. B4 picks
the terminal pattern, which keeps volume counting honest for the joint that took the
load last, but it is a lossy answer to a real question. **Left as a limitation,
deliberately** — a second column or a join table would spread across every query in
the engine to serve a handful of rows.

**A duplicate the reading found, and the graph now catches.** `Seated_Leg_Tucks` and
`Seated_Flat_Bench_Leg_Pull-In` carry byte-identical instructions under two ids — the
same movement, twice. `docs/enrichment/graph.md` records it as a `variant_of` pair.

**Two rows have no instructions at all.** `Iron_Cross` and `Side_Bridge` (the latter
now closed by the rule, at `core lateral flexion`, decided from its unambiguous name).
The moment a decision cannot cite anything, the file has to say so rather than quietly
looking like the rest.
