# The entrance is a conversation, not a classifier

Session 8 planned a router: *a message is a report, a plan request, or a question*. A router classifies and then each branch answers from constants, which is what the bot does today with one branch instead of three — every message reaches `planning()`, and what the user wrote is stored in the graph state as `said` under a comment saying nothing reads it.

The seven lines the bot can say are `STARTED`, `BLOCKED`, `QUEUED`, `FAILED`, `WRITTEN`, `SUPERSEDED` and `NO_PLAN`. Three more branches would make twenty-one.

This ADR replaces the router. It does not touch the engine, the planner graph or ADR-0001.

## Decision

1. **The entrance is a node that talks.** A chat model holds the conversation and decides what to do with a turn, including answering it itself. It is a supervisor in LangGraph's sense, not a classifier: ADR-0004 item 1 already names *supervisor* among the graphs.
2. **The subgraphs are reached as tools.** `plan_today` and `log_workout` invoke the planner and logger subgraphs, which are otherwise unchanged — the planner keeps its refusal loop, its `interrupt()` and its `record` node. The engine's read tools are on the same surface, so *"how much chest have I done this cycle"* is answered without entering a subgraph at all.
3. **Two models, chosen per node.** The entrance runs on a small fast model; the planner keeps the one `LLM_BACKEND` names. ADR-0004 item 8 already gives the supervisor a model of its own; this extends it to the entrance, which is the node latency is felt on.
4. **What the entrance may not decide.** It reads prose and writes prose. It does not choose which workout is due — that is the rotation, read off the performed workouts. It does not judge whether a plan fits — that is the validator. It states no training fact it did not get from a tool.
5. **`BLOCKED` and `FAILED` stay constants.** They are the two cases where the model is absent or not to be trusted: a precondition the machine gets wrong, and a run that raised. Nothing raised leaves the machine, and a generated apology is a place for it to leak out of.
6. **The entrance answers before the work is finished.** A plan takes minutes (ADR-0004 item 7). The turn is answered at once and the run proceeds behind it, its progress in the draft.

## Why

- **A router cannot stop being wooden.** Its output is a branch, and a branch's words are written in advance. The complaint that prompted this was not *the bot picked the wrong branch*; it was that everything it says is a constant.
- **Latency is what makes or breaks this, and it is per node.** Measured on the dev laptop: the local model generates **10.3 tok/s** and reads **52 tok/s** on CPU. A conversational entrance on that model costs half a minute to say hello, which is worse than the silence it replaces. On a small fast model the same entrance is immediate, and the minutes stay where they are unavoidable — inside planning.
- **The engine/agent split is what makes a talking entrance safe.** ADR-0001 keeps prescription out of the engine; item 4 above keeps invention out of the agent. A model that reads training facts through tools can hold a conversation without being the source of any of them.
- **It costs no rework.** The planner graph, the validator, the interrupt and the tool surface are all reached as they are. What changes is what sits in front of them.

## Consequences

- **Supersedes** session 8 item 2 of ROADMAP.md, *the router*.
- **`STARTED`, `QUEUED`, `WRITTEN`, `SUPERSEDED` and `NO_PLAN` stop being constants** and become things the entrance says. `BLOCKED` and `FAILED` do not.
- **`bot.Coach` is renamed.** It is the turn-taking — one run at a time per thread, and the queue behind it — and the domain word is needed for the node that does the coaching.
- **A second provider setting**, because two nodes now name two models. The run record carries the model per node from ADR-0007, which is where that becomes true.
- **Both eval suites are unaffected.** They enter at the subgraphs, which do not change.
- **`said` stops being write-only.** It is the conversation the entrance reads, and `planner.starting` must keep leaving it alone.
