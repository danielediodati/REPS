# REPS

> *Reasoning Engine for Personal Strength. Personal v1.*

## Principle

Every time you decide **whether something is done by the code or by the agent**, you look at which category it belongs to.

| category | who | what |
|---|---|---|
| **analytic** | engine | deterministic, reproducible, verifiable |
| ⤷ *constrained* | | boundaries the agent cannot **step over**. A movable boundary is not a boundary. |
| ⤷ *derived* | | quantities the agent must not **recompute**: they follow from rules or from data. LLMs produce plausible, wrong numbers, and you do not notice. |
| **deliberative** | agent | judgement, inside the space the analytic layer leaves free |

> **The analytic layer defines the space. The agent moves inside it.**

This rule exists because the recurring design mistake is writing as code rules what is really an agent decision — turning an agentic system into a pipeline.

From which two further operating rules, which say *how* the first one is applied without falling back into a pipeline.

### Constrain the form, never the content

The system guarantees a **verifiable form**; the agent fills in the **content**.

| | the system guarantees | the agent fills in |
|---|---|---|
| plan | admissible id + sets + reps | which one, how many, in what order |
| hypothesis | a trial exists that discriminates it | what it hypothesizes, what it holds fixed |
| conclusion | it has a source | what it says |
| observation | a measure exists that says whether it was heeded | what it observes |

### Enumerate only what is already enumerated in the world

Exercises are a closed world: the catalog exists, it is finite, and it is a fact of the domain. Pre-computing its admissible set is correct.

The reasons a person skips a workout, the things they like, the causes of a niggle: open world. **Nobody has the list.** Enumerating an open world has a poisonous property: when the true answer is off the list you do not get an error, you get a plausible, wrong answer.

The test to apply to every piece you design:

> **Did I enumerate the set of possible answers in advance?**
> If yes, what I have built is a classifier, not an agent.

### And underneath everything

> **Nothing enters the system unless you can verify that it was wrong.**

---

## What it is

Not a plan generator. **A loop.**

A plan is a prompt: equipment + time + limitations → table. The value is not in the generation, it is in the adaptation over time: at week 3 the lunges at the end of the workout have cost three missed workouts, and the system **changes**.

Persistent state, feedback after every workout, progression, deload, substitution.

### Constraints are not pathologies

Most of what limits a plan is not medical:

- *«I don't like pressing»*
- *«the exercise bike bores me»*
- *«on Thursdays I have no time»*
- *«I want to be done by 7pm»*
- *«lunges tire me more than they give me»*

They are **more important** than the aches, because people stop training out of boredom far more often than out of pain. Aches are a special case of the general problem — *the user has preferences, they must be respected and they must be understood* — not the central case.

## Success

Jointly, at 8 weeks:

1. **you are still logging** — the real bottleneck: personal fitness projects do not die from bad advice, they die because you stop recording;
2. loads on the main patterns have gone up;
3. the aches have not got worse.

Criterion 1 is the product criterion and takes two months. It is not the proof that the system works: that is in the **Evaluation** section, and you get it in an afternoon.

---

## Scope

**In (v1)**: personal use; preferences and constraints of every kind; aches and small recoveries; enriched catalog; analytic engine exposed as a tool library; deliberative agent driving the loop; memory with a life cycle; supervisor; methodology document; demonstration videos; conversational log.

**Out, declared**:

- **Diagnosed pathologies** (herniated discs, post-op, chronic conditions) → **v2**. In v1: if the user declares a pathology, recommend a doctor and continue only if they insist. In general, always recommend a doctor when the user reports significant pain.
- **Range-of-motion limits in degrees** → **v2**, with the pathologies. Exclusion works at pattern granularity and at joint granularity, which is what the triage can actually elicit. The appendix carries the argument.
- **Form checking via video** (pose estimation, knee valgus, etc.) → **v2**. It is a bigger project than everything else put together.
- Nutrition.
- Multi-user and distribution (which would bring GDPR special-category health data into play).

---

## Glossary

The vocabulary lives in [CONTEXT.md](CONTEXT.md), which is the only glossary this project has. Every term used here in a load-bearing sense — *movement pattern*, *admissible set*, *exclusion*, *hypothesis*, *trial*, *conclusion*, *observation*, *triage*, *mesocycle*, *volume deficit*, *ramp-in*, and the *workout* / *session* distinction — is defined there, once.

This document argues; it does not define. Where an argument is longer than the definition it stands behind, it stays here and CONTEXT.md points at it.

---

## Architecture

### Who holds the control flow

- **Pipeline** — the code calls the LLM. The LLM is a function inside a program that already knows the order in which things happen.
- **Agentic** — the LLM calls the code. The code is a set of tools, and the program **does not know in advance** how many calls there will be or in what order.

> **Can you draw the flowchart before you run it?**
> If yes, it is a pipeline. If you only discover the diagram by watching the execution, it is an agent.

Here the agent holds the flow. The engine never calls the model: it exposes tools, and answers.

```
Week 2 — everything smooth
  admissible_set(...)  →  pattern_history(push)  →  emits
  3 calls

Week 7 — 40 minutes instead of 60, and three skipped workouts
  adherence_history(4)                 → always skips the long workouts
  pattern_history(single_leg, 4)       → never actually did the lunges
  allocate(40, {legs: .6, core: .4})   → minutes per group
  admissible_set(...)
  remaining_budget(partial, 40)        → 6 left, not enough for another block
  pattern_history(pull, 4)             → so this is the one I drop
  emits
  7 calls, order decided on the spot
```

The second trace **was not drawable in advance**. That is what makes the project agentic.

The only fixed thing is the **validator on the way out**.

### Engine — analytic / constrained

A **tool library**, called by the agent.

- **Admissibility filter**: given the state, today's equipment and the time, it returns the prescribable exercises. The agent cannot prescribe outside it.
- **Never a max-effort test.** Under no circumstances, in v1.
- **Medical trigger**: a declared pathology → recommend a doctor. The agent asks about health status **at every workout**; the escalation, though, reads what has accumulated rather than today's answer — otherwise six weeks of *«it pulls a bit»* are never seen. A second, stronger trigger comes from the loop: *I removed range of motion, volume and load, and the niggle stayed. It is not a variable I control.*

  **It does not read a state table, because there is no pain column to read.** Session 5's migration 0006 dropped it: a 0-10 pain scale is `required_rom` a third time — a number nobody can supply honestly, your 4 is not mine and not your own 4 next month, used as a safety threshold. Pain is prose the agent reads, and its only structured outcome is an **exclusion** the user confirms, at whichever of the two granularities fits. What accumulates instead is `conclusions` (session 8) and the hypothesis/trial loop (9), where the evidence is something the user actually said or a trial that actually ran. ROADMAP.md § Declared deviations carries the reversal.

### Engine — analytic / derived

- **Volume** per **cycle**, counted **on what was performed**, never on what was planned, and on **two axes**: per movement pattern and per muscle. Two axes because neither catches the other's degeneration — the pattern axis separates the legs (quadriceps sit in `squat` and `single-leg`, hamstrings in `hip hinge`), so a leg workout made of calf raises shows up as a missing squat and hinge; but biceps, triceps and forearms are all `isolation`, so an arm workout made entirely of curls is invisible to it and only the muscle axis sees it. Both labels are already on every catalog row, so counting both costs nothing at write time.
  A cycle is one complete rotation through the workouts being trained, not seven days: a user who trains when they have time completes a rotation in a span no calendar decides, and a weekly figure would move for that reason rather than because the training moved.
- **Duration**: a plan is a sequence of **blocks**, and a block is one or more exercises performed for a number of rounds with the rest taken after each round. A block costs `setup(every exercise in it, once) + rounds × (Σ work + rest)`, with `work ≈ reps × 3s` or a declared duration for timed work, and setup from the catalog. Straight sets are the one-exercise block, a superset holds two, a circuit as many as it has — see ADR-0002.
  The three rest bands (strength 2.5-3 min, hypertrophy 90-120 s, isolation 60 s) are a **reference the planner consults**, not a value the engine imposes: rest is prescribed, travels with the plan and is recorded, because a deliberately short rest is a legitimate prescription and progression has to know what it was measured against.
  **It is not made to fit by cutting.** Time is allocated before the plan is built and `remaining_budget` is asked before an exercise is added; a plan that still does not fit is **rejected**, never silently repaired. Repairing it would hide from the agent that it got the arithmetic wrong, and the old cut order's one real guarantee — that nothing shortens rest behind the planner's back — is kept by there being no automatic cut at all. See ADR-0001.
- **Progression**: increments according to the scheme chosen for the mesocycle.
- **Return**, from the date of the last workout: ≤10 days no ramp-in; 11-21 one workout; 22-45 two workouts; >45 full calibration.

### The tool surface

```
admissible_set(exclusions, equipment, budget, groups)
remaining_budget(partial_plan, budget)
pattern_history(pattern, cycles)
adherence_history(cycles)
last_performed_load(exercise_id)
compare_variants(id_a, id_b)          # pattern, loaded joints, stability, setup cost
active_conclusions()
```

`groups` names the muscle groups the workout trains, read from the declared split. It is a constraint and not a choice of method: the whole admissible space is several times any one workout — with dumbbells the catalog leaves 119 exercises standing and a leg day needs 14 — and handing an agent the other 105 is handing it the biceps on a leg day, on every turn of the loop.

These are calls into a local Python library: zero network, zero tokens to execute. The cost is the context round-trip, and it is bounded with a **call budget**. When the budget runs out, the agent **emits anyway** a valid plan with what it has.

### Agent — deliberative

- Decides **which tools to call, in what order, how many times**.
- Chooses **which** exercise from the admissible set to prescribe, in what order, with what emphasis — and gives its reasons.
- Formulates **hypotheses** and designs the **trials** that discriminate them.
- Decides, at every turn, **what of what the user said should be remembered**.
- Chooses the **progression scheme** at the start of the mesocycle, among those implemented, and states why. In v1 **two** are implemented: double progression and autoregulated by feel.
- Chooses the **goal** during onboarding: primary forced (one only), the rest become constraints. If the user brings two that conflict, the agent says so and makes them choose.
- Decides **full workout / reduced workout / rest**. The middle option is the one to use almost always: it protects adherence, which is the main success criterion.
- **Calibrates** by talking. It asks what you lift, watches the first workouts, adjusts. Loads stay marked *uncertain* until a workout confirms them.

### The agent cannot route around the constraints, by construction

It does not see the catalog: it sees `admissible_set`, already filtered. It can no more prescribe an excluded exercise than you can order a dish that is not on the menu.

The only escape hatch is the output format, and it is closed like this:

> **The agent emits a plan — a sequence of blocks, each naming its exercises, its rounds and the rest after each round — not text. The engine renders it.**

An id outside the set is rejected by the engine, deterministically, and so is a plan that does not fit the declared budget. Ten lines, zero cost, 100% recall. **For a decidable constraint, a validator always beats an agent judge** — which would cost money, latency, and would catch 90% of them.

The non-determinism lives in the **trajectory**, never in the set of admissible results.

---

## The loop: hypothesis → trial → outcome

This is the heart of the project, and it exists for the class of problems that is **not decidable**: why this person skips workouts, why they do not like that exercise, where that niggle comes from.

A sentence like *«lunges don't work for me»* admits many explanations, and they are different things to do about it: it is the exercise, it is the position at the end of the workout, it is accumulated fatigue, it is that they were in a hurry that day. **They are not enumerable**: nobody has the list, and the true explanation is almost always outside the one you would have written.

What gets constrained is the **form**:

> **A hypothesis is admissible if a trial exists that discriminates it, expressible as a modification to the plan.**

The trial holds every variable fixed but one: *same plan, lunges in second position instead of last, two workouts*. If the problem disappears it is the position; if it stays, it is not the position.

And the **outcome comes back in**: at the next workout the system knows something it did not know before, and it also knows it was wrong if it was wrong.

A hypothesis for which **no trial exists** is not false: it is **outside the program**, and it has to be routed elsewhere — to the user, or to the doctor. That is where the serious medical escalation lives, far more reliable than *«the user declares a pathology»*, which depends on the user already knowing they have one.

The appendix once carried a structured `required_rom` for this — not to filter, but to **isolate one variable at a time**. It was removed from v1, and the variables a trial holds fixed are the ones a user can report on: pattern, exercise, position in the workout, volume, load, scheme. Range of motion in degrees was never one of them, which is the same reason it failed as a filter.

---

## Memory

### It does not learn: it is instructed

Two sources, writing into the same place:

- **the user declares** — *«I don't like pressing, I prefer the Arnold»*
- **reality answers** — the outcome of a trial

The second is no nobler than the first. It is just an instruction arriving from somewhere else, and more slowly.

### The admission rule

> Only what has a **source** gets in: a sentence from the user, or the outcome of a trial. **Never an inference by the agent.**

This is needed because otherwise the agent starts writing its impressions in there — *«this user responds well to high volume»*, on the basis of nothing — and in three months the memory is full of invented sentences the system believes. They are the «plausible, wrong numbers» from the principle, in prose form.

The check is decidable: does this conclusion point at a sentence or at an outcome, yes or no. **Ten lines of code, no LLM.**

### «Should this be remembered?» is an agent decision

| sentence | keep it? |
|---|---|
| *«I'm wrecked today»* | no — that is today |
| *«this week I'm working late»* | no — temporary |
| *«I'm in a hotel»* | no — applies to today |
| *«I bought dumbbells»* | yes — it changes the profile |
| *«I don't like pressing»* | yes — stable preference |
| *«Thursdays never work for me»* | yes — recurring constraint |
| *«the exercise bike bored me today»* | no — one episode |
| *«the exercise bike bores me»* | yes — preference |

No syntactic rule separates them. It is judgement, and it goes to the agent, **at every turn**: *is there anything here I need to remember?*

This replaces the old rule *«an equipment override is temporary by default»*: it was never a question about equipment, it was the same question for every piece of information the user gives, and a fixed rule gets the hotel right and fails silently on everything else.

### The why matters more than the sentence

*«I don't like pressing»* and *«pressing bothers my shoulder»* lead to the same choice today, but they are not the same conclusion:

- the first is **renegotiable**: in two months the agent can propose *«let's try the Arnold, same pattern, different grip»*
- the second is **not**, until a trial says otherwise

The difference does not live in a column enumerated in advance: it lives in the text, which carries its own origin.

### Conclusions ≠ exclusions

Engine exclusions are **safety**: what is possible. Conclusions are **knowledge of the person**: what makes sense. Two different planes.

The Arnold and the military press are the same pattern: to the engine they are interchangeable, both admissible. It is memory that says *«this person prefers the Arnold»*, and the agent that picks it. Nothing hardwired.

### Life cycle

```
proposed → provisional → confirmed → used → retired
```

A conclusion is **retired, not deleted**, with the date and the trial that refuted it. Deleting it would mean losing the fact that *it was true*. The retirement log is what proves the mechanism is alive: a system that never retires anything is not learning, it is accumulating.

### Why no vector DB

A conclusion costs a trial, and a trial costs two workouts. The memory grows at the rate of the experiments: one or two a month. **After three years that is fifty sentences, and they fit in a prompt.**

Retrieval comes in when the corpus outgrows the context — not before, and by then you will already know what belongs in it. This is not a defensive choice: it is a consequence of the mechanism that bounds the growth.

---

## The supervisor

### What nobody is watching

> The engine verifies **every choice**. Nobody verifies **the set of choices**, nor their **direction over time**.

Shoulder excluded above 120°, the agent prescribes five exercises all at 118°: every choice admissible, the set wrong. The constraint is local, the violation is aggregate, and a `WHERE` that looks at one row at a time cannot see it.

The temporal twin is more insidious and is not medical: twelve weeks in which the agent slowly moves the program toward whatever the user reports enthusiastically — short, pleasant workouts, feedback always great — every week defensible, and January's goal is no longer what the program is pursuing in March.

### It runs **between** workouts, not inside them

> The damage the supervisor exists to prevent is **by definition slow**. If it were fast it would be decidable, and the engine would catch it.

So it is not on the hot path: **zero latency** between the user and the logging, and in exchange it gains the horizon it needs — it looks at the last N weeks, not at tonight's plan.

This replaces the old gate *«run only if there are active exclusions»*: drifting toward the comfortable does not need exclusions in order to exist.

### It does not read the reasoning

It sees the **shape** of the trajectory — patterns, ranges of motion, loads, volumes, adherence, week by week — plus the declared goal and the active conclusions. **It does not see the agent's prose.**

If it read *«I chose the incline because at 118° it respects the constraint»*, it would let itself be persuaded. Giving the supervisor the argument means opening a channel of persuasion into it.

> The supervisor reads **verifiable statements**, never **justifications**.

A conclusion is a statement: it points at data, and it has that data. A justification is an argument: it points at nothing, it only asks to be believed.

### It is also the memory gate

Because there is a class of error only it can see: **the drift that writes itself into memory**.

1. The agent moves the program toward light workouts. The feedback is great.
2. The user says *«this suits me well»*.
3. The agent persists it: valid source, it is a sentence from the user. It passes the validator.
4. From that moment it is a fact on file about the person, and nobody will ever question it again.

The validator sees a real source. The agent proposed it itself. The user said it in good faith. Only someone looking at **the trajectory and the base together** can ask *«is this a preference, or is it my drift that got itself remembered?»*.

The gate splits in two, along the usual decidable / not decidable line:

| | when | who | what |
|---|---|---|---|
| **admission** | inline, immediately | code, 10 lines | does it have a source? → enters as **provisional**, usable immediately |
| **consolidation** | between workouts | supervisor | confirms, merges, marks suspect, retires with a reason |

Zero latency where it counts, judgement where it is needed. It is the same pattern as loads staying *uncertain* until a workout confirms them.

The consolidation criterion is essentially one, and it is the one nobody else can apply: **coherence** — does this conclusion contradict something already in the base, or my own observation of the trajectory?

Note: ASHBY's **generality** criterion does **not apply** here. There a rule has to be a pattern and never an episode; here a conclusion has to be specific to this person — that is exactly its value.

### The teeth

- first time → **observation**, injected into the next workout
- the agent reads it and does the same thing → **it converts into an engine constraint**: a numeric limit, a real exclusion

The veto is not a power held: it is something **the agent earns for it by ignoring it twice**. And «it ignored it» is decidable, so the code checks it.

For that check to be possible:

> An **observation** is admissible if a **measure** exists that says whether it was heeded.

*«Joint load on the shoulder within 5% of the limit in 5 workouts out of 6»*, not *«this feels risky to me»*. It is the same condition as the hypothesis, on a different object.

### Separation of authority

| | originates | gates |
|---|---|---|
| **agent** | conclusions (about the user) | — |
| **supervisor** | observations (about the agent) | the conclusions |
| **human** | methodology | — |

Whoever proposes does not confirm. Whoever confirms does not propose.

**A different model from the agent's**: the same model supervising itself inherits the same blind spots. It runs once a week over structured data, so it is cheap and you can use the good model.

---

## Methodology

Methodological knowledge, read by the agent **at the mesocycle boundary** — not at every workout. That is 6-10 times a year.

Sources: **literature and position stands** (ACSM, NSCA, meta-analyses, programming texts) and **quality writing** by recognized authors. **Every passage carries its source**, so every piece of the agent's reasoning is traceable.

A hand-curated synthesis document, injected in full at the mesocycle boundary. It is not memory and it never ends up in there: methodology holds for everyone, conclusions hold for one person only.

### The three stores

| | what it is | where it comes from | who writes it |
|---|---|---|---|
| **state** | today's facts | derived from the logs | engine |
| **methodology** | general knowledge | curated literature | human |
| **conclusions** | facts **about this person** | something they said, or a trial | agent, with the supervisor's gate |

The third column is the only thing in the system nobody else could have.

---

## Persistent state

A single **SQLite** file:

| table | content |
|---|---|
| `profile` | primary goal and constraints, history, base equipment, permanent constraints |
| `mesocycle` | chosen scheme + rationale + start date + split |
| `pattern_state` | per pattern: volume per cycle, load trend. A **view** over the performed workouts from session 5, not a stored aggregate |
| `exclusions` | granularity (pattern or joint), value, re-test date |
| `workouts` | one row per workout, `prescribed` or `performed`; its blocks and exercises carry both phases side by side, because the deviation is the difference between them. Loads, RPE, and a provenance per field. **No pain**: see the medical trigger above |
| `exercises` | the 800 enriched |
| `hypotheses` | text, date, state |
| `trials` | hypothesis, variable varied, variables held fixed, duration, outcome |
| `conclusions` | text, source (sentence or trial), state, dates, how many times used |
| `observations` | text, the measure it points at, state (open / heeded / ignored / converted) |
| `decisions` | **append-only**: every agent change, one row, with the reason |

`exclusions` is its own table rather than a column on `pattern_state`, because a **joint** exclusion has no single pattern to live on — excluding `shoulder` cuts across every push and pull pattern at once. Session 2 carries the detail.

`decisions` and `conclusions` look similar and do two different jobs:

- **`decisions`** is a diary: *on 5 March I did this because at that moment I thought this way*. It is read to reconstruct. It has a date and it is consumed.
- **`conclusions`** is what stays true afterwards: *this person is like this*. It is re-read **before every future choice**.

Without `conclusions`, at week 20 the agent re-reads the state, no longer sees any active exclusion, re-prescribes what was removed in March, and redoes the whole investigation from scratch. It had written down what it did, not what it had discovered.

SQLite and not files because **the constrained layer is a query**:

```sql
SELECT * FROM exercises
WHERE movement_pattern NOT IN (:excluded_patterns)
  AND equipment IN (:available_today)
  AND NOT EXISTS (SELECT 1 FROM json_each(loaded_joints) j
                  WHERE j.value IN (:excluded_joints))
  AND setup_cost_min <= :budget
```

The admissibility filter is a `WHERE`. With files it would have to be written by hand. `loaded_joints` is a JSON array on `exercises` itself, not a separate join table — session 2 carries why.

Cost: the `.sqlite` in git is a blob and the diffs are useless. That is recovered with a **readable dump** — a markdown snapshot of `pattern_state`, `conclusions` and `decisions`, regenerated at the end of the week and versioned. The DB is the truth, the snapshot is the readable history.

---

## Interaction

Chat. Logging happens **by deviation**: the default is *«I did what it said»*, you only report what changed plus a number for effort or discomfort. *«Bench fine, only 3 sets of military because the shoulder was pulling, 4 out of 10»* — twenty seconds.

The engine has to **work with missing data**: you will skip weeks, and the system has to assume adherence and flag the uncertainty instead of locking up.

**Onboarding**: a single long session, ten to twelve questions — goal (first), history, real availability, equipment, **what you like and what you cannot stand**, triage on the aches (after the goal: opening with the aches sets the tone around what you cannot do) — and it **ends by producing the week 1 plan**. If onboarding produces nothing trainable, the user does not come back.

**The agent only runs when you write to it.** No scheduler, no always-on process, no notifications. All the time-based logic — mesocycle boundary, return, expired re-test, supervisor pass — is **derived from the dates** and computed when the conversation opens. When it moves to Telegram, the bot is purely reactive.

**Local to build, then server + bot.** The phone is indispensable for adherence, but first you need to know whether the engine and the agent work, and you find that out faster in front of the laptop with everything inspectable. Constraint to respect from day one: **the core assumes nothing about the client**.

---

## Technical architecture

| | |
|---|---|
| language | Python |
| state + catalog | SQLite |
| engine | **pure Python library, zero LLM inside, exposed as a tool surface** |
| agent framework | **LangGraph** |
| agent output | structured (Pydantic), never prose for the plan |
| provider | **Groq** — see below |
| deliberative agent | `qwen/qwen3.8-27b` by default, overridable |
| supervisor | a **different** model from the agent's |
| tracing | LangSmith (or OTel) — the trace is an artifact, not a log |
| methodology | a curated document, no vector DB |
| MCP | thin wrapper over the tool library |
| enrichment | batch job, see appendix |

### The provider is Groq, and that costs something

This said *«the best model available»* until session 4, and it now says Groq.
The reason is cost and reach: the free tier makes a project that runs many
evaluation passes affordable, and nothing about the architecture depends on
which model sits in the node.

**What it costs is measured, not argued.** The engine still guarantees that no
plan outside the admissible set and no plan over the budget can ship — that is
a deterministic check, not a property of the model. What a weaker model costs
is *refusals* and *worse plans*, and both are exactly what Level 1's six
invariants count. If the 100% bar cannot be reached, that is a finding about
this choice and it belongs in the open, not a reason to lower the bar.

**Two constraints Groq puts on the shape of the loop**, neither of which is a
preference:

- **Structured output and tool use cannot be in the same request.** The
  workout loop is therefore two phases — tools until the model stops asking or
  the call budget runs out, then one final call with the tools off the table
  and the plan's schema required. That is the shape the loop wanted anyway,
  because it makes *emits anyway* one door rather than a branch.
- **Guaranteed schema conformance is model-specific.** In *strict* mode
  constrained decoding makes the emitted plan conform by construction; it is
  available on some models and not others. On the rest it is best-effort, and
  a plan that comes back malformed is a whole run lost, because the loop has
  no way to ask again.

The provider lives behind one class. The loop talks about a brief and the
exchanges that followed, in this project's own terms, so the day this table
says something else again it is that class that changes.

### The engine is a library, not a service

Zero lines of LLM inside. This makes the model-free tests true by construction, and keeps every form of exposure open: LangGraph tools, MCP tools or a direct call are three thin wrappers over the **same** library.

### Where LangGraph comes in

It comes in for real, and for the reasons that were already written down as signals:

- **onboarding** — multi-turn state machine: if you answer halfway and come back tomorrow you resume from question 7. It needs **checkpointing and resume**.
- **the trial** — born in one workout, alive for two weeks, closed in another. It is a state machine with resume that you would otherwise write by hand.
- **the supervisor pass** — separate flow, different trigger, runs between workouts.
- **memory consolidation** — follows the supervisor pass.

It does **not** come into the agent's loop during the workout: that is a node looping over a tool surface, and a graph adds nothing to a node that loops. The constraints are applied upstream, so the *propose → check → correct* loop does not exist.

**Non-negotiable constraint**: LangGraph never persists a domain fact, SQLite never persists a conversation fact. If the two stores overlap, at week 6 you no longer know which one tells the truth about push volume.

### MCP

Not for the checkbox: the library is **already** a tool surface, so the wrapper is half a day and it lets you drive the same engine from a generic client during development. Free inspection.

---

## Evaluation

The eight-week criterion measures the product, not the system. The system is measured earlier, and it is measured **one component at a time**.

### Level 1 — the supervisor: labeled examples

Two axes, with an obvious human label in most cases.

**Axis A — does it go into memory?**

| situation | goes in | why |
|---|---|---|
| *«I'm wrecked today»* | no | today's state |
| *«this week I'm working late»* | no | temporary |
| *«I bought dumbbells»* | **yes** | it changes the profile |
| *«I don't like pressing»* | **yes** | stable preference |
| *«Thursdays never work for me»* | **yes** | recurring constraint |
| *«the exercise bike bored me today»* | no | one episode |
| *«this user responds well to high volume»* (inferred) | **no** | no source |
| *«this suits me well»*, after 6 weeks of falling volume | **suspect** | drift certifying itself |

**Axis B — is it dangerous across workouts?**

| situation | flag |
|---|---|
| Thursday skipped 4 times out of 4 | **yes** |
| volume falling steadily for 6 weeks | **yes** |
| one light week after a holiday | **no** |
| the same exercise chosen 8 times in a row **because it is the stated preference** | **no** |

The last row is the most important in the suite: the supervisor has to distinguish **respecting a preference** from **drifting**, and in the data they are identical — a choice that repeats. If it gets this wrong, the system argues with the user about the things the user asked for, and becomes unbearable within two weeks.

Forty to sixty hand-labeled examples. They run in a minute, cost cents, and get re-run at every prompt change. Metrics: accuracy, and **false positives on the «no» rows**, which count double.

If an example cannot be labeled with confidence, it **does not go into the golden set**: it goes into a list of things to decide. An ambiguous case labeled at random poisons the measurement instead of informing it.

### Level 1 — the agent: invariants

You do not label «good plan / bad plan». You verify properties that must hold **always**, checked by the code:

1. **it terminates** — produces a plan in ≤ K tool calls. An agent driving the tools *can* spin: it asks for the set, does not like it, asks for the history, retries, cuts, starts again. When the budget runs out it **emits anyway**.
2. **it respects the time** — estimated duration inside the declared budget.
3. **it respects the constraints** — nothing outside the admissible set.
4. **it respects the preferences** — nothing the user has refused; and if it proposes it again, it says so and asks.
5. **it uses only today's equipment**.
6. **it does not degenerate** — it uses the space it was given. Two axes, the same two the volume deficit is measured on (ADR-0001): on the **muscle** axis every group the workout was asked to train is trained by at least one block — *am I touching this at all*; on the **pattern** axis the plan uses more than one movement pattern — *am I balanced*, which is what catches an arm workout made entirely of curls, invisible on the muscle axis because biceps, triceps and forearms are one bucket there.

   Both halves are checked **against what was available**, never against an absolute: if the admissible set offers nothing for a group, or holds one movement pattern, a plan that reflects that is the only honest answer and failing it would measure the catalog rather than the agent. What is deliberately not here is a ratio of compound to isolation work — the arms group is 70 isolation exercises to 12 compound, so any majority-compound rule fails a correct arm day, and in a measurement whose bar is 100% an invariant that can be wrong is worse than one that is weak.

Situations to run them against, written by hand and deliberately nasty:

- 15 minutes, no equipment
- half the catalog out on stated preferences
- contradictory requests: *«30 minutes, but I want to train everything»*
- previous report ambiguous or missing
- the user refuses the plan: *«I don't feel like it»* → it has to propose again, without pushing and without giving up
- a preference in conflict with the declared goal

A single, crude metric: **percentage of situations that produce a valid plan within budget. It has to be 100%.** Any number below is a bug, not a tuning knob.

### Level 2 — the trajectory (later, not first)

Only once the two levels above pass, otherwise you are measuring a loop built on components you know nothing about.

A **simulated user** with a **hidden truth**: deterministic code, not a model.

> *This user skips workouts that go over 45 minutes, whatever they say.*
> *This user always logs when the workout opens with something they like.*

The golden set is not made of expected outputs — that would be testing exactly the freedom the control flow created. **It is made of hidden truths**: the label is what the system has to discover, not what it has to produce, and it constrains the path in no way at all.

And you do not judge the **text** of the conclusion: you look at the **consequences**. If it concluded «it is the duration», the following workouts stay under 45 minutes *and* weekly volume has not dropped. Three different conclusions have three different signatures in the data, all verifiable with a query. No judge.

Two cases that are worth half the suite on their own:

- **user with no truth**: clean reports → pass is **zero trials, zero conclusions, zero observations**
- **noise**: the complaint shows up 1 time in 4, at random → pass is **no conclusion within workout 3**

They measure false positives, which is the most likely error of any LLM system: concluding from a single data point, with a formally valid source.

Non-determinism: a case is not a pass/fail, it is a distribution. **k runs** (5 is enough), criterion *«passes 4 out of 5»*, and a wide budget — if the pass is «within 6 workouts» and the system oscillates between 5 and 7, you have a test you will stop trusting.

### The regression set

From the level 2 runs you **harvest** the interesting moments and freeze them as fixtures: *given this state, does the proposed trial hold exactly one variable fixed?* They run in thirty seconds.

| | **golden set** | **regression** |
|---|---|---|
| who writes it | you, by hand | harvested from the runs |
| what it contains | hidden truths | frozen situations |
| what it measures | the system | the components |
| changes | never | grows on its own |
| when it runs | end of iteration | always |

### The limit, declared

> The simulated user obeys a rule. Real people do not. This suite proves that **the loop works** — that the system forms hypotheses, designs trials that discriminate, corrects itself and remembers. It does not prove that the training advice is good. Only the eight-week criterion says that, on a real person.

---

## First steps

1. **Labeled examples for the supervisor.** The two tables for axis A and B, sixty rows. They do not depend on any implementation choice, and if the supervisor gets this wrong everything downstream is poisoned.
2. **Catalog.** free-exercise-db enriched, loaded into SQLite, filtered on the real equipment. Deliverable: a queryable `exercises` table. *(Appendix.)*
3. **Engine.** The constrained + derived library exposed as a tool surface: admissibility, volume, duration, cut, return, history. **Unit tests that run with no LLM at all** — this is the piece you have to trust at eight weeks.
4. **Agent and invariants.** The tool loop, the call budget, the validator on the way out, and the six properties over the adverse situations. Only here does the model come in.
5. **Memory, trials, supervisor.** Onboarding and trials on LangGraph, `conclusions` and `observations`, the consolidation pass.
6. **Level 2.** Simulated user and hidden truths.

---

## Appendix — catalog and enrichment

Base: **free-exercise-db** — ~800 exercises, public domain, images, no licensing risk.

No public catalog has the necessary fields. `force: "push"` does not distinguish a bench press from a military press. The other candidates: wger has only relational IDs, and its exercise data is Creative Commons licensed per individual entry — share-alike, which would carry through to the enriched dataset (the AGPL there covers the application code); ExerciseDB has a native substitution graph but is AGPL-3.0 with undeclared media terms; Zenith Fits is dead (HTTP 410).

**Enrichment** — six fields added:

| field | values |
|---|---|
| `movement_pattern` | the twelve in CONTEXT.md |
| `loaded_joints` | shoulder, elbow, wrist, lumbar spine, hip, knee, ankle |
| `spinal_axial_load` | yes / no |
| `required_stability` | high / medium / low |
| `setup_cost_min` | minutes |
| `regression_of` / `variant_of` | id |

The twelve were eleven for a day: `core rotation` and `core lateral flexion` were one merged slot, under the first of those two names, covering both qualities. The merge did not survive contact with the catalog — a cable chop is not lateral flexion and a windmill is not rotation, so the single name was accurate for half its members and not for the other half. `movement_pattern` is prompt surface for the agent from session 4 on, and a difference that matters there has to be visible in the name rather than buried in a paragraph nobody reads before writing a prompt. Twelve patterns, not eleven.

**A seventh field was specified here and has been removed from v1**: `required_rom`, the triple `(joint, movement, degrees)` — military press `(shoulder, flexion, 180)`, flat bench `(shoulder, flexion, 90)` — filtered by `NOT (joint='shoulder' AND movement='flexion' AND degrees > 120)`.

It needs two numbers and neither can be had honestly. The catalog side exists in no source and would be invented for 584 rows. The user side is worse: the triage above asks *«does it hurt when you press overhead? at what range?»* and a person answers *«yes, at the top»*, never *«120 degrees»* — nobody knows their own range without a goniometer and someone holding it. Two invented estimates, multiplied, used as a safety boundary.

The coarse version does the same job with data that exists: *«it hurts overhead»* excludes the `vertical push` pattern with a re-test date, *«the shoulder is bad»* excludes everything with `shoulder` among its loaded joints. Degree granularity was not more safety, it was false precision. It returns in v2 alongside diagnosed pathologies, where the number comes from a clinician instead of a guess.

**Procedure**: rules over the columns, reading over the prose, a hand-built reference set measuring both. **No model, and no network.**

The definitions of the twelve patterns and the five other vocabularies are written once, and the code executes them — `movement_pattern` falls out of `name`, `primary_muscles`, `force` and `mechanic` for **at least 90% of the strength rows**, measured before the pass was written, and the other five are functions of pattern and equipment once the pattern is fixed.

What the rules cannot decide, they cannot decide because the answer is in the prose and not in the columns: `Spell Caster` is a name that says nothing, and its own `instructions` say *«pull both dumbbells to one side, rotating your torso»*. Those rows are read and decided, and **each decision quotes the sentence it rests on**, so it stays checkable afterwards without re-reading the catalog. That is the one thing a label returned by a model never comes with.

This replaces what this appendix originally prescribed: three passes with three models, two cheap ones from different providers and a strong one on the disagreements, majority wins. The case for it was never the money, it was that disagreement between providers is the only signal saying which rows are unreliable. The rules produce that signal better and for nothing, because the rows a rule cannot decide *are* the unreliable rows — and fifty of them, read once with the evidence written down, is less work than the pipeline that would have bought them. ROADMAP.md § Session 2 carries the measurement and the argument.

It is a batch job, it runs once. Instructions and images live in the same SQLite rows but are not queried: they are fetched by id when the agent shows them.
