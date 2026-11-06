# Italian questions, English texts

Type: research
Status: resolved

## Question

The owner asks in Italian and the sources are mostly English. Which open embedding models retrieve well across that gap, and which alternatives exist (translating the question, translating the corpus)? For each model: licence, size, dimensions, published multilingual or cross-lingual retrieval scores (MTEB, MIRACL or similar) with Italian where reported, whether Ollama serves it, and whether OpenRouter offers it or an equivalent.

## Answer

Start with `bge-m3` (MIT, 568M, 1024 dimensions, 8K context): Italian questions over English Wikipedia score Recall@100 76.0 on MKQA, against 45.2 for BM25. It is served both by Ollama and by OpenRouter's embeddings API (`baai/bge-m3`, $0.01 per million tokens), so ADR-0015 holds either way. Challengers to measure on the corpus: `qwen3-embedding:0.6b` and `snowflake-arctic-embed2` (Ollama only). Translating the query is the fallback if Italian Recall@5 lags English; translating the corpus is out, since the cited text would stop being the licensed source. A reranker (`bge-reranker-v2-m3`) runs locally only. Public scores only shortlist. Details in `research/answer-embeddings.md` on branch `research/answer-embeddings`.
