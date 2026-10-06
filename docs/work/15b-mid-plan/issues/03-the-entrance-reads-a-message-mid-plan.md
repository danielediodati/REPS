# The entrance reads a message mid-plan

Status: ready-for-agent

Blocked by: 02.

Read first: `spec.md`; CONTEXT.md (Entrance, Situation, Run, Negotiation); ADR-0006, ADR-0007 item 7 (a cut run).

## Where it stands

`bot.Turns` (:374) runs one turn at a time per thread and queues anything that arrives meanwhile; the entrance says `QUEUED` and the message waits out the run. That was chosen when a plan was minutes on Ollama. It means a correction (*«anzi, 30 minuti»*) gets the wrong plan first and the right one after, and a question (*«quanto ho fatto di stacco?»*) waits minutes for a one-second answer.

## What to build

The entrance reads a message that arrives while the planner works, and:

| The message is | What happens |
|---|---|
| a question its read tools answer | answered at once; the planner carries on |
| a correction of the ask, or a new ask | the run in flight is stopped between graph steps, and the new one opens in the same negotiation |
| a report | queued as today: the logger and the planner write the same tables |

- Stopping is a Negotiation operation (ticket 02). A model call already sent finishes and is paid; nothing after it starts.
- A stopped run leaves a run record. Whether that is a new ending or ADR-0007's *cut* is settled here and written into CONTEXT.md and ADR-0007.
- ADR-0006 describes `Turns` as one run per thread and the queue behind it; correct it.

## Acceptance criteria

- [ ] On scripted models: a correction mid-run stops the run, the corrected plan is the one offered, and the stopped run has a record.
- [ ] On scripted models: a question mid-run is answered before the plan arrives, and the plan still arrives.
- [ ] A report mid-run is still queued.
- [ ] A paid pass, estimated and approved first: the three message kinds mid-run on the entrance's model, read by the user.
