# The retrieval ladder

Type: grilling
Status: resolved
Blocked by: 08

## Question

The first version is the simplest retrieval: `bge-m3` dense search, top 5, no rewriting ([Italian questions, English texts](02-italian-questions-english-texts.md), [Where retrieval runs](03-where-retrieval-runs.md)). If it misses a bar, which techniques are climbed, in what order, and when does climbing stop: hybrid search, a reranker, query translation, chunk size? What does each rung cost in latency on the laptop, and which metric must it raise to stay?

## Answer

Grilled 2026-11-07.

- **Rung zero, always run**: `bge-m3` against `qwen3-embedding:0.6b` and `snowflake-arctic-embed2`, at $0. Highest Recall@5 wins, MRR breaks a tie; the techniques are tried on the winner.
- **When to climb**: only while a retrieval bar misses ([the bars](08-the-bars.md)). Stop at the first configuration that clears them all. If the rungs run out, stop and the owner decides with the numbers; no rung is added unasked.

| Order | Rung | When |
|---|---|---|
| 1 | Query translation | only if the Italian-on-English rows lag far behind; a paid call, asked for first |
| 2 | Hybrid search, sparse and dense fused in Qdrant | |
| 3 | Chunk size | |
| 4 | Local reranker (`bge-reranker-v2-m3`) | last, the slowest |

- **A rung stays** when it raises the missing metric by at least 3 of 60 rows (5 points) and drops no other bar. The paired difference, row by row, is reported with its 95% interval.
- **Latency ceiling**: retrieval within 2 s at p95 on the laptop. A rung over it does not stay, whatever it raises.
- **What reruns**: each rung is measured on retrieval alone, at $0 (query translation aside). Answers and the judge run once, on the final configuration, asked for first with an estimate.
