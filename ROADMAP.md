# Roadmap — sessions

> *A working hypothesis. Companion to [TRAINER.md](TRAINER.md): that one says **what** gets built and why, this one says **in what order** and where the cuts fall.*

## Slicing rule

A **session** ends with a binary that runs and that you can exercise. Not with a finished component.

> **If there is no command to run at the end of the session, the session was sliced wrong.**

Every session unpacks into **no more than five issues**. Each issue closes with `/implement` in a clean context, so it has to stand on its own and point at the sections of TRAINER.md it needs.

An honest note on what *«testable by the end user»* means: until session 4 the end user is **you in front of a CLI**, and what you verify is that the engine answers truthfully. From 4 onward it is someone who wants to train, and what you verify is the plan. The jump is at 4, not before, and it has to be budgeted for.

## The path

| # | version | at the end you can |
|---|---|---|
| 1 | `0.1.0` | browse 800 exercises filtering by equipment |
| 2 | `0.2.0` | ask *«what can I do today»* and get the admissible set back |
| 3 | `0.3.0` | know how long a plan takes — supersets included — and what fits the time you have |
| 4 | `0.4.0` | **get a real plan** from an agent that cannot break the constraints |
| 5 | `0.5.0` | report the workout in twenty seconds and watch the state move |
| 6 | `0.6.0` | start from nothing: ten questions, and a week 1 plan at the end |
| 7 | `0.7.0` | cross the weeks — progression, deload, return from a break |
| 8 | `0.8.0` | be remembered: preferences and constraints survive the session |
| 9 | `0.9.0` | watch the system form a hypothesis about you and design the trial |
| 10 | **`1.0.0`** | **train for eight weeks without the program drifting** |

`1.0.0` is defined by TRAINER.md's criterion: *you are still logging, the loads have gone up, the aches have not got worse*. Everything needed to hold up for two months is inside. Everything needed to **demonstrate** that the loop works comes after, and that is session 11.

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

> Issue 5 is the one addition to what this session originally listed. *«~800 exercises»* counts stretching, cardio, plyometrics and strongman: how many are actually strength work is both the real size of the pool the admissible set is drawn from and the multiplier on the enrichment that follows. The session ended with it: **584 of 876**, the other 292 being stretching (123), plyometrics (61), powerlifting (38), olympic weightlifting (35), strongman (21) and cardio (14). Run `trainer catalog --stats` for the rest.

## Session 2 — `0.2.0` — The admissible catalog

**Runs**: `trainer admissible --equipment "body only" --time 45 --exclude "vertical push"`.

1. Migration for the six enrichment fields, plus `demo_url`, plus per-field provenance — a value a rule derived from the columns and a value someone decided by reading are not worth the same, and a re-import must not touch either of them. — **done** `5a6a64f`
2. The vocabulary definitions written out, and the deterministic pass that applies them. The definitions *are* the rules: one document, read by a person and executed by the code. — **done** `213582c`
3. 60-80 movements decided by hand as the reference set — decided **before** looking at what the rules produced — `enrich check` scoring the database against it, and `catalog --pattern`. — **done** `c206e45`
4. The rows the rules could not decide, read and settled against the exercise's own `instructions`, each decision quoting the line it rests on; a spot-check back over the rows the rules did decide; and the `variant_of` / `regression_of` graph. — **done** `b6a6f28`
5. `profile` and `pattern_state` with the exclusions and their re-test date, `admissible_set(exclusions, equipment, budget)` as a library function, the command that exposes it, and the tests — **with no LLM at all**. — **done** `79fdb07`

> The field worth verifying by hand is `movement_pattern`: get it wrong there and every downstream volume count is wrong without you noticing.

> **Issue 4's residue was 38 rows, not the 60 the draft measured**: the real rule (issue 2) already closes 22 of them, and every one lands on exactly the pattern the draft gave it by hand, so none needed re-deciding, only removing. `trainer enrich check` before and after loading the residue: `movement_pattern` and `loaded_joints` go from 94.2% to **100%** (69 of 69) against the issue 3 reference set; `spinal_axial_load`/`required_stability`/`setup_cost_min` move from 88.6/74.3/87.1% to 91.4/80.0/92.9%, and every disagreement left is a rule gap `docs/enrichment/definitions.md` already documents, not a residue problem. A 21-row spot-check of rows the rule *did* decide, read independently against their own instructions, found zero disagreements. The `variant_of`/`regression_of` graph resolves TRAINER.md's running example by id: `Arnold_Dumbbell_Press` and `Kettlebell_Arnold_Press` both point at `Standing_Military_Press`. 584 of 584 strength rows now carry a `movement_pattern`.

> **Issue 5 gave exclusions their own table rather than a column on `pattern_state`**, which is what TRAINER.md's persistent-state table said before this session — a joint exclusion has no single pattern to live on, so a table keyed by pattern cannot hold it. TRAINER.md is corrected. `admissible_set` is one SQL query: the pattern half a native-column `NOT IN`, the joint half a `NOT EXISTS` over `loaded_joints`'s own `json_each`, both composed in the same `WHERE` rather than filtered afterwards in Python — the shape TRAINER.md's own illustrative query already showed, now matching what actually runs.

> **`required_rom` was dropped, and the seven fields of TRAINER.md's appendix are six.** The filter it existed for — `NOT (joint='shoulder' AND movement='flexion' AND degrees > 120)` — needs two numbers, and neither can be obtained honestly. The catalog side («the military press requires 180° of shoulder flexion») exists in no source and would have to be invented for 584 rows. The user side is worse: TRAINER.md's own triage asks *«does it hurt when you press overhead? at what range?»*, and a real person answers *«yes, at the top»*, not *«120 degrees»*. Nobody knows their own range in degrees without a goniometer and someone holding it. The filter would multiply an invented estimate about the catalog by an invented estimate about the user, and use the product as a **safety boundary**.
>
> What replaces it is the coarse version, which is free and which works with the answers people actually give: *«it hurts when I press overhead»* excludes the `vertical push` pattern, with a re-test date; *«the shoulder is bad in general»* excludes everything carrying `shoulder` in `loaded_joints`. The first falls out of `movement_pattern`, the second out of `loaded_joints`, and both are there anyway. Degree granularity did not add safety, it added false precision. It comes back in v2 with diagnosed pathologies, where a clinician supplies the number instead of the user guessing it.

> **Sessions 2 and 3 were merged, and this is why.** With `required_rom` gone, the old session 2 ended at `trainer catalog --pattern hinge` — a column added to a command that already existed, which the slicing rule at the top of this file does not accept as a session. The old session 3 was four issues. Together they are five, and they end at a question a person would actually ask.

> **The history of this session, because it was re-cut four times and every cut removed something.** It began as: enrichment prompt, three passes with three models, full run, *then* verify fifty rows by hand — which measures quality only after the one external spend has already happened. First cut: a deterministic pass in front, and the hand-built reference set in front of the money.
>
> Second cut, after measuring the deterministic pass before writing it. A throwaway rule set over `name`, `primary_muscles`, `force` and `mechanic` decides `movement_pattern` for **524 of the 584 strength rows**, and the sixty left over are not a class of exercise: they are `Kettlebell Turkish Get-Up`, `Spell Caster`, `Cocoons`, `Battling Ropes`, `Muscle Up`, `Landmine 180's`, plus plain gaps a real pass closes at once. So the majority vote between two cheap providers went. Its whole value was the disagreement signal — *which rows are unreliable* — and the rules produce that signal better and for nothing, because **the rows a rule cannot decide are the unreliable rows**, named, and reproducible on every re-vendor of the dataset. The remaining five fields are functions of pattern and equipment once the pattern is fixed: one judgement written in the definitions, not 584 opinions.
>
> Third cut: `required_rom` out, and with it the only expensive field in the project. Which is worth stating plainly, because two days of argument about models, providers and majority votes turn out to have been an argument about a field that should not exist. What is left to produce is a pattern from twelve values, five fields that follow from it, and a graph of equivalences.
>
> **Fourth cut: no model in this session at all.** The residue needs prose read — `Spell Caster` is a name that says nothing, while its own instructions say *«pull both dumbbells to one side, rotating your torso»*, and that is a rotation. Reading prose and deciding is what the agent closing the ticket does. Routing it through a second model inside the product buys nothing here and costs a network dependency, a provider, keys, fixtures and a validator, for **fifty rows that get read once**.
>
> What it buys *back* is bigger than what it costs, and this is the part a model pipeline cannot do: a decision made by reading can **quote the sentence it rests on**. `Cocoons` is core work because its instructions say *«flex the spine, bringing your arms back over your head»*. That citation goes in the file next to the value, so the decision is checkable by anyone, later, without re-reading the catalog. A model returns a label and no evidence.
>
> So **session 2 contains no LLM and no network**: deterministic rules, decisions in committed files with their evidence, and a reference set measuring both. The first model in the project is the agent of session 4, where it belongs.

> Concretely, from the imported catalog: `Arnold Dumbbell Press` and `Standing Military Press` share `force: push`, `mechanic: compound` and `category: strength`, and differ only on equipment. Nothing in the raw fields says they are the same movement. TRAINER.md's running example — *«the Arnold and the military press are the same pattern, to the engine they are interchangeable»* — has no field to rest on until this session supplies one. The Arnold also exists in two rows, dumbbell and kettlebell, which is why a conclusion points at a movement and never at an id.

## Session 3 — `0.3.0` — Time

**Runs**: declare a cycle and a time cap, and it tells you what fits — costing whatever structure you prescribe, supersets included.

1. Duration model: a plan is a sequence of **blocks**, rest is **prescribed**, setup from the catalog. First shipped costing a flat list at a fixed rest (`9e21b10`) and reworked to blocks in the same session — see ADR-0002. — **done** `ac270f0`
2. `remaining_budget` and `allocate`: the arithmetic of a declared time budget over declared proportions. **No cut** — see ADR-0001. — **done** `00d09c2`
3. The training config file: cycle length, duration cap, split, volume denominator. Declared by the user, read by the engine, written by nobody — see ADR-0003. It also created the muscle group mapping the six names are read from, which let ticket 02's declined finding land: `allocate` now refuses a group that is not one of them. — **done** `888e97b`
4. `pattern_history` and `last_performed_load` against still-empty state — they have to answer «I don't know», not break. — **done** `6529537`
5. MCP wrapper over the library. Half a day, and from here on you inspect the engine from a generic client while developing. — **done** `719a5ac`

> MCP is pulled in earlier than TRAINER.md has it, on purpose: it costs little and the return is all in the later sessions, when the agent starts getting things wrong and you want to see what it sees.

> **This session was re-cut mid-flight, after issue 1 had shipped.** The original plan had the engine derive the split, enforce a coverage rule, fix rest at the top of each band, and repair an over-long plan with a fixed cut order — four rules that between them left the agent filling slots in a plan the engine had already decided. ADR-0001 carries the argument and the line that replaced it: the engine costs and constrains, the agent decides how to train. What died with it: `simulate_cut`, the old issue 3 (*tests that the cut never touches the rest periods* — there is no cut), and the idea that rest is a value the engine owns. What arrived: blocks, so a superset can be costed at all, and the config file, so the requirements the user declares stop looking like state the system measured.

## Session 4 — `0.4.0` — The first plan

**Runs**: `trainer plan` and you get a workout you can do tonight.

The biggest session and the least divisible: the agent without the validator is not shippable, so they stay together.

1. One tool surface, two doors: the tool definitions — preconditions, error translation, shaping — leave `mcp_server.py` for a module both the MCP server and the agent register over, and `compare_variants` joins them. Zero new logic, one definition per tool. — **done** `15d6283`
2. The plan is a document: the structured shape the agent emits — blocks, each with its exercises, rounds, prescribed rest and the reason it is there, never prose — the deterministic validator on the way out (id outside the set → rejected; over the declared budget → rejected, never trimmed, ADR-0001) and the ASCII renderer. **No model**: `trainer plan --from FILE` pushes a hand-written plan through the same door the agent will use. — **done** `ee798ff`
3. Agent node that loops over the tools, with a **call budget**; when the budget runs out it **emits anyway**. Out through issue 2's validator, and no way back in — *propose → check → correct* is the loop TRAINER.md does not have. — **done** `56ec4be`
4. The request the agent is actually asked: which workout of the split, the allocation over its groups, the exclusions, the equipment, the preferences as data — and the refusal, *«I don't feel like it»* → it proposes again, without pushing and without giving up. — **done** `24793ba`
5. The six invariants over the six adverse situations from TRAINER.md. **Metric: 100%.** Anything below is a bug, not a tuning knob. — **done** `77d7845`

> **The order is not TRAINER.md's, on purpose.** Structured output and validator come *before* the agent, as one issue, so that the day the first model emits something there is already a door that rejects it and a renderer that shows it — the same argument that pulled MCP into session 3. And the tool surface is a **prefactor**: `mcp_server.py` already holds the precondition, error and shaping layer the agent needs, and a second copy of it diverges at the first tool that is added to one door and not the other.

> **No LangGraph in this session.** TRAINER.md is explicit that the workout loop *«is a node looping over a tool surface, and a graph adds nothing to a node that loops»*. What arrives here is the provider SDK and a structured output shape; LangGraph arrives in session 6, where checkpointing and resume are the point.

> **`pytest` stays offline.** `conftest.py` removes sockets and credentials from every test on purpose, and that guarantee is worth more than the convenience of one runner: issues 3 and 4 are covered against a stand-in model, and the real one runs only in issue 5, under `trainer eval`.

> **`--workout N` is a flag, not something derived.** Nothing tracks the rotation's position until `workouts` arrives in session 5. Naming it here is what stops session 5 from inventing it.

## Session 5 — `0.5.0` — Logging by deviation

**Runs**: do the workout, write *«bench fine, only 3 sets of military because the shoulder was pulling»*, and the state moves.

1. Migration 0006: `workouts` and its two states, the per-exercise child table, the provenance and RPE columns, `pattern_state.pain` gone. And `trainer plan` persists the workout it prescribes — **in the CLI**, never in the agent or the validator. **No model.** — **done** `a8594a8`
2. The performed workout as a document: the shape the agent will emit, the validator restricted to verifiable facts, provenance per field, the proposed exclusion it can carry, and the renderer. `trainer log --from FILE` pushes a hand-written document through the same door the agent will use. **No model** — the mirror of session 4's issue 2.
3. What the state can now answer: `pattern_state` becomes a view, the muscle axis gets its counterpart, `state._SOURCES` gets its second entry. The cycle index and the position in the rotation become derived, so `--workout N` stops being a flag nobody computes. `pattern_history` and `last_performed_load` stop answering «I don't know»; `adherence_history` and the volume deficit arrive. Plus the two read tools that do not exist yet — catalog search, and the prescribed workouts with no report. **No model.**
4. The logging agent: `trainer log` interactive, six read tools and zero write tools, `surface()` parameterised by which agent is asking, the loop with its call budget, the clarifying question, the proposed exclusion with its confirmation, and the atomic write. **The session's first model.**
5. The measurement: about thirty reports written by hand and blind, eighteen unambiguous and twelve that must make it ask, scored by code with false confidence weighted double.

> **The log is an agent, not a parser, and that is the whole reason this session is not an ETL.** `text → extraction → rows` is drawable before it runs, which is TRAINER.md's own test for a pipeline. A report is not extracted, it is **interpreted against something**: «the bench felt heavy» becomes a fact only after `last_performed_load`, and «I swapped the presses because the shoulder was pulling» needs what was prescribed, what replaces it, and whether the replacement is admissible — three tools, in an order decided on the spot.

> **The validator on the way in cannot be the validator on the way out.** Session 4's refuses a plan outside the admissible set, because that plan has not happened and can still be prevented. Session 5's cannot refuse **a fact**: you had an exclusion on `vertical push` and you pressed anyway, and that is the most valuable row in the database — it is what feeds session 9's hypotheses and the escalation. So a performed workout is **recorded and flagged**, never rejected. The validator keeps only what is verifiable and not a matter of opinion: the id exists in the catalog, the numbers are numbers, the unit is the declared one. Everything else is a flag on the row.

> **No pain scale — and that is the position consistent with this project, not a discount.** *«4 out of 10»* is `required_rom` a third time: a number nobody can supply honestly — your 4 is not mine, and it is not your own 4 next month — used as a safety threshold. What survives needs nothing new: the agent reads the prose and decides whether it is worth an **exclusion**, `classify` decides the granularity against the catalog's own vocabulary rather than by inference, and the user confirms before it is written. No metric in between, no threshold, no accumulation. The numbers say why both granularities have to stay: the `shoulder` joint takes out 251 of 582 exercises across six patterns, `vertical push` takes out 50, and neither is a substitute for the other. TRAINER.md's medical trigger loses the state table it was written to read; it moves to `conclusions` (session 8) and the hypothesis/trial loop (9), and TRAINER.md is corrected to say so.

> **Writes are never tools.** If the model can call the write, the model decides when the database changes: the single door disappears, the validator becomes optional, and an interrupted run leaves half a workout behind. The agent emits and the engine writes — the same symmetry as session 4, where the agent does not call `render` either. It is also why issue 1 puts plan persistence in the CLI: `trainer eval` runs eighteen agent loops against the project database, and a plan that persisted from inside the agent would write eighteen phantom prescribed workouts into the very state the measurement is taken from, where issue 3 would then count them as an unreported rotation.

> **`pattern_state` had to stop being a table.** `pattern_history(pattern, cycles)` takes a window of cycles, and one aggregate row per pattern cannot answer for a window — `state.volume_history`'s own docstring already says session 5's rows are what would give it the dimension it lacks. Worse, `cycle_length` lives in a file the user edits: change it from 4 to 3 and every historical cycle boundary moves, which a view gets right on the next read and a stored aggregate gets silently wrong forever, because nothing in the engine watches that file. `_SOURCES` holds a table name and a key column, so a view drops in without touching `state.py` — which is exactly the «one more entry, not a second contract» this session was promised. `load_trend` is the one field that is not a count over rows, and it gets a written rule rather than a stored judgement, for the same reason session 2's definitions are executable: a rule is checkable, an opinion is not.

> **Nothing is persisted between turns.** The clarifying question happens inside one invocation, in memory, and the workout is written whole or not at all — Ctrl-C leaves no rubble. Session 6's issue 5 is the non-negotiable test that LangGraph never persists domain and SQLite never persists conversation, and a half-finished report parked in a table would make it red before it is written. Multi-turn resume is what session 6 buys, and it is worth buying once.

> The case TRAINER.md declares central should be tried immediately: **skipping two weeks**. Adherence is the default *inside* one report — what you do not mention was done as prescribed. A prescribed workout with no report at all is a different mechanism and needs a different word: it is **unreported**, it contributes no volume, and nothing closes it automatically. Assuming adherence there would fabricate three workouts that never happened and push the volume *up* at the exact moment training stopped. The engine states the fact; whether to ask about it is the agent's call.

> **The reports in the eval set are in Italian**, and they are the first Italian in the repo. They are fixtures, not documentation, and CLAUDE.md's English rule covers documents, code, identifiers and commits: an eval over English sentences would measure a system nobody uses. Field names and comments stay English. They are written **before** seeing what the agent produces, the same discipline as session 2's reference set and for the same reason — a set written afterwards measures how well you rationalise the output.

> **If issue 4 overruns, the cut is not issue 5.** The measurement is what this session ships beyond a write path; without it this is a persistence session with a model attached. The cut is the eval set from thirty rows to twenty, **keeping both halves**. The twelve that must make it ask are the ones measuring whether the system knows that it does not know, and a suite of only the easy rows rewards a model that guesses confidently — which is the failure being tested for.

## Session 6 — `0.6.0` — Onboarding

**Runs**: from an empty database to a week 1 plan, in a single conversation.

1. Multi-turn graph on LangGraph with checkpointing: answer halfway, come back tomorrow, resume from question 7.
2. The ten-to-twelve questions, in TRAINER.md's order — goal first, aches last.
3. Primary goal forced to one; the others become constraints. Two goals in conflict → the agent says so and makes you choose.
4. Triage on **movements**, never on symptoms: it produces exclusions with a re-test date, not diagnoses. Plus the medical trigger.
5. Test of the non-negotiable constraint: **LangGraph never persists domain, SQLite never persists conversation**.

> The triage produces exclusions at **pattern** granularity, and at joint granularity when the user names a joint. That is the whole of it: the degree thresholds went out with `required_rom`, and this is the session that would have had to ask for them.

## Session 7 — `0.7.0` — The long timescale

**Runs**: week 4 is different from week 1, and if you disappear for three weeks the return is gradual.

1. `mesocycle` table: the agent picks the scheme and **states why**.
2. The two v1 schemes — double progression and autoregulated by feel.
3. Return computed from the dates: ≤10 days nothing, 11-21 one ramp-in, 22-45 two, beyond that a full calibration.
4. **The methodology document.** A hand-curated synthesis with inline sources, injected in full at the mesocycle boundary. Human work, not generatable.
5. Append-only `decisions`: every change, one row, with the reason.

> Issue 4 is not in TRAINER.md's «First steps» even though it is inside the v1 scope. It is the one thing the agent deliberates on at the mesocycle boundary: without it, session 7 ships a progression engine, not a trainer.

## Session 8 — `0.8.0` — Conclusions

**Runs**: you tell it you hate pressing, and at week 6 it still remembers.

1. `conclusions` table and the **admission rule**: does it have a source? Ten-line validator, inline, it enters as *provisional*.
2. The agent decides at every turn what should be remembered — and the *why*, not just the sentence.
3. `active_conclusions` as a tool, re-read **before every choice**.
4. Life cycle: states, retirement with a reason, usage counter.
5. The test that separates the two stores: `decisions` is read to reconstruct, `conclusions` to decide. A conclusion inferred without a source has to be **rejected**.

## Session 9 — `0.9.0` — Hypothesis, trial, outcome

**Runs**: *«lunges don't work for me»* → the system does not conclude, it designs a trial.

1. `hypotheses` and `trials` tables; the constrained form: **admissible only if a trial exists that discriminates it**.
2. The trial as a modification to the plan that holds every variable fixed but one, with a duration.
3. State machine on LangGraph: born in one workout, alive for two weeks, closed in another.
4. The outcome **comes back in**: at the next workout the system knows something it did not know before, and knows it was wrong if it was wrong.
5. Routing: a hypothesis with no possible trial is not false, it is outside the program → to the user, or to the doctor.

> TRAINER.md justified `required_rom`'s structure by this session — *«not to filter, but to isolate one variable at a time»*. With the field gone, the variables a trial holds fixed are pattern, exercise, volume, load and scheme, which are the things a user can actually report on. Range of motion was never among the things they could report in degrees.

## Session 10 — `1.0.0` — The supervisor

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
| 11 | `1.1.0` | **Level 2** — simulated user with hidden truths, the two control cases (user with no truth, noise), k=5 runs, and the regression set harvested from the runs |
| 12 | `1.2.0` | Server + Telegram bot. Purely reactive, no scheduler. The core does not change: it never assumed anything about the client |
| 13 | `2.0.0` | Diagnosed pathologies — and with them `required_rom`, which session 2 dropped because in v1 nobody can supply the numbers it needs; form checking via video |

Session 11 is the only one that **ships nothing to the end user**, and that should be said out loud. It ships the right to trust the loop. It comes after 1.0.0 and not before because TRAINER.md is explicit: level 2 can only be measured once the components underneath pass, otherwise you are measuring a loop built on parts you know nothing about — and the parts do not all pass before session 10.

## Declared deviations from TRAINER.md

| | «First steps» says | here | why |
|---|---|---|---|
| supervisor golden set | step 1, before everything | session 10 | this is the most debatable call in this file: *«if the supervisor gets this wrong, everything downstream is poisoned»* is still true. But the supervisor does not run until 10, and sixty rows written at session 1 would be rewritten once the real state exists. The risk is mitigated by the admission gate (session 8) being code, not a model |
| MCP | does not appear | session 3 | costs half a day and pays back over seven sessions |
| methodology document | absent from «First steps» | session 7, issue 4 | it is in the v1 scope but had no slot |
| `required_rom` | one of the seven enrichment fields | **removed from v1**, back in session 13 | the filter needs a degree value on the catalog side that no source has, and a degree value on the user side that no user knows. Two invented numbers multiplied into a safety boundary. Pattern-level and joint-level exclusion does the same job with data that already exists. Session 2 carries the argument |
| pain as a tracked quantity | `pattern_state` carries pain, `workouts` carries pain, and the medical trigger reads the state table | **no scale and no accumulation** — pain is prose the agent reads, and its only structured outcome is an exclusion the user confirms | a 0-10 scale is the `required_rom` failure applied to the most delicate thing the system touches: nobody's 4 is anybody else's, or their own next month, and an escalation threshold built on it is false precision used as a safety boundary. The trigger moves to `conclusions` (session 8) and the hypothesis/trial loop (9), where the evidence is something the user said or a trial outcome rather than a number they guessed |
| demonstration videos | absent from «First steps» | a nullable `demo_url` added by session 2's migration, filled by hand from session 4 | in the v1 scope with no slot, and no candidate catalog closes it: free-exercise-db has two static images per exercise and no video, ExerciseDB has video under AGPL with undeclared media terms, and Zenith Fits — the one that had real demonstration videos — is dead. So the field holds a **link**, never hosted media: linking is not distribution. It cannot be model-generated either — asked for a video URL, a model returns a well-formed dead link, which is the *«plausible and wrong»* failure in its most silent form. Curated human work, like the methodology document. The volume is small enough for that to work: one person meets 40-60 distinct exercises in eight weeks, not 800 |

## Risks

**Extending enrichment to the other categories has no slot, on purpose.** Session 1's issue 5 counted them: 292 rows outside `strength` — stretching (123), plyometrics (61), powerlifting (38), olympic weightlifting (35), strongman (21), cardio (14). Running session 2's existing rules over them decides 55%, but the number hides a split: on powerlifting (92%), olympic (60%) and strongman (38%) the rules are right, because those rows are strength work under another label; on stretching and plyometrics they return values that are **plausible and wrong** — a foam-roll `Adductor` stretch comes back `isolation`, a `Backward Medicine Ball Throw` comes back `horizontal pull` — because the keyword rules were written for loaded work and find the muscle name anyway. Cardio correctly decides almost nothing: a stationary bike has no movement pattern.

So the 94 powerlifting/olympic/strongman rows are cheap and safe, and the rest needs rules of its own. Neither blocks anything: the 584 strength rows already carry everything the planner needs, and this widens the pool rather than unlocking it. It is written here rather than scheduled because the slicing rule caps a session at five issues and no session has a spare one — the day it gets a slot, it is one issue, not two.

**Session 4 is bigger than the others and does not divide well.** The agent without the validator cannot ship. If it overruns, the cut to make is issue 5 (the invariants) into a `0.4.1` of its own — never issue 2, which is the validator and the only thing standing between the agent and a plan nobody checked.

**Session 2 is five issues carrying two jobs**, the catalog and the admissible set, and it is the widest session before 4. If it overruns, the cut is issue 4's `variant_of` / `regression_of` graph, which slides into session 4 where substitution first needs it — never the reference set in issue 3, which is the only measurement in the session.

**Sessions 1-3 contain no model and no network; from session 4 on, both.** The rhythm changes abruptly at 4: the first three are deterministic and fast, and every verification in them is an equality. From 4 onward every verification becomes a distribution. Do not estimate the second group at the speed of the first. The corollary for session 2 is that its cost is *reading* — fifty rows of instructions, decided and cited — and reading does not parallelise the way a batch job does.

**Enrichment has no external cost worth naming any more, and the risk it carried has changed hands.** The vocabulary *is* the run, since the rules are the definitions executed: a wrong boundary in issue 2's document is a wrong column across hundreds of rows, silently. Two things stand against that, and both are in the session — the reference set of issue 3, which is why it has to be decided blind to the rules' output and why `movement_pattern` is scored on its own, and issue 4's spot-check back over what the rules claimed, read against the instructions rather than against the columns the rules already used.
