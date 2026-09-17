# Session 8: you can see what it is doing

**Goal**: everything the machine writes is in one directory you copy in one move, and a run that stopped can be read back afterwards.

**Demo**: pull the plug mid-run, restart, and read back what the bot was doing and why it stopped.

**Read first**:
- ADR-0003, what the user declares and what the system writes -- 01 amends it;
- ADR-0004, the architecture -- item 5, the checkpointer;
- TRAINER.md § Architecture;
- CONTEXT.md: *prescribed*, *constraint*.

**Order**: 01 first, because it decides where the log of 02 is born and a log written before it would have to move. 03 and 04 are a pair and can run beside 01.

**Out of scope**:
- the logger subgraph, the entrance that talks, the asynchronous next plan: session 9;
- onboarding writing `training.toml` by talking to the user: session 11 (ADR-0003);
- a plan worth doing: session 10.

## Facts the tickets rely on

**Where things are written today.**
- `engine/database.py`: `TRAINER_DB`, default `trainer.sqlite` in the working directory.
- `coach/checkpoints.py`: `TRAINER_CHECKPOINTS`, default `checkpoints.sqlite` in the working directory, refusing to be the training database.
- `engine/config.py`: `TRAINER_CONFIG`, default `training.toml` in the working directory; `src/trainer/data/training.example.toml` is the committed example.
- `evaluation.py`: `RECORDS = Path("eval-runs")`, a constant, relative to the working directory.
- Two directories away from each other therefore mean two different databases, silently.

**The run record.** `coach/record.py` derives it from the graph's state: `of(state, model, provider)` returns provider, model, outcome, attempts with their violations, calls, tokens and per-node seconds; `document()` writes it as JSON, and `summary()` as ASCII lines for the terminal. `trainer plan --record` and both eval suites are the only callers. Nothing has ever read a record back out of a checkpoint.

**The checkpointer.** `saver()` yields a `SqliteSaver` over its own file. LangGraph's msgpack serializer writes unregistered types today and warns it will stop reading them back; `LANGGRAPH_STRICT_MSGPACK` and the `allowed_msgpack_modules` argument are the two ways to be explicit. The state holds `plan.Request`, `plan.Violation` and `plan.WorkoutPlan`.

**Logging.** `coach/bot.py` has a module logger and calls it, and nothing anywhere configures logging: there is no handler, so the record is whatever stderr happens to be. `BLOCKED` and `FAILED` are the two chat lines that point at it, today as *«dove gira il bot»*. Nothing raised leaves the machine (ticket 07/02's rule): the engine's states carry absolute paths, and quoting them into Telegram publishes this installation's account name and disk layout.

**Tests.** `conftest.py` takes sockets and credentials away from every test. A test that writes must point `TRAINER_HOME` at a `tmp_path`, the way the suites already point `TRAINER_DB`.
