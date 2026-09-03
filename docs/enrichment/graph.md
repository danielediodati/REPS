# The `variant_of` / `regression_of` graph

Recognising that two named movements are the same, or that one is easier than the
other, needs reading a movement's own name and instructions — `docs/enrichment/
definitions.md` is explicit that a single row's columns cannot supply either, and
`enrichment.derive()` never writes them. This file is that reading. `trainer enrich
curated` loads it with `graph.py`'s own parser and writes every edge with `curated`
provenance.

**`variant_of` is a star, never a chain.** Every group below has exactly one
`representative`; every other member points at it directly, so a query never follows
`variant_of` more than one hop. `graph.py` refuses a representative that is itself
someone else's member, and refuses an id claimed by two groups.

**`regression_of` is directional and acyclic.** The row named `easier` is the one that
gets `regression_of = harder` — usable as a substitution when the harder version is not
available today, per `docs/enrichment/definitions.md`. `graph.py` refuses a cycle.

## Variant groups

| representative | member | note |
|---|---|---|
| `Standing_Military_Press` | `Arnold_Dumbbell_Press` | TRAINER.md's running example: *"the Arnold and the military press are the same pattern, to the engine they are interchangeable"* — both are a standing, two-arm overhead press, differing only in how the shoulder is loaded through the rotation |
| `Standing_Military_Press` | `Kettlebell_Arnold_Press` | the Arnold exists twice, dumbbell and kettlebell, and TRAINER.md says both point at the same equivalence class — the representative is the plain press so the group stays a star rather than the two Arnold rows pointing at each other and one of them also at the press |
| `Barbell_Bench_Press_-_Medium_Grip` | `Dumbbell_Bench_Press` | `docs/enrichment/reference-set.md` already quotes both: *"lie back on a flat bench... push the bar back"* / *"lie down on a flat bench... push the dumbbells up"* — the same horizontal push, different implement |
| `Barbell_Bench_Press_-_Medium_Grip` | `Machine_Bench_Press` | same movement, machine-supported — reference-set.md: *"Seated chest-press machine"* |
| `Barbell_Bench_Press_-_Medium_Grip` | `Bench_Press_-_With_Bands` | same movement, lying, bands standing in for plates |
| `Barbell_Squat` | `Dumbbell_Squat` | reference-set.md: *"Same movement pattern, held at the sides"* |
| `Barbell_Squat` | `Goblet_Squat` | *"squat down between your legs... holding a kettlebell"* — same squat, front-loaded |
| `Barbell_Curl` | `Dumbbell_Bicep_Curl` | reference-set.md: *"Same as above, dumbbell equivalent"* |
| `Barbell_Curl` | `EZ-Bar_Curl` | reference-set.md: identical curl, bar shape only difference |
| `Seated_Cable_Rows` | `Leverage_Iso_Row` | both a seated machine/cable row pulling the handles to the torso — reference-set.md: *"Seated machine row"* |
| `Pushups` | `Push-Up_Wide` | own instructions: *"support your body on your toes and hands... allow the elbows to flex, lowering your chest... press your upper body back up"* — the same horizontal push, hands set wider |
| `Pushups` | `Pushups_Close_and_Wide_Hand_Positions` | own instructions describe the identical movement with hands "wider than shoulder width" or "closer than shoulder width" |
| `Pullups` | `Wide-Grip_Rear_Pull-Up` | own instructions: *"Pull your torso up until the bar is near the back of your neck"* — the same vertical pull, behind-the-neck variant |
| `Pullups` | `V-Bar_Pullup` | own instructions: *"pull your torso up while leaning your head back slightly"* on a neutral-grip handle — same movement, different grip |
| `Seated_Flat_Bench_Leg_Pull-In` | `Seated_Leg_Tucks` | `docs/enrichment/residue.md` found this while reading: the two ids carry **byte-identical instructions** in the source dataset |

## Regression edges

| easier | harder | note |
|---|---|---|
| `Band_Assisted_Pull-Up` | `Pullups` | the band removes part of bodyweight from the same vertical pull — `docs/enrichment/definitions.md`'s own example of the mechanism, *"an assisted pull-up is a `regression_of` a pull-up"* |
| `Wide-Grip_Lat_Pulldown` | `Pullups` | own instructions describe the same vertical pull with the load on a stack instead of bodyweight — usable in place of a pull-up on a day the load needs to come down, not up |
| `Incline_Push-Up` | `Pushups` | own instructions: hands elevated on a bench reduces the share of bodyweight pressed, same horizontal push |
| `Bodyweight_Squat` | `Barbell_Squat` | reference-set.md: *"the axial-load rule requires 'a real external load,' bodyweight alone does not qualify"* — same squat, no load yet |

## Confirming the required case

`Arnold_Dumbbell_Press`, `Kettlebell_Arnold_Press` and `Standing_Military_Press` all
resolve to the one group above, representative `Standing_Military_Press` — the case
`docs/work/02-admissible-catalog/issues/04-reading-the-residue.md` names by id.
