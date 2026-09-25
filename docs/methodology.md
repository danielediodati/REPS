# Methodology

What the planner knows about training. The engine decides what is **possible**; the planner decides what is **good**, and this is what it reasons with. It gives ranges and principles, never a template: where a workout lands inside a range depends on the person, the time they give and what they say.

## Ranges by goal

The goal is one per mesocycle. Volume is weekly in the literature and counted per **cycle** here; a cycle is roughly a week of training.

| | strength | hypertrophy | recomposition | muscular endurance |
|---|---|---|---|---|
| reps per set | 1–6 | 6–30, mostly 6–15 | 8–20 | 15–30 |
| reps in reserve | 1–3 | 0–3 | 0–3 | 0–2 |
| sets per exercise | 2–5 | 2–5 | 2–4 | 2–4 |
| rest between sets | 3–5 min | 1–3 min | 45 s–2 min | 30–90 s |
| working sets per muscle per cycle | 6–15 | 10–20 | 10–20 | 8–16 |
| sources | [7], [10], [3] | [1], [2], [3], [7], [8] | [9], [1] | [7] |

- **Recomposition** is hypertrophy work at a higher density: shorter rest buys time for more exercises and costs reps per set [2], [8]. Its rest band is practice, not a finding: [9] does not prescribe one.
- **The upper volume bounds are practice.** The evidence is a dose-response with ≥10 sets a week as its top category [1], [10]; no study sets a ceiling.
- **Strength on body weight and bands** means a harder variant (archer, single-leg, more tension), not a heavier bar. The limit is progression, not the tool [6].

## Principles

**A working set** ends within the reps in reserve of the goal. Going all the way to failure adds little or nothing [4], [10]; a warm-up set is not counted.

**Volume is counted per muscle**, one of the catalog's `primary_muscles`, never per group: `arms` hides biceps and triceps, `legs` hides six muscles. The groups divide the session's time, nothing else ([muscle-groups.md](../src/trainer/data/muscle-groups.md)).

**A session has parts**, sized to the time; compound before isolation, larger muscles before smaller [7], and strength work early in the session [10]:

| part | what it is for |
|---|---|
| warm-up and activation | preparing the joints and the first movement |
| main work | compound movements, the heaviest sets, while fresh |
| accessories | isolation, angles and muscles the main work did not reach |
| closing | mobility, stretching, core |

**Choosing exercises**: a second exercise for the same muscle has to add something (another angle, range or tool). Variants of one movement are one movement: four push-ups are not four exercises.

**How exercises are grouped**:

| structure | what it buys | what it costs |
|---|---|---|
| straight sets | full rest, the most reps per set | time |
| superset | time [5] | reps, when the two share a muscle |
| circuit | time and conditioning | reps per set on every exercise in it |

**Volume matters more than structure**: set structure does not consistently change outcomes [10]. A circuit is fine when every muscle in it still gets its sets; it is not a way to spend fewer of them. Time left over goes to the muscle furthest below its range.

**What the person says changes the plan**, and the planner decides how:

| they say | what the planner knows |
|---|---|
| a joint hurts | change the range or the variant; keep the muscle if it can be trained without pain |
| one side is weaker | unilateral work, weak side first, the strong side matching its reps |
| back after a long break | further from failure for the first sessions |
| little time or tired today | fewer sets before a different structure |

## Sources

1. Schoenfeld BJ, Ogborn D, Krieger JW. Dose-response relationship between weekly resistance training volume and increases in muscle mass. *J Sports Sci*. 2017;35(11):1073–1082.
2. Schoenfeld BJ et al. Longer interset rest periods enhance muscle strength and hypertrophy in resistance-trained men. *J Strength Cond Res*. 2016;30(7):1805–1812.
3. Schoenfeld BJ, Grgic J, Ogborn D, Krieger JW. Strength and hypertrophy adaptations between low- vs. high-load resistance training. *J Strength Cond Res*. 2017;31(12):3508–3523.
4. Refalo MC et al. Influence of resistance training proximity-to-failure on skeletal muscle hypertrophy. *Sports Med*. 2023;53(3):649–665.
5. Weakley JJS et al. The effects of traditional, superset, and tri-set resistance training structures on perceived intensity and physiological responses. *Eur J Appl Physiol*. 2017;117(9):1877–1889.
6. Calatayud J et al. Bench press and push-up at comparable levels of muscle activity results in similar strength gains. *J Strength Cond Res*. 2015;29(1):246–253.
7. American College of Sports Medicine. Progression models in resistance training for healthy adults. *Med Sci Sports Exerc*. 2009;41(3):687–708.
8. Grgic J, Lazinica B, Mikulic P, Krieger JW, Schoenfeld BJ. The effects of short versus long inter-set rest intervals in resistance training on measures of muscle hypertrophy: a systematic review. *Eur J Sport Sci*. 2017;17(8):983–993.
9. Barakat C, Pearson J, Escalante G, Campbell B, De Souza EO. Body recomposition: can trained individuals build muscle and lose fat at the same time? *Strength Cond J*. 2020;42(5):7–21.
10. Currier BS et al. American College of Sports Medicine position stand. Resistance training prescription for muscle function, hypertrophy, and physical performance in healthy adults: an overview of reviews. *Med Sci Sports Exerc*. 2026;58(4):851–872. Updates [7].
