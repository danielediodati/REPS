# The engine costs and constrains; it never prescribes method

Rules define what is **possible** — the admissible set, the time available, the
exclusions. The agent decides what is **good** — which split, how the workout is
structured, how long to rest, which exercise fills a slot, whether today is a
full workout or a reduced one. Anything the engine computes that answers *what
is good* is a rule standing where deliberation belongs, and it turns the agent
into a transformation step with a language model inside it.

## Why this is written down

Session 3 was designed twice. The first design had the engine derive the split
from the cycle length, enforce a per-workout coverage rule (*a leg workout must
contain a squat and a hip hinge*), fix rest at the top of each of TRAINER.md's
three bands, and repair an over-long plan with a fixed cut order. Every one of
those is defensible on its own and all four together leave the agent filling
slots in a plan the engine already decided.

The document had already said so and it was missed twice. TRAINER.md's state
table lists the mesocycle as *«chosen scheme + rationale + start date + split»*
— `split` sits beside `rationale`, and a value derived from a rule needs no
reason recorded next to it. And *volume deficit* was in the glossary from the
start: the mechanism for noticing a degenerate plan already existed, as a
number that accumulates and that someone has to look at, not as a prohibition
issued in advance.

## What it rules out

- **A cut.** Time is allocated before the plan is built, against a declared
  budget, and `remaining_budget` is asked before an exercise is added rather
  than after. A plan that does not fit is **rejected** by the validator, not
  silently repaired — repairing it hides from the agent that it got the
  arithmetic wrong. `simulate_cut` is not built.
- **A fixed rest value.** TRAINER.md's three bands become a reference the
  planner may consult, never a value the engine imposes. Rest is prescribed,
  travels with the plan, and is recorded, so progression knows what it is
  measuring against. TRAINER.md's *«never the rest periods»* survives in the
  only sense still standing: an automatic cut must never shorten rest behind
  the planner's back — and there is no longer an automatic cut to do it.
- **A menu of splits, a coverage rule, a table of time ratios.** *60-40 on two
  groups* is what one workout might look like, not a law; three groups in a
  workout make it meaningless. The engine does the arithmetic over whatever
  proportions it is handed.

## The deficit is measured on two axes, not one

Replacing the coverage rule with a deficit only works if the deficit can see
the degeneration the rule was aimed at, and one axis cannot. Counted per
movement pattern, a leg workout made of calf raises is caught — the catalog
puts quadriceps in `squat` and `single-leg` and hamstrings in `hip hinge`, so
their absence is visible. An arm workout made entirely of curls is not: biceps,
triceps and forearms are all `isolation`, and the pattern axis sees one
undifferentiated bucket of 281 rows.

So volume is counted per movement pattern **and** per muscle, over a cycle.
The pattern axis answers *am I balanced* — push against pull, squat against
hinge; the muscle axis answers *am I touching this at all*. Every catalog row
already carries both labels, so counting both costs nothing when a workout is
written down.

This is also what keeps the six muscle groups honest. They are the unit a
workout's **time** is allocated to and nothing else: as an accounting axis
`arms` would erase exactly the biceps/triceps distinction this paragraph
exists to preserve. Allocation is coarse on purpose; measurement is not.

## What is left in the engine

Costing a plan (`plan_duration`), the remaining budget, the admissible set,
and the volume deficit — per pattern and per muscle, per cycle. All four are
arithmetic or set operations over the catalog and the logged state. None of
them decides how to train.
