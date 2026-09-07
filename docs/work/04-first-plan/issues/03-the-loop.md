# 03 — `trainer plan` asks a model, inside a call budget

**Status:** ready-for-agent

**Blocked by:** 01 (the tool surface it loops over), 02 (the schema it emits and
the validator it goes out through).

## What to build

The first model in the project. `trainer plan --equipment dumbbell --time 45`
prints a workout you can do tonight.

**A node that loops, not a graph.** TRAINER.md § *Where LangGraph comes in* is
explicit that the workout loop *«is a node looping over a tool surface, and a
graph adds nothing to a node that loops»*. LangGraph arrives in session 6, for
onboarding, where checkpointing and resume are the point. Here: the provider SDK
directly, and the tool surface from ticket 01.

**The call budget.** The cost of a tool call is the context round-trip, and it is
bounded (TRAINER.md § *The tool surface*). The loop counts tool calls against a
declared budget, and when the budget runs out **it emits anyway** — it stops
offering tools and asks for the plan with what it has. That is invariant 1 of
TRAINER.md § *Level 1 — the agent*, and it is behaviour, not an error path.

**The way out is ticket 02's validator, and there is no way back in.** A plan
that fails validation is reported as rejected, with the rule that rejected it.
It is not trimmed, and it is not handed back to the model to fix: *propose →
check → correct* is the loop TRAINER.md deliberately does not have, because the
constraints are applied upstream. A rejection here is a bug to go and read, which
is exactly what ticket 05 counts.

**The run record.** What the model called, in what order, with what arguments,
how much budget went, whether it emitted on exhaustion, and the plan it emitted.
The trace is an artifact, not a log — and ticket 05 measures on it.

**Tests stay offline.** `conftest.py` takes away sockets and credentials from
every test on purpose, and that guarantee is worth more than the convenience of
one runner. The loop is exercised in `pytest` against a stand-in model that
returns scripted tool calls and a scripted plan. The real model runs in ticket 05
and nowhere else.

**Read first:** TRAINER.md § *Who holds the control flow* (the two traces, and
why the second one was not drawable in advance), § *The tool surface*, § *Agent —
deliberative*, § *Level 1 — the agent: invariants*, § *Technical architecture*.

## Acceptance criteria

- [ ] `trainer plan --equipment dumbbell --time 45` prints a rendered workout, produced by a real model call.
- [ ] The tools offered are exactly ticket 01's surface: no second definition, and no tool the MCP door does not also have.
- [ ] Tool calls are bounded by a declared budget. A run that exhausts it still emits a plan, and the record says it was emitted on exhaustion.
- [ ] The emitted plan goes through ticket 02's validator before anything is printed; a rejection is reported with its rule and the plan is neither repaired nor re-asked.
- [ ] The whole loop — tool calls, budget exhaustion, emission, validation, rendering — is covered by `pytest` against a stand-in model, with the suite's no-network and no-credentials fixtures untouched.
- [ ] A missing API key is reported as a state with the way out, never as a traceback and never as a user error.
- [ ] The model is named in one place, not spelled out at each call site.
- [ ] The run record holds the calls in order with their arguments, the budget consumed, the exhaustion flag and the emitted plan, and can be written out for ticket 05 to read.
