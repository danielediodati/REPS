# One Negotiation, two doors

Status: ready-for-agent

Read first: `spec.md`; CONTEXT.md (Negotiation, Run, Ending, Run record); ADR-0004 item 5 (one owner per store), ADR-0006, ADR-0007, ADR-0008 item 5 (the machine opens the next mesocycle), ADR-0014.

A refactor: nothing the user sees changes.

## Where it stands

The negotiation has no module; it is a string in the planner's state, and its life is spread over four places.

| Piece | Where |
|---|---|
| a negotiation's id, a run's identity, its ending written | `coach/record.py` (`negotiation_id`, `identity`, `born`, `closing`) |
| a turn-down closes the run and opens the next in the same negotiation; acceptance writes the workout | `coach/planner.py` (`starting`, `following`, `propose`, `prescribe`) |
| a tap answers the plan in hand or is told it is superseded; a new run supersedes the pending one; is the next mesocycle already offered or being prepared | `coach/bot.py` (`answering` :1069, `_planning` :688, `_preparing` :1231, `_asked_for` :1252, `prepared` :1210, `Graphs.preparing`) |
| reading what happened | `coach/runs.py` |

The CLI drives the same life with its own code: `cli._ran` (:1710) invokes and resumes as accepted. The only test of "at most one plan" is `tests/test_bot.py:1488`, through a fake Telegram chat.

## Decided

- **Scope**: plan proposals only (mesocycle, change, adaptation). The onboarding's and the logger's exclusion confirmations stay in the bot.
- **Operations**: open a request (superseding any proposal pending on the thread); answer a proposal by id (kept / redo; a stale id is reported superseded and writes nothing); prepare the next mesocycle (supervisor, then planner; nothing if one is offered or being prepared); what is pending (nothing, asked, unasked).
- **Results** are domain values with nothing of Telegram: proposed (plan and id), accepted (workout written), superseded, refused to the end. The bot renders them; the CLI uses the same ones.
- **The caller builds the request**, preconditions included (`bot._handed`, the CLI's flags). Only "prepare the next" builds its own.
- **Synchronous**, with an optional progress callback for the bot's drafts. The bot keeps calling it through `asyncio.to_thread`, as `streamed` does today: one `SqliteSaver` serves both doors.
- **No new store**: it reads and writes the planner's checkpoint and the run records, as today.
- **Callers**: bot and CLI. The eval suites keep invoking the planner graph directly; they measure the graph.

## Acceptance criteria

- [ ] Every existing test in `test_bot.py` and `test_cli.py` passes unchanged.
- [ ] New tests on the Negotiation alone, no Telegram types: two answers to one proposal write one workout; opening a request supersedes the pending one; a stale id writes nothing; preparing the next is a no-op when one is offered or in preparation.
- [ ] `bot.py` no longer reads interrupts or `unasked` from the planner's state; `cli._ran` is gone.
- [ ] No paid model is called to close this ticket.
