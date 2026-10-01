# Prompt caching

Status: ready-for-agent

Blocked by: none.

Read first: ADR-0011 (each node runs the cheapest configuration that clears its bar); `models.openrouter` and `OpenRouterChat` (`coach/models.py`); `record._tokens` (`coach/record.py`).

## What to build

- **The record counts cached input**: `tokens.cached`, summed from each reply's `usage_metadata["input_token_details"]["cache_read"]`, beside `input` and `output`. A provider that reports none counts 0.
- **The planner caches what repeats**: on an Anthropic model, a `cache_control: {"type": "ephemeral"}` breakpoint on the last message of each request, so each turn of its tool loop reads the turns before it (tools, system, brief, earlier calls) from the cache. Through OpenRouter's content-block form on the existing `ChatOpenAI` client; no Anthropic SDK. No breakpoint on a model that caches by itself.
- **Haiku 4.5 caches only a prefix of 4096 tokens or more**: shorter is silently uncached, so the system prompt alone may not reach it. The first turns of a run may read nothing; the measurement says how much.
- **The planner's tool list never changes within a run.** Anthropic renders `tools` → `system` → `messages`, and a change to the tool definitions invalidates all three. Today two requests drop the tools: the turn past the budget (`bind_tools(...) if spent < budget else model`) and `emit` (`with_structured_output`, no tools). Both send the same definitions instead and stop their use with `tool_choice: "none"`, which invalidates only the messages cache, so tools and system are still read. Whether the history is read too on those turns, and whether `emit`'s varying `output_config.format` breaks it, the measurement says.
- **The other nodes are measured, not changed**: whether DeepSeek on `parasail` and gpt-oss on `cerebras` already cache shows in `tokens.cached`. They drop tools the same way (logger: reads past the budget, `ask_user` past `ASK_BUDGET`, `emit`; onboarding: tools past the budget, back after each answer; entrance: per turn by state), which breaks an automatic prefix cache as well. One tool cannot be switched off portably with `tool_choice`, and taking it off the table is how the logger's question budget holds (`logger.py`, `turn`), so changing that is a separate ticket, decided with the user once the numbers show a host caches and it pays: the planner is over 95% of the spend (ADR-0011).

| Node | Model / host | Today |
|---|---|---|
| Planner | Haiku 4.5 / `anthropic` | no cache: Anthropic caches only on a breakpoint |
| Logger, Onboarding | deepseek-v4-flash / `parasail` | unknown, automatic if the host does it |
| Entrance | gpt-oss-120b / `cerebras` | unknown, automatic if the host does it |

**Spends credits.** The measurement below is estimated first and runs only on the user's go (CLAUDE.md).

## Acceptance criteria

- [ ] A run record carries `tokens.cached` (unit test on a scripted reply with `cache_read`).
- [ ] The planner's request to an Anthropic model carries the breakpoint, and to any other model does not (unit tests, no model).
- [ ] In a scripted planner run that spends its budget and emits, every request carries the same tool definitions, and each request's messages start with the previous request's (unit test, no model).
- [ ] One `trainer eval --suite plan --only no-equipment --repetitions 1` before and after: $ a mesocycle and `tokens.cached`, the `emit` call's included, written as a row in ADR-0011.
- [ ] Full test suite and mypy green.
