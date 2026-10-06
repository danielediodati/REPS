# One roster of node models

Status: ready-for-agent

Read first: `spec.md`; ADR-0011 (each node runs the cheapest configuration that clears its bar); ADR-0006 item 3 (the entrance on a model of its own).

A refactor: no node changes the model it runs on.

## Where it stands

Which model each of the five nodes runs on is spread over:

| Piece | Where |
|---|---|
| four parallel constants per node: `X_MODEL_ENV`, `X_REASONING_ENV`, `X_HOST_ENV`, `X_CHOICE`, then `_CHOICES` mapping them again | `coach/models.py:49-130, 316` |
| one factory per node; the entrance branches on its own backend | `models.py:292-392` |
| five models built and checked one by one at start-up | `cli.bot_command` (:1004-1017) |
| five Chats passed positionally, two of them with fallbacks of their own: onboarding to the entrance's, supervisor to the planner's. `models.onboarding()` falls back to the coach's model instead; only tests reach `bot.graphs`' fallbacks today | `bot.graphs` (:1682) |
| a test helper that stands in a model for four node names and misses `supervisor` | `tests/test_cli.py` `stand_in` (:1682) |

A sixth node means touching all five places.

## What to build

- One node → configuration table in `models.py`, with a single fallback rule per node.
- One call that builds and checks every node's model, taken whole by the bot, the CLI and the eval suites.
- Tests swap that one thing, not five attributes.

## Acceptance criteria

- [ ] For every backend (`ollama`, `groq`, `openrouter`) and with and without each node's variables set, every node resolves to the same model, effort and host as before: a test pins it.
- [ ] `bot.graphs` takes the roster, with no fallbacks of its own; `bot_command` checks it in one call.
- [ ] `stand_in` covers every node by construction.
- [ ] `.env.example` and the README name the same variables as before.
- [ ] No paid model is called to close this ticket.
