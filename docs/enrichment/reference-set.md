# Reference set — blind enrichment, 70 movements

70 distinct `category: strength` movements, decided **blind against `definitions.md`
before any automated output was consulted**. Every decision below was made by
reading that movement's own `name`, `primaryMuscles`/`secondaryMuscles` and
`instructions` array directly in the vendored source
`src/trainer/data/free-exercise-db/exercises.json`, then applying the rules in
`definitions.md` by hand — against a database (`unenriched.sqlite`) where every
enrichment column is NULL on every row, so there was nothing automated to see even
by accident. `trainer enrich derive` / `trainer enrich check` were never run, no
`.git` history was opened, and `src/trainer/engine/enrichment.py`,
`docs/enrichment/residue.md`, `ROADMAP.md` and the enrichment/catalog tests were
never read. Nothing that looked like a rule's output for a specific id was ever
seen; see the confirmation at the very end of this file.

Columns: `id`, `name`, `equipment`, `movement_pattern`, `loaded_joints`,
`spinal_axial_load` (Y/N), `required_stability` (H/M/L), `setup_cost_min`,
uncertainty marker (`?` = genuinely uncertain), and the note citing the
instruction phrase or the `definitions.md` rule the decision rests on.

## Isolation (12)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Barbell_Curl | Barbell Curl | barbell | isolation | elbow | N | M | 3 | | "curl the weights forward while contracting the biceps" — textbook curl; biceps isolates elbow. Standing bilateral free-weight = medium; isolation is always axial-no. |
| Dumbbell_Bicep_Curl | Dumbbell Bicep Curl | dumbbell | isolation | elbow | N | M | 1 | | Same as above, dumbbell equivalent. |
| Leg_Extensions | Leg Extensions | machine | isolation | knee | N | L | 1 | | "using your quadriceps, extend your legs" on a leg-extension machine; quadriceps isolates knee per joint table. Machine = low stability. |
| Triceps_Pushdown | Triceps Pushdown | cable | isolation | elbow | N | L | 2 | | "using the triceps, bring the bar down"; triceps isolates elbow. Cable = low stability, cable work is explicitly axial-no. |
| Weighted_Crunches | Weighted Crunches | medicine ball | isolation | lumbar spine | N | L | 1 | | "roll your shoulders off the floor... flex your abdominals" — a dynamic, weighted crunch: B1, produces spinal flexion, so isolation, not anti-extension. Lying = low stability. |
| Exercise_Ball_Crunch | Exercise Ball Crunch | exercise ball | isolation | lumbar spine | N | L | 1 | ? | "flex the waist by contracting the abdominals and curl the shoulders and trunk upward" — B1 crunch again, isolation. Marked `?` on stability only: lying on a ball is "lying" by the letter of the rule (→ low) but the ball itself is an unstable surface the rule doesn't address. |
| Calf_Raises_-_With_Bands | Calf Raises - With Bands | bands | isolation | ankle | N | M | 1 | | "stand up on your toes... contract the calves" with a band; calves isolate ankle. Standing bilateral = medium. |
| EZ-Bar_Curl | EZ-Bar Curl | e-z curl bar | isolation | elbow | N | M | 2 | ? | "curl the weights forward while contracting the biceps" on an EZ bar; biceps isolates elbow. `?` on setup cost: e-z curl bar equipment has no price in `definitions.md`'s setup-cost table; 2 min is a guess between a loaded barbell (3) and a pick-up implement (1). |
| Hanging_Leg_Raise | Hanging Leg Raise | body only | isolation | lumbar spine | N | M | 0 | ? | "raise your legs until the torso makes a 90-degree angle" — B1 names this exact case: "a leg raise brought up dynamically... is isolation," abdominals isolate lumbar spine. `?` on stability: a bodyweight hang is none of the three defined buckets (not one-arm/leg, not carry, not machine/cable/lying/seated, not "standing" either) — a genuine gap in the taxonomy; medium is the closest fit, not a rule match. |
| Cable_Crunch | Cable Crunch | cable | isolation | lumbar spine | N | L | 2 | | "flex the waist as you contract the abs" on a cable — B1 crunch, isolation, cable = low stability, cable work = axial-no. |
| One-Legged_Cable_Kickback | One-Legged Cable Kickback | cable | isolation | hip | N | H | 2 | ? | "contract your glutes to slowly kick the working leg back" — one joint, one muscle (glutes), isolation; glutes isolate hip. `?` on stability: the support leg is single-leg standing throughout, which literally matches "high for anything performed on one leg," but the rule's "one leg" examples (lunge, split squat, pistol squat) are all load-bearing squat-family movements, not a standing-leg-as-base isolation move — a boundary the rule doesn't resolve cleanly. |
| Band_Pull_Apart | Band Pull Apart | bands | isolation | shoulder | N | M | 1 | | "reverse fly motion, moving your hands out laterally" — one joint (shoulder), rear-delt/traps target; shoulders/traps isolate the shoulder joint per the table. Standing bilateral band work = medium. |

## Horizontal push (6)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Barbell_Bench_Press_-_Medium_Grip | Barbell Bench Press - Medium Grip | barbell | horizontal push | shoulder, elbow | N | L | 3 | | "lie back on a flat bench... push the bar back to the starting position" — load leaves the torso on a path parallel to the floor, the textbook `horizontal push` example. Lying = low stability and axial-no. |
| Dumbbell_Bench_Press | Dumbbell Bench Press | dumbbell | horizontal push | shoulder, elbow | N | L | 1 | | Same movement, dumbbell equivalent — "lie down on a flat bench... push the dumbbells up." |
| Pushups | Pushups | body only | horizontal push | shoulder, elbow | N | M | 0 | ? | "lower yourself... press your upper body back up" — bodyweight horizontal push, the definition's own second example. `?` on stability: prone-on-floor, bilateral, unsupported by a bench or machine — outside all three defined buckets; medium is the closest fit by elimination, not a direct rule match. |
| Cable_Chest_Press | Cable Chest Press | cable | horizontal push | shoulder, elbow | N | L | 2 | | "pressing the handles together straight in front of you," seated — cable work is explicitly axial-no and low-stability. |
| Machine_Bench_Press | Machine Bench Press | machine | horizontal push | shoulder, elbow | N | L | 1 | | Seated chest-press machine; machine = low stability, axial-no. |
| Bench_Press_-_With_Bands | Bench Press - With Bands | bands | horizontal push | shoulder, elbow | N | L | 1 | | "lie down on the bench... bring the handles up using your pectoral muscles" — lying = low stability, axial-no. |

## Vertical push (7)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Standing_Military_Press | Standing Military Press | barbell | vertical push | shoulder, elbow | Y | M | 3 | | "lift the bar up over your head," feet on the floor, no bench — the exact `definitions.md` example of `vertical push`, and of `spinal_axial_load: yes` ("a standing overhead press"). |
| Dumbbell_Shoulder_Press | Dumbbell Shoulder Press | dumbbell | vertical push | shoulder, elbow | N | L | 1 | | "sit on a military press bench or utility bench that has back support" — this specific entry is seated with back support, not standing, so it does not qualify for axial-yes; seated-on-a-bench = low stability. |
| Handstand_Push-Ups | Handstand Push-Ups | body only | vertical push | shoulder, elbow | N | M | 0 | ? | "lower yourself... push yourself back up" while inverted against a wall — load travels overhead, matching the definition's other named example verbatim. Axial-no: the lifter is inverted, not standing. `?` on stability: inverted bodyweight bilateral work fits none of the three buckets; medium by elimination only. |
| Two-Arm_Kettlebell_Military_Press | Two-Arm Kettlebell Military Press | kettlebells | vertical push | shoulder, elbow | Y | M | 1 | | "clean two kettlebells to your shoulders... press the kettlebells up and out" — a clean into a standing overhead press; standing, unsupported, real external load = axial-yes, standing bilateral free-weight = medium. |
| Machine_Shoulder_Military_Press | Machine Shoulder (Military) Press | machine | vertical push | shoulder, elbow | N | L | 1 | | Seated shoulder-press machine — machine-supported, axial-no, low stability. |
| Kettlebell_Thruster | Kettlebell Thruster | kettlebells | vertical push | shoulder, elbow | Y | M | 1 | ? | "squat by flexing your hips and knees... press both kettlebells overhead" — `B4`: a movement loading two patterns (squat + overhead press); the rule is the pattern the load ends in, which here is the press. Standing, unsupported, real load = axial-yes. `?` flags that, per `B4`'s own stated limitation, the squat portion also genuinely loads hip/knee/ankle, which this single-pattern joint set does not capture. |
| Dips_-_Triceps_Version | Dips - Triceps Version | body only | vertical push | shoulder, elbow | N | M | 0 | ? | Explicit `definitions.md` rule: "A dip sits with vertical push: the torso stays upright and the load still travels up, not away from it." Axial-no: the lifter is suspended between bars, not standing. `?` on stability: bodyweight, hanging, bilateral — outside all three defined buckets, medium by elimination. |

## Horizontal pull (6)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Bent_Over_Barbell_Row | Bent Over Barbell Row | barbell | horizontal pull | shoulder, elbow | Y | M | 3 | ? | "lift the barbell to you... torso stationary" — load moves toward the torso on a horizontal path, the definition's named `row` example. `?` on axial load: standing and unsupported holding a real barbell meets the letter of the yes-rule, but the torso is bent forward rather than upright the way the rule's own examples (squat, deadlift, standing press) are; the doc does not resolve this posture directly. |
| Seated_Cable_Rows | Seated Cable Rows | cable | horizontal pull | shoulder, elbow | N | L | 2 | | "pull the handles back towards your torso" — seated cable row, cable work = axial-no, low stability. |
| One-Arm_Dumbbell_Row | One-Arm Dumbbell Row | dumbbell | horizontal pull | shoulder, elbow | N | H | 1 | | "place your right hand on the other end of the bench for support" while rowing with the other arm — bench-supported so axial-no, but it is literally a one-arm movement, so `required_stability: high` per the explicit rule. |
| Leverage_Iso_Row | Leverage Iso Row | machine | horizontal pull | shoulder, elbow | N | L | 1 | | Seated machine row — machine-supported, axial-no, low stability. |
| Two-Arm_Kettlebell_Row | Two-Arm Kettlebell Row | kettlebells | horizontal pull | shoulder, elbow | Y | M | 1 | ? | "bend over to get in the starting position... pull them to your stomach" — standing, unsupported, real load; same bent-over-posture uncertainty as the barbell row above. |
| Face_Pull | Face Pull | cable | horizontal pull | shoulder, elbow | N | L | 2 | | "pull the weight directly towards your face" — horizontal path toward the torso, cable = axial-no, low stability. |

## Vertical pull (5)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Pullups | Pullups | body only | vertical pull | shoulder, elbow | N | M | 0 | ? | "pull your torso up until the bar touches your upper chest" — torso moves up to the load, the definition's own `pull-up` example. Axial-no: hanging, not standing. `?` on stability: hanging bilateral bodyweight is outside all three buckets, medium by elimination. |
| Wide-Grip_Lat_Pulldown | Wide-Grip Lat Pulldown | cable | vertical pull | shoulder, elbow | N | L | 2 | | "bring the bar down until it touches your upper chest" — a pulldown, the other named example. Cable + seated = axial-no, low stability. |
| Weighted_Pull_Ups | Weighted Pull Ups | other | vertical pull | shoulder, elbow | N | M | 1 | ? | Same movement as Pullups with an added weight belt. `?` on setup cost — "other" equipment has no price in the doc's table; 1 min assumes the belt/plate is a quick pick-up, closer to a dumbbell than a barbell. `?` on stability for the same hanging-bodyweight reason as Pullups. |
| Chin-Up | Chin-Up | body only | vertical pull | shoulder, elbow | N | M | 0 | ? | "pull your torso up until your head is around the level of the pull-up bar" — same pattern as Pullups, closer grip. Same stability gap. |
| Muscle_Up | Muscle Up | other | vertical pull | shoulder, elbow | N | M | 1 | ? | Explicit `definitions.md` rule: "a muscle-up is `vertical pull` (the primary muscle is `lats`, and the pulling portion is what defines the movement)" — the `B4` override, against the naive "the dip is terminal" reading. Primary muscle confirmed `lats` in the source data. `?` flags both that the dip-portion joint loading is not captured (per `B4`'s stated limitation) and that "other" setup cost is a guess. |

## Squat (6)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Barbell_Squat | Barbell Squat | barbell | squat | hip, knee, ankle | Y | M | 3 | | "lower the bar by bending the knees and hips... descending and rising roughly in place" — the definition's own named example, verbatim also the `spinal_axial_load: yes` example. |
| Dumbbell_Squat | Dumbbell Squat | dumbbell | squat | hip, knee, ankle | Y | M | 1 | | Same movement pattern, held at the sides; standing, unsupported, real load = axial-yes. |
| Leg_Press | Leg_Press | machine | squat | hip, knee, ankle | N | L | 1 | | "press the platform... your legs are fully extended" — knee-dominant, both legs, in place, but machine-supported: the doc's own `spinal_axial_load: no` and `required_stability: low` example ("less demanding of balance than... a leg press"). |
| Bodyweight_Squat | Bodyweight Squat | body only | squat | hip, knee, ankle | N | M | 0 | | Same pattern, no added load — axial-load rule requires "a real external load," bodyweight alone does not qualify, so no. Standing bilateral = medium. |
| Goblet_Squat | Goblet Squat | kettlebells | squat | hip, knee, ankle | Y | M | 1 | | "squat down between your legs... holding a kettlebell" — standing, unsupported, real load = axial-yes. |
| Squats_-_With_Bands | Squats - With Bands | bands | squat | hip, knee, ankle | N | M | 1 | ? | "bend the knees and lower the legs" against band tension. `?` on axial load: bands provide elastic tension, not a weight that gravitationally "bears down" through the spine the way a barbell/kettlebell load does — a case the doc's examples do not cover, so `no` here is a judgement call, not a rule match. |

## Hip hinge (7)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Barbell_Deadlift | Barbell Deadlift | barbell | hip hinge | hip, lumbar spine | Y | M | 3 | | "bend forward and grasp the bar... push with your legs while getting your torso upright" — the definition's own named example, and its own `spinal_axial_load: yes` example verbatim. |
| Stiff-Legged_Dumbbell_Deadlift | Stiff-Legged Dumbbell Deadlift | dumbbell | hip hinge | hip, lumbar spine | Y | M | 1 | | "lower the dumbbells... bending at the waist while keeping your back straight" — hip-dominant hinge, knees stay soft ("knees slightly bent"); standing, unsupported, real load = axial-yes. |
| One-Arm_Kettlebell_Swings | One-Arm Kettlebell Swings | kettlebells | hip hinge | hip, lumbar spine | Y | M | 1 | ? | Explicit named example in `definitions.md`: "a kettlebell swing." The source `instructions` array for this id is empty — the name itself, quoted directly in the taxonomy, is the evidence. `?` because a swing is ballistic rather than a held static load, and there is no instruction text to confirm form; standing/unsupported/real-load reasoning still points to axial-yes, but with less confidence than the other hinge rows. |
| Trap_Bar_Deadlift | Trap Bar Deadlift | other | hip hinge | hip, lumbar spine | Y | M | 3 | ? | "drive through the heels and extend your hips and knees" — explicit named example: "a barbell or trap-bar deadlift" for both the pattern and axial-yes. `?` only on setup cost: "other" equipment is unpriced in the doc; 3 min assumes it needs loading like a barbell. |
| Cable_Deadlifts | Cable Deadlifts | cable | hip hinge | hip, lumbar spine | N | L | 2 | | "squat down by flexing your hips and knees... driving through your heels extend your hips and knees" — a deadlift's hip-hinge motion, but performed on a cable machine: cable work is explicitly axial-no and low-stability regardless of the movement pattern, a clean illustration that pattern and equipment-support are decided separately. |
| Power_Clean | Power Clean | barbell | hip hinge | hip, lumbar spine | Y | M | 3 | | Explicit rule: "a clean or a snatch... the whole olympic-lift family in this catalog is `hip hinge`, regardless of what a naive reading of 'the bar ends up overhead' would suggest." Standing, unsupported, barbell = axial-yes. |
| Smith_Machine_Stiff-Legged_Deadlift | Smith Machine Stiff-Legged Deadlift | machine | hip hinge | hip, lumbar spine | N | L | 1 | | Same hinge motion as the dumbbell version, but on a fixed Smith-machine bar path — machine-supported overrides to axial-no and low stability, same logic as the cable deadlift above. |

## Single-leg (7)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Barbell_Lunge | Barbell Lunge | barbell | single-leg | hip, knee, ankle | Y | H | 3 | | "step forward with your right leg and squat down" — the definition's own named example ("a lunge"). Standing, unsupported, real load = axial-yes; one-leg-at-a-time = high stability by the explicit rule. |
| Dumbbell_Step_Ups | Dumbbell Step Ups | dumbbell | single-leg | hip, knee, ankle | Y | H | 1 | | "step on the elevated platform... extending the hip and knee of your right leg" — the definition's other named example ("a step-up"). Same axial/stability reasoning. |
| Kettlebell_Pistol_Squat | Kettlebell Pistol Squat | kettlebells | single-leg | hip, knee, ankle | Y | H | 1 | | "hold one leg off of the floor and squat down on the other" — a pistol squat, named directly in the definition. |
| Smith_Single-Leg_Split_Squat | Smith Single-Leg Split Squat | machine | single-leg | hip, knee, ankle | N | M | 1 | ? | "place one foot slightly forward under the bar and extend your other leg back" on a Smith machine — single-leg loading, but the fixed bar path removes most of the balance demand a free single-leg movement would have. `?`: the doc's stability rule doesn't resolve fixed-machine-path vs. one-leg in conflict; machine-supported so axial-no is confident, but stability is a genuine judgement call between the "one leg = high" and "machine = low" rules — medium as a compromise. |
| Step-up_with_Knee_Raise | Step-up with Knee Raise | body only | single-leg | hip, knee, ankle | N | H | 0 | | "step up, putting your left foot on the top of the bench... extend through the hip and knee" — bodyweight step-up, no external load so axial-no; one-leg-at-a-time = high stability. |
| Barbell_Walking_Lunge | Barbell Walking Lunge | barbell | single-leg | hip, knee, ankle | Y | H | 3 | | "step forward with one leg, flexing the knees... step forward with your rear foot, repeating on the opposite leg" — travelling, but the definition's own carry/lunge distinction settles this: a carry is "a load held while travelling, full stop," where the legs "do what they always do"; here the legs are doing genuine single-leg squat work each step, so this stays `single-leg`, not `carry`. |
| Kettlebell_One-Legged_Deadlift | Kettlebell One-Legged Deadlift | kettlebells | single-leg | hip, knee, ankle | Y | H | 1 | ? | "stand on one leg... perform a stiff legged deadlift by bending at the hip" — single-leg per the general rule ("either pattern performed on one leg at a time"). `?` on joints: the loaded-joints rule states flatly "a squat or single-leg movement loads hip, knee and ankle," which I followed literally, but the instructions explicitly keep "that knee slightly bent" — biomechanically this reads as a one-leg hip hinge (hip + lumbar spine) rather than a knee-loaded squat-family movement, and the doc does not separately address this case. |

## Core anti-extension (4)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Plank | Plank | body only | core anti-extension | lumbar spine | N | M | 0 | ? | Explicit named example: "a plank." "Keep your body straight at all times, and hold this position" — a fixed position resisting lumbar extension. `?` on stability: a static prone hold is not "lying" in the passive, balance-removing sense the rule intends (it's the whole point of the exercise), nor does it match any of the three defined buckets; medium is a judgement call, not a rule match. |
| Barbell_Ab_Rollout | Barbell Ab Rollout | barbell | core anti-extension | lumbar spine | N | M | 3 | ? | "keeping a slight arch on your back, lift your hips and roll the barbell towards your feet... keeping the abs tight" — name contains "rollout," which per the explicit name-rule wins over the source's `mechanic: isolation` tag ("a name that says plank, rollout or fallout outright wins"). Not standing (kneeling) so axial-no. `?` on stability, same gap as Plank. |
| Suspended_Fallout | Suspended Fallout | other | core anti-extension | lumbar spine | N | M | 1 | ? | Explicit named example in `definitions.md`, quoted by id: "`Suspended_Fallout`... is `mechanic: isolation` in the catalog, and neither is [`Plank`]... a name that says plank, rollout or `fallout` outright wins." "Maintain a neutral spine... your shoulders being the only joints allowed to move" confirms the anti-extension demand. Leaning into straps, not standing unsupported = axial-no. `?` on stability (same gap) and on setup cost ("other" unpriced; 1 min assumes the straps are already hung). |
| Exercise_Ball_Pull-In | Exercise Ball Pull-In | exercise ball | core anti-extension | lumbar spine | N | M | 1 | ? | Explicit named example, quoted verbatim in `B3`: "a plank held while the limbs move (a ball pull-in, a spider crawl) is still anti-extension." "Keeping your back completely straight and the upper body stationary, pull your knees in" matches exactly. Push-up position on the floor, not standing = axial-no. `?` on stability, same gap as the other trunk holds. |

## Core rotation (4)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Spell_Caster | Spell Caster | dumbbell | core rotation | lumbar spine | Y | M | 1 | ? | Explicit named example in `definitions.md`: "`Spell Caster` and `Landmine 180's` visibly rotate the torso." "Rotate your torso to swing the weights to your opposite side" confirms transverse-plane rotation. `?` on axial load: standing, unsupported, real dumbbell load meets the letter of the yes-rule, but this is a dynamic rotational swing rather than the rule's own examples (squat/deadlift/press/carry), which the doc does not directly address. |
| Landmine_180s | Landmine 180's | barbell | core rotation | lumbar spine | Y | M | 3 | ? | Same explicit named-example citation as above. "Rotating the trunk and hips as you swing the weight all the way down to one side" — clear transverse rotation. Same axial-load uncertainty as Spell Caster. |
| Standing_Cable_Wood_Chop | Standing Cable Wood Chop | cable | core rotation | lumbar spine | N | L | 2 | ? | "pull the handle down and across your body to your front knee while rotating your torso" — a cable chop, the definition's own named example ("a cable chop"). Cable work = axial-no. `?` on stability only: the letter of the rule makes any cable exercise low-stability, but this one explicitly requires the lifter to "pivot your back foot and bend your knees" for balance — a real tension between the rule's letter and this exercise's actual demand. |
| Pallof_Press | Pallof Press | cable | core rotation | lumbar spine | N | L | 2 | ? | Explicit named example: "a Pallof press." "Press the cable away from your chest... core should be tight" resisting the cable's rotational pull. Same cable-vs-actual-demand stability tension flagged as the wood chop. |

## Core lateral flexion (4)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Kettlebell_Windmill | Kettlebell Windmill | kettlebells | core lateral flexion | lumbar spine | N | H | 1 | | Explicit named example: "a kettlebell windmill." "Bending at the hip to one side, sticking your butt out, slowly lean" — a frontal-plane lean, not a turn, matching the pattern definition exactly. One arm holds the kettlebell locked overhead throughout = `required_stability: high` per the explicit one-arm rule. |
| Advanced_Kettlebell_Windmill | Advanced Kettlebell Windmill | kettlebells | core lateral flexion | lumbar spine | N | H | 1 | | Explicit named correction in `definitions.md`: "`Advanced Kettlebell Windmill` is `mechanic: isolation`, and it is not — it is a compound trunk-stability movement," grouped with the plain Kettlebell Windmill as the example where "nothing rotates, the body bends sideways." Same one-arm-overhead reasoning gives high stability. |
| Side_Bridge | Side Bridge | body only | core lateral flexion | lumbar spine | N | H | 0 | ? | Explicit named example: "a side plank" — "Side Bridge" is the catalog's name for the same movement (a static side-plank hold). `?` on stability: balanced on one forearm and the edge of one foot, which reads as "performed on one arm" under the explicit high-stability rule, but that rule's own examples are all *working*-arm movements (a row, a press), not a *supporting*-arm static hold — the doc doesn't disambiguate the two. |
| Weighted_Ball_Side_Bend | Weighted Ball Side Bend | exercise ball | core lateral flexion | lumbar spine | N | L | 1 | ? | "Raise the side of your torso up by laterally flexing at the waist" — uses the pattern definition's own words ("a lean in the frontal plane") almost verbatim, even though "side bend" is not one of the doc's four named examples. Lying on the ball = low stability by the letter of the "lying" rule; `?` flags that an exercise ball is not a stable lying surface the way a bench is, same tension as Exercise Ball Crunch. |

## Carry (1)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Sled_Overhead_Backward_Walk | Sled Overhead Backward Walk | other | carry | shoulder, wrist, lumbar spine | Y | H | 2 | ? | This is `definitions.md`'s own worked example, quoted verbatim: "`B5`: `Sled Overhead Backward Walk` qualifies — a load is held overhead while walking." Explicit `carry` example for both axial-yes ("a loaded carry") and high stability ("for any carry"). `?` only on setup cost: "other" equipment is unpriced; 2 min assumes handles need attaching and the sled loading, between a machine (1) and a barbell (3). No second carry candidate exists in this catalog — no "farmer's walk," "suitcase carry" or "yoke walk" entries were found; `Monster Walk` (bands) was checked and correctly excluded per the doc's own words ("`Monster Walk` does not [qualify] — a band resists the step, nothing is carried"). |

## Not classified — B6 (1, bonus, not counted toward the twelve)

| id | name | equipment | pattern | joints | axial | stab. | setup | ? | note |
|---|---|---|---|---|---|---|---|---|---|
| Battling_Ropes | Battling Ropes | other | *(null)* | — | N | M | 1 | ? | `definitions.md`'s own `B6` example, quoted verbatim: "`Battling Ropes` is conditioning and none of the twelve patterns fits. The field stays null, with the reason on record." Included here only to demonstrate the null case was recognised, not as one of the 69 pattern-bearing rows. All other fields are correspondingly low-confidence: no pattern to derive joints from; no real gravitational load bearing down (rope tension, not weight) so axial-no; setup cost for "other" equipment is a guess. |

## Summary

**69 movements carry one of the twelve patterns** (plus one bonus B6 null-pattern
row, `Battling_Ropes`, included to show the null case was recognised rather than
guessed at). All twelve patterns are represented: isolation (12), horizontal push
(6), vertical push (7), horizontal pull (6), vertical pull (5), squat (6), hip
hinge (7), single-leg (7), core anti-extension (4), core rotation (4), core
lateral flexion (4), carry (1). Carry has only one representative — the catalog
has no second candidate; `Sled Overhead Backward Walk` is `definitions.md`'s own
worked example, and the obvious alternates ("farmer's walk," "suitcase carry")
simply do not exist as rows in this free-exercise-db export.

**All eleven equipment values are represented**: barbell (11), dumbbell (8),
kettlebells (9), cable (10), machine (7), body only (10), bands (4), exercise
ball (3), medicine ball (1), e-z curl bar (1), other (6).

**31 of the 70 rows carry a `?`.** Most are not doubts about the *pattern* — the
patterns above are almost all pinned to an explicit name, quoted phrase, or
worked example in `definitions.md`. The uncertainty clusters in two places the
document itself doesn't fully resolve: (1) `required_stability` for bodyweight
movements that are hanging, suspended, or holding a static trunk position — none
of the three defined buckets (one-limb/carry, machine-or-lying-or-seated,
standing-bilateral-free-weight) cleanly covers a pull-up, a dip, or a plank, so
those got "medium" by elimination rather than by rule; and (2) `spinal_axial_load`
for standing, unsupported, real-load movements that are bent-over (rows) or
rotational (Spell Caster, Landmine 180's, the windmills) rather than the doc's
own upright examples (squat, deadlift, standing press, carry) — the literal rule
says yes, but the intuition behind "bears down through the spine" is less clean
for those postures than for the named examples. A handful of other one-off
judgement calls (band resistance vs. a real gravitational load; "other" equipment
setup costs, which the doc's pricing table never covers) are called out
individually in their rows.

**Confirmation on the constraints**: no file under `src/trainer/engine/` with
"enrich" in its name was opened; `docs/enrichment/residue.md` and no other file
under `docs/enrichment/` besides the given `definitions.md` copy was opened;
`ROADMAP.md` was not opened; no test file was opened; no `git log`/`show`/`blame`/
`diff` or `.git/` access was made; `trainer enrich derive` and `trainer enrich
check` were never run; `TRAINER_DB` was only ever pointed at the given
`unenriched.sqlite`. Nothing resembling a rule's output for a specific id was
seen at any point.
