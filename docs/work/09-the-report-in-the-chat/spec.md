# Session 9: the report in the chat

**Goal**: after training you write the report in Telegram, the bot asks one question and you answer with a button.

**Demo**: a chat. You report a workout in your own words, the bot asks the one thing it needs, and you tap the answer.

**Read first**:
- ADR-0007, what a run and a negotiation are -- 01 builds it and everything else stands on it;
- ADR-0006, the entrance -- 03 builds it;
- ADR-0005, a plan becomes a workout when it is accepted;
- ADR-0004, the architecture;
- CONTEXT.md: *run*, *negotiation*, *ending*, *run record*, *report*, *adherence*, *pending question*.

**Order**: 01 first and alone. Both the logger and the entrance write runs, and built before the run has a definition they are built twice. Then 02, which is the second subgraph the entrance will route to, and 03, which puts the entrance in front of both. 04 is withdrawn (ADR-0008); 05 last, because it measures what 02 built through the door 03 added.

**Out of scope**:
- the mesocycle, and the next one prepared unasked: session 10 (ADR-0008);
- a plan worth doing, the methodology and the time floor: session 11 (its tickets 02 and 03 are already cut);
- onboarding, memory, triage: session 13;
- hypotheses and trials: session 14. What a refusal leaves behind is *kept* here (ADR-0007 item 4) and promoted to a conclusion there.

## Facts the tickets rely on

**The run boundary today.** `planner.starting()` returns a state that clears `messages`, `attempts`, `refusals`, `spent`, `timings`, `violations`, `plan` and `workout`. `bot.planning()` calls it for a new request; `planner.propose()` returns `dict(starting(again))` when the user turns a plan down, carrying `refused`, `because` and possibly `minutes` forward inside the `Request`. So a run already ends at a refusal, and the refused run's record is overwritten rather than kept. `said` is the one key `starting` must keep leaving alone (ADR-0006).

**What travels into a later run today.** `plan.Request.refused` is one plan and `because` one string, both replaced each time. `planner.brief()` renders them; `plan._not_the_plan_that_was_refused` compares the emitted plan against that single `refused`. After three refusals the first plan can be re-offered and the invariant passes it.

**The record.** `coach/record.py`: `of(state, model, provider)` returns provider, model, outcome, attempts with violations, calls, tokens and per-node seconds; `document()` writes it as JSON; `summary()` as ASCII. `outcome()` derives `refused`/`valid`/`unfinished` from `violations` and `attempts`. `record.Run` (model, provider, budget) travels in the run's config and lands in each checkpoint's metadata. `trainer plan --record`, both eval suites and `trainer runs` are the callers.

**The reader.** `coach/runs.py`: `conversations()` takes the last checkpoint of every thread off the saver; `read()` takes one thread's last checkpoint. Neither builds the graph, so neither can see a pending `interrupt()` -- `bot.py:613` does that with `graph.get_state(...).interrupts`.

**The old logger.** `agent.py` is a hand-written tool loop on Groq with its own HTTP error handling, its own `QUESTION_MARKER = "QUESTION:"` protocol for asking the user something, and its own settings: `GROQ_MODEL` (default `qwen/qwen3.8-27b`), `GROQ_API_KEY`, `GROQ_MAX_TOKENS`. `coach/models.py` reads those constants for its own Groq path, so `agent.py` cannot be deleted before they move. `trainer log` and `log_evaluation.py` are its callers.

**The log eval set.** `docs/logging/` holds the 30-report set; `log_evaluation.py` runs it against `agent.py` and reads `agent.QUESTION_MARKER` as a field.

**The tool surface.** `tools.py` is shared by the agent and the MCP server. The logger reads and writes performed workouts through it; the planner reads the admissible set through it. Both subgraphs are on the same surface (ADR-0006 item 2).
