# 04 — What the agent is actually asked, and the plan you don't want

**Status:** ready-for-agent

**Blocked by:** 03.

## What to build

Ticket 03 proves the plumbing: a model loops over tools and emits something
valid. This one makes what it emits worth doing, by assembling the request
properly and by handling the case where you say no.

**Today's request, from what the project already knows.** One typed object,
built before the model is called:

- **which workout of the rotation** — `--workout N`, read against
  `training.toml`'s `split`, which names the muscle groups that workout trains.
  It is a flag rather than something derived, because nothing tracks the
  rotation's position yet: `workouts` is session 5. Naming it here is what stops
  session 5 from having to invent it.
- **the allocation** — `allocate` over those groups, so minutes are divided
  before the plan is built rather than cut after (ADR-0001).
- **the time** — defaults to the declared `duration_cap_min`, never above it.
- **the exclusions** — the persisted ones whose re-test date has not arrived,
  applied without being asked for, plus whatever `--exclude` adds for this run
  only.
- **the equipment** — today's, in the catalog's own vocabulary.
- **the preferences** — what the user says they will not do. There is nowhere
  to persist them yet (`conclusions` is session 8), so they are stated per run.
  Invariant 4 of ticket 05 measures against them, so they have to exist as data
  and not as a sentence inside a prompt.

**The rest bands are offered, never imposed.** `duration.reference_rest` is a
reference the planner may consult; rest is prescribed by the agent and travels
with the plan (ADR-0001). The prompt says so.

**The agent gives its reasons.** Each block carries why it is there — ticket 02's
schema already has the field. The renderer prints them.

**The refusal.** `trainer plan --refused FILE --because "..."` takes back a plan
with *«I don't feel like it»* and proposes again: a different plan, still valid,
still inside the budget, without pushing and without giving up. TRAINER.md lists
this among the six adverse situations, so ticket 05 cannot measure it unless it
exists. Two turns, not a conversation: the refused plan and the reason are inputs
to a fresh run, and nothing about the exchange is persisted — SQLite never
persists a conversation fact.

**Read first:** TRAINER.md § *Agent — deliberative*, § *Interaction*, § *Level 1
— the agent: invariants* (the adverse situations). ADR-0001 (allocate before,
never cut after; rest is prescribed, not imposed), ADR-0003 (what the user
declares and where it lives). `src/trainer/data/training.example.toml`.

## Acceptance criteria

- [ ] `trainer plan --workout 2` reads `training.toml`, trains the groups that workout of the split names, and divides the time among them with `allocate`.
- [ ] No `training.toml`, or a `--workout` outside the cycle, is reported as a state with the way out — the same shape `trainer config` already uses — never as a complaint about a missing field.
- [ ] `--time` defaults to the declared `duration_cap_min` and is refused above it.
- [ ] Persisted exclusions still inside their re-test date are applied without being asked for; `--exclude` adds to them for one run and persists nothing.
- [ ] A stated preference reaches the agent as data, and a plan that contains something the user refused is visible as such — not merely absent from the prompt.
- [ ] Every block carries the agent's reason, and the rendered output prints it.
- [ ] `trainer plan --refused FILE --because "..."` produces a plan that is valid, inside the budget, and not the refused one.
- [ ] The refusal path writes nothing to SQLite: TRAINER.md's non-negotiable constraint holds, and a test says so.
- [ ] All of it is covered in `pytest` against ticket 03's stand-in model; the real model is still only in ticket 05.
