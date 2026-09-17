# The declared minutes are a target, not a ceiling

Status: ready-for-agent

`_inside_the_budget` refuses a plan that runs over and says nothing about one that runs under. A plan that spends 25 minutes of a 45-minute request is valid today, and the six invariants pass it: `_respects_the_time` reads only `plans.BUDGET`, and `_does_not_degenerate` measures which groups are covered, never how much of the clock was used.

**The decision, from the user**: the plan must land within **five minutes either side** of the request. Forty-five minutes accepts forty to fifty.

This widens the ceiling as well as adding a floor, and that is deliberate. It also contradicts `training.toml`, where `duration_cap_min` is documented as *"the most a single workout may run"* — the word has to change with the rule, or the file and the validator say opposite things.

## What to build

- **`plan.TOLERANCE_MIN = 5`**, and `_inside_the_budget` refusing on either side of it. Two messages, because the two are not the same mistake: over is *the workout does not fit the time you have*; under is *you asked for 45 minutes and this gives you 25*. Neither is repaired — ADR-0001 stands, the plan is refused whole and the planner writes another.
- **`_respects_the_time` keeps reading `plans.BUDGET`** and therefore covers both without changing: one rule, one name, read in one place.
- **The brief says the number.** `PLANNING` currently says *"The plan must fit the time declared"*, which a 25-minute plan satisfies. It has to say that the plan is built **to** the time, within five minutes.
- **`training.example.toml` and `config.TrainingConfig`**: `duration_cap_min` is the time a workout is built to, give or take five minutes. Renaming the key is a migration and is out of scope; the documentation of it is not.

## What this may break, and it is the point of the ticket

`trainer eval --suite plan` has a bar of 100% over six adverse situations, and a floor is a new way to fail. `no-equipment` is 15 minutes of body weight, so its floor is 10; `contradictory` is 30 minutes over six groups. **Run the suite before and after**, and report both. If a situation cannot be satisfied with the floor, that is a finding about the request or the model, not a reason to lower the floor quietly.

## Acceptance criteria

- [ ] A plan under the floor is refused, with a violation naming how far under it is.
- [ ] A plan over by three minutes is accepted, and one over by eight is not.
- [ ] `trainer eval --suite plan` reported before and after, with the invariants at 100%.
- [ ] `training.toml`'s own words and the rule agree.
- [ ] The full test suite and mypy are green.

## Comments

Found by running the bot for real: two circuits, nine exercises, 25 minutes of 45, and nothing anywhere objected.

**A floor alone will not buy a good workout.** The same run showed why the plan was cheap: the five triceps exercises cost 14 minutes as one circuit and 32 as straight sets, because a circuit pays three rests instead of fifteen. Given a floor and no methodology, a model that wants to fill time can add exercises to a circuit rather than prescribe sets. That half is issue 02, and this ticket does not close it.
