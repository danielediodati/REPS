# The plan in the chat, and the refusal loop made visible

Status: ready-for-agent

The plan is rendered for Telegram, and what happens while it is being built is streamed into the chat.

**What is streamed is the graph's progress, not the plan.** The planner emits JSON against a constrained schema: there is no prose to scroll token by token. The tools it calls and the violations it is sent back are the things worth showing, and they are the reason this ticket exists — the refusal going back to the planner is the central decision of ADR-0004, and without this it is invisible. The user sees a plan appear and cannot tell the graph from any wrapper around a model. On Ollama it does a second job, covering minutes of silence.

## What to build

- **A Telegram rendering of the plan**, built from the same data `plan.render` renders for the terminal. Markdown the client will accept; the terminal's ASCII folding is a console constraint and does not apply here.
- **Progress lines from the graph's own stream**, one per step, in the user's language:

  ```
  guardo cosa puoi fare oggi con manubri e 45 minuti
  controllo quanto tempo resta -> 45 min
  scrivo il piano
  il validatore ha rifiutato: budget superato di 8 min, 2 violazioni
  riscrivo il piano
  piano valido, 4 blocchi
  ```

  The violations are named, from `plan.Violation` — ticket 03 of session 6 made them a list rather than the first one raised, and this is what that is for.
- **`sendMessageDraft` with one stable non-zero `draft_id` per run**, re-sent as the lines accumulate so the draft updates in place. The draft is ephemeral, about 30 seconds, so it is re-sent while the run continues and never relied on to persist.
- **The finished plan is an ordinary message**, sent once, and it is the only thing that stays in the chat.

## Acceptance criteria

- [ ] A run in the owner's chat shows progress updating in place, then the plan as one message.
- [ ] A refused attempt shows the violations by name before the retry, seen in a real run against Ollama.
- [ ] A test shows the draft is never the final message: the plan is sent with `sendMessage` after the last draft.
- [ ] A test shows the progress lines are built from the graph's stream, with a scripted chat model and no network.
- [ ] The full test suite and mypy are green.

## Comments

This ticket gates the demo recording. A local run is minutes long, and recorded without it the demo is a still screen.

**The link to Telegram stalls, and this ticket writes to it far more often than ticket 01 did.** Measured on the dev laptop while diagnosing the first real run: `api.telegram.org` answers in about 135 ms eight times out of eight, and once in three stalled past 20 seconds without reaching TCP at all — ahead of the socket, not IPv6, which has no route here and fails in 15 ms. python-telegram-bot's default `connect_timeout` is 5 seconds, so a send caught by one of those stalls times out.

Ticket 01 left the defaults alone deliberately: one observation is thin evidence for a number, and `Coach._tell` already makes a failed send survivable — the bot logs it, keeps its queue and answers the next message. A draft re-sent every few seconds for the length of a run is a different exposure, so if progress lines start disappearing, raise the timeouts on `ApplicationBuilder` here, where there is enough traffic to measure whether it helped.
