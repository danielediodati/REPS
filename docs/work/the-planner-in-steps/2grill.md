# The planner in steps — to grill

Status: needs-triage

A proposal, not a decision. It is grilled first, then written as an ADR, then cut into a session placed **before 12.4**.

## Where it came from

On 2026-09-25 the first screening of 12.4 (the planner's matrix) ran on the mesocycle suite (10.5): six adverse situations, each a two-slot mesocycle (`evaluation.SPLIT`), six invariants per workout, bar 100%.

| Model, effort, host | Held | $ a situation | s a situation |
|---|---|---|---|
| `openai/gpt-oss-20b` low, CoreWeave | 0 / 6: emit returned empty text three times, then the host stopped answering | 0.0021 | 76 |
| `openai/gpt-oss-20b` low, AkashML | 1 / 2 run, 4 not run (429, shared pool) | 0.0019 | 183 |
| `openai/gpt-oss-120b` low, DeepInfra | 2 / 6 | 0.0032 | 211 |
| `deepseek/deepseek-v4-flash` high, DeepInfra | 5 / 6 | 0.0069 | 497 |

`deepseek-v4-flash` takes only `high` or `xhigh` as an effort. Records: the scratchpad of that session, not kept.

The failures shared by all three models:

- **Time far under the floor.** First attempts of 3–7 minutes against 30 asked; feedback raises them, the attempts run out before 25. DeepSeek, which made ~12 tool calls a situation against 2–4, missed by 1–6 minutes instead.
- **Exercises in the wrong workout**: a core exercise in the chest-and-back slot. `planner._mesocycle_schema` holds `exercise_id` to the **union** of every slot's admissible ids, so the shape allows it and only the validator catches it, at the cost of an attempt.
- **Invented `despite` rows**: exercises the user never refused, written as refused, even where no preference exists.
- gpt-oss-20b repeated one wrong emission three times, word for word, ignoring the feedback.

Also found: the suite sends no per-group `allocation`, which the door does (`plan._divided`), so the suite asks for more than a real request does.

## The user's reasoning

The user's position: the problem is structural. A small model reasons well on small questions, and today it is asked for everything in one emission. How the user would build a programme:

1. **The type**, from the number of sessions in the cycle and the goal.
2. **A style**, one concept repeated in every session: e.g. supersets, or straight sets, with short rest; reps in a band per session.
3. **The muscles across the sessions**, with recovery in mind: a muscle worked as a secondary is not worked as a primary the day after; a large group paired with a small one (chest with biceps).
4. **The time across the groups**: the larger the muscle, the more exercises it needs.
5. **The exercises**, last.

The model decides every step; the whole is checked together.

## Why this is not ETL

ETL drift was **code taking decisions from the model** (session 3: split derived from the cycle length, a fixed cut order, rest fixed at the top of a band; see ADR-0001). Here each step is a model decision; code only orders the steps and checks what is possible. It is task decomposition (plan-and-execute), which is what LangGraph's nodes and conditional edges are for.

It moves decisions **toward** the model:

| Step | Who decides today |
|---|---|
| 1. type | nobody, explicitly: implicit inside one emission |
| 2. style | does not exist: each workout invents its own |
| 3. muscles across sessions | the user, by hand, in `training.toml`'s `split` (ADR-0003) |
| 4. time across groups | code: `plan._divided` splits evenly, "as a starting point" |
| 5. exercises | the model, together with 1–4 |

TRAINER.md's state table already puts `split` beside `rationale`: the split was always meant as a reasoned choice.

## The guard against ETL

To go in the ADR and be checked on every node:

> **A step belongs to the model if it cannot be replaced by a function without losing something.** A node that could be written in Python with the same result is ETL there: remove it or give it back to the model. Code orders the steps and checks the possible; it never fills a step and never chooses between good options.

And: **a step's output is a decision in words with its reason**, inside the methodology's ranges ([methodology.md](../../../src/trainer/data/methodology.md)), never a pick from a closed menu. A field like *style: A, B or C* is a template.

## Risks

1. **An early error propagates.** A wrong style at step 2 contaminates 3–5. The validator must send the model back to **the step that owns the broken rule** (time → 4, admissible → 5), not always to the end; and a step must be able to reopen the one before it.
2. **Step 3 reopens ADR-0003.** Today the user declares the split.
3. **More calls, more latency.** Each is smaller, so cost should not grow much; wall time will. Acceptable for a mesocycle planned every few weeks.
4. **The model as a form-filler** (see the guard).

## Questions to grill

1. **Step 3 and ADR-0003.** Does the split become the planner's, with `training.toml` declaring only what the user wants trained and how many sessions? Or does the planner work inside the declared split and decide only pairings and secondaries? What does onboarding (session 13) then write?
2. **What each step produces**, and where it is kept: in the graph state only, in the mesocycle row, shown to the user? Is the style part of the accepted mesocycle, so a change (10.3) keeps it?
3. **Which steps see which tools.** Does step 5 alone get `admissible_set`, per workout? Does step 4 get `remaining_budget` / `allocate`?
4. **Where a refusal goes.** Map each validator rule to the step that owns it. What bounds the attempts: per step, or per run?
5. **One emission per workout at step 5**, each held to its own admissible ids? That removes the wrong-workout error by shape, as the single workout already does.
6. **Does the user see the steps?** In Telegram the draft already streams progress (7.2): the type and the style could be what it shows.
7. **Adaptation and change (10.3).** An adaptation plans one workout: does it rerun step 5 only, inside the mesocycle's style? A change: from which step?
8. **Is step 1 a step?** With the goal declared and the sessions counted, is "the type" a decision left to make, or already given?
9. **The suite.** Does it grade the steps (e.g. step 3 respects recovery) or only the final mesocycle? Invariants stay legal-only (ADR-0010): a judgement is not an invariant.
10. **The allocation gap in the suite**: fix it now, or leave it to this redesign, which replaces `_divided` anyway?

## Effect on the roadmap

- **12.4 waits for this.** Measuring models on a planner about to change measures the wrong thing. The four rows above are the *before*.
- **12.3 (the logger's matrix) is untouched** and can run now.
- **Also for 12.4, found in the same screening**: provider calls have no timeout (one hung minutes), and a provider error reaches the matrix as `'NoneType' object is not iterable` rather than as a state naming the host.

## References

- ADR-0001, ADR-0003, ADR-0004, ADR-0008, ADR-0010; TRAINER.md § State
- `src/trainer/coach/planner.py` (`MESOCYCLE_PLANNING`, `mesocycle_brief`, `_mesocycle_schema`), `src/trainer/plan.py` (`_divided`, `validate_mesocycle`), `src/trainer/evaluation.py`
- `docs/work/12-reasoning-and-cost/spec.md` (candidates, hosts)
