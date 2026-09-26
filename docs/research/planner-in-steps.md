# The planner in steps: a proposal, being measured

Research date: 2026-09-25. A proposal, not a decision: measured first (question 0), then grilled, then an ADR and a session placed **before 12.4**.

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
2. **A style**: the model decides whether a style is held across the sessions, and which (e.g. supersets, or straight sets, with short rest; reps in a band per session). Not every programme has one: the methodology says volume matters more than structure, and a mandatory style would be the user's own taste made a template (the 11.2 trap).
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

And: **a step's output is a decision in words with its reason**, inside the methodology's ranges ([methodology.md](../../src/trainer/data/methodology.md)), never a pick from a closed menu. A field like *style: A, B or C* is a template.

## Risks

1. **An early error propagates.** A wrong style at step 2 contaminates 3–5. The validator must send the model back to **the step that owns the broken rule** (time → 4, admissible → 5), not always to the end; and a step must be able to reopen the one before it.
2. **Step 3 reopens ADR-0003.** Today the user declares the split.
3. **More calls, more latency.** Each is smaller, so cost should not grow much; wall time will. Acceptable for a mesocycle planned every few weeks.
4. **The model as a form-filler** (see the guard).

## Questions to grill

0. **Measure before redesigning** (grilled 2026-09-25). The evidence is four runs at one repetition, and DeepSeek reached 5 / 6 on one emission: the cause may be model size, not structure. Questions 1–10 wait for the number.

   | | Decided |
   |---|---|
   | On `main`, for real | a timeout on provider calls; a provider error reported as a state naming the host |
   | On a probe branch | everything below; thrown away once steps 1–3 are decided |
   | Suite | every slot carries its `allocation`, from `plan._divided` as the door's does |
   | Emission | one per workout, in sequence, each seeing the ones already accepted; a last small emission writes `cycles` and `why` over all of them |
   | Prompt | `PLANNING`, the single workout's, plus *workout N of M, and the ones before* in the message |
   | Tools | the planner's ten, at every workout |
   | Attempts | today's budget **per workout**; cost and calls reported beside it |
   | Turned down | the refused mesocycle is in every workout's brief, checked at the end; identical reopens every workout |
   | Invented `despite` | an error like any other |
   | Measure | `gpt-oss-120b` low, DeepInfra, 3 repetitions **before** (`main`) and 3 **after** (branch): ~$0.12, on the user's go |
   | Rule | after ≥ 4 / 6 mean and ≥ +2 on before → structural, grill steps 1–3; under +1 → model size, no steps; between → read the time and wrong-workout columns |
   | Result | the numbers, per rule, with cost and time, go here on `main` |

   **Measured 2026-09-25**, `gpt-oss-120b` low, DeepInfra, 3 repetitions. Before is `87c0686` (`main`), after is `34f49e5` (`probe/planner-per-workout`).

   | | Before | After |
   |---|---|---|
   | Runs holding every invariant | 9 / 18 (50%), 2 not run | 11 / 18 (61%) |
   | Mean situations held | 3.0 / 6 | 3.7 / 6 |
   | $ in all, a run | $0.132, $0.0070 | $0.077, $0.0037 |
   | s a run | 140 | 93 |

   Refusals over every attempt, by rule (a run makes several):

   | Rule | Before | After |
   |---|---|---|
   | budget (time) | 17 | 22 |
   | preferences (`despite`) | 13 | 10 |
   | duplicates | 12 | 1 |
   | admissible: wrong workout | 3, and 4 in the turned-down plans | 0 |
   | slots: wrong workout count | 2 | 0 |
   | shape: not JSON | 2 | **13** |

   - **Not conclusive.** 5 of the after's 7 failed runs were lost to an emission that is not JSON, a provider fault and not the plan: the after lies anywhere between 11 and 16 / 18. The before lost one run the same way. Measured again once that fault is a provider refusal rather than an attempt (question 0, second pass).
   - The structural errors went (wrong workout, workout count, duplicates); the time did not move, with the allocation in every brief.
   - The fault: a single-workout emission that is not JSON under the strict schema, 8 of 13 empty (`Expecting value: line 1 column 1`), each still paid for. The record kept no emitted text, so its cause could not be read.
   - One workout at a time was **cheaper and faster**, not dearer: each call carries less.

   **Second pass, decided 2026-09-25.** On `main` first: each attempt's emitted text in the record; an emission that is not JSON is a provider refusal, retried within `REJECTIONS`, not an attempt. Then before and after again, same model, host and repetitions (~$0.21, on the user's go), under the same rule. More than 1 run in 18 lost to a provider fault voids the pass.

   **Second pass, measured 2026-09-26**, before `c5be289`, after `d03d28f`.

   | | Before | After |
   |---|---|---|
   | Runs holding every invariant | 7 / 18 (38%) | 8 / 18 (44%) |
   | Lost to a provider fault | 1 | **10**: 6 never JSON, 2 at the length limit, 1 429, 1 more never JSON |
   | $ in all, a run | $0.062, $0.0031 | $0.051, $0.0051 |

   - **Void by the rule**: the after lost 10 runs. Of the 8 it ran to the end it held 7 of 8, which says nothing: every `no-history` run was among the lost.
   - **The fault is DeepInfra not holding the strict schema** for `gpt-oss-120b`. The kept text breaks the schema's own structure, which a constrained decoder cannot write: a `prescription` object with its key missing, strings cut mid-word, empty replies, and two replies that ran to the length limit (114,507 and 16,384 completion tokens, $0.020 and $0.010 for one call). `require_parameters` routes only to hosts that *declare* `response_format`; it does not make them honour it.
   - Before also went from 9 to 7 / 18 between passes: at 18 runs a situation's swing is two runs.

   **Third pass, 2026-09-26**, with `strict=True` (`303721d`), after `88fd021`.

   | | Before | After |
   |---|---|---|
   | Runs holding every invariant | 7 / 18 | 10 / 18 |
   | Lost to a provider fault | 3 | 8 |
   | Held, of the runs that finished | 7 / 15 | **10 / 10** |
   | $ a run, s a run | $0.0029, 98 | $0.0030, 68 |

   - **Void by the rule** again, both sides.
   - **Strict did not stop the broken emissions** on DeepInfra, which a constrained decoder could not write: the host does not enforce the schema for this model. Ten single emissions in a short context were valid with and without it.
   - **The retry returned the same bytes**: every lost run failed three times at the same character. Asking again unchanged does not recover.
   - A run lost this way leaves no record, so its text was not kept: the diagnosis misses exactly the runs it was for.
   - Of the runs that finished, the after held every one; the before failed on time and duplicates as in every pass. Suggestive, not measured: which runs are lost is not random.
1. **Step 3 and ADR-0003.** Does the split become the planner's, with `training.toml` declaring only what the user wants trained and how many sessions? Or does the planner work inside the declared split and decide only pairings and secondaries? What does onboarding (session 13) then write?
2. **What each step produces**, and where it is kept: in the graph state only, in the mesocycle row, shown to the user? Is the style part of the accepted mesocycle, so a change (10.3) keeps it?
3. **Which steps see which tools.** Does step 5 alone get `admissible_set`, per workout? Does step 4 get `remaining_budget` / `allocate`?
4. **Where a refusal goes.** Map each validator rule to the step that owns it. What bounds the attempts: per step, or per run?
5. **One emission per workout at step 5**, each held to its own admissible ids? That removes the wrong-workout error by shape, as the single workout already does.
6. **Does the user see the steps?** In Telegram the draft already streams progress (7.2): the type and the style could be what it shows.
7. **Adaptation and change (10.3).** An adaptation plans one workout: does it rerun step 5 only, inside the mesocycle's style? A change: from which step?
8. **Is step 1 a step?** With the goal declared and the sessions counted, is "the type" a decision left to make, or already given?
9. **The suite.** Does it grade the steps (e.g. step 3 respects recovery) or only the final mesocycle? Invariants stay legal-only (ADR-0010): a judgement is not an invariant.
10. **Is every step needed?** Step 1 may be given (goal and sessions are declared) and step 3 hangs on question 1; the measured errors point at 4 and 5.

## Effect on the roadmap

- **12.4 waits for this.** Measuring models on a planner about to change measures the wrong thing. The four rows above are the *before*.
- **12.3 (the logger's matrix) is untouched** and can run now.
- **Fixed before the measure, found in the same screening**: an OpenRouter call is bounded (`models.TIMEOUT_S`, one retry), and a host's error, or its silence, reaches the matrix as `ProviderFailed` naming the host instead of `'NoneType' object is not iterable`.

## References

- ADR-0001, ADR-0003, ADR-0004, ADR-0008, ADR-0010; TRAINER.md § State
- `src/trainer/coach/planner.py` (`MESOCYCLE_PLANNING`, `mesocycle_brief`, `_mesocycle_schema`), `src/trainer/plan.py` (`_divided`, `validate_mesocycle`), `src/trainer/evaluation.py`
- `docs/work/12-reasoning-and-cost/spec.md` (candidates, hosts)
