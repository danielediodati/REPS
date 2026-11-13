# Vector stores for a small embedded RAG index

*Researched 2026-11-06. Not committed.* Scale: 2k-10k chunks, 1024-dim bge-m3 dense (Ollama), optional bge-m3 sparse later, one user, Windows 11, everything under `~/.reps/`.

## Summary table

| | Chroma | Qdrant (local `path=`) | LanceDB | Milvus Lite | sqlite-vec |
|---|---|---|---|---|---|
| Licence | Apache-2.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 | MIT / Apache-2.0 |
| Embedded dir on disk | yes | yes (client-only mode) | yes | yes, but not on Windows via pymilvus | yes (SQLite ext.) |
| Windows | yes | yes | yes (win_amd64 wheel) | **no official path** (see below) | yes |
| Dense | yes | yes (brute force) | yes (ANN index optional) | yes | yes (brute force) |
| Sparse vectors | Cloud only | **yes** | not documented | yes | no |
| BM25 / full text | substring/regex only locally | text index with scoring (local) | native FTS index | BM25 | use SQLite FTS5 |
| RRF hybrid | Cloud only ("local in a future release") | **yes** (`RrfQuery`, DBSF) | **yes** (default reranker) | yes (`RRFRanker`) | manual |
| Filtering | yes | payload filters | SQL-like, prefilter default | yes | SQL |
| LangChain pkg | `langchain-chroma` 1.1.0 (2025-12-12, MIT) | `langchain-qdrant` 1.1.0 (2025-10-22, MIT) | `langchain-lancedb` 0.1.0 (2026-08-01, MIT) | `langchain-milvus` 0.4.0 (2026-07-17, MIT) | `langchain-community` only |
| GitHub stars (2026-11-06) | ~29.6k | ~1.4k (client) | ~11.9k | ~465 | ~8.2k (last push 2026-05) |

## Per candidate

### Chroma
- `chromadb` 1.5.9; Apache-2.0. Embedded persistent client, but a heavy dependency tree: onnxruntime, tokenizers, kubernetes, opentelemetry (3 packages), grpcio, bcrypt, uvicorn, typer, rich... ([PyPI](https://pypi.org/project/chromadb/)).
- Hybrid is the blocker: the Search API (dense, sparse, hybrid, RRF) "is available for Chroma Cloud. Support for local Chroma deployments will be available in a future release" ([docs](https://docs.trychroma.com/cloud/search-api/overview.md)). Local full-text is only `where_document` `$contains`/`$regex` ([docs](https://docs.trychroma.com/docs/querying-collections/full-text-search)).
- `langchain-chroma` 1.1.0 is 11 months old (PyPI) but requires `chromadb>=1.3.5`, so it tracks.
- Most adopted; weakest hybrid story for an embedded user.

### Qdrant, local mode (`QdrantClient(path=...)`)
- `qdrant-client` 1.20.0; Apache-2.0. Core deps: grpcio, httpx[http2], protobuf, pydantic, portalocker, numpy, urllib3 ([PyPI](https://pypi.org/project/qdrant-client/)). Medium weight, no ONNX unless the `fastembed` extra.
- Local mode persists to a folder ([README](https://github.com/qdrant/qdrant-client), [LangChain docs](https://docs.langchain.com/oss/python/integrations/vectorstores/qdrant)).
- Source of `qdrant_local.py` ([GitHub](https://github.com/qdrant/qdrant-client/blob/master/qdrant_client/local/qdrant_local.py)): accepts `sparse_vectors_config`, `query_points` with nested `prefetch`, `RrfQuery`/`FusionQuery`. Search is **exact brute force**, HNSW params ignored, exclusive folder lock, a `UserWarning` above 20,000 points ("small-scale data, demos, and tests"). Snapshots/sharding raise `NotImplementedError`. Our 10k ceiling is under the warning threshold, and brute force over 10k x 1024 floats is milliseconds.
- RRF with configurable `k` and weights, DBSF, sparse+dense prefetch documented for the server ([docs](https://qdrant.tech/documentation/concepts/hybrid-queries/)); the local file confirms the query types are accepted, but I did not read the scoring code, so test hybrid in local mode before relying on it.
- `langchain-qdrant` 1.1.0 supports `RetrievalMode.DENSE/SPARSE/HYBRID` and a `sparse_embedding` param taking any `SparseEmbeddings` implementation (bge-m3 sparse would need a small adapter; `FastEmbedSparse` ships BM25) ([LangChain docs](https://docs.langchain.com/oss/python/integrations/vectorstores/qdrant)). Release is 12 months old; client is actively pushed (2026-11-03).
- Path off local mode to a server (Docker) is the same API: good portfolio story.

### LanceDB
- `lancedb` 0.41.0; Apache-2.0; Python >=3.10. Deps: pyarrow>=16, numpy, pydantic, deprecation, tqdm, lance-namespace ([PyPI](https://pypi.org/project/lancedb/)). Rust core in an abi3 wheel; the 0.24.0 win_amd64 wheel was 35 MB (I could not read the current wheel size). pyarrow adds weight.
- Embedded in-process, data is Lance columnar files in a directory; versioned tables. Rebuild is trivial (drop table, re-add).
- Hybrid: vector + full-text search, merged with RRF by default, filters apply to both, prefilter default ([docs](https://docs.lancedb.com/search/hybrid-search)). FTS is BM25 text, not bge-m3 sparse; sparse vectors not documented, so later bge-m3 sparse would not fit natively.
- `langchain-lancedb` 0.1.0 (2026-08-01), young, pre-1.0, MIT. 11.9k stars.

### Milvus Lite
- `milvus-lite` 3.2.2 (2026-10-13); Apache-2.0; pure-Python wheel (`py3-none-any`, 277 KB) depending on `faiss-cpu`, `pyarrow`, `numpy`, `grpcio` ([PyPI](https://pypi.org/project/milvus-lite/)). 3.x is a ground-up pure-Python rewrite; old `.db` files are incompatible ([README](https://github.com/milvus-io/milvus-lite)).
- Has sparse vectors, BM25, `RRFRanker`/`WeightedRanker`. Intended for "local development and small-scale workloads"; one process per data dir.
- **Windows:** the README lists Windows "where the Python dependencies are available" with CI on Python 3.10 only. But `pymilvus` 3.0.2 declares `milvus-lite` only for `sys_platform != "win32"` and `langchain-milvus` 0.4.0 likewise ([pymilvus PyPI](https://pypi.org/project/pymilvus/), [langchain-milvus PyPI](https://pypi.org/project/langchain-milvus/)). So the supported toolchain does not install it on Windows; and Python 3.12 is not in the Windows CI. Verdict: not viable here without fighting the dependency markers.
- 465 stars, young rewrite.

### sqlite-vec (baseline)
- 0.1.9; MIT/Apache-2.0; ext. for SQLite, brute-force KNN, no sparse, no RRF (combine with FTS5 by hand). Last push 2026-05-18, version still 0.x ([PyPI](https://pypi.org/project/sqlite-vec/), [GitHub](https://github.com/asg017/sqlite-vec)). Zero new infrastructure since the app already uses SQLite; no LangChain store of its own (only a `langchain-community` one, not verified here).

### Others (not verified in depth)
- FAISS: library, no metadata filtering or persistence story beyond pickle; not considered.
- pgvector / Weaviate embedded / Vespa: need a server or are heavier than the use case.

## Recommendation

**Qdrant in local mode (`QdrantClient(path="~/.reps/qdrant")`) with `langchain-qdrant`.**
- It is the only embedded option that natively covers dense + sparse + RRF in one store with a maintained LangChain integration and a working Windows install, so bge-m3 sparse later needs no re-platforming.
- Brute-force is a non-issue at 2k-10k points; stay under the 20k warning.
- Rebuild is `rmtree` the folder and re-ingest; the same code moves to a Docker server if ever needed.
- Costs: sparse bge-m3 needs a custom `SparseEmbeddings` adapter; hybrid scoring in local mode should be smoke-tested; `langchain-qdrant` hasn't released in a year.

Runner-up: **LanceDB** if dense + BM25 text hybrid is enough (best-documented RRF, bigger community, but heavier wheel and a 0.1.0 LangChain package). Skip Chroma (hybrid not local) and Milvus Lite (not on Windows via pymilvus). If dense-only is the near-term need, sqlite-vec is the zero-dependency fallback.

Unverified: current wheel sizes for qdrant-client/chromadb/lancedb 0.41; whether local Qdrant's RRF scoring behaves identically to the server.
