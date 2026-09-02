# Roadmap — sessions

> *A working hypothesis. Companion to [TRAINER.md](TRAINER.md): that one says **what** gets built and why, this one says **in what order** and where the cuts fall.*

## Slicing rule

A **session** ends with a binary that runs and that you can exercise. Not with a finished component.

> **If there is no command to run at the end of the session, the session was sliced wrong.**

Every session unpacks into **no more than five issues**. Each issue closes with `/implement` in a clean context, so it has to stand on its own and point at the sections of TRAINER.md it needs.

An honest note on what *«testable by the end user»* means: until session 5 the end user is **you in front of a CLI**, and what you verify is that the engine answers truthfully. From 5 onward it is someone who wants to train, and what you verify is the plan. The jump is at 5, not before, and it has to be budgeted for.

## The path

| # | version | at the end you can |
|---|---|---|
| 1 | `0.1.0` | browse 800 exercises filtering by equipment |
| 2 | `0.2.0` | query the catalog by movement pattern and range of motion |
| 3 | `0.3.0` | ask *«what can I do today»* and get the admissible set back |
| 4 | `0.4.0` | know how long a selection takes and what would get cut |
| 5 | `0.5.0` | **get a real plan** from an agent that cannot break the constraints |
| 6 | `0.6.0` | report the workout in twenty seconds and watch the state move |
| 7 | `0.7.0` | start from nothing: ten questions, and a week 1 plan at the end |
| 8 | `0.8.0` | cross the weeks — progression, deload, return from a break |
| 9 | `0.9.0` | be remembered: preferences and constraints survive the session |
| 10 | `0.10.0` | watch the system form a hypothesis about you and design the trial |
| 11 | **`1.0.0`** | **train for eight weeks without the program drifting** |

`1.0.0` is defined by TRAINER.md's criterion: *you are still logging, the loads have gone up, the aches have not got worse*. Everything needed to hold up for two months is inside. Everything needed to **demonstrate** that the loop works comes after, and that is session 12.

---

## Session 1 — `0.1.0` — The raw catalog

**Runs**: `trainer catalog --equipment dumbbell` lists the exercises.

1. Skeleton: Python package, SQLite with versioned migrations, CLI, `engine/` laid out as a pure library separate from everything else. — **done** `35d2d1f`
2. Import free-exercise-db into `exercises` — native fields, instructions and images included, retrievable by id. — **done** `c6f11f3`
3. `catalog` command with filters on the native fields. — **done** `c5a5060`
4. Markdown dump of the catalog, versioned — the first half of the *«the DB
   is the truth, the snapshot is the readable history»* mechanism. — **done**
   `a2d3ecc`
5. Catalog profile: counts by category, equipment, level, mechanic and force. — **done** `8ba09c4`

> The equipment value is `dumbbell`, singular — the source's vocabulary, verified against the dataset. Normalising it to something more natural in the CLI would introduce a private vocabulary at the very first command of the project, and everything downstream would inherit it.

> Issue 5 is the one addition to what this session originally listed. *«~800 exercises»* counts stretching, cardio, plyometrics and strongman: how many are actually strength work is both the real size of the pool the admissible set is drawn from and the multiplier on session 2's enrichment cost — the only external cost in the project. The session ended with it: **584 of 876**, the other 292 being stretching (123), plyometrics (61), powerlifting (38), olympic weightlifting (35), strongman (21) and cardio (14). Run `trainer catalog --stats` for the rest.

## Session 2 — `0.2.0` — The enriched catalog

**Runs**: `trainer catalog --pattern hinge --max-rom shoulder:flexion:120`.

1. Migration with the seven fields from the appendix; `required_rom` structured as a triple, in a child table because one exercise loads more than one joint. Plus per-field provenance — a value written by a rule, by hand or by a vote is not worth the same.
2. The vocabulary definitions written out, and the deterministic pass that applies whatever the native fields already decide.
3. 60-80 movements decided by hand as the reference set, the command that scores the database against it, and the new filters exposed on the CLI.
4. Enrichment prompt with typed output, rejecting anything that does not validate. One model, one exercise, nothing written.
5. Three-pass job — two cheap models from different providers, the strong one only on the disagreements, majority vote — measured against the reference set before it runs, then the full run over the strength rows and a report of the residual disagreements.

> The field worth verifying by hand is `movement_pattern`: get it wrong there and every downstream volume count is wrong without you noticing.

> **This session was re-sliced before it was started.** The original order — prompt, three passes, full run, *then* verify fifty rows by hand — measured quality only after the one external spend in the project had already happened. Two changes. A deterministic pass first, because `spinal_axial_load`, `setup_cost_min` and a good share of `movement_pattern` are already implied by columns the catalog holds, and a rule is auditable, free and reproducible where a vote is none of the three. And a hand-built reference set *before* the run instead of a hand check after it, so the accuracy figure exists while the decision to spend is still open. What made this cheap to decide: two cheap models over 584 rows is single-digit dollars, so the case for the three passes was never the money — it is that disagreement between two different providers is the only signal that says which rows are unreliable, and one model working alone produces one confident opinion and no signal at all.

> Concretely, from the imported catalog: `Arnold Dumbbell Press` and `Standing Military Press` share `force: push`, `mechanic: compound` and `category: strength`, and differ only on equipment. Nothing in the raw fields says they are the same movement. TRAINER.md's running example — *«the Arnold and the military press are the same pattern, to the engine they are interchangeable»* — has no field to rest on until this session supplies one. The Arnold also exists in two rows, dumbbell and kettlebell, which is why a conclusion points at a movement and never at an id.

## Session 3 — `0.3.0` — The admissible set

**Runs**: `trainer admissible --equipment bodyweight --time 45 --exclude vertical_push`.

1. `profile` and `pattern_state` tables, with the exclusions and their re-test date.
2. `admissible_set(exclusions, equipment, budget)` — the `WHERE` from TRAINER.md, as a library function.
3. Unit tests with **no LLM at all**: an excluded pattern never shows up, absent equipment never shows up, an expired exclusion stops excluding.
4. The command that exposes it.

## Session 4 — `0.4.0` — Time

**Runs**: give it a selection, it tells you how long it takes and what it would drop to fit into 40 minutes.

1. Duration model: `Σ [ setup + sets × (work + rest) ]`, rest from the scheme, setup from the catalog.
2. `remaining_budget` and `simulate_cut`, with the order isolation → secondary patterns → sets on the primaries.
3. Tests that the cut **never touches the rest periods**, on any branch.
4. `pattern_history` and `last_performed_load` against still-empty state — they have to answer «I don't know», not break.
5. MCP wrapper over the library. Half a day, and from here on you inspect the engine from a generic client while developing.

> MCP is pulled in earlier than TRAINER.md has it, on purpose: it costs little and the return is all in the later sessions, when the agent starts getting things wrong and you want to see what it sees.

## Session 5 — `0.5.0` — The first plan

**Runs**: `trainer plan` and you get a workout you can do tonight.

The biggest session and the least divisible: the agent without the validator is not shippable, so they stay together.

1. The tool surface exposed to the agent — thin wrappers over the same library, zero new logic.
2. Agent node that loops over the tools, with a **call budget**; when the budget runs out it **emits anyway**.
3. Structured output: the agent emits `(id, sets, reps)`, never prose. The engine renders the plan.
4. Deterministic validator on the way out: id outside the set → rejected. Ten lines.
5. The six invariants over the six adverse situations from TRAINER.md. **Metric: 100%.** Anything below is a bug, not a tuning knob.

## Session 6 — `0.6.0` — Logging by deviation

**Runs**: do the workout, write *«bench fine, only 3 sets of military because the shoulder was pulling, 4 out of 10»*, and the state moves.

1. `workouts` table; the default is adherence, you only report the deviation.
2. Conversational parsing → structured rows, with confirmation when it is ambiguous.
3. Volume counted **on the pattern performed**, never on the planned one; `pattern_state` updated accordingly.
4. Real `pattern_history` and `adherence_history`, plus the **volume deficit** as a single quantity.

> The case TRAINER.md declares central should be tried immediately: **skipping two weeks**. The engine has to assume adherence and flag the uncertainty, not lock up.

## Session 7 — `0.7.0` — Onboarding

**Runs**: from an empty database to a week 1 plan, in a single conversation.

1. Multi-turn graph on LangGraph with checkpointing: answer halfway, come back tomorrow, resume from question 7.
2. The ten-to-twelve questions, in TRAINER.md's order — goal first, aches last.
3. Primary goal forced to one; the others become constraints. Two goals in conflict → the agent says so and makes you choose.
4. Triage on **movements**, never on symptoms: it produces exclusions with a re-test date, not diagnoses. Plus the medical trigger.
5. Test of the non-negotiable constraint: **LangGraph never persists domain, SQLite never persists conversation**.

## Session 8 — `0.8.0` — The long timescale

**Runs**: week 4 is different from week 1, and if you disappear for three weeks the return is gradual.

1. `mesocycle` table: the agent picks the scheme and **states why**.
2. The two v1 schemes — double progression and autoregulated by feel.
3. Return computed from the dates: ≤10 days nothing, 11-21 one ramp-in, 22-45 two, beyond that a full calibration.
4. **The methodology document.** A hand-curated synthesis with inline sources, injected in full at the mesocycle boundary. Human work, not generatable.
5. Append-only `decisions`: every change, one row, with the reason.

> Issue 4 is not in TRAINER.md's «First steps» even though it is inside the v1 scope. It is the one thing the agent deliberates on at the mesocycle boundary: without it, session 8 ships a progression engine, not a trainer.

## Session 9 — `0.9.0` — Conclusions

**Runs**: you tell it you hate pressing, and at week 6 it still remembers.

1. `conclusions` table and the **admission rule**: does it have a source? Ten-line validator, inline, it enters as *provisional*.
2. The agent decides at every turn what should be remembered — and the *why*, not just the sentence.
3. `active_conclusions` as a tool, re-read **before every choice**.
4. Life cycle: states, retirement with a reason, usage counter.
5. The test that separates the two stores: `decisions` is read to reconstruct, `conclusions` to decide. A conclusion inferred without a source has to be **rejected**.

## Session 10 — `0.10.0` — Hypothesis, trial, outcome

**Runs**: *«lunges don't work for me»* → the system does not conclude, it designs a trial.

1. `hypotheses` and `trials` tables; the constrained form: **admissible only if a trial exists that discriminates it**.
2. The trial as a modification to the plan that holds every variable fixed but one, with a duration.
3. State machine on LangGraph: born in one workout, alive for two weeks, closed in another.
4. The outcome **comes back in**: at the next workout the system knows something it did not know before, and knows it was wrong if it was wrong.
5. Routing: a hypothesis with no possible trial is not false, it is outside the program → to the user, or to the doctor.

## Session 11 — `1.0.0` — The supervisor

**Runs**: the full loop, and now it is safe to leave it running for eight weeks.

1. **Golden set**: 40-60 hand-labeled examples, axis A and axis B. False positives on the «no» rows weighted double. An example you cannot label does not go in.
2. A pass on LangGraph **between** workouts, triggered by the dates when the conversation opens. Zero latency on the hot path.
3. Verified isolation: it sees the shape of the trajectory, the goal, the active conclusions — **never the agent's prose**.
4. Consolidation gate: confirms, merges, marks suspect, retires with a reason. A single criterion, coherence.
5. The teeth: observation injected → if the agent does the same thing a second time, it converts into an engine constraint. «It ignored it» is decidable, so the code checks it.

> The single most important row in the whole suite is in issue 1: *the same exercise eight times in a row because it is the stated preference* → **do not flag**. Respecting a preference and drifting are identical in the data. If the supervisor gets this one wrong, the system argues with the user about what the user asked for, and that is unbearable within two weeks.

---

## After 1.0.0

| # | version | what |
|---|---|---|
| 12 | `1.1.0` | **Level 2** — simulated user with hidden truths, the two control cases (user with no truth, noise), k=5 runs, and the regression set harvested from the runs |
| 13 | `1.2.0` | Server + Telegram bot. Purely reactive, no scheduler. The core does not change: it never assumed anything about the client |
| 14 | `2.0.0` | Diagnosed pathologies; form checking via video |

Session 12 is the only one that **ships nothing to the end user**, and that should be said out loud. It ships the right to trust the loop. It comes after 1.0.0 and not before because TRAINER.md is explicit: level 2 can only be measured once the components underneath pass, otherwise you are measuring a loop built on parts you know nothing about — and the parts do not all pass before session 11.

## Declared deviations from TRAINER.md

| | «First steps» says | here | why |
|---|---|---|---|
| supervisor golden set | step 1, before everything | session 11 | this is the most debatable call in this file: *«if the supervisor gets this wrong, everything downstream is poisoned»* is still true. But the supervisor does not run until 11, and sixty rows written at session 1 would be rewritten once the real state exists. The risk is mitigated by the admission gate (session 9) being code, not a model |
| MCP | does not appear | session 4 | costs half a day and pays back over seven sessions |
| methodology document | absent from «First steps» | session 8, issue 4 | it is in the v1 scope but had no slot |
| demonstration videos | absent from «First steps» | a nullable `demo_url` added by session 2's migration, filled by hand from session 5 | in the v1 scope with no slot, and no candidate catalog closes it: free-exercise-db has two static images per exercise and no video, ExerciseDB has video under AGPL with undeclared media terms, and Zenith Fits — the one that had real demonstration videos — is dead. So the field holds a **link**, never hosted media: linking is not distribution. It cannot be model-generated either — asked for a video URL, a model returns a well-formed dead link, which is the *«plausible and wrong»* failure in its most silent form. Curated human work, like the methodology document. The volume is small enough for that to work: one person meets 40-60 distinct exercises in eight weeks, not 800 |

## Risks

**Session 5 is bigger than the others and does not divide well.** The agent without the validator cannot ship. If it overruns, the cut to make is issue 5 (the invariants) into a `0.5.1` of its own — never issue 4.

**Sessions 1-4 have no models in them and 5-11 do.** The rhythm changes abruptly: the first ones are deterministic and fast, from 5 onward every verification becomes a distribution. Do not estimate the second group at the speed of the first.

**Enrichment (session 2) is the only point with a real external cost** and it runs exactly once — but the cost is single-digit dollars over 584 rows, so the risk was never the money. It is that the run is only as good as the vocabulary it applies and nobody would know otherwise. That is what the reference set in session 2's issue 3 is for: the accuracy figure comes before the spend, not after it.
