# Refusal and *"only 30 minutes"* as `interrupt()`, and the plan that is accepted

Status: ready-for-agent

A valid plan stops the graph and waits. The buttons resume the same thread, and the workout is written only when the user accepts it. ADR-0005 is the decision this ticket implements — read it first.

## What to build

- **The graph ends at the interrupt.** After `validate` passes, a node calls `interrupt()` with the plan. The graph does not go on to write anything by itself: whoever resumes the thread does. `trainer eval` invokes the graph and never resumes, so the measurement cannot leave a prescribed workout behind — the guarantee `cli.py`'s plan command holds today by keeping the write in the command, kept structurally instead.
- **Three buttons**: accept, *Non mi va*, *Solo 30 minuti*. The `callback_data` carries the thread the tap resumes, so a tap always finds its run.
- **Accept resumes, and a node after the resume writes the prescribed workout** with `workouts.record_prescribed`.
- **A refusal resumes with what the user said**, which reaches the planner as `Request.because` and `Request.refused` — the fields already exist. A refused plan is never written.
- **A tap on a plan that has been superseded** — the thread has moved on, or a later plan was accepted — is answered with a state: *this plan is from three days ago, I will make a new one*. Not an error, and never a silent no-op.
- **CONTEXT.md, *Workout*.** *Prescribed* becomes *when the user accepts the plan emitted for it*. Correct it here, with the code that makes it true.

## The guarantee about what the user says

Session 6 carried `--refused --because`, and the test that guarded it went with them. It comes back **scoped**, because the unscoped version is not true: the refusal reaches the planner through `PlannerState`, and the checkpointer persists the state by construction.

- What it protects: the user's words never become a **training fact**. A *"non mi va, sempre panca"* said on a bad Tuesday must not settle into a preference, an exclusion or a workout.
- Where it is asserted: over every value of every table in `TRAINER_DB`, after a full refuse-then-accept cycle.
- The checkpointer holds conversation, which is its job under ADR-0004 item 5. `because` stays in the thread: pruning it means code that hunts a string inside checkpoints, which is more fragile than the thing it protects.

## Acceptance criteria

- [ ] A valid plan reaches the chat with three buttons and the graph is waiting, not finished.
- [ ] Tapping accept writes exactly one prescribed workout; a test shows the id and the blocks.
- [ ] Tapping *Non mi va* produces a different plan, and **no** workout row is written for the first one.
- [ ] A test walks every table in `TRAINER_DB` after a refuse-then-accept cycle and finds the refusal sentence in none of them.
- [ ] A test shows `trainer eval` invoking the graph writes no prescribed workout, because it never resumes.
- [ ] A tap on a superseded plan is answered with a state naming what will happen next.
- [ ] CONTEXT.md's *Workout* entry says *prescribed* is acceptance.
- [ ] The full test suite and mypy are green.
