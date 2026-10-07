# A plan is answered in words too

Status: ready-for-agent

Read first: `spec.md`; CONTEXT.md (Entrance, Situation, Run, Negotiation, Ending); ADR-0006, ADR-0007 items 7 and 8.

## Where it stands

Found using `1.0.0rc1`, 2026-10-07, on the demo's home:

- A proposed plan is answered only by its buttons. Text sent while one is open goes to the entrance, which does not know a proposal is pending (only the next mesocycle is, `entrance.WAITING_MESOCYCLE`). *«ok»* accepts nothing.
- An adaptation of today's workout stayed `waiting` after today's workout was reported. A tap on it still resumes it: an adaptation accepted for a workout already done.
- *Solo 30 minuti* reads as a label, not as what it does. The user asked what the three buttons mean.
- `Negotiation.open` over a pending proposal supersedes it and writes no ending, so it reads as *cut* (15b.3, "From 02").

## What to build

While a proposal is open, the entrance sees it, and what the user writes is read against it:

| The user writes | What happens |
|---|---|
| *«ok»*, *«perfetto»*, *«daje»* | accepted, as the *Va bene* tap |
| *«no»*, *«non mi piace»* | turned down, as the *Non mi va* tap, and the next plan follows |
| *«senza panca»*, *«ho 20 minuti»* | a new ask in the same negotiation; the open proposal ends |
| a report of the workout the proposal adapts | the logger reads it; the proposal ends |
| anything else: a question, an unrelated report | answered as today; the proposal stays open |

- Which row a message is is the entrance model's judgement; accepting and turning down go through the same `Negotiation.answer` a tap does.
- A proposal that ends without an answer gets an ending written then, never *cut*. Whether that is a new ending or an existing one is settled here and written into CONTEXT.md (Ending) and ADR-0007.
- The buttons left on a closed proposal do nothing when tapped, and the chat says why (a Situation).
- The adapted workout's buttons are *Va bene* and *Non mi va*; *Solo 30 minuti* goes, since writing it does the same. The README's "What it does" table gains the written answers.

## Acceptance criteria

- [ ] On scripted models: each row of the table, with the run records it leaves.
- [ ] Reporting the workout an open adaptation adapts ends the adaptation; a tap on it afterwards changes nothing.
- [ ] No run in the archive reads `cut` after a new ask over an open proposal.
- [ ] The adaptation set (`docs/adapting/eval-set.toml`) gains rows for written answers to an open proposal, and `trainer eval --suite adapt` passes its bars: a paid pass, estimated and approved first.
