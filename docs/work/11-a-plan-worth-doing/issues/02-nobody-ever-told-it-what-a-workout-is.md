# Nobody ever told the planner what a good workout is

Status: ready-for-agent

The first real plan out of the bot, for chest and arms in 45 minutes with body weight and bands:

```
Blocco 1 · 3 giri · 90s di recupero · 10:18
  Cross Over - With Bands, Incline Push-Up, Clock Push-Up, Push-Up Wide  -- 8 reps each
Blocco 2 · 3 giri · 90s di recupero · 14:00
  Band Skull Crusher, Bench Dips, Speed Band Overhead Triceps,
  Standing Towel Triceps Extension, Body Tricep Press  -- 10 reps each
Totale 25 min su 45
```

It passes every rule the engine has. `PLANNING` is a list of prohibitions and never says what a workout *is*; a circuit is the cheapest shape that fits a budget, and nothing told the model otherwise. A larger model did not fix it (issue 03, comments: `gpt-oss-120b` on OpenRouter, 10–14 minutes of 45).

## The methodology

[`docs/methodology.md`](../../../../docs/methodology.md), written from the literature, sources checked on PubMed, reviewed by the user. What was settled writing it:

- **Knowledge, not a template.** Ranges per goal and principles; where a workout lands inside them is the planner's decision, from the time given and what the person says. Rules extracted from one person's plan are overfitting.
- **Nothing personal.** The project is generic; one user's injuries, sides and schedule are memory (session 13), never the repo.
- **What the user says in the moment is already reachable**: `Adapting.said` and `Refusal.because` carry it to the planner. What must last across sessions (*"my left side is weaker"*) waits for session 13's memory.
- **One goal per mesocycle**, declared in `training.toml` as `goal`; changing it is a new mesocycle. Onboarding writes it from session 13.

## What to build

- **The planner reads the methodology.** It goes in the brief of `PLANNING` and `MESOCYCLE_PLANNING`, with the request's goal named. It must ship with the package, so the file moves under `src/trainer/data/` beside `muscle-groups.md`, and `docs/` links to it.
- **`goal` in `training.toml`**, a sixth declaration. Its values are the goal columns of the methodology, read from the file, never copied into a constant (CLAUDE.md § Standing rules). A missing `goal` is reported as a state with its fix.
- **`mechanic` in the planner's `KEEPS`**, so the model can tell compound from isolation, which the methodology's parts rely on.

## Acceptance criteria

- [ ] The same request as above, chest and arms in 45 minutes with body weight and bands, does not come back as a circuit of same-muscle exercises.
- [ ] `trainer eval --suite plan` reported before and after, with the invariants at 100%.
- [ ] An unknown `goal` is rejected naming the ones the methodology has.
- [ ] The full test suite and mypy are green.

## Comments

Issue 03 puts a floor under the clock. It does not fix this: given a floor and no methodology, a tenth exercise in a circuit is still the cheapest way to fill the time.

Issue 01's measurement (a large model at full reasoning) no longer blocks writing the methodology; it says whether the methodology is enough on the local model.
