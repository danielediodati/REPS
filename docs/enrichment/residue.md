# The residue: the rows the columns cannot answer

The 60 `category: strength` rows a rule over `name`, `primary_muscles`, `force` and `mechanic` leaves undecided for `movement_pattern`, decided by reading each exercise's own `instructions`.

**Every decision quotes the sentence that produced it.** That is the whole point of the file: a year from now a value here can be checked in seconds by someone who was not present, without opening the source data. Two rows have no instructions in free-exercise-db at all, and they say so.

`uncertain` means the eleven patterns do not cleanly contain the movement and the value is the closest of eleven, not a confident answer. Ticket 03's reference set does not cover most of these rows, so nothing else in session 2 will catch a wrong one — treat the uncertain column as the review list.

> This file was produced against the throwaway rule set that measured the residue, not against the final `enrich derive`. When the real rules land, the residue will differ at the margin — the plain gaps below (`Barbell Deadlift`, `Weighted Pull Ups`, `Pull Through`, `Stiff Leg Barbell Good Morning`, `Kettlebell Thruster`, `Two-Arm Kettlebell Clean`, `Muscle Up`) should be decided by a rule and drop out of it. The decisions themselves stand: they are about the movement, not about which pass reached it.

## Boundary rules the reading forced

These are decisions about the taxonomy, not about single rows, and each one settles a whole family. They belong in ticket 02's definitions document, where the rules and this file both read them from one place.

| # | boundary | ruling | why |
|---|---|---|---|
| B1 | dynamic spinal flexion — crunch, sit-up, reverse crunch, leg pull-in, hanging knee raise | **`isolation`** | `core anti-extension` and `core anti-rotation` are *anti*-patterns: the trunk's job is to resist a movement, not to produce one. A crunch produces spinal flexion, so it is not an anti-pattern, and none of the other nine fit. It is the largest family in the residue |
| B2 | trunk work in the transverse plane — chops, lifts, Russian-twist family, windmills, get-ups | **`core anti-rotation`** | this is the widest reading of the pattern and it is deliberate. Reading it strictly — only Pallof-style resisted rotation — leaves the pattern with almost no members while `isolation` becomes a dumping ground, and it breaks substitution: a Pallof press is the sane replacement for a cable chop, and the engine can only know that if they share a pattern |
| B3 | plank-based, with the limbs moving — ab rollout, ball pull-in, spider crawl, butt-ups | **`core anti-extension`** | the trunk is holding a plank throughout and the limbs are what moves. The demand is continuous resistance to extension, which is the definition, even though something in the picture is moving |
| B4 | a movement that loads two patterns — thruster, muscle-up, jammer, split snatch | **the pattern the load ends in**, with a note | `movement_pattern` is one column and TRAINER.md's glossary makes it *the* level at which you program, exclude and count. Picking the terminal pattern keeps volume counting honest for the joint that took the load. It is the least bad rule for a real limitation, not a good rule — see the finding below |
| B5 | a loaded carry | **`carry` requires holding a load while travelling** | `Sled Overhead Backward Walk` qualifies and is the residue's only member. `Monster Walk` does not: the band resists the step, nothing is carried |
| B6 | no honest answer | **null, with the reason** | `Battling Ropes` is conditioning and none of the eleven fits. A null is a state the schema makes readable; a wrong pattern is a volume count that stays wrong and nobody notices |

## The decisions

| id | pattern | ± | the line it rests on |
|---|---|---|---|
| `Ab_Roller` | core anti-extension | | *«Slowly roll the ab roller straight forward, stretching your body into a straight position»* — B3 |
| `Advanced_Kettlebell_Windmill` | core anti-rotation | ? | *«Keeping the kettlebell locked out at all times, push your butt out in the direction of the locked out kettlebell»* — B2. Lateral flexion under an overhead isometric; the closest of eleven, not a fit |
| `Air_Bike` | isolation | | *«Bring your right elbow close to your left knee by crunching to the side»* — B1 |
| `Alternate_Heel_Touchers` | isolation | | *«Crunch over your torso forward and up about 3-4 inches to the right side»* — B1 |
| `Barbell_Deadlift` | hip hinge | | *«leaning the torso forward at the waist while keeping the back straight»*. A gap in the throwaway rules, not a real residue |
| `Battling_Ropes` | **null** | | *«whipping the ropes up and down as fast as you can»* — B6. Conditioning; no honest value among the eleven |
| `Bent_Press` | vertical push | ? | *«press the weight vertically be extending through the elbow, keeping your arm perpendicular to the ground»*. There is a real press here, unlike the windmill it resembles |
| `Bottoms_Up` | isolation | | *«Rotate and elevate your pelvis to raise your glutes from the floor»* — B1 |
| `Butt-Ups` | core anti-extension | ? | *«Begin a pushup position but with your elbows on the ground»* — B3. Borderline: the hips pike deliberately rather than being held still |
| `Cable_Internal_Rotation` | isolation | | *«Pull the single hand cable attachment toward your body by internally rotating your shoulder»*. Single joint — the source's `mechanic: compound` is wrong here |
| `Cable_Judo_Flip` | core anti-rotation | | *«Twist your body away from the pulley as you bring the rope over your shoulder»* — B2 |
| `Cocoons` | isolation | | *«flex the spine, bringing your arms back over your head to perform a simultaneous crunch motion»* — B1 |
| `Double_Kettlebell_Snatch` | hip hinge | | *«Swing the kettlebells between your legs forcefully... Drive through with your hips»*. Ends overhead but nothing is pressed — B4 would say vertical push, the hips did the work |
| `Double_Kettlebell_Windmill` | core anti-rotation | ? | *«Bending at the hip to one side, sticking your butt out, slowly lean»* — B2 |
| `Elbow_to_Knee` | isolation | ? | *«flexing the spine and rotating your torso to bring the left elbow to the right knee»*. B1 and B2 both reach for it; flexion is the larger half |
| `Exercise_Ball_Pull-In` | core anti-extension | | *«keeping your back completely straight and the upper body stationary, pull your knees in towards your chest»* — B3 |
| `External_Rotation_with_Band` | isolation | | *«rotating your arm in a backhand motion, keeping your elbow in place»* |
| `Flat_Bench_Leg_Pull-In` | isolation | | *«Bend your knees and pull your upper thighs into your midsection»* — B1 |
| `Flutter_Kicks` | isolation | | *«Squeeze your glutes and hamstrings and straighten the legs until they are level with the hips»* |
| `Glute_Kickback` | isolation | | *«lift up your right leg until the hamstrings are in line with the back while maintaining the 90-degree angle bend»* |
| `Hanging_Pike` | isolation | ? | *«Pull your legs up as you exhale until you almost touch your shins with the bar»* — B1. The lats hold an isometric that B3 would notice |
| `Hip_Extension_with_Bands` | isolation | | *«move the resisted leg back as far as you can while keeping the knee straight»* |
| `Hip_Flexion_with_Band` | isolation | | *«raise your knee up to 90 degrees and pause»* |
| `Iron_Cross` | **null** | | **No instructions in the source.** The name is used both for a gymnastic ring hold and for a dumbbell raise variant, and nothing in the row separates them |
| `Kettlebell_Figure_8` | core anti-rotation | ? | *«pass it to your other hand between your legs. The receiving hand should reach from behind the legs»* — B2. The hinge is the position; passing the bell is the work |
| `Kettlebell_Halo` | isolation | ? | *«move the kettlebell up past one ear and around behind your head»*. Shoulder-girdle work; nothing else of the eleven applies |
| `Kettlebell_Halo_With_Overhead_Extension` | vertical push | | *«extend your elbows to press the kettlebell up and overhead until your arms are straight»* — B4 |
| `Kettlebell_Pass_Between_The_Legs` | core anti-rotation | ? | *«pass it to your other hand between your legs, in the fashion of a "W"»* — B2 |
| `Kettlebell_Pirate_Ships` | core anti-rotation | | *«Initiate the movement by turning to one side, swinging the kettlebell to head height»* — B2 |
| `Kettlebell_Thruster` | vertical push | ? | *«press both kettlebells overhead by extending your arms straight up, using the momentum from the squat»* — B4. It is equally a squat, and the single column cannot say so |
| `Kettlebell_Turkish_Get-Up_Lunge_style` | core anti-rotation | ? | *«Keeping the kettlebell locked out at all times, pivot to the opposite side»* — B2. Nothing is pressed after the first rep; the trunk resists throughout |
| `Kettlebell_Turkish_Get-Up_Squat_style` | core anti-rotation | ? | *«While looking up at the kettlebell, slowly stand up»* — B2, same reading |
| `Kettlebell_Windmill` | core anti-rotation | ? | *«Bending at the hip to one side... slowly lean until you can touch the floor with your free hand»* — B2 |
| `Kipping_Muscle_Up` | vertical pull | ? | *«pulling yourself up with both arms... This puts you into the proper position to continue into the dip portion»* — B4 says the terminal pattern is the dip, the primary muscle says lats. Two patterns, one column |
| `Landmine_180s` | core anti-rotation | | *«rotating the trunk and hips as you swing the weight all the way down to one side»* — B2 |
| `Landmine_Linear_Jammer` | vertical push | ? | *«extending the elbows to straighten the arms»* out of a squat. The bar travels up and forward; vertical is the nearer of the two presses |
| `Leg_Pull-In` | isolation | | *«Bend your knees and pull your upper thighs into your midsection»* — B1 |
| `London_Bridges` | horizontal pull | ? | *«Keeping your body straight, lean back and lower your body by slowly going hand over hand»* |
| `Monster_Walk` | isolation | ? | *«Place a band around both ankles and another around both knees»* — B5 says this is not a carry. Abductor work under band tension |
| `Muscle_Up` | vertical pull | ? | *«Initiate a pull up by pulling the elbows down to your side»* — B4, same problem as the kipping version |
| `One-Arm_Kettlebell_Snatch` | hip hinge | | *«drive through with your hips and knees, accelerating the kettlebell upward»* |
| `One-Arm_Kettlebell_Split_Snatch` | hip hinge | ? | *«extending the hips, knees, and finally the ankles, to raise the kettlebell overhead»*. Received in a lunge, which single-leg would want |
| `One-Arm_Medicine_Ball_Slam` | isolation | ? | *«flex the shoulders, spine, and hips to throw the ball hard into the ground»* — B1 by the spine, but the movement is a throw and fits none of the eleven well |
| `Otis-Up` | isolation | | *«flexing the hips and spine to raise your torso up from the ground»* — B1 |
| `Physioball_Hip_Bridge` | hip hinge | | *«extending the hips using your glutes and hamstrings, raising your hips upward as you bridge»* |
| `Pull_Through` | hip hinge | | *«all of the motion should originate through the hips»* |
| `Reverse_Hyperextension` | hip hinge | | *«Reverse the motion by extending the hips, kicking the leg back»* |
| `Rope_Climb` | vertical pull | | *«pull yourself up with your arms, bringing your knees towards your chest»* |
| `Seated_Flat_Bench_Leg_Pull-In` | isolation | | *«Bring the knees in toward you as you move your torso closer to them»* — B1 |
| `Seated_Leg_Tucks` | isolation | | **Instructions identical to `Seated_Flat_Bench_Leg_Pull-In`, word for word.** Same movement under two ids — a `variant_of` pair the graph must catch |
| `Side_Bridge` | core anti-rotation | ? | **No instructions in the source.** Decided from the name, which is unambiguous: a side plank resists lateral flexion, and B2 is the nearest of eleven. The only value in this file with no citation |
| `Single-Arm_Linear_Jammer` | vertical push | | *«Perform the movement by extending the elbow, pressing the weight up»* |
| `Sled_Overhead_Backward_Walk` | **carry** | | *«Walk backwards, keeping your arms raised above your head»* — B5. The only true carry in the residue |
| `Spell_Caster` | core anti-rotation | | *«rotate your torso to swing the weights to your opposite side»* — B2 |
| `Spider_Crawl` | core anti-extension | | *«Support your weight on your hands and toes... bring the knee toward your elbow»* — B3 |
| `Standing_Cable_Lift` | core anti-rotation | | *«pull the handle up and across your body until your arms are in a fully-extended position above your head»* — B2 |
| `Stiff_Leg_Barbell_Good_Morning` | hip hinge | | *«move your torso forward by bending at the hips»* |
| `Two-Arm_Kettlebell_Clean` | hip hinge | | *«extending through the legs and hips as you raise the kettlebells towards your shoulders»* |
| `Weighted_Pull_Ups` | vertical pull | | *«pull your torso up until your head is above your hands»* |
| `Wind_Sprints` | isolation | | *«Begin by quickly raising one knee as high as you can»*, hanging from a bar — B1 |

## Counts

| pattern | rows |
|---|---|
| isolation | 21 |
| core anti-rotation | 13 |
| hip hinge | 9 |
| vertical push | 5 |
| core anti-extension | 4 |
| vertical pull | 4 |
| horizontal pull | 1 |
| carry | 1 |
| **null** | 2 |
| | **60** |
| **uncertain** | **21 of 58 decided** |

Counted by parsing this file's own table, not by hand: 60 rows in, 60 rows out, and the id set matches the undecided set exactly. Four of the eleven patterns have no member here — `horizontal push`, `squat`, `single-leg` and, once `Sled Overhead Backward Walk` is set aside, very nearly `carry`. That is the expected shape: those are the patterns a rule reads straight off `primary_muscles` and a name, so nothing of them reaches the residue.

## What the reading found, beyond the values

**A movement can load two patterns and the schema has one column.** `Kettlebell Thruster` is a squat and an overhead press; `Muscle Up` is a vertical pull and a dip. B4 picks the terminal pattern, which keeps volume counting honest for the joint that took the load, but it is a lossy answer to a real question. It matters twice downstream: volume counted on the pattern performed, and the admissible set, where excluding `vertical push` should plausibly also exclude the thruster — and under B4 it does, by luck rather than by design. **Left as a limitation, deliberately**, because a second column or a join table would spread across every query in the engine to serve a handful of rows.

**Two native fields are wrong on rows this file touched.** `Cable Internal Rotation` is `mechanic: compound` and is plainly a single-joint movement. `Seated Leg Tucks` and `Seated Flat Bench Leg Pull-In` carry byte-identical instructions under two ids. Neither is worth patching upstream — the enrichment overrides both — but they are evidence for the rule already standing in CLAUDE.md: read vocabulary from the data, and do not assume the data is right about itself.

**Two rows have no instructions at all.** `Iron Cross` and `Side Bridge`. It is a small number, but it is the reason the citation is a criterion rather than a nicety: the moment a decision cannot cite anything, the file has to say so rather than quietly looking like the other 58.

**The uncertain column is a third of the residue, and it concentrates.** 21 of the 58 decided rows are marked uncertain, and **8 of those are `core anti-rotation` under B2** — the windmills, the two get-ups, the two kettlebell passes, the side bridge. That is not eight hard rows, it is **one** unresolved question — how wide the pattern is — answered once in ticket 02's definitions and then applied. If B2 is wrong it is wrong for all eight together, which is the good case: a single decision to review rather than eight. The remaining 13 are genuinely one-off, and B4's two-pattern movements are five of them.
