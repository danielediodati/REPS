# OpenRouter is the only provider

Since ADR-0011 every node runs a measured choice on OpenRouter. Groq and Ollama stayed selectable through `LLM_BACKEND` and `ENTRANCE_BACKEND`, but nothing ran on them: no node had a measured configuration there, and the local model held neither the planner's invariants (ADR-0004) nor the entrance's latency (ADR-0006).

## Decision

1. **OpenRouter is the only provider.** `LLM_BACKEND`, `ENTRANCE_BACKEND` and every `GROQ_*` and `OLLAMA_*` setting are removed, with the `groq`, `ollama` and their LangChain packages.
2. **Each node's model is its measured choice**, or its own `<NODE>_MODEL`, or `OPENROUTER_MODEL` for all of them (ADR-0011).
3. **A model on another provider is reached through OpenRouter**, which routes to Groq and others as hosts.

## Consequences

- **Gone with Ollama**: the context-length check, the memory sampler in the eval runner, and the local entrance default (`llama3.1`).
- **Gone with Groq**: `GROQ_MAX_TOKENS` and the free tier's daily-quota state. A spent quota is OpenRouter's 402.
- **Nothing runs offline.** Checking the model before a run still needs the network.
- **Amends ADR-0004 item 8, ADR-0006 item 3 and ADR-0011 item 3.**
