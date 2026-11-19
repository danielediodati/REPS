# Retrieval runs on the laptop

Milestone 16 gives the entrance a retrieval tool over a corpus of openly licensed texts. Its passages are embedded and searched. ADR-0015 left OpenRouter as the only provider, and OpenRouter serves `baai/bge-m3` too.

## Decision

1. **Embeddings run on the owner's Ollama**, the ordinary one on its default port, on the CPU. So does the small chat model that puts each question into English before the search (amended 2026-11-10, ticket 16.1.7: the owner chose $0 over a paid call). The other chat models stay on OpenRouter.
2. **The index lives in a Qdrant server**, the native binary, started by the owner outside the bot, with its storage in `~/.reps/qdrant/`.
3. **The bot checks both at start** and reports what is missing as a state naming the fix: start Ollama, pull the model, start Qdrant, build the corpus.
4. **A server down mid-session leaves the retrieval tool answering that the sources are unavailable**. The entrance says it cannot answer from sources, and the conversation goes on.

## Rejected

- **Embeddings on OpenRouter**: same weights and a few cents, but the challengers to measure (`qwen3-embedding`, `snowflake-arctic-embed2`) exist only on Ollama.
- **An embedded store** (a library writing a folder): no second process, but not the shape of a deployed RAG.
- **Hybrid search, other chunk sizes, a local reranker** (amended 2026-11-11, ticket 16.1.7): measured on the answer set against `snowflake-arctic-embed2` dense with the question also in English, which is served at 1200 characters, top 5. Hybrid with RRF +0 rows of 61, 500 characters -6, 2000 characters +0, `bge-reranker-v2-m3` over the top 20 -9 and 17 s at p95.
- **Chroma**: dense search only outside its cloud. **Milvus**: needs Docker, which this machine lacks. **LanceDB**: no open source server.

## Consequences

- Two processes besides the bot, both the owner's to start.
- The home is still the one directory to copy. The vectors are rebuilt from the committed chunks at $0.
- Hybrid search (dense, sparse, RRF) stays possible in the same store; measured once, it gained nothing.
- Recall@5 stops at 42 of 61 covered rows, the passage being in the top 20 for 54: the answers' bars, not retrieval's, decide whether the replies hold.
- More passages to the entrance (ticket 16.1.9, luna, one rep): top 10 and top 15 raised covered answered from 84% to 90% and 97%, but faithful fell from 81% to 56% and 60% and verbatim-and-labelled from 88% to 69% and 74%. Top 5 stays.
- **Amends ADR-0015**: Ollama returns, for embeddings and the question's translation. Milestone 17's ADR extends it to chat nodes.
