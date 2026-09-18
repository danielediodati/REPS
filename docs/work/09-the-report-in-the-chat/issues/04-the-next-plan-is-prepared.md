# The next plan is prepared before it is asked for

Status: ready-for-agent

Blocked by: 02, 03 -- a performed workout is what triggers it, and the entrance is what delivers it.

The plan takes minutes on the local model, and today those minutes are always spent while you wait. They do not have to be: the moment a workout is performed, the next one is knowable.

## What to build

- **A performed workout triggers planning**, and the plan waits in the chat rather than being asked for. The rotation already says which workout is next; nothing about the request is guessed.
- **A negotiation nobody asked for is still a negotiation** (ADR-0007). It is opened by the machine, it holds its runs, and it ends when the user accepts a plan or it is left. Left is derived when read, never written: the reader says how long it has been waiting.
- **It is superseded rather than duplicated.** If you ask for today's workout and a prepared one is already waiting, you get the prepared one or a fresh run supersedes it -- one of the two, decided in the ticket, and never two plans in the chat for the same day.
- **It does not run while you are being answered.** One run at a time per thread is what the turn-taking guarantees, and a background plan must not make the bot look busy to the person typing into it.
- **The declaration decides whether it happens at all.** A plan prepared for a day the user does not train is minutes of a laptop's CPU spent on nothing.

## What 03 left for this one

- **A run has to be startable without an entrance turn in front of it.** 03 made a turn one run: the entrance is its first node and `entrance.carried` hands the run and its seconds to the subgraph, which is how one document names both models. A plan nobody asked for has no entrance turn, so it opens its own run with `planner.starting` alone -- which works today, and is the thing to say out loud rather than discover.
- **`bot._planning` and `bot._logging` both take the entrance's final state**, for `carried` only. The machine-triggered path is the same two functions without it.
- **The entrance's latency does not matter here and does matter everywhere else.** Measured on `llama3.1` on the dev laptop: about a minute for a user turn, six seconds to say one thing that happened (ADR-0006, *Why*). Nobody is waiting on a prepared plan, so this is the one path where the minutes are free -- and the line it arrives on is a relayed situation, which is the cheap kind.
- **`bot.under(thread, PLANNING)` is the thread a prepared plan runs on**, the same one a requested plan uses. That is what makes *superseded rather than duplicated* fall out of the checkpointer instead of needing a rule.

## Acceptance criteria

- [ ] Reporting a workout leaves a plan waiting in the chat, without a request.
- [ ] The prepared plan is the next workout of the rotation, against the declaration and the exclusions in force.
- [ ] Asking for today's workout while one is waiting never leaves two plans in the chat for the same day.
- [ ] A message arriving while a plan is being prepared is answered, not queued behind it.
- [ ] The prepared negotiation appears in `trainer runs list` and is distinguishable from one the user opened.
- [ ] A prepared plan left unanswered is reported as waiting, with how long, and never as abandoned.
- [ ] The full test suite and mypy are green.
