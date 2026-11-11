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

## The ladder's numbers

Retrieval-only, top 5, one rep, against the fixture in `TRAINER_DB`. Rungs 0-2 were first read on set version 1; set version 2 labels every answering passage (`dba81a1`), and every rung was read again on it, paired against the kept configuration.

| Rung | Set 1 Recall@5 | Set 2 Recall@5 | Set 2 paired against kept | p95 | Verdict |
|---|---|---|---|---|---|
| 0 - `bge-m3` | 20 of 60 | - | - | 0.08 s | |
| 0 - `qwen3-embedding:0.6b` | 18 of 60 | - | - | 0.17 s | |
| 0 - `snowflake-arctic-embed2` | 23 of 60 | - | - | 0.08 s | wins |
| 1 - question also in English, `gemma4:e2b` | 30 of 60 | 42 of 61 (68% [56%, 79%]), MRR 0.51 | kept | 1.14 s | stays |
| 2 - hybrid search, RRF | 28 of 60 | 42 of 61 | 3 gained, 3 lost, +0 [-9, +9] | 0.94 s | out |
| 3 - chunks of 500 chars | 28 of 60 | 36 of 61 | 0 gained, 6 lost, -10 [-18, -2] | 0.99 s | out |
| 3 - chunks of 2000 chars | 31 of 60 | 42 of 61 | 2 gained, 2 lost, +0 [-7, +7] | 0.91 s | out |
| 4 - `bge-reranker-v2-m3` over the top 20, CPU | - | 33 of 61, MRR 0.37 | 4 gained, 13 lost, -15 [-27, -2] | 17.1 s | out, over the ceiling too |

The rungs ran out at 42 of 61, below the 49 the bar needs: the owner decides. On set 2 the labelled passage is in the top 20 for 54 of 60 covered rows.
