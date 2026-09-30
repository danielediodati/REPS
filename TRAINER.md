# REPS

> *Reasoning Engine for Personal Strength.* A strength coach built as an agent. A deterministic engine defines what is possible; a LangGraph agent decides what is good, over weeks.

**Two goals:**
- **The project** shows agentic engineering on a real problem: a graph that corrects itself, asks, waits, remembers and is watched.
- **The product** keeps one person training. At 8 weeks: (1) they are still logging, (2) loads on the main patterns have gone up, (3) aches have not got worse.

Vocabulary: [CONTEXT.md](CONTEXT.md). Architecture decision: [ADR-0004](docs/adr/0004-an-agent-graph-over-the-engine-reached-through-telegram.md).

## Principles

| layer | who | what |
|---|---|---|
| **analytic** | engine | deterministic and verifiable: boundaries the agent cannot cross, quantities it must not recompute |
| **deliberative** | agent | judgement inside the space the engine leaves |

**Constrain the form, never the content.**

| | the system guarantees | the agent fills in |
|---|---|---|
| plan | admissible ids, a valid shape, within five minutes of the budget | which exercises, how many, in what order, and why |
| hypothesis | a trial exists that discriminates it | what it hypothesizes |
| conclusion | it has a source | what it says |
| observation | a measure says whether it was heeded | what it observes |

**Enumerate only what the world already enumerates.** The catalog is a closed set, so pre-filtering it is correct. Why someone skips workouts is an open question. A list of reasons turns the agent into a classifier, and when the true reason is off the list it is plausibly wrong.

**Pipeline or agent?** If you can draw the flowchart before running it, it is a pipeline. The code provides tools; the graph decides how many calls to make, and in what order.

**Nothing enters the system unless you can verify that it was wrong.**

## Scope

**In (v1)**:
- personal use;
- constraints of every kind, most of them not medical (*«I don't like pressing»*, *«Thursdays never work»*);
- aches and small recoveries;
- the enriched catalog, and the engine as tools;
- the agent graph, memory with a life cycle, and the supervisor;
- Telegram.

**Out**:
- diagnosed pathologies and range of motion in degrees: v2; in v1 the agent recommends a doctor;
- form checking from video;
- nutrition;
- multi-user.

## Architecture

```
Telegram  <->  bot on the PC (long polling)
                 |
               router --> planner <-> engine tools
                 |           |
                 |        validate --refused--> planner      (bounded)
                 |           | ok
                 |        [interrupt] accept / "non mi va" / "only 30 min" --> save
                 |
                 +------> logger <-> engine tools
                 |           [interrupt] question / confirm exclusion --> save
                 |
                 +------> onboarding   [interrupt] per question

memory writer --> LangGraph store (only with a source)
supervisor: a separate graph, a different model, run between workouts
models: Ollama locally, or Groq (LLM_BACKEND)
```

### Engine: the analytic layer

A pure Python library with no LLM in it, exposed as tools (`src/trainer/tools.py`) and also served over MCP.

- **Admissible set.** The exercises allowed by equipment, time, muscle groups and exclusions, computed as one SQL query.
- **Duration.** A plan is a sequence of blocks, and a block costs `setup + rounds × (Σ work + rest)`. The agent prescribes the rest; the bands are a reference (strength 2.5-3 min, hypertrophy 90-120 s, isolation 60 s). A plan is built to the budget, within five minutes either side; outside it is refused, never cut or padded (ADR-0001, ADR-0002).
- **Volume.** Rounds performed per cycle, on two axes: movement pattern and muscle.
- **Progression and return** (after 1.0). Increments follow the mesocycle's scheme. The ramp-in depends on days since the last workout: up to 10 none, 11-21 one workout, 22-45 two, over 45 a full calibration.
- **Never a max-effort test.**
- **Writes are never tools.** The agent emits a document, and the engine writes it whole or not at all.

### Agent: the deliberative layer

- Chooses the tools, the exercises, their order and the rest, and says why.
- Plans a **mesocycle**, not a workout: every workout of the cycle with fixed exercises, and how many cycles it holds, with a reason. Between workouts it plans nothing; today's is read off the mesocycle, adapted only for today's constraint (ADR-0008).
- Emits a **plan**, never prose, against a schema whose `exercise_id` can only be an admissible id. The validator checks what a schema cannot, and sends refusals back.
- Asks instead of guessing (`interrupt()`). Proposes an exclusion only for the user to confirm.
- Decides between a full workout, a reduced one and rest. The reduced workout protects adherence.
- Decides, at every turn, what is worth remembering.
- Formulates hypotheses and designs the trials that test them.
- Picks one primary goal during onboarding (the others become constraints), and the progression scheme at a mesocycle boundary.

**Pain.** No pain scale, no health check-in, no referral to a doctor. Pain is prose, and its only structured outcome is an exclusion the user confirms.

### Stores

| store | holds | written by |
|---|---|---|
| engine SQLite | catalog; workouts (prescribed or performed, provenance per field); exclusions; volume views | engine |
| engine SQLite, declarations | cycle length, duration cap, split, volume denominator, equipment, goal; one dated version per change | onboarding (ADR-0013) |
| LangGraph checkpointer | the live run of each thread, paused threads | graph |
| run archive (`runs/` in the home) | every closed run, one document per run under its negotiation | graph (ADR-0007) |
| LangGraph store | preferences, conclusions, hypotheses, observations, each with a source | agent, gated by the supervisor |
| [methodology](src/trainer/data/methodology.md) | ranges per goal and principles, from the literature with sources; the planner reads it | human |

No store writes another's facts.

## The loop: hypothesis → trial → outcome

This loop handles what is not decidable: why someone skips workouts, why *«lunges don't work for me»*. The explanations cannot be enumerated, so the **form** is constrained instead.

1. **A hypothesis is admissible only if a trial exists that discriminates it.** The trial is a plan modification that holds every variable fixed but one: *same plan, lunges second instead of last, for two workouts*.
2. **The outcome comes back in.** The system now knows something new, or knows it was wrong.
3. **A hypothesis with no possible trial is outside the program.** It goes to the user, or to a doctor.

## Memory

- **Admission.** Only what has a source gets in: a sentence from the user, or a trial outcome. Never the agent's inference (*«responds well to high volume»*). The check is code: a conclusion carries the user's sentence verbatim, and is refused unless that sentence appears in one of the user's messages.
- **What to remember is judged every turn**, by the node already reading it (onboarding, entrance, logger) through a `remember` tool. No node of its own, so no extra model call.

  | sentence | keep? |
  |---|---|
  | *«I'm wrecked today»* | no |
  | *«I bought dumbbells»* | yes |
  | *«the bike bored me today»* | no |
  | *«the bike bores me»* | yes |

  No syntactic rule separates these.
- **The why matters.** *«I don't like pressing»* is renegotiable. *«Pressing hurts my shoulder»* is not, until a trial says otherwise.
- **Conclusions are not exclusions.** An exclusion is safety: what is possible. A conclusion is knowledge of the person: what makes sense.
- **Life cycle**: proposed → provisional → confirmed → used → retired, with a date and a reason. Retired, never deleted.
- **No vector DB.** Conclusions grow at the rate of trials, so after three years they still fit in a prompt.

## The supervisor

The engine checks every choice. Nobody checks the **set** of choices, or its **direction over time**: twelve weeks drifting toward short, pleasant workouts, each week defensible on its own.

- **When it runs.** Between workouts, on a different model, adding no latency for the user.
- **What it reads.** The shape of the trajectory, the goal and the conclusions. **Never the agent's prose**, which would open a channel of persuasion.
- **Memory gate.**
  - Admission is inline code: a conclusion with a source enters as provisional.
  - Consolidation belongs to the supervisor: confirm, merge, mark suspect or retire, on one criterion, coherence.
  - This is what catches drift that has certified itself, e.g. *«this suits me»* after six weeks of falling volume.
- **Teeth.** An observation must point at a measure. The first time, it is injected into the next workout. Ignored a second time, it becomes an engine constraint. Whether it was ignored is decidable, so code checks it.
- **Separation.**
  - The agent originates conclusions.
  - The supervisor originates observations and gates conclusions.
  - A human writes the methodology.

## Evaluation

Each component is measured on its own, against fixtures named in the environment (`TRAINER_DB`).

**Agent invariants.** Checked by code on every run, on each workout of the mesocycle it emits, with a target of 100%. The agent:
1. terminates within the call budget, emitting a plan anyway;
2. fits the declared time;
3. stays inside the admissible set;
4. leaves out what the user refused, or says so;
5. uses only today's equipment;
6. does not degenerate: every requested group is trained and more than one pattern is used, both judged against what was available.

The situations are deliberately nasty:
- 15 minutes with no equipment;
- half the catalog refused;
- *«30 minutes, but everything»*;
- a missing report;
- *«I don't feel like it»*;
- a preference against the goal.

**Logger.** 30 hand-written reports:
- **18** that the sentence determines, scored on the document and its volume;
- **12** that must make it ask; writing a value instead of asking counts double.

**Supervisor.** 40-60 labeled examples on two axes: *does it go into memory?* and *is it dangerous across workouts?* The key row: the same exercise eight times because it is the stated preference must **not** be flagged.

**Level 2** (after 1.0). A simulated user with a hidden truth written in code, e.g. *skips workouts over 45 minutes*.
- The system is judged on whether it discovers that truth, by the consequences in the data.
- Two controls: a user with no truth should produce no conclusions, and random noise should produce no conclusion before workout 3.
- Each case runs 5 times and passes at 4 of 5.

**The limit.** This proves the loop works, not that the advice is good. Only the 8-week criterion tests that.

## Interaction

The interface is Telegram, and it is asynchronous.

- **Logging is by deviation.** *«panca bene, solo 3 serie di military perché la spalla tirava»*: whatever is not mentioned was done as prescribed.
- **A prescribed workout with no report is unreported**, never assumed done.
- **The next plan is prepared** as soon as a report arrives.
- **Onboarding** is one conversation the agent leads in its own words, with no script. Code holds only that it cannot end while a declaration is missing. It ends in a first mesocycle.

## Appendix: catalog and enrichment

**Base.** free-exercise-db: 876 exercises, public domain, 584 of them strength. No public catalog has the fields planning needs (`force: push` does not tell a bench press from a military press).

**Added fields**, six in all:
- `movement_pattern`, twelve values, defined in CONTEXT.md;
- `loaded_joints`;
- `spinal_axial_load`;
- `required_stability`;
- `setup_cost_min`;
- the `variant_of` / `regression_of` graph.

**How they were decided.**
- Rules over the native columns decide most rows.
- The 38 rows the rules cannot decide were read and settled against each exercise's own instructions, each decision quoting the sentence it rests on.
- A hand-built reference set measures both.
- No model and no network were used.

**`required_rom`** (degrees per joint) was dropped, because neither the catalog nor a user can supply that number honestly. Exclusion works at pattern and joint granularity instead.
