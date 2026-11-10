# 07: The embedders compared and the ladder

Status: ready-for-agent

**What to build:** retrieval measured and, if needed, improved. Rung zero always runs: `bge-m3`, `qwen3-embedding:0.6b` and `snowflake-arctic-embed2` compared in retrieval-only mode at $0. Then rungs are climbed only while a retrieval bar misses. If nothing misses, the ticket closes saying so. Decided in [the retrieval ladder](../../answer-from-sources/issues/09-the-retrieval-ladder.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 06.

**Constraint from 06:** `trainer eval --suite answer --retrieval-only` is the measurement, at $0 and with no chat model: it searches each covered row's question as written, and prints Recall@5 with Wilson's 95% interval (`eval_runner.interval`), MRR and p95 search time, with the Italian-on-English rows apart. Rung zero on `bge-m3`, dense, top 5 read Recall@5 20 of 60 (33%, [23%, 46%]), MRR 0.20, p95 0.07 s; Italian-on-English 5 of 24. The paired difference between two rungs is not computed yet.

`CORPUS_EMBEDDER` picks the Ollama model; each embedder's build is its own Qdrant collection, kept beside the others, so the three can be built once and compared. `Search` sends the question as is: an embedder that wants a query instruction (`qwen3-embedding`) needs it added here.

- [ ] The three embedders compared; highest Recall@5 wins, MRR breaks a tie; the corpus is built with the winner
- [ ] Rungs in order, only while a bar misses: query translation (only if the Italian-on-English rows lag far behind; paid, asked for first), hybrid search, chunk size, local reranker
- [ ] A rung stays when it raises the missing metric by at least 3 of 60 rows, drops no other bar and keeps retrieval within 2 s at p95 on the laptop; the paired difference is reported with its interval
- [ ] Stop at the first configuration clearing every retrieval bar; if the rungs run out, stop and report for the owner to decide; no rung added unasked
- [ ] The numbers of every rung tried are recorded
