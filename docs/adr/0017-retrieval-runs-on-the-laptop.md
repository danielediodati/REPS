# Retrieval runs on the laptop

Milestone 16 gives the entrance a retrieval tool over a corpus of openly licensed texts. Its passages are embedded and searched. ADR-0015 left OpenRouter as the only provider, and OpenRouter serves `baai/bge-m3` too.

## Decision

1. **Embeddings run on the owner's Ollama**, the ordinary one on its default port, on the CPU. Chat models stay on OpenRouter.
2. **The index lives in a Qdrant server**, the native binary, started by the owner outside the bot, with its storage in `~/.reps/qdrant/`.
3. **The bot checks both at start** and reports what is missing as a state naming the fix: start Ollama, pull the model, start Qdrant, build the corpus.
4. **A server down mid-session leaves the retrieval tool answering that the sources are unavailable**. The entrance says it cannot answer from sources, and the conversation goes on.

## Rejected

- **Embeddings on OpenRouter**: same weights and a few cents, but the challengers to measure (`qwen3-embedding`, `snowflake-arctic-embed2`) exist only on Ollama.
- **An embedded store** (a library writing a folder): no second process, but not the shape of a deployed RAG.
- **Chroma**: dense search only outside its cloud. **Milvus**: needs Docker, which this machine lacks. **LanceDB**: no open source server.

## Consequences

- Two processes besides the bot, both the owner's to start.
- The home is still the one directory to copy. The vectors are rebuilt from the committed chunks at $0.
- Hybrid search (dense, sparse, RRF) stays possible in the same store, if a metric asks for it.
- **Amends ADR-0015**: Ollama returns, for embeddings only. Milestone 17's ADR extends it to chat nodes.
