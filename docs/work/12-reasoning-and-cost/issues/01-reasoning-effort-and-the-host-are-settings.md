# Reasoning effort and the host are settings

Status: ready-for-agent

Blocked by: nothing.

Today the effort is fixed: `models.REASONING = "low"` on Ollama, nothing on Groq or OpenRouter, so Qwen on OpenRouter reasons as long as it likes. And `:nitro` picks a host per request, so two runs of one configuration may be two different machines.

## What to build

- **Effort per node**: `PLANNER_REASONING`, `LOGGER_REASONING`, `ENTRANCE_REASONING` (`none`, `low`, `medium`, `high`; empty is the provider's default). On OpenRouter it is the `reasoning` request parameter.
- **Sent only where the model takes it.** Under `provider.require_parameters` a parameter the model does not support makes it unroutable. Whether it does is read from OpenRouter's model listing (`supported_parameters`), never from a list here; asked of a model that has none, `ready` says so before the run, naming the variable.
- **The host is a setting**: `OPENROUTER_PROVIDER` pins one (`provider.order` with fallbacks off). Empty keeps OpenRouter's routing.
- **The run record carries both**, beside the model name: which effort was asked and which host answered (the response names it).

## References

- ADR-0006 (a model per node), ADR-0010
- `src/trainer/coach/models.py`, `src/trainer/coach/record.py`
- `docs/research/paid-llm-provider.md`

## Acceptance criteria

- [ ] `LOGGER_REASONING=low` reaches the request; a test reads it off the built model.
- [ ] A model without the setting is refused by `ready` with the variable named, against a stubbed listing.
- [ ] One real request with `OPENROUTER_PROVIDER` set: the record names that host.
- [ ] Full test suite and mypy green.
