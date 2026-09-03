# 01 — How long does this actually take

**What to build:** `engine/duration.py` and the `Selection` shape everything in this session builds on. A selection is an ordered sequence of items — exercise id, sets, reps — and `plan_duration(connection, selection)` turns it into minutes: `Σ [setup + sets × (work + rest)]`, `setup` read once per exercise from the catalog's `setup_cost_min`, `work ≈ reps × 3s`, and `rest` a function of the exercise's `movement_pattern` and the reps prescribed for that item.

**This is the first thing anyone can be honest with an agent about.** Session 4's agent cannot promise *«this fits in 40 minutes»* until something in the engine can actually say how long a list of exercises takes — everything else in this session (the cut, the budget) is downstream of getting this number right.

**Rest is not one number, and it is not asked of the user.** TRAINER.md gives three bands — strength 2.5-3 min, hypertrophy 90-120 s, isolation 60 s — keyed off the kind of set being performed, not off a value anyone types in. This ticket has to turn that into a rule with no gap and no invented input:

- if the item's `movement_pattern` is `isolation`, rest is **60 s**, regardless of reps — TRAINER.md gives it one value, not a range, because isolation work does not vary by load the way a compound lift does;
- otherwise the bucket follows the reps prescribed for that item: **reps ≤ 6 → strength**, **reps > 6 → hypertrophy**. Six is the conventional strength/hypertrophy boundary in the literature this project already leans on for the methodology document (session 7), so it is not a number invented for this ticket alone.

**Take the top of each range, not the middle.** This number is later spent by `simulate_cut` to decide whether a selection fits a declared budget. Undercounting rest means the real workout runs long *after* the system has already told the user it fits — the failure mode this project keeps naming as the one to avoid. So strength rest is **180 s**, hypertrophy rest is **120 s**, both the upper bound TRAINER.md gives. This is not the same move as `required_rom`'s invented degrees: TRAINER.md already supplies the range, this only picks the conservative end of a range that is already sourced.

**`setup_cost_min` is spent once per exercise, not once per set.** The formula's parenthesisation says so — `setup` sits outside the `sets ×` term — and it is exactly the enrichment field session 2 already wrote for every strength row, read the same way `admissible_set` already reads it as a `<=` bound.

**A `Selection` is new vocabulary, and only this session's tickets after this one get to extend it.** Keep it to what duration actually needs — exercise id, sets, reps — and leave `role` (primary/secondary) out: that distinction exists only for the cut in ticket 02, and adding it here would be a field this ticket has no use for and cannot test.

Reference: TRAINER.md § Engine — analytic / derived (Duration), § Persistent state (`setup_cost_min`); ROADMAP.md § Session 3.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `Selection` / `SelectionItem` (exercise id, sets, reps) is a typed shape in `engine/duration.py`, documented as the vocabulary the rest of this session's tickets extend rather than replace
- [ ] `plan_duration(connection, selection)` returns minutes as `Σ [setup + sets × (work + rest)]`, `work = reps × 3` seconds
- [ ] An `isolation`-pattern item rests 60 s regardless of reps
- [ ] A non-isolation item with reps ≤ 6 rests 180 s; with reps > 6 rests 120 s
- [ ] `setup_cost_min` is added once per exercise in the selection, never once per set
- [ ] An exercise id not in the catalog, or not enriched (`movement_pattern IS NULL`), is a named error — not a silent default rest value
- [ ] Unit tests cover all three rest buckets, an exercise appearing with multiple sets, and a selection spanning several exercises, with no LLM and no network
- [ ] `tests/test_engine_boundary.py` still passes — `duration.py` imports nothing outside the engine's own allowed set

## Comments
