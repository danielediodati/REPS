# 05 — Six adverse situations, six invariants, 100%

**Status:** ready-for-agent

**Blocked by:** 04.

## What to build

The measurement the session is judged on. `trainer eval` runs TRAINER.md's six
hand-written, deliberately nasty situations against the real agent and checks
the six invariants over every run, by code.

**The six situations**, declared as fixtures rather than buried in the runner —
they are hand-written data and they will be added to:

1. 15 minutes, no equipment;
2. half the catalog out on stated preferences;
3. contradictory: *«30 minutes, but I want to train everything»*;
4. the previous report ambiguous or missing — today, state is empty and
   `pattern_history` answers `known: false`, which is the answer;
5. the user refuses the plan: *«I don't feel like it»* — it proposes again,
   without pushing and without giving up (ticket 04's refusal path);
6. a preference in conflict with the declared goal.

**The six invariants**, each decided by code and never by a judge — for a
decidable constraint a validator always beats an agent judge:

1. **it terminates** — a plan within the call budget, and if the budget runs out
   it emitted anyway;
2. **it respects the time** — estimated duration inside the declared budget;
3. **it respects the constraints** — nothing outside the admissible set;
4. **it respects the preferences** — nothing the user refused, and if it proposes
   one again it says so and asks;
5. **it uses only today's equipment**;
6. **it does not degenerate** — every muscle group the workout's split entry
   names is trained by at least one block, and the workout is not filled with
   isolation work because that was the short path.

Invariant 6 is the one that has to be pinned down before it can be checked;
that definition is the ticket's own decision to make and to write down, because
*«does not degenerate»* is the only one of the six that is not already a
sentence about the admissible set or the clock.

**The metric.** Percentage of runs that produce a valid plan within budget. It
has to be **100%**. Anything below is a bug, not a tuning knob. The output is
the situation-by-invariant matrix and that one number, and the command exits
non-zero below it.

**Not under `pytest`.** The suite removes sockets and credentials from every
test on purpose, and this is the one thing in the project that needs both.
`trainer eval` is its own runner and leaves `conftest.py` alone.

Each situation runs more than once — a model is a distribution, and one green
run is not a measurement. The repetition count is declared and small; every run
counts towards the metric, and the bar stays at 100%.

**Read first:** TRAINER.md § *Level 1 — the agent: invariants* (the six
properties, the six situations, and the single metric), § *The agent cannot
route around the constraints*. ROADMAP.md § Risks — if the session overruns,
this ticket is the one that becomes a `0.4.1` of its own.

## Acceptance criteria

- [ ] `trainer eval` runs the six situations against the real agent and prints the situation-by-invariant matrix plus the single percentage.
- [ ] Every invariant is decided by code reading the run record and the plan. No model judges another model's output anywhere in this ticket.
- [ ] Invariant 6's definition is written down where it will be read, not left implicit in the check.
- [ ] The six situations are declared as data, so a seventh is a row and not a code change.
- [ ] Each situation runs a declared number of times; every run counts, and the bar is 100%.
- [ ] The command exits non-zero below 100%, and a failure names the situation, the invariant and the run record that shows it.
- [ ] What a full pass costs — tool calls and tokens — is reported, so the price of re-running it after a prompt change is known.
- [ ] `pytest` still runs with no network and no credentials, and `trainer eval` is not reachable from it.
