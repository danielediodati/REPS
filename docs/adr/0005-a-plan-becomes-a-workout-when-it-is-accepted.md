# A plan becomes a workout when it is accepted

Until session 7 a plan and a prescribed workout were the same event: `trainer plan` printed the plan and wrote it, in that order and on purpose. There was no way to turn one down. Telegram gives the user a button, and the two events come apart.

## Decision

1. **A workout is `prescribed` when the user accepts the plan emitted for it**, not when it is emitted. CONTEXT.md's *Workout* entry says so.
2. **A proposed plan lives in the checkpointer** and nowhere else. A refused plan never reaches SQLite, and there is no `refused` state in the database.
3. **The graph ends at the interrupt.** After the validator passes, a node calls `interrupt()` with the plan and the run stops there.
4. **Whoever resumes the thread causes the write.** A node after the resume calls `workouts.record_prescribed`. The bot resumes when a button is tapped; `trainer plan` resumes immediately, having no buttons.

## Why

- **A refused plan left in the database corrupts the signal the project is built on.** `state.volume_deficit` leaves an `outstanding` prescription out of both sides, but the moment a later workout overtakes it, it counts as planned-and-never-performed. Refuse a plan, accept the next one, train it exactly: the deficit reports a shortfall for a workout that never existed. The more the button is used, the more the system believes training is being abandoned — which is the exact reading ADR-0001 relies on to see a plan degenerating.
- **And it makes the agent ask about workouts that never happened.** `state.unreported` names the same row from the same moment.
- **`record_prescribed` writes one workout per call, deliberately** — two plans in a day are two prescriptions, not a correction — so there is no upsert to fall back on.
- **A third state in the database was rejected** for the reason `unreported` is not one: storing it means something has to go and set it, and nothing does. A plan that was turned down is not a fact about training; it is a thing that did not happen.
- **The write had to leave the CLI command.** It lives there today because `trainer eval` runs eighteen graph invocations against the project database, and a write inside the agent would leave eighteen phantom prescribed workouts in the very state the measurement is taken from. Ending the graph at the interrupt keeps that guarantee **structurally**: the eval invokes and never resumes, so it cannot write, and nobody has to remember the rule.
- **Two alternatives were weighed.** A node reached automatically after validation puts the write back inside what the eval executes — the eighteen phantoms again. Writing in the bot's button handler keeps the eval clean but puts a database write in the interface and leaves the CLI with a second copy of it.

## Consequences

- **CONTEXT.md** changes: *prescribed* is acceptance.
- **`trainer plan` needs a checkpointer**, with no bot involved, because it now invokes and resumes. The same machine runs behind both doors.
- **The write moves out of the plan command** into a graph node after the resume.
- **The refusal sentence is not covered by this.** It reaches the planner through the graph state, which the checkpointer persists; what is guaranteed is that it never becomes a training fact. ADR-0004 item 5 already assigns conversation to the checkpointer.
