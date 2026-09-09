# 04 — The logging agent

**Status:** ready-for-agent

**Blocked by:** 02 (the door) and 03 (the tools it reads through).

## What to build

`trainer log`, interactive. The session's first model, and the heaviest ticket
of the five.

**It is a node that loops over a read-only tool surface**, the same shape as
session 4's planner and for the same reason: a report is not *extracted*, it is
**interpreted against something**. *«the bench felt heavy»* becomes a fact only
after `last_performed_load`. *«I swapped the presses because the shoulder was
pulling»* needs what was prescribed, what replaces it, and whether the
replacement is admissible — three tools, in an order decided on the spot and not
drawable in advance. That is what makes this an agent and not a parser with a
branch in it.

**Six tools, all reads**: the prescribed workout being reported against, the
prescribed workouts with no report, `last_performed_load`, `pattern_history`,
catalog search, `compare_variants`.

**Zero writes.** If the model can call the write, the model decides when the
database changes: the single door disappears, the validator becomes optional,
and an interrupted run leaves half a workout behind. The agent emits and the
engine writes — the same symmetry as session 4, where the agent does not call
`render` either.

`surface()` becomes parameterised by which agent is asking. One definition per
tool and never a second copy: a copy diverges at the first tool added to one
door and not the other. That is session 4's ticket 01 argument, unchanged.

**Exercise resolution is closed first.** The candidates are the exercises of the
prescribed workout — ten, not eight hundred. Catalog search is the fallback, and
it is called exactly when the closed set fails, which is exactly when there has
been a substitution: the interesting case. An id recalled from the model's own
memory is never acceptable — a well-formed dead id passes anything that does not
check the catalog, and the error becomes volume filed under the wrong exercise,
silently.

**The clarifying question.** When the report does not determine a value, the
agent asks rather than filling it. *«4 out of 10»* is genuinely effort **or**
discomfort, and TRAINER.md's own sentence does not say which. The turn happens
**inside one invocation**, in memory. Nothing is persisted between turns:
session 6's ticket 5 is the non-negotiable test that LangGraph never persists
domain and SQLite never persists conversation, and a half-finished report parked
in a table would make it red before it is written. Ctrl-C leaves no rubble.

**Pain, and the exclusion.** Pain is prose the agent reads. There is no scale,
no threshold and no accumulation anywhere in this ticket. Its only structured
outcome is a **proposed exclusion** — granularity, value, re-test date — which
travels inside the emitted document, is shown in the render, and requires the
user's confirmation in the same turn. `exclusions.classify` decides the
granularity against the catalog's own vocabulary, never the model. The write is
atomic: the workout and the exclusion enter together, or neither does.

The confirmation exists because an exclusion is the hard boundary and the
numbers are not small: the `shoulder` joint takes 251 exercises of 582 out of
the admissible set across six patterns, `vertical push` takes 50. Creating one
silently from a passing remark would cost the user a third of the catalog with
nobody telling them.

**What issue 02 already decided, so this ticket does not decide it again.**
The document the agent emits is `log.PerformedWorkout`, and four things about
it are settled:

- **The proposed exclusion carries a value, a re-test date and a `why` — no
  granularity.** `exclusions.classify` resolves the value against the
  catalog's own vocabulary, and a granularity on the wire would be a second
  answer to a question the engine already answers. The model names the thing;
  it does not label it.
- **Adherence is applied by `log.to_performed`, not by the model.** The agent
  may emit only what deviated: a prescribed exercise the document never names
  comes through with the prescription's numbers and a provenance of `assumed`.
  Emitting the whole workout with every value marked is also correct and
  changes nothing downstream — which of the two the prompt asks for is this
  ticket's call, and the eval in issue 05 is what decides it.
- **The write is `workouts.record_performed`, called from the CLI command.**
  It takes the workout, its blocks, the user's verbatim words and the
  exclusion, in one transaction, and it refuses a workout that was already
  reported. `test_agent.py::test_only_the_cli_calls_a_writer` is the guard
  that fails if this ticket puts it anywhere else.
- **`log.validate` raises, `log.flags` returns, and nothing in this ticket
  may turn a flag into a refusal** — a report is a fact. `flags` is read
  off the blocks `to_performed` resolved, never off the document: an
  exercise adherence filled in is as much a performed exercise as one the
  user named, and it is checked against the exclusions like any other.

**Read first:** `agent.py` in full — the loop, the call budget, the strict
structured output, the run record. ROADMAP.md § Session 5, the notes on the
agent, on writes never being tools, and on nothing persisting between turns.
TRAINER.md § Who holds the control flow, § The agent cannot route around the
constraints. CONTEXT.md § What a report says. CLAUDE.md § Standing rules.

## Acceptance criteria

- [ ] `trainer log` takes TRAINER.md's own sentence and moves the state: the deviation is recorded, the volume changes on both axes.
- [ ] The surface holds six tools and no writer. A test asserts no registered tool can write.
- [ ] `surface()` returns different sets for the planner and the logger, from one definition per tool.
- [ ] A substitution is resolved through catalog search only after the prescribed set fails, and the id it returns exists in the catalog.
- [ ] A report that does not determine a value produces a question, not a filled field — verified against a stand-in model, offline.
- [ ] The answer to that question lands with provenance `asked`.
- [ ] A bare number is never assigned to RPE or to pain without asking.
- [ ] A mention of pain that the agent judges worth an exclusion produces a proposal shown in the render, and nothing is written until the user confirms.
- [ ] Declining the proposal writes the workout and no exclusion. Accepting it writes both, in one transaction.
- [ ] Interrupting mid-conversation writes nothing, and no conversation state is left in SQLite.
- [ ] The call budget is enforced, and when it runs out the agent emits with what it has rather than looping.
- [ ] `pytest` stays offline: this ticket is covered against a stand-in model, and the real one runs only under ticket 05.
