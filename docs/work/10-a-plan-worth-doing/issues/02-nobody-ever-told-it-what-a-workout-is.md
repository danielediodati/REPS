# Nobody ever told the planner what a good workout is

Status: needs-info

The first real plan out of the bot, for chest and arms in 45 minutes with body weight and bands:

```
Blocco 1 · 3 giri · 90s di recupero · 10:18
  Cross Over - With Bands, Incline Push-Up, Clock Push-Up, Push-Up Wide  -- 8 reps each
Blocco 2 · 3 giri · 90s di recupero · 14:00
  Band Skull Crusher, Bench Dips, Speed Band Overhead Triceps,
  Standing Towel Triceps Extension, Body Tricep Press  -- 10 reps each
Totale 25 min su 45
```

Two circuits, nine exercises, four push-up variants for chest. It passes every rule the engine has.

## Why it happened, measured rather than guessed

- **Nothing in this project checks whether a plan is good.** `trainer eval` says so itself: *"Not good plan / bad plan -- properties that must hold always"*. The six invariants are legality. This plan is legal.
- **The brief is a list of prohibitions.** `PLANNING` says what is admissible, what may not repeat, what may not overrun. It never says what a workout *is*. `PlanBlock.rounds` tells the model that one exercise is straight sets and more is a circuit — it describes the form and never says when to reach for which.
- **A circuit is the cheap shape.** The same five exercises cost 14 minutes as one block and 32 as five: three rests against fifteen. Asked to fit a budget and told nothing about structure, a model finds the shape that fits.
- **The reasoning is deliberately at its minimum.** `models.REASONING = "low"`, because on the dev laptop `high` costs 296 s against 39 s for the same prompt. That trade was made for the machine and has never been measured in plans.

## What is needed before this can be specified

**The user's own methodology**, which is not the agent's to invent and not the engine's to hold: how many exercises a group gets, what a working set is, which rest goes with which intent, and when a superset or a circuit is the right answer rather than the cheap one. ROADMAP has *the methodology document* under **After 1.0.0**; this plan is what that deferral looks like from the outside.

**The measurement that separates the causes**, which is issue 01. One identical request on Groq, on a large model at full reasoning. If the plan is sound, the cause is the local model and the machine. If it is the same shape, the cause is the empty brief — which is the likelier of the two and the only one a document fixes. Blocked today: the configured Groq model answers 404.

## Comments

Issue 03 puts a floor under the clock. It does not fix this: given a floor and no methodology, filling the time by adding a tenth exercise to a circuit is still the cheapest move available.
