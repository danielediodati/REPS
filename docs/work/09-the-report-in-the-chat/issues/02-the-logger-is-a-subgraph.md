# The logger is a subgraph, on the same tools

Status: ready-for-agent

Blocked by: 01 -- the logger writes runs, and a run built before it has a definition is built twice.

`trainer log` still runs `agent.py`, the hand-written tool loop on Groq that predates ADR-0004: its own HTTP error handling, its own `QUESTION:` marker for asking the user something, its own settings. It is the last thing in the system that is not a graph, and the one place where a question to the user is a string convention rather than an `interrupt()`.

## What to build

- **The logger as a subgraph on the tool surface `tools.py` already exposes**, the way the planner is. It reads the prescribed workout, reads the report, writes the performed workout with its provenance per field.
- **The clarifying question is an `interrupt()`**, not a marked line in prose. It is a pending question in CONTEXT.md's sense: it can wait days without losing the thread, and it resumes the run rather than starting another.
- **The exclusion confirmation is an `interrupt()`** too: an exclusion is a hard boundary used only for safety, and it is confirmed before it is written, never inferred from a report.
- **Buttons where the answer is closed**, prose where it is not. What the user taps resumes the thread the button carries, the way a plan's buttons already do.
- **`trainer log` runs the subgraph**, on the provider `LLM_BACKEND` names, like `trainer plan`.
- **`agent.py` is deleted with it**, and with it `QUESTION_MARKER` and the hand-written adapter. `coach/models.py` reads `GROQ_MODEL`, `GROQ_API_KEY` and `GROQ_MAX_TOKENS` from `agent.py` today, so those settings move into `models.py` first. **`GROQ_MODEL`'s default names a model that is not there** -- the Groq path dies on a 404 -- so it is set to one that answers, checked by running it, and `models.ready()` reports a model Groq does not have as a state with its fix.
- **A report is a fact and is never refused** for what the user did. What the engine noticed is a flag, computed when the workout is read.

## Acceptance criteria

- [ ] `trainer log --say "..."` writes a performed workout through the subgraph, with provenance per field, on both providers.
- [ ] A report that needs one thing clarified stops on an `interrupt()`, and answering it days later resumes the same run.
- [ ] A report implying an exclusion stops for confirmation, and nothing is written to `exclusions` until it is confirmed.
- [ ] A run of the logger leaves a run document, like a run of the planner (01).
- [ ] `agent.py` and `QUESTION_MARKER` are gone, and nothing imports them.
- [ ] `trainer bot` and `trainer plan` still work on Groq, against a model that answers.
- [ ] The full test suite and mypy are green.
