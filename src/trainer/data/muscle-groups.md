# The six muscle groups

The catalog's seventeen `primary_muscles` values, each assigned to one of the six
muscle groups a workout's time is allocated to — `chest`, `back`, `shoulders`,
`arms`, `legs`, `core` — or to none. CONTEXT.md defines the term; this file is the
mapping itself, and it is the only place the six names exist. Every reader of the
vocabulary reads it from here, because a hand-copied list of values was wrong in
three places once already (CLAUDE.md § Standing rules).

**Allocating time is all this mapping does.** Volume is never counted on this axis:
`arms` erases exactly the biceps/triceps distinction the muscle axis exists to
keep. A question about what the body is accumulating is asked per **muscle** — one
of the seventeen below — or per movement pattern, never per group.

**Every one of the seventeen is here, including the one that maps to nothing.** A
value absent from this table is a value silently dropped from every allocation, so
`tests/test_muscle_groups.py` fails the day the catalog grows an eighteenth rather
than letting it fall through.

## The mapping

`group` is one of the six, or `-` for a muscle no split ever asks for.

| muscle | group | why |
|---|---|---|
| `abdominals` | `core` | the trunk flexors — the group's own centre |
| `abductors` | `legs` | hip musculature; it moves the leg, and no split trains it apart from one |
| `adductors` | `legs` | hip musculature, the same as its opposing pair |
| `biceps` | `arms` | elbow flexion |
| `calves` | `legs` | below the knee, but nothing else trains with it |
| `chest` | `chest` | the group is named for it |
| `forearms` | `arms` | grip and wrist work, trained with the elbow flexors it shares a limb with |
| `glutes` | `legs` | hip extension is the leg's largest movement, not a group of its own |
| `hamstrings` | `legs` | knee flexion and hip extension |
| `lats` | `back` | the pull that comes from overhead |
| `lower back` | `core` | **trunk musculature, not back.** The spinal erectors resist and produce trunk motion; they belong with the abdominals they oppose, and a `back` day that counts them is counting bracing as pulling |
| `middle back` | `back` | the horizontal pull |
| `neck` | `-` | **no group.** Its eight rows stay reachable in the catalog and no split ever asks for them; there is no honest group to fold them into, and inventing one would put time on a body part nobody is training |
| `quadriceps` | `legs` | knee extension |
| `shoulders` | `shoulders` | the group is named for it |
| `traps` | `back` | scapular retraction and elevation — trained by the same pulls as the rest of the upper back |
| `triceps` | `arms` | elbow extension |
