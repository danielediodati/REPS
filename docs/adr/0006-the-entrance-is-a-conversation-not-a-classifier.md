# The entrance is a conversation, not a classifier

Session 8 planned a router: *a message is a report, a plan request, or a question*. A router classifies and then each branch answers from constants, which is what the bot does today with one branch instead of three — every message reaches `planning()`, and what the user wrote is stored in the graph state as `said` under a comment saying nothing reads it.

The seven lines the bot can say are `STARTED`, `BLOCKED`, `QUEUED`, `FAILED`, `WRITTEN`, `SUPERSEDED` and `NO_PLAN`. Three more branches would make twenty-one.

This ADR replaces the router. It does not touch the engine, the planner graph or ADR-0001.

## Decision

1. **The entrance is a node that talks.** A chat model holds the conversation and decides what to do with a turn, including answering it itself. It is a supervisor in LangGraph's sense, not a classifier: ADR-0004 item 1 already names *supervisor* among the graphs.
2. **The subgraphs are reached as tools.** `plan_mesocycle` and `log_workout` invoke the planner and logger subgraphs (`plan_today` until ADR-0008, when today's workout became `todays_workout`, a read of the mesocycle), which are otherwise unchanged — the planner keeps its refusal loop, its `interrupt()` and its `record` node. The engine's read tools are on the same surface, so *"how much chest have I done this cycle"* is answered without entering a subgraph at all.
3. **Two models, chosen per node.** The entrance runs on a small fast model; the planner keeps the one `LLM_BACKEND` names. ADR-0004 item 8 already gives the supervisor a model of its own; this extends it to the entrance, which is the node latency is felt on.
4. **What the entrance may not decide.** It reads prose and writes prose. It does not choose which workout is due — that is the rotation, read off the performed workouts. It does not judge whether a plan fits — that is the validator. It states no training fact it did not get from a tool.
5. **`BLOCKED` and `FAILED` stay constants.** They are the two cases where the model is absent or not to be trusted: a precondition the machine gets wrong, and a run that raised. Nothing raised leaves the machine, and a generated apology is a place for it to leak out of.
6. **The entrance answers before the work is finished.** A plan takes minutes (ADR-0004 item 7). The turn is answered at once and the run proceeds behind it, its progress in the draft.

## Why

- **A router cannot stop being wooden.** Its output is a branch, and a branch's words are written in advance. The complaint that prompted this was not *the bot picked the wrong branch*; it was that everything it says is a constant.
- **Latency is what makes or breaks this, and it is per node.** Measured on the dev laptop: the local model generates **10.3 tok/s** and reads **52 tok/s** on CPU. A conversational entrance on that model costs half a minute to say hello, which is worse than the silence it replaces. A model of its own is what keeps the minutes where they are unavoidable — inside planning.

  **Measured again once it existed, and *small* was not enough.** On `llama3.1` on the same laptop, one user turn is **about a minute**: ~2.7k input tokens, almost all of it the tool definitions, read at that same 52 tok/s, and two turns to it — one to decide, one to say so. Saying one thing that happened, which binds no tools, is **6 seconds**. So the entrance is immediate only where it is not reading a tool surface; the levers are a genuinely small model (`ENTRANCE_MODEL`) or the other provider (`ENTRANCE_BACKEND`), and both are settings rather than code. This is the same finding as the roadmap's risk note, one model down: on this machine there is no GPU in play.
- **The engine/agent split is what makes a talking entrance safe.** ADR-0001 keeps prescription out of the engine; item 4 above keeps invention out of the agent. A model that reads training facts through tools can hold a conversation without being the source of any of them.
- **It costs no rework.** The planner graph, the validator, the interrupt and the tool surface are all reached as they are. What changes is what sits in front of them.

## Consequences

- **Supersedes** session 8 item 2 of ROADMAP.md, *the router*.
- **`STARTED`, `QUEUED`, `WRITTEN`, `SUPERSEDED` and `NO_PLAN` stop being constants** and become things the entrance says. `BLOCKED` and `FAILED` do not.
- **`bot.Coach` is renamed.** It is the turn-taking — one run at a time per thread, and the queue behind it — and the domain word is needed for the node that does the coaching.
- **Amended in session 15b: a message mid-plan is read, not queued.** While a plan is written, `Turns` hands a new message to the entrance: a question is answered at once, a correction or a new ask stops the run between graph steps and its replacement goes ahead of the queue, and a report or a declaration waits for the plan. Anything else still queues.
- **Amended in session 15c: a plan waiting is answered in words too.** While a proposal waits, the entrance is told so and offered `accept_plan` and `turn_down_plan`, which go through the same `Negotiation.answer` a tap does; a new ask replaces the plan, a report of the workout it adapts ends it, and anything else leaves it waiting.
- **A second provider setting**, because two nodes now name two models. The run record carries the model per node from ADR-0007, which is where that becomes true.
- **Both eval suites are unaffected.** They enter at the subgraphs, which do not change.
- **`said` stops being write-only.** It is the conversation the entrance reads, and `planner.starting` must keep leaving it alone.

## Amended in session 12

**On OpenRouter the entrance runs `openai/gpt-oss-120b` at low effort on Cerebras** (ADR-0011): 0.3–1.2 s a turn, against a minute on `llama3.1` here. `llama3.1` stays the default on Ollama.

## Amended in session 15b

**The entrance runs on OpenRouter only** (ADR-0015). `ENTRANCE_BACKEND` and the `llama3.1` default are gone; `ENTRANCE_MODEL` still gives it a model of its own.
