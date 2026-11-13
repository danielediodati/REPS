# Embeddings for Italian questions over English texts

Ticket: `docs/work/answer-from-sources/issues/02-italian-questions-english-texts.md`. Gathered 2026-11-06. No paid credits spent (the OpenRouter model lists are public, unauthenticated).

## Answer

- **Default: `bge-m3`.** MIT, 567M params, 1024 dims, 8K context. Italian-query to English-passage retrieval (MKQA, `it`) Recall@100 76.0 dense. Served by Ollama locally (`bge-m3`) and by OpenRouter (`baai/bge-m3`, $0.01/M tokens): one model, both hosts.
- **Contenders to measure against it:** `qwen3-embedding:0.6b` (Apache-2.0, 32K, strongest MTEB-multilingual retrieval of the small open models, but needs an English instruction on the query) and `snowflake-arctic-embed2` (Apache-2.0, its own card reports CLEF results that include Italian, Ollama only, not on OpenRouter).
- **No translation needed first.** Public numbers show multilingual dense models lose little across Italian to English (below). Translating the query is the cheap fallback if the owner's eval shows a gap; translating the corpus is not worth it.
- **Reranker, if the ladder reaches it:** `bge-reranker-v2-m3` (Apache-2.0, 0.6B) run locally through a Python library, or `qwen/qwen3-reranker-8b` / `cohere/rerank-*` listed on OpenRouter. Ollama has no rerank endpoint.
- Public scores are not on the owner's corpus. They only shortlist; the Recall@5 / MRR eval in the map decides.

## The gap itself

MKQA (Longpre et al.) is the closest public benchmark: queries in 25 languages, answers found in English Wikipedia, so Italian question to English text. Recall@100 for `it`, from Table 2 of the M3-Embedding paper (arXiv 2402.03216):

| Model | it | 25-language avg |
|---|---|---|
| BM25 | 45.2 | 39.9 |
| mDPR | 66.0 | 60.6 |
| mContriever | 72.3 | 67.9 |
| multilingual-e5-large | 76.8 | 70.9 |
| E5-mistral-7b | 77.1 | 70.1 |
| OpenAI text-embedding-3 | 73.6 | 69.5 |
| **bge-m3 dense** | 76.0 | 75.1 |
| bge-m3 dense+sparse | 76.3 | 75.3 |
| bge-m3 all (dense, sparse, multi-vector) | 76.5 | 75.5 |

- Italian is an easy language here: bge-m3 and e5-large are within 1 point on it. The 25-language average, not Italian, is where bge-m3 pulls ahead (low-resource languages).
- Lexical BM25 collapses across languages (45.2), so keyword-only retrieval cannot bridge Italian to English.
- Recall@100 is a loose bar ("found somewhere in 100"), not Recall@5. Treat as a sanity floor.
- MIRACL (monolingual, per language) does not include Italian (its languages: ar bn en es fa fi fr hi id ja ko ru sw te th zh de yo, plus es/fr/de/yo variants). Its numbers say nothing about Italian directly.

## Candidates

"Ollama" = official library tag. "OpenRouter" = listed by `GET https://openrouter.ai/api/v1/embeddings/models` on 2026-11-06 (40 models; endpoint `POST /api/v1/embeddings`).

| Model | Licence | Params | Dims | Context | Ollama | OpenRouter |
|---|---|---|---|---|---|---|
| bge-m3 | MIT | 568M | 1024 | 8192 | `bge-m3` 1.2 GB | `baai/bge-m3`, $0.01/M |
| multilingual-e5-large | MIT | 560M | 1024 | 512 | no | `intfloat/multilingual-e5-large`, $0.01/M |
| multilingual-e5-base | MIT | 278M | 768 | 512 | no | no |
| multilingual-e5-small | MIT | 118M | 384 | 512 | no | no |
| snowflake-arctic-embed-l-v2.0 | Apache-2.0 | 568M (303M non-emb) | 1024 (MRL to 256) | 8192 | `snowflake-arctic-embed2` 1.2 GB | no |
| nomic-embed-text-v2-moe | Apache-2.0 | 475M (305M active) | 768 (MRL to 256) | 512 | `nomic-embed-text-v2-moe` 958 MB | no |
| granite-embedding-278m-multilingual | Apache-2.0 | 278M | not read | 512 | `granite-embedding:278m` 563 MB | no |
| Qwen3-Embedding-0.6B | Apache-2.0 | 596M | up to 1024 (MRL 32-1024) | 32K | `qwen3-embedding:0.6b` 639 MB | no (4b: `qwen/qwen3-embedding-4b` $0.02/M; 8b: `qwen/qwen3-embedding-8b` $0.01/M) |
| embeddinggemma-300m | Gemma terms (not OSI) | 303M | 768 (MRL to 128) | 2048 | `embeddinggemma` | no |
| embeddinggemma-2 (new) | not checked | 270M text backbone, 740M full multimodal | 768 | 8192 | `embeddinggemma-2` 270m/440m/570m/740m | no |
| pplx-embed-v1-0.6b | MIT | 596M | not read | 32K | no | `perplexity/pplx-embed-v1-0.6b`, $0.004/M |

Scores as published. The cards report different benchmarks, so they do not rank the models against each other.

| Model | Published retrieval score | Italian |
|---|---|---|
| bge-m3 | MKQA it 76.0 (above); MIRACL avg nDCG@10 dense 69.2 (paper Table 14) | MKQA yes; not in MIRACL |
| multilingual-e5-large | MKQA it 76.8; Mr.TyDi MRR@10 avg 70.5 (card); needs `query: ` / `passage: ` prefixes | MKQA yes; card does not name Italian |
| snowflake-arctic-l-v2.0 | nDCG@10 BEIR 55.6, MIRACL 55.8, CLEF focused 52.9, CLEF full 54.3. Same card table, bge-m3: 48.8 / 56.8 / 40.8 / 41.3; me5-base: 51.4 / 54.0 / 43.0 / 34.6 | Ollama page says its evaluation covers en, fr, es, it, de |
| nomic-embed-text-v2-moe | BEIR 52.86, MIRACL 65.80 (card) | not itemised |
| granite-278m-multilingual | card lists MTEB tasks; no MIRACL read | Italian listed as supported |
| Qwen3-Embedding-0.6B | MTEB multilingual mean 64.33, retrieval 64.64 | 100+ languages, not itemised |
| embeddinggemma-300m | MTEB multilingual v2 mean 61.15 (768d) | 100+ languages, not itemised |
| Qwen3-Embedding-8B | no. 1 on the MTEB multilingual leaderboard at 70.58 (5 Jun 2025, per the Ollama page) | not itemised |

Notes:
- **Arctic-embed-l-v2 is the strongest cross-lingual retriever of the 568M class on its own table** (CLEF 52.9 / 54.3 against bge-m3 40.8 / 41.3), and CLEF is built on European languages. The claim is first-party; verify on the owner's corpus.
- **Short context is no problem for chunks.** A 512-token model (e5, nomic, granite) is fine for passages of a few hundred tokens.
- **Prefixes and instructions are part of the config.** e5 needs `query: ` / `passage: `. Arctic needs `query: ` on queries only. Qwen3 wants a one-line English task instruction on queries (card: +1 to 5%). bge-m3 needs none. Getting these wrong silently costs recall.
- **Newer models (autumn 2026) exist**: embeddinggemma-2, Cohere Embed 5, Gemini Embedding 2, NVIDIA Nemotron 3.5 Embed, Voyage 4. I found no Italian-specific figure for any in the pages read. Cohere, Gemini and Voyage are closed weights. Nemotron 3.5 Embed 1B/8B are free on OpenRouter (`nvidia/nemotron-3.5-embed-1b:free`, multilingual, 32K) with a free tier's rate limits and no Ollama tag seen. Not shortlisted for lack of evidence.
- `bge-m3` is the only candidate on both Ollama and OpenRouter with the same weights.

## Hosting fit (ADR-0015)

- OpenRouter has an embeddings API: `POST /api/v1/embeddings` with `model` and `input` (string or array), listing at `/api/v1/embeddings/models`. Open models cost $0.004-0.02 per million tokens: a corpus of a few million tokens costs cents.
- Ollama serves embeddings via `/api/embed` (L2-normalised vectors). ADR-0015 removed Ollama from the LLM path; embeddings through it would reintroduce a local dependency. A 568M model on the 8-core CPU is workable for a small corpus. OpenRouter keeps ADR-0015 intact; Ollama would need an amendment. That is for the grilling ticket, not here.
- Corpus and query must use the same model; pin the model id in the fixture next to the vectors.

## Alternatives to a cross-lingual model

| Approach | Cost | Verdict |
|---|---|---|
| Multilingual embedding, Italian query as is | none | Start here. Public cross-lingual numbers for Italian are close to the same-language ceiling. |
| Translate the query to English (one cheap LLM call per question, or folded into the query-rewrite step the map already lists) | one small call per question, through OpenRouter | Fallback if measured Recall@5 is low on Italian but fine on the same questions in English. Risk: drift on exercise names. |
| Translate the corpus to Italian | LLM cost on every document, repeated per refresh; the cited text is no longer the licensed source | Reject. |
| Hybrid with BM25 | none | Does not help across languages (BM25 it 45.2 on MKQA); the map says add only if it raises a metric. |

Open point for the spec: the passage cited to an Italian-speaking owner is English. Quote or paraphrase in Italian is a product choice, not a retrieval one.

## Rerankers

| Model | Licence | Params | Where |
|---|---|---|---|
| bge-reranker-v2-m3 | Apache-2.0 | 0.6B (base bge-m3), multilingual | Hugging Face; no Ollama rerank endpoint (Ollama's embeddings docs list `/api/embed` only) |
| Qwen3-Reranker-0.6B | Apache-2.0 | 0.6B, 32K | Hugging Face; MTEB-R 65.80, CMTEB-R 71.31, MMTEB-R 66.36 |
| `qwen/qwen3-reranker-8b` | Apache-2.0 | 8B | OpenRouter listing |
| `cohere/rerank-4-pro`, `rerank-5-fast`, `rerank-5-pro` | closed | n/a | OpenRouter listing |
| `nvidia/nemotron-3.5-rerank-8b:free` | n/a | 8B | OpenRouter listing (free tier) |

OpenRouter lists rerankers among its models, but I found no public docs page for a rerank endpoint (`/docs/api-reference/rerank` and `GET /api/v1/rerank` both returned 404). How to call them was not verified; check before relying on it.

## Sources

- bge-m3 card: https://huggingface.co/BAAI/bge-m3 ; paper (MKQA Table 2, MIRACL Table 14): https://arxiv.org/abs/2402.03216
- multilingual-e5-large: https://huggingface.co/intfloat/multilingual-e5-large
- Arctic-embed-l-v2.0: https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0
- nomic-embed-text-v2-moe: https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe
- granite-embedding-278m-multilingual: https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual
- Qwen3-Embedding-0.6B: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B ; Qwen3-Reranker-0.6B: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
- EmbeddingGemma: https://huggingface.co/google/embeddinggemma-300m
- bge-reranker-v2-m3: https://huggingface.co/BAAI/bge-reranker-v2-m3
- Parameter counts and licences: Hugging Face model API, `https://huggingface.co/api/models/<id>`
- Ollama: https://ollama.com/library/bge-m3 , /qwen3-embedding , /snowflake-arctic-embed2 , /granite-embedding , /nomic-embed-text-v2-moe , /embeddinggemma-2 ; https://docs.ollama.com/capabilities/embeddings
- OpenRouter: https://openrouter.ai/docs/api-reference/embeddings ; https://openrouter.ai/api/v1/embeddings/models

## Not verified

- Per-model Italian scores for Qwen3-Embedding, EmbeddingGemma, nomic and granite (cards report aggregates).
- bge-m3 and reranker cards show charts only; bge-m3 numbers above come from the paper.
- Dimensions of granite-278m and pplx-embed; licence of embeddinggemma-2.
- Ollama quantisation per tag (pages do not say); it may shift scores slightly.
