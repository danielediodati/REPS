# Session 7: on the phone

**Goal**: the planner graph is reached from Telegram. A plan arrives in the chat with buttons, and turning it down or shortening the time resumes the same thread.

**Demo**: a screen recording. You ask Telegram for today's workout, the plan arrives with buttons, you tap *Non mi va*, and a different plan follows.

**Read first**:
- ADR-0004, the architecture — items 4 (`interrupt()`), 6 (Telegram), 7 (asynchronous) and 8 (the provider);
- ADR-0005, when a plan becomes a workout;
- ADR-0001, the engine never repairs a plan;
- TRAINER.md § Architecture and § Interaction;
- CONTEXT.md: *prescribed*, *pending question*, *constraint*, *preference*.

**Order**: 01 is the process the rest runs in, and 05 should follow it immediately — it is what makes a misconfigured machine say so instead of failing strangely later. 03 carries ADR-0005 into the code and 04 needs its resume. 02 can land last, but **before the demo is recorded**: without it a local run is minutes of still screen.

**Out of scope**:
- the logger, the router, the asynchronous next plan: session 8;
- memory, onboarding, triage: session 10;
- anything running on the phone (ADR-0004, item 9);
- `trainer log` stays on the hand-written Groq adapter whatever `LLM_BACKEND` names, until session 8. It already reports a missing key as a state before the user types their report (`agent.NO_CREDENTIALS`), so nothing here touches it.

## Facts the tickets rely on

**The graph.**
- `coach/planner.py`: `build(model, checkpointer=...)` returns the compiled graph; `PlannerState` holds `request`, `said`, `messages`, `spent`, `attempts`, `violations`, `refusals`, `timings`, `plan`. `ATTEMPTS` is 3, and `planner.starting(request)` is the input that begins a run on a thread another run has already used.
- `coach/checkpoints.py`: `saver()` yields a `SqliteSaver` over its own file, `TRAINER_CHECKPOINTS`, refusing to share the training database.
- langgraph 1.2.11 is installed; `interrupt` and `Command` come from `langgraph.types`.
- The graph stops at `propose`, which calls `interrupt()` with the plan, and the `record` node after the resume is the only thing in it that writes to SQLite (ADR-0005, ticket 03). `planner.accepted()` and `planner.refused(because, minutes)` are what a resume carries.
- `trainer plan` and `trainer eval` therefore both build the graph with a checkpointer: the command resumes immediately and the eval never resumes.

**Today's request.** `plan.requested(connection, today, plan.Asked(...))` assembles it, and both doors call it (ticket 04):
- `plan.Asked` is what a door was *told*; everything it does not name is derived. *«Cosa faccio oggi?»* is an empty `Asked`.
- equipment falls back to `training.toml`'s fifth declaration, the minutes to its cap, the groups to `constraints.rotated` — which reads the position off the performed workouts.
- `constraints.constraining_today` gathers standing exclusions, the budget and the groups; `config.TrainingConfig.groups_for(workout)` still serves a named workout.
- `plan.Request` is the one object the validator checks against, and `requested` is the only place it is built — a test fails the build if a second place appears.
- the unenriched catalog and the missing `training.toml` are reported from there, so neither door has its own copy of either state.

**The plan.** `plan.render(connection, plan, blocks, budget_min)` produces the lines the CLI prints. `plan.validate` returns `plan.Violation`s by name. `workouts.record_prescribed` writes one workout per call and says so.

**What reads a prescribed workout**, and why a refused plan must never become one:
- `state.volume_deficit` leaves an `outstanding` prescription out of both sides, and counts it as planned-never-performed the moment a later workout overtakes it;
- `state.unreported` names it from that same moment.

**The provider.** `models.chat()` reads `LLM_BACKEND` (default `ollama`, `gpt-oss:20b`). `models.ready()` already checks that Ollama is reachable and the model pulled, and returns early for Groq. `_context_length()` returns `None` when `OLLAMA_CONTEXT_LENGTH` is unset, and Ollama then uses a default far below the 8192 the session 6 measurement ran at.

**Telegram.**
- `sendMessageDraft` (Bot API 9.3) streams a partial message. The draft is **ephemeral** — about 30 seconds — and re-sending it with the same non-zero `draft_id` updates it in place with an animation. The finished message is an ordinary `sendMessage`; a draft never persists.
- Bot API 9.5 opened the method to all bots. python-telegram-bot binds 9.3 in v22.6 and 9.5 in v22.7, and snake-cases every API method.
- Long polling needs no public IP and no tunnel. Updates wait at Telegram for at most 24 hours while the PC is off.

**Tests.** `conftest.py` takes sockets and credentials away from every test. Everything here is tested offline: a scripted chat model for the graph, and handlers driven with constructed update objects for the bot.
