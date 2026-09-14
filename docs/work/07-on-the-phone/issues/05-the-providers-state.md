# The provider's state, checked when the bot starts

Status: ready-for-agent

Everything the bot needs to answer at all is knowable before the first message. Each missing piece is reported as a state with its fix, never as a failure of the thing the user asked for.

**Only the selected provider is checked.** Failing for a provider nobody is using is noise.

## What to build

- **Ollama** (`models.ready()` already does the first two):
  - the server is reachable, or *start Ollama, or point `OLLAMA_BASE_URL` at the server*;
  - the model is pulled, or *run `ollama pull gpt-oss:20b`*;
  - **`OLLAMA_CONTEXT_LENGTH` is set**, and the bot refuses to start when it is not. Unset, Ollama uses a default far below the 8192 that session 6 measured 6 of 6 at. The tool result carrying today's admissible set is then truncated, the model plans against a cut list, and the validator refuses it for reasons that have nothing to do with the cause. The message says exactly that: *set it to 8192 in `.env` — below that the admissible set is truncated and plans are refused for no visible reason.*
- **Groq**: the key, which `agent.NO_CREDENTIALS` already words.
- **Telegram**: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID`, from ticket 01.
- **One startup block** naming the provider, the model, the context length and the chat it will answer.

## Acceptance criteria

- [ ] With Ollama down, `trainer bot` stops and names the fix; the same for a model that is not pulled.
- [ ] With `OLLAMA_CONTEXT_LENGTH` unset, `trainer bot` stops and explains what a short context does to planning.
- [ ] With `LLM_BACKEND=groq` and no key, the bot stops with the Groq state; with a key, it does **not** check Ollama at all.
- [ ] Missing Telegram settings stop the bot by name.
- [ ] The startup block prints provider, model, context length and owner chat.
- [ ] Every check is covered by a test, offline.
- [ ] The full test suite and mypy are green.
