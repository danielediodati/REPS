# A run is a thing you can read back

Status: ready-for-agent

`trainer runs` was built in session 8 over a state machine that deletes its own history at the moments worth reading. Tap *Non mi va* and `planner.propose()` returns `dict(starting(again))`: the tool calls, the tokens, the seconds per node and the validator's attempts, for the run that produced the plan you just rejected, are gone. Session 10 asks how many plans it takes before one is worth doing, and today the question deletes its own evidence.

ADR-0007 is this ticket written down. Read it first; what follows is only what changes.

## What to build

- **A run ends, and the ending is written**: accepted, turned down, refused by the validator to the end, or fallen over. Written by the graph at the moment it happens, not derived afterwards from two counters. A run that raised is ended by whoever catches it -- the node cannot write after it has raised.
- **The closed run is a document in the home**, written with `record.document()`, which stays the one definition of how a record is written. The checkpointer keeps only the live run, so `starting()` may go on clearing the thread: what it clears has already been written down.
- **A negotiation holds the runs.** One ask, N runs, at most one plan accepted. Each run says which negotiation it belongs to and, if it was born from a refusal, which run it follows.
- **What a refusal leaves behind belongs to the negotiation and travels into every later run of it**: the last refused plan whole with the words, the earlier ones as their exercise ids with the words. Never the messages, the tool calls or the validator's attempts. `planner.brief()` renders the list; a `Request` carrying one `refused` plan is what it replaces.
- **`plan._not_the_plan_that_was_refused` reads the list.** It keeps the weakest reading -- not the same document -- and stops being blind past one step.
- **`trainer runs` reads documents.** No graph, no provider, no model: it is the tool you reach for when the provider is what is wrong. `runs list` names negotiations and what they came to; `runs show` prints a negotiation's runs, or one run, `--json` for the document. The live run is the one thing read off the checkpointer, and a run in it with no document beside it is one that was cut -- which is the session 8 demo, now saying so without a word for it.
- **`record.UNFINISHED` goes**, with the guessing it stood for. A negotiation nobody answered is derived when read -- *waiting since the 14th* -- and never written: an absence is not an event.
- **`record.Run` goes.** Model, provider and budget were the identity of a run answered by one model; the model belongs to the node that did the work and moves into the record's node entries. `runs list` stops naming a model.

`said` stays untouched by `starting()` (ADR-0006).

## Acceptance criteria

- [ ] Turning down two plans and accepting the third leaves three run documents: the two refused with their words and their plans, the accepted one with the workout it wrote.
- [ ] `trainer runs list` shows that evening as one negotiation with three runs, not as three unrelated rows.
- [ ] A run cut mid-flight (the process killed between checkpoints) is reported as cut, and is distinguished from one waiting on an answer, with no provider configured and Ollama unreachable.
- [ ] `trainer runs` runs to completion with `LLM_BACKEND` naming a provider that cannot be built.
- [ ] A test drives four refusals and asserts the first plan, re-offered, is refused by `_not_the_plan_that_was_refused`.
- [ ] A test asserts the brief carries every refusal of the negotiation, the last one whole and the earlier ones as ids.
- [ ] The record's nodes carry the model that answered them; nothing at the top of the document names one.
- [ ] `trainer plan --record` and both eval suites write the same document as before, through the same function.
- [ ] The checkpoints already on disk still read back.
- [ ] The full test suite and mypy are green.
