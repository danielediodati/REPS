# The entrance talks

Status: ready-for-agent

Blocked by: 01, 02 -- it routes to two subgraphs, and both must exist and write runs the same way.

Every message the bot gets reaches `planning()`. You can write anything and you get today's workout, because what you wrote is stored as `said` under a comment saying nothing reads it. ADR-0006 is the decision; this is the ticket.

## What to build

- **An entrance node that holds the conversation**, on a small fast model of its own, reaching the planner and the logger as tools, with the engine's read tools on the same surface -- so *"quanto petto ho fatto questo ciclo"* is answered without entering a subgraph.
- **The per-node model.** The entrance names its own model and provider; the planner and the logger keep the one `LLM_BACKEND` names. The record's node entries carry the model that answered each node (01 moved them there), so a record never reports the entrance's model for work the planner did.
  - 01 stopped halfway: `planner.build` takes one `models.Chat` and its `timed` wrapper stamps that name on every node it wraps. One model per graph is enough while there is one graph; the entrance is where the wrapper has to be told which model answered the node it is timing.
- **Five of the seven fixed lines go**: `STARTED`, `QUEUED`, `WRITTEN`, `SUPERSEDED` and `NO_PLAN` become things the entrance says. `BLOCKED` and `FAILED` stay constants -- they are the two cases where the model is absent or not to be trusted, and nothing raised leaves the machine.
- **The entrance answers before the work is finished.** A plan takes minutes; the turn is answered at once and the run proceeds behind it with its progress in the draft.
- **What the entrance may not decide** (ADR-0006 item 4): not which workout is due, not whether a plan fits, and no training fact it did not get from a tool.
- **`bot.Coach` is renamed.** It is the thread's turn-taking -- one run at a time, and the queue behind it -- and the word is needed for the node that coaches. `bot._Conversation` is that same turn-taking and keeps it; `runs.Conversation` was renamed to the negotiation in 01.
- **`said` is what the entrance reads**, and `planner.starting()` goes on leaving it alone.
- **The logger's two interrupts already carry the shape of their answer.** 02 made the payload say which kind it is: `{"kind": "clarify", "ask": ...}` is prose the user writes, and `{"kind": "exclusion", "ask": ..., "granularity": ..., "value": ..., "retest_date": ...}` is yes or no. The terminal reads that in `cli._answered`; the chat is where the closed one becomes two buttons. Resuming takes a string for the first and a bool for the second.
- **02 left the run's beginning and ending in two copies after all.** `record.identity` and `record.closing` are shared, but each graph's `starting` and its `timed` wrapper are its own, and `turn` mints an identity for a run Studio started in both of them. Three small copies, and the entrance makes a fourth unless they come together first.

## Acceptance criteria

- [ ] A message that is neither a report nor a plan request is answered by the entrance, in Italian, without entering a subgraph.
- [ ] A report reaches the logger and a request for today's workout reaches the planner, both on the model `LLM_BACKEND` names while the entrance is on its own.
- [ ] The run document of a planning run names the planner's model on the planner's nodes, and the entrance's on the entrance's.
- [ ] The five lines are gone from the constants and nothing prints them; `BLOCKED` and `FAILED` are unchanged.
- [ ] The entrance's turn is answered before the planner has finished, and the plan follows in the same chat.
- [ ] A test asserts the entrance states no training fact that did not come from a tool.
- [ ] The full test suite and mypy are green.
