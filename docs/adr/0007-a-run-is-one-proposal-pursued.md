# A run is one proposal pursued

Session 8 built a reader over the planner's state, `trainer runs list` and `trainer runs show`, and the reader found that the word it is named after has no definition. In the code `run` means a queue item (`bot._attempt`), one invocation of the graph (`bot.streamed`), and whatever the thread holds now (`record.of`). Those are three different spans, and only one of them is a thing.

The boundary already exists and nobody had named it: `planner.starting()` clears the thread. And `propose()` returns `dict(starting(again))` when a plan is turned down, so **a refusal already ends a run** — it is just not recorded, it is overwritten. The tool calls, the tokens, the seconds per node and the attempts the validator refused, for the run that produced the plan you rejected, are destroyed at the moment you reject it.

Session 10 asks how many plans it takes before one is worth doing. Today the evidence for that question is deleted by the question being asked.

## Decision

1. **A run is one proposal pursued**: from the request being assembled to the user's answer. It survives a restart and can wait days on a pending question.
2. **Turning a plan down ends the run**, which is what the code already does. The run that follows carries which refusal it was born from, so a negotiation can be read as a chain rather than a pile.
3. **A negotiation holds the runs**: one ask, N runs, at most one plan accepted. It is the level the user experiences, and the level ADR-0005's acceptance closes.
4. **What a refusal leaves behind belongs to the negotiation**, and travels into every later run of it: the last refused plan whole, with the words; the earlier ones as their exercise ids, with the words. Never the messages, the tool calls or the validator's attempts — those are how a run got there, not what was rejected — and never a generated summary.
5. **`_not_the_plan_that_was_refused` reads that list** instead of a single plan. It keeps the weakest possible reading, *not the same document*: how different the second plan must be stays the agent's business (ADR-0001).
6. **A closed run is a document and leaves the checkpointer.** It is written into the home with `record.document()`, already declared the one definition of how a record is written. The checkpointer keeps only the run that is alive.
7. **Two axes, two places.** How a run *ended* is written by the graph when it happens. *Where the reader found it* — waiting on an answer, or cut — is derived at read time and applies only to the live run. `record.UNFINISHED` goes: a cut run is the one thing in the checkpointer with no record beside it, which says it without a word.
8. **A negotiation abandoned is derived, never written.** An absence is not an event, and writing it would need a clock running on a machine that is off half the time. The reader says *waiting since the 14th* and the person decides.
9. **The reader depends on nothing that can break.** `trainer runs` reads documents: no provider, no graph, no model. It is the tool you reach for when something is broken.

## Why

- **Points 1 and 2 are already true in the code.** What this buys is not behaviour, it is that the behaviour stops being an accident nobody can name.
- **The measurement session 10 needs is the count of rejected plans.** It cannot be recovered later: a run not written down at the moment it closes is gone.
- **A pile of runs is unreadable, a chain is not.** An evening of three refusals is four rows, and without the link they look like four unrelated things.
- **One step of memory is not memory.** Both the brief and the validator's rule read a single `refused` plan, so after three refusals the planner may re-offer the first one and the invariant passes it.
- **A summary is a model call to save a model call.** It loses the exercise ids, which are the only thing needed to avoid repeating, and it puts a place in the loop where the machine invents something about the user. *"I don't feel like lunges today"* and *"lunges never work for me"* summarise the same and are not the same; the second is session 12's material and it gets there through a trial, not through a paraphrase.
- **The checkpointer is a live-state mechanism, not an archive.** Ticket 8.3 already had to guard against its serializer refusing to read back what it had written. An archive in a format we do not own is one upgrade away from being unreadable, and it is the user's own history.
- **The reader is used when the provider is what is wrong.** Reading the interrupt state through `graph.get_state` would make `trainer runs` need a configured model to tell you why the model could not be reached.

## Amended in session 9

**A run is one thing pursued, and a proposal is only one kind.** The logger
became the second subgraph, and a run of it reads one report into a document:
it pursues nothing and there is nothing to accept or turn down. It ends
`done`, the fifth ending, and everything else here holds unchanged — it is
written the moment it happens, it leaves a document in the archive, and where
the reader found it stays the reader's to derive.

## Consequences

- **`record.Run` goes.** The model, provider and budget carried in the run's config were the identity of a run answered by one model; the model belongs to the node that did the work and goes in the record's node entries.
- **ADR-0006 is corrected here.** It states that the run record already carries the model per node. It does not: `record.of` writes one model and one provider at the top. This is the ticket where that becomes true.
- **`runs.Conversation` is a negotiation**, and `bot._Conversation` stays what it is, the thread's turn-taking. The rename goes with `bot.Coach`, which ADR-0006 already asks for.
- **The checkpointer stops carrying history.** It holds one live run per thread; the home carries the archive, which grows with every negotiation.
- **Session 12 gets its material for free**: a refused plan and the words that refused it, paired, in a document that outlives the run.
- **ROADMAP.md session 9 gains this as its first issue**, and the deletion issue dissolves into the issues that replace each piece: a deletion is the second half of the work that makes it possible, not a unit of value.
- **The engine does not change.** ADR-0001 stands, and the validator's rule stays the weakest reading of *propose something else*.
