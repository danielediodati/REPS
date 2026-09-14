# The bot, long-polling from the graph's process

Status: ready-for-agent

`trainer bot` is the process the rest of the session runs in: it holds the graph, the checkpointer and the Telegram connection for as long as it lives.

## What to build

- **Dependency**: `python-telegram-bot>=22.7`. That release binds Bot API 9.5, which is where `sendMessageDraft` became available to every bot (ticket 02 needs it; pinning it once here avoids a second dependency change).
- **Settings, from the environment** and never from `training.toml`, which holds the four things the user declares about their training (ADR-0003):
  - `TELEGRAM_BOT_TOKEN`;
  - `TELEGRAM_OWNER_ID`, the only user id the bot answers.

  Both go in `.env.example`, with the line that says where to get a token. `python-dotenv` is already a dependency and already read by the `trainer` command.
- **`trainer bot`**, a command that long-polls until interrupted. It builds the model with `models.chat()`, opens the checkpointer with `checkpoints.saver()`, compiles the graph once, and keeps all three for the life of the process.
- **Owner only.** An update from any other user id is answered with nothing and logged as one line. This is checked before anything else looks at the message.
- **One chat is one thread.** The `thread_id` is derived from the chat id, so the same conversation keeps its state across restarts — the checkpointer is on disk.
- **A message arriving while a run is in flight is queued**, and the bot says so in one line rather than dropping it or starting a second run on the same thread. A run is not cancelled and restarted: on Ollama that throws away minutes of work, and *"actually, 30 minutes"* is what ticket 03's interrupt is for.
- **Startup line**: the provider, the model and the thread the chat maps to. Ticket 05 turns this into a real check.

## Acceptance criteria

- [ ] `trainer bot` starts, answers `/start` in the owner's chat, and keeps running.
- [ ] A message from a user id that is not `TELEGRAM_OWNER_ID` is answered with nothing, and a test shows it.
- [ ] A test shows a second message arriving during a run is queued and acknowledged, not dropped.
- [ ] The bot survives a restart with the thread intact: a test drives two handler calls across two compiled graphs over one checkpoint file.
- [ ] Missing `TELEGRAM_BOT_TOKEN` or `TELEGRAM_OWNER_ID` stops the command with a state naming the variable and `.env.example`.
- [ ] Tests run offline, with constructed update objects; no test opens a socket.
- [ ] The full test suite and mypy are green.
