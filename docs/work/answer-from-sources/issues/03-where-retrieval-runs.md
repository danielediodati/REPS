# Where retrieval runs

Type: grilling
Status: resolved
Blocked by: 02

## Question

Do the embeddings run on the laptop, at $0 like the student of milestone 17, or hosted, and where does the index live: beside the SQLite database (e.g. sqlite-vec) or in a store of its own? What does the choice cost in a call's latency, in setup on a new machine (the home directory), and in ADR-0015's single provider?

## Answer

Grilled 2026-11-07. Recorded in [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md).

| Question | Decision |
|---|---|
| Embeddings | Local, on the owner's ordinary Ollama (default port, CPU), `bge-m3` first. The challengers are Ollama-only, so the eval needs it anyway. |
| Index | A Qdrant server, native Windows binary, started by the owner; storage in `~/.reps/qdrant/`. Dense search first; Qdrant also holds sparse vectors and RRF for the ladder's hybrid rung. |
| ADR-0015 | Amended by ADR-0017: Ollama returns for embeddings only. Milestone 17's ADR extends it to chat nodes. |
| New machine | `trainer corpus build` embeds the committed chunks at $0. The bot starts anyway and names what is missing as a state. |
| Down mid-session | The retrieval tool answers that the sources are unavailable; the entrance says it cannot answer from sources; the conversation goes on. |
| Latency | Estimated, not measured: ~0.1-0.3 s to embed a question on CPU, milliseconds to search a few thousand points. |

The store comparison (Qdrant, Chroma, LanceDB, Milvus, sqlite-vec) is in `research/vector-stores.md` on branch `research/vector-stores`.
