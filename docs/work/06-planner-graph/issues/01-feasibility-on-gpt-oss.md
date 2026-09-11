# Feasibility: does gpt-oss:20b reach a valid plan with feedback?

Status: ready-for-agent

Build the smallest planner graph that can answer this question, and measure it before anything else is built on top of it. The build is the agent's; three steps need the user (below).

## What to build

- **Dependencies.** Add `langgraph`, `langgraph-cli[inmem]` (it provides `langgraph dev`) and `langchain-ollama`. Read the settings from the environment:
  - `OLLAMA_MODEL`, default `gpt-oss:20b`;
  - `OLLAMA_CONTEXT_LENGTH`;
  - `OLLAMA_BASE_URL`.
- **`src/trainer/coach/planner.py`.** The graph is built from a chat model it is given, so tests pass a scripted one. Here the served graph and the probe use Ollama; choosing between Ollama and Groq is ticket 04. The state holds the request, the messages, the attempts, the last violations and the plan. Nodes:
  - `planner`: the model bound to the planner's tools (`agent.PLANNER`), with `agent.PLANNING` as the system prompt and `agent.brief(request)` as the brief.
  - `tools`: runs each call through the existing tool functions, trimming results with `agent.NOT_FOR_CONTEXT`.
  - `emit`: the model with no tools and a JSON schema built for this request. The schema is `WorkoutPlan`'s strict schema, with `exercise_id` restricted to an `enum` of the ids that `admissible_set` returns for the request.
  - `validate`: calls `plan.validate`. On a refusal, the refusal message goes back to `planner` as feedback, up to 3 attempts in total. The feedback is a message of its own: `agent.PLANNING` is shared with the Groq loop until ticket 05, so it does not promise a retry.
- **Edges.**
  - `planner` goes to `tools` when it calls a tool, and to `emit` when it does not. A turn of prose never ends the run.
  - A spent call budget also goes to `emit`.
- **`langgraph.json`**, so that `uv run langgraph dev` serves the graph to Studio.
- **A probe**, as a script or a `trainer` subcommand, never run by `pytest`.
  - It sets `TRAINER_DB` and builds the situations on that same file, so the tools read the database the situations were built on (CLAUDE.md).
  - It runs each of the six situations in `evaluation.py` once. A situation that starts after a refusal takes two runs, as `evaluation._once` does: the first plan is turned down, and the second is the one measured.
  - Per situation it prints whether the plan was valid, attempts, tool calls and wall time.
  - It records the peak memory of the Ollama process over the whole run.
- **Offline tests with a scripted chat model.** They cover:
  - a refusal goes back to `planner` carrying the validator's message;
  - the third refusal ends the run as refused;
  - a turn with no tool call reaches `emit`;
  - the enum holds exactly today's admissible ids.

## Steps that need the user

Ask, and wait for the answer, before each one.

- **Ollama settings.** The server must run with `OLLAMA_IGPU_ENABLE=1` and `OLLAMA_CONTEXT_LENGTH=16384`. Ask before setting these as user environment variables and restarting Ollama.
- **Memory.** Ask the user to close heavy apps before the probe. The last probe was killed for low memory.
- **Studio.** Ask the user to open the URL `langgraph dev` prints and confirm the run is visible.

## Acceptance criteria

- [ ] `uv run langgraph dev` serves the planner graph: a run completes through the server's HTTP API, and the user has confirmed it in Studio.
- [ ] A refusal reaches `planner` with the validator's message, seen in a test and in a real run.
- [ ] A test shows the emit schema cannot express an id outside today's admissible set.
- [ ] The probe ran over the six situations on `gpt-oss:20b`, and its numbers are appended to `docs/research/on-device-llm-android.md` § 5.
- [ ] A verdict is added to ADR-0004 § Why: either the model holds, or it does not and the fallback to measure next is named (`qwen3.5:9b`, or Groq). **If it does not hold, stop and report to the user before ticket 02.**
- [ ] The full test suite and mypy are green.
