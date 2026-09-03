# The residue: the rows the columns cannot answer

The 60 `category: strength` rows a rule over `name`, `primary_muscles`, `force` and `mechanic` leaves undecided for `movement_pattern`, decided by reading each exercise's own `instructions`.

**Every decision quotes the sentence that produced it.** That is the whole point of the file: a year from now a value here can be checked in seconds by someone who was not present, without opening the source data. Two rows have no instructions in free-exercise-db at all, and they say so.

`uncertain` means the twelve patterns do not cleanly contain the movement and the value is the closest of twelve, not a confident answer. Ticket 03's reference set does not cover most of these rows, so nothing else in session 2 will catch a wrong one — treat the uncertain column as the review list.

> **Split while this file was being written.** TRAINER.md's glossary held one pattern here, first `core anti-rotation` then a merged `core rotation`. Reading the rows below showed both names were wrong for part of the group — several rows *rotate* the trunk, several *lean* it sideways, and no single name covers both without lying about one. The glossary now has two patterns, `core rotation` and `core lateral flexion`, defined at B2a and B2b below. Every occurrence in this file already uses the split names.

> This file was produced against the throwaway rule set that measured the residue, not against the final `enrich derive`. When the real rules land, the residue will differ at the margin — the plain gaps below (`Barbell Deadlift`, `Weighted Pull Ups`, `Pull Through`, `Stiff Leg Barbell Good Morning`, `Kettlebell Thruster`, `Two-Arm Kettlebell Clean`, `Muscle Up`) should be decided by a rule and drop out of it. The decisions themselves stand: they are about the movement, not about which pass reached it.

## Boundary rules the reading forced

These are decisions about the taxonomy, not about single rows, and each one settles a whole family. They belong in ticket 02's definitions document, where the rules and this file both read them from one place.

| # | boundary | ruling | why |
|---|---|---|---|
| B1 | dynamic spinal flexion — crunch, sit-up, reverse crunch, leg pull-in, hanging knee raise | **`isolation`** | `core anti-extension` resists a movement rather than producing one, and none of the other patterns fit a movement that dynamically flexes the spine either. It is the largest family in the residue |
| B2a | trunk work that turns the body — chops, judo-flips, landmine swings, pirate-ship swings | **`core rotation`** | the trunk produces or resists motion in the transverse plane. `Spell_Caster` and `Landmine_180s` are the clearest members: the torso visibly rotates |
| B2b | trunk work that leans the body under a fixed or shifting load — windmills, side planks, the loaded lean phase of a get-up | **`core lateral flexion`** | the trunk produces or resists motion in the frontal plane, not the transverse one. `Kettlebell_Windmill` and `Side_Bridge` are the clearest members: nothing rotates, the body bends sideways. TRAINER.md's glossary held one merged slot, `core anti-rotation` then `core rotation`, for both B2a and B2b for most of this session — see TRAINER.md § Glossary for why the merge did not survive contact with these thirteen rows |
| B3 | plank-based, with the limbs moving — ab rollout, ball pull-in, spider crawl, butt-ups | **`core anti-extension`** | the trunk is holding a plank throughout and the limbs are what moves. The demand is continuous resistance to extension, which is the definition, even though something in the picture is moving |
| B4 | a movement that loads two patterns — thruster, muscle-up, jammer, split snatch | **the pattern the load ends in**, with a note | `movement_pattern` is one column and TRAINER.md's glossary makes it *the* level at which you program, exclude and count. Picking the terminal pattern keeps volume counting honest for the joint that took the load. It is the least bad rule for a real limitation, not a good rule — see the finding below |
| B5 | a loaded carry | **`carry` requires holding a load while travelling** | `Sled Overhead Backward Walk` qualifies and is the residue's only member. `Monster Walk` does not: the band resists the step, nothing is carried |
| B6 | no honest answer | **null, with the reason** | `Battling Ropes` is conditioning and none of the twelve fits. A null is a state the schema makes readable; a wrong pattern is a volume count that stays wrong and nobody notices |

## The decisions

| id | pattern | ± | the line it rests on |
|---|---|---|---|
| `Ab_Roller` | core anti-extension | | *«Slowly roll the ab roller straight forward, stretching your body into a straight position»* — B3 |
| `Advanced_Kettlebell_Windmill` | core lateral flexion | | *«Keeping the kettlebell locked out at all times, push your butt out in the direction of the locked out kettlebell»* — B2b, against an overhead isometric |
| `Air_Bike` | isolation | | *«Bring your right elbow close to your left knee by crunching to the side»* — B1 |
| `Alternate_Heel_Touchers` | isolation | | *«Crunch over your torso forward and up about 3-4 inches to the right side»* — B1 |
| `Barbell_Deadlift` | hip hinge | | *«leaning the torso forward at the waist while keeping the back straight»*. A gap in the throwaway rules, not a real residue |
| `Battling_Ropes` | **null** | | *«whipping the ropes up and down as fast as you can»* — B6. Conditioning; no honest value among the twelve |
| `Bent_Press` | vertical push | ? | *«press the weight vertically be extending through the elbow, keeping your arm perpendicular to the ground»*. There is a real press here, unlike the windmill it resembles |
| `Bottoms_Up` | isolation | | *«Rotate and elevate your pelvis to raise your glutes from the floor»* — B1 |
| `Butt-Ups` | core anti-extension | ? | *«Begin a pushup position but with your elbows on the ground»* — B3. Borderline: the hips pike deliberately rather than being held still |
| `Cable_Internal_Rotation` | isolation | | *«Pull the single hand cable attachment toward your body by internally rotating your shoulder»*. Single joint — the source's `mechanic: compound` is wrong here |
| `Cable_Judo_Flip` | core rotation | | *«Twist your body away from the pulley as you bring the rope over your shoulder»* — B2a |
| `Cocoons` | isolation | | *«flex the spine, bringing your arms back over your head to perform a simultaneous crunch motion»* — B1 |
| `Double_Kettlebell_Snatch` | hip hinge | | *«Swing the kettlebells between your legs forcefully... Drive through with your hips»*. Ends overhead but nothing is pressed — B4 would say vertical push, the hips did the work |
| `Double_Kettlebell_Windmill` | core lateral flexion | | *«Bending at the hip to one side, sticking your butt out, slowly lean»* — B2b |
| `Elbow_to_Knee` | isolation | ? | *«flexing the spine and rotating your torso to bring the left elbow to the right knee»*. B1 and B2a both reach for it; flexion is the larger half |
| `Exercise_Ball_Pull-In` | core anti-extension | | *«keeping your back completely straight and the upper body stationary, pull your knees in towards your chest»* — B3 |
| `External_Rotation_with_Band` | isolation | | *«rotating your arm in a backhand motion, keeping your elbow in place»* |
| `Flat_Bench_Leg_Pull-In` | isolation | | *«Bend your knees and pull your upper thighs into your midsection»* — B1 |
| `Flutter_Kicks` | isolation | | *«Squeeze your glutes and hamstrings and straighten the legs until they are level with the hips»* |
| `Glute_Kickback` | isolation | | *«lift up your right leg until the hamstrings are in line with the back while maintaining the 90-degree angle bend»* |
| `Hanging_Pike` | isolation | ? | *«Pull your legs up as you exhale until you almost touch your shins with the bar»* — B1. The lats hold an isometric that B3 would notice |
| `Hip_Extension_with_Bands` | isolation | | *«move the resisted leg back as far as you can while keeping the knee straight»* |
| `Hip_Flexion_with_Band` | isolation | | *«raise your knee up to 90 degrees and pause»* |
| `Iron_Cross` | **null** | | **No instructions in the source.** The name is used both for a gymnastic ring hold and for a dumbbell raise variant, and nothing in the row separates them |
| `Kettlebell_Figure_8` | core rotation | ? | *«pass it to your other hand between your legs. The receiving hand should reach from behind the legs»* — B2a, weakly. The hinge is the position; passing the bell hand to hand is the work, and it is closer to rotation than to a lean |
| `Kettlebell_Halo` | isolation | ? | *«move the kettlebell up past one ear and around behind your head»*. Shoulder-girdle work; nothing else of the twelve applies |
| `Kettlebell_Halo_With_Overhead_Extension` | vertical push | | *«extend your elbows to press the kettlebell up and overhead until your arms are straight»* — B4 |
| `Kettlebell_Pass_Between_The_Legs` | core rotation | ? | *«pass it to your other hand between your legs, in the fashion of a "W"»* — B2a, same weak case as `Kettlebell_Figure_8` |
| `Kettlebell_Pirate_Ships` | core rotation | | *«Initiate the movement by turning to one side, swinging the kettlebell to head height»* — B2a |
| `Kettlebell_Thruster` | vertical push | ? | *«press both kettlebells overhead by extending your arms straight up, using the momentum from the squat»* — B4. It is equally a squat, and the single column cannot say so |
| `Kettlebell_Turkish_Get-Up_Lunge_style` | core lateral flexion | ? | *«Keeping the kettlebell locked out at all times, pivot to the opposite side»* — B2b, resisting a lean under the locked-out load. Uncertain for a B4 reason, not a B2b one: the legs drive a lunge transition throughout, and the single column can only record the trunk demand or the leg one |
| `Kettlebell_Turkish_Get-Up_Squat_style` | core lateral flexion | ? | *«While looking up at the kettlebell, slowly stand up»* — B2b, same reading, and the same B4 conflict with the squat it stands up out of |
| `Kettlebell_Windmill` | core lateral flexion | | *«Bending at the hip to one side... slowly lean until you can touch the floor with your free hand»* — B2b |
| `Kipping_Muscle_Up` | vertical pull | ? | *«pulling yourself up with both arms... This puts you into the proper position to continue into the dip portion»* — B4 says the terminal pattern is the dip, the primary muscle says lats. Two patterns, one column |
| `Landmine_180s` | core rotation | | *«rotating the trunk and hips as you swing the weight all the way down to one side»* — B2a |
| `Landmine_Linear_Jammer` | vertical push | ? | *«extending the elbows to straighten the arms»* out of a squat. The bar travels up and forward; vertical is the nearer of the two presses |
| `Leg_Pull-In` | isolation | | *«Bend your knees and pull your upper thighs into your midsection»* — B1 |
| `London_Bridges` | horizontal pull | ? | *«Keeping your body straight, lean back and lower your body by slowly going hand over hand»* |
| `Monster_Walk` | isolation | ? | *«Place a band around both ankles and another around both knees»* — B5 says this is not a carry. Abductor work under band tension |
| `Muscle_Up` | vertical pull | ? | *«Initiate a pull up by pulling the elbows down to your side»* — B4, same problem as the kipping version |
| `One-Arm_Kettlebell_Snatch` | hip hinge | | *«drive through with your hips and knees, accelerating the kettlebell upward»* |
| `One-Arm_Kettlebell_Split_Snatch` | hip hinge | ? | *«extending the hips, knees, and finally the ankles, to raise the kettlebell overhead»*. Received in a lunge, which single-leg would want |
| `One-Arm_Medicine_Ball_Slam` | isolation | ? | *«flex the shoulders, spine, and hips to throw the ball hard into the ground»* — B1 by the spine, but the movement is a throw and fits none of the twelve well |
| `Otis-Up` | isolation | | *«flexing the hips and spine to raise your torso up from the ground»* — B1 |
| `Physioball_Hip_Bridge` | hip hinge | | *«extending the hips using your glutes and hamstrings, raising your hips upward as you bridge»* |
| `Pull_Through` | hip hinge | | *«all of the motion should originate through the hips»* |
| `Reverse_Hyperextension` | hip hinge | | *«Reverse the motion by extending the hips, kicking the leg back»* |
| `Rope_Climb` | vertical pull | | *«pull yourself up with your arms, bringing your knees towards your chest»* |
| `Seated_Flat_Bench_Leg_Pull-In` | isolation | | *«Bring the knees in toward you as you move your torso closer to them»* — B1 |
| `Seated_Leg_Tucks` | isolation | | **Instructions identical to `Seated_Flat_Bench_Leg_Pull-In`, word for word.** Same movement under two ids — a `variant_of` pair the graph must catch |
| `Side_Bridge` | core lateral flexion | | **No instructions in the source.** Decided from the name, which is unambiguous: a side plank resists lateral flexion, which B2b names directly. The only value in this file with no citation |
| `Single-Arm_Linear_Jammer` | vertical push | | *«Perform the movement by extending the elbow, pressing the weight up»* |
| `Sled_Overhead_Backward_Walk` | **carry** | | *«Walk backwards, keeping your arms raised above your head»* — B5. The only true carry in the residue |
| `Spell_Caster` | core rotation | | *«rotate your torso to swing the weights to your opposite side»* — B2a |
| `Spider_Crawl` | core anti-extension | | *«Support your weight on your hands and toes... bring the knee toward your elbow»* — B3 |
| `Standing_Cable_Lift` | core rotation | | *«pull the handle up and across your body until your arms are in a fully-extended position above your head»* — B2a |
| `Stiff_Leg_Barbell_Good_Morning` | hip hinge | | *«move your torso forward by bending at the hips»* |
| `Two-Arm_Kettlebell_Clean` | hip hinge | | *«extending through the legs and hips as you raise the kettlebells towards your shoulders»* |
| `Weighted_Pull_Ups` | vertical pull | | *«pull your torso up until your head is above your hands»* |
| `Wind_Sprints` | isolation | | *«Begin by quickly raising one knee as high as you can»*, hanging from a bar — B1 |

## Counts

| pattern | rows |
|---|---|
| isolation | 21 |
| hip hinge | 9 |
| core rotation | 7 |
| core lateral flexion | 6 |
| vertical push | 5 |
| core anti-extension | 4 |
| vertical pull | 4 |
| horizontal pull | 1 |
| carry | 1 |
| **null** | 2 |
| | **60** |
| **uncertain** | **17 of 58 decided** |

Counted by parsing this file's own table, not by hand: 60 rows in, 60 rows out, id set matches the undecided set exactly. `core rotation` and `core lateral flexion` were one merged pattern under the name `core rotation` for most of this session, at 13 rows; splitting it left 7 in `core rotation` and 6 in `core lateral flexion` — see B2a/B2b below. Three of the twelve patterns have no member here at all — `horizontal push`, `squat`, `single-leg` — and `carry` has exactly one, `Sled Overhead Backward Walk`. That is the expected shape: those are the patterns a rule reads straight off `primary_muscles` and a name, so almost none of them reaches the residue.

## What the reading found, beyond the values

**A movement can load two patterns and the schema has one column.** `Kettlebell Thruster` is a squat and an overhead press; `Muscle Up` is a vertical pull and a dip. B4 picks the terminal pattern, which keeps volume counting honest for the joint that took the load, but it is a lossy answer to a real question. It matters twice downstream: volume counted on the pattern performed, and the admissible set, where excluding `vertical push` should plausibly also exclude the thruster — and under B4 it does, by luck rather than by design. **Left as a limitation, deliberately**, because a second column or a join table would spread across every query in the engine to serve a handful of rows.

**Two native fields are wrong on rows this file touched.** `Cable Internal Rotation` is `mechanic: compound` and is plainly a single-joint movement. `Seated Leg Tucks` and `Seated Flat Bench Leg Pull-In` carry byte-identical instructions under two ids. Neither is worth patching upstream — the enrichment overrides both — but they are evidence for the rule already standing in CLAUDE.md: read vocabulary from the data, and do not assume the data is right about itself.

**Two rows have no instructions at all.** `Iron Cross` and `Side Bridge`. It is a small number, but it is the reason the citation is a criterion rather than a nicety: the moment a decision cannot cite anything, the file has to say so rather than quietly looking like the other 58.

**The uncertain column started at 21 and dropped to 17 in two steps that both trace to one naming mistake.** `Advanced_Kettlebell_Windmill`, `Double_Kettlebell_Windmill`, `Kettlebell_Windmill` and `Side_Bridge` were marked uncertain only because the old merged name did not literally cover what they do; splitting `core rotation` from `core lateral flexion` at B2a/B2b resolved all four without touching a row — they are clean fits for `core lateral flexion` now.

**Four rows remain uncertain across the split pattern, two on each side, and neither pair is the naming problem any more.** `Kettlebell_Figure_8` and `Kettlebell_Pass_Between_The_Legs` (`core rotation`) are uncertain because passing a bell between the legs is weak evidence of rotation at all. The two `Turkish_Get-Up` rows (`core lateral flexion`) are uncertain because they carry the B4 problem — a leg drive and a trunk-stability demand in one movement, one column — and they are two of **five B4-tagged rows in the uncertain list**, with `Kettlebell_Thruster`, `Kipping_Muscle_Up` and `Muscle_Up`. Together these two reasons explain **7 of the 17** uncertain rows; the other **10 are one-off**, unrelated to either the core-pattern split or the two-pattern limitation.
