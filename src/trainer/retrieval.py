"""Search over the corpus: its chunks embedded on Ollama into Qdrant (ADR-0017), and the states that stop it."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import httpx2

from trainer import corpus
from trainer.corpus import Chunk
from trainer.engine import home

TOP = 5
"""How many passages a search returns."""

EMBEDDER_ENV = "CORPUS_EMBEDDER"
EMBEDDER = "bge-m3"
"""The embedding model on Ollama, unless `CORPUS_EMBEDDER` names another."""

TRANSLATOR_ENV = "CORPUS_TRANSLATOR"
"""The chat model on Ollama that also puts each question into English; unset, none does."""

HYBRID_ENV = "CORPUS_HYBRID"
"""Set to 1, the corpus is built and searched by its words beside its vectors."""

OLLAMA_HOST_ENV = "OLLAMA_HOST"
OLLAMA_PORT = 11434
OLLAMA_HOST = f"http://localhost:{OLLAMA_PORT}"
QDRANT_URL_ENV = "QDRANT_URL"
QDRANT_URL = "http://localhost:6333"

QUERY_INSTRUCTIONS = {
    "qwen3-embedding": "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:",
    "snowflake-arctic-embed2": "query: ",
}
"""What each embedder's model card puts before a question, by model name without its tag; passages go bare."""

STORAGE = "qdrant"
"""Qdrant's storage, inside the home."""

_BATCH = 32


class Unavailable(Exception):
    """Retrieval cannot run; the message names the fix."""


class OllamaDown(Unavailable):
    """Ollama does not answer."""


class ModelNotPulled(Unavailable):
    """Ollama answers but does not hold the embedding model."""


class QdrantDown(Unavailable):
    """Qdrant does not answer."""


class NotBuilt(Unavailable):
    """The index holds no complete build of the committed corpus at its version."""


@dataclass(frozen=True)
class Passage:
    """A chunk a search returned, with its similarity to the question."""

    chunk: Chunk
    score: float


class Embedder(Protocol):
    """Turns texts into vectors."""

    model: str
    where: str

    def ready(self) -> None:
        """Raise the state that stops embedding, if any."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order."""


class Translator(Protocol):
    """Puts a question into English."""

    model: str

    def ready(self) -> None:
        """Raise the state that stops translating, if any."""

    def english(self, question: str) -> str:
        """The question in English."""


class Store(Protocol):
    """Holds vectors in named collections and finds the nearest."""

    where: str

    def ready(self) -> None:
        """Raise the state that stops the store, if any."""

    def collections(self) -> list[str]:
        """Every collection's name."""

    def count(self, name: str) -> int:
        """How many points a collection holds."""

    def create(self, name: str, size: int, *, hybrid: bool = False) -> None:
        """An empty collection of vectors of `size` by cosine; with `hybrid`, words weighted by IDF beside them."""

    def drop(self, name: str) -> None:
        """Delete a collection."""

    def add(
        self,
        name: str,
        start: int,
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
        words: Sequence[Sparse] | None = None,
    ) -> None:
        """Store points numbered from `start`, with their words in a hybrid collection."""

    def nearest(
        self, name: str, vector: Sequence[float], top: int, words: Sparse | None = None
    ) -> list[tuple[dict[str, Any], float]]:
        """The `top` payloads nearest to `vector`, nearest first; with `words`, both rankings fused."""


Sparse = dict[int, float]
"""A text's words, each hashed to an index, with its weight."""

BM25_K1 = 1.2
BM25_B = 0.75
PREFETCH = 20
"""How many passages each ranking hands to the fusion in a hybrid search."""
RRF_K = 2
"""Reciprocal rank fusion's constant, Qdrant's default."""


def _index(word: str) -> int:
    return int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:4], "big")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def passage_words(text: str, average: float) -> Sparse:
    """A passage's words, each weighted by BM25's saturated term frequency; the IDF is the store's."""
    found = _words(text)
    counts: dict[int, int] = {}
    for word in found:
        counts[_index(word)] = counts.get(_index(word), 0) + 1
    norm = BM25_K1 * (1 - BM25_B + BM25_B * len(found) / average) if average else BM25_K1
    return {index: n * (BM25_K1 + 1) / (n + norm) for index, n in counts.items()}


def question_words(text: str) -> Sparse:
    """A question's words, each once."""
    return {_index(word): 1.0 for word in _words(text)}


_PREFIX = "reps-corpus-"
_HYBRID = "-hybrid"


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "_", model)


class Search:
    """The corpus as one interface: built into an index, searched, and its state read."""

    def __init__(
        self,
        embedder: Embedder,
        store: Store,
        version: int,
        chunks: Sequence[Chunk],
        *,
        translator: Translator | None = None,
        hybrid: bool = False,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.version = version
        self.chunks = chunks
        self.translator = translator
        self.hybrid = hybrid

    @property
    def described(self) -> str:
        """The embedder and the collection, and where each runs; the translator, if any."""
        translated = f", questions also in English by {self.translator.model}" if self.translator else ""
        return (
            f"{self.embedder.model} on {self.embedder.where}, "
            f"{self.collection} on {self.store.where}{translated}"
        )

    @property
    def collection(self) -> str:
        """The collection this embedder's build of this corpus version lives in, dense or hybrid."""
        return f"{self._stem}-v{self.version}"

    @property
    def _stem(self) -> str:
        return _PREFIX + _slug(self.embedder.model) + (_HYBRID if self.hybrid else "")

    def _builds(self) -> dict[int, str]:
        """This embedder's builds of this kind in the store, by corpus version."""
        pattern = re.compile(rf"^{re.escape(self._stem)}-v(\d+)$")
        found = {}
        for name in self.store.collections():
            matched = pattern.match(name)
            if matched:
                found[int(matched.group(1))] = name
        return found

    def check(self) -> None:
        """Raise the state that stops a search, naming its fix."""
        self.embedder.ready()
        if self.translator:
            self.translator.ready()
        self.store.ready()
        builds = self._builds()
        if self.version in builds:
            held = self.store.count(self.collection)
            if held == len(self.chunks):
                return
            raise NotBuilt(
                f"the corpus build at version {self.version} holds {held} of {len(self.chunks)} "
                "passages; run `trainer corpus build`"
            )
        if builds:
            raise NotBuilt(
                f"the corpus is built at version {max(builds)}, the repo's is {self.version}; "
                "run `trainer corpus build`"
            )
        raise NotBuilt(
            f"the corpus is not built on {self.embedder.model}; run `trainer corpus build`"
        )

    def state(self) -> Unavailable | None:
        """What stops a search, or None when it can run."""
        try:
            self.check()
        except Unavailable as missing:
            return missing
        return None

    def build(self, progress: Callable[[int, int], None] | None = None) -> None:
        """Embed every chunk into a fresh collection for this version and drop this embedder's older builds."""
        self.embedder.ready()
        self.store.ready()
        stale = self._builds()
        if self.collection in stale.values():
            self.store.drop(self.collection)
        chunks = self.chunks
        average = sum(len(_words(chunk.text)) for chunk in chunks) / len(chunks) if chunks else 0.0
        created = False
        for start in range(0, len(chunks), _BATCH):
            batch = chunks[start : start + _BATCH]
            vectors = self.embedder.embed([chunk.text for chunk in batch])
            if not created:
                self.store.create(self.collection, len(vectors[0]), hybrid=self.hybrid)
                created = True
            words = [passage_words(chunk.text, average) for chunk in batch] if self.hybrid else None
            self.store.add(self.collection, start, vectors, [asdict(chunk) for chunk in batch], words)
            if progress:
                progress(start + len(batch), len(chunks))
        for version, name in stale.items():
            if version != self.version:
                self.store.drop(name)

    def search(self, question: str, top: int = TOP) -> list[Passage]:
        """The `top` passages nearest the question, or its English when translated, nearest first."""
        asked = [question]
        if self.translator:
            english = self.translator.english(question)
            if english and english != question:
                asked.append(english)
        instruction = QUERY_INSTRUCTIONS.get(self.embedder.model.split(":")[0], "")
        best: dict[str, Passage] = {}
        vectors = self.embedder.embed([instruction + one for one in asked])
        for one, vector in zip(asked, vectors, strict=True):
            words = question_words(one) if self.hybrid else None
            for payload, score in self.store.nearest(self.collection, vector, top, words):
                passage = Passage(Chunk(**payload), score)
                if passage.chunk.id not in best or score > best[passage.chunk.id].score:
                    best[passage.chunk.id] = passage
        return sorted(best.values(), key=lambda one: one.score, reverse=True)[:top]


_TIMEOUT_S = 300.0
"""Long enough for a batch embedded on the CPU, with the model loading first."""


class Ollama:
    """Embeddings from an Ollama server."""

    def __init__(self, model: str, host: str, transport: httpx2.BaseTransport | None = None) -> None:
        self.model = model
        self.where = host
        self._client = httpx2.Client(base_url=host, transport=transport, timeout=_TIMEOUT_S)

    def _down(self, error: Exception) -> OllamaDown:
        return OllamaDown(
            f"Ollama does not answer at {self.where} ({_ascii(error)}); start it with `ollama serve`"
        )

    def _not_pulled(self) -> ModelNotPulled:
        return ModelNotPulled(
            f"Ollama at {self.where} does not hold {self.model}; run `ollama pull {self.model}`"
        )

    def ready(self) -> None:
        """Raise OllamaDown or ModelNotPulled."""
        try:
            response = self._client.get("/api/tags")
            response.raise_for_status()
            pulled = {model["name"] for model in response.json()["models"]}
        except (httpx2.HTTPError, ValueError, KeyError, TypeError) as error:
            raise self._down(error) from error
        if self.model not in pulled and f"{self.model}:latest" not in pulled:
            raise self._not_pulled()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order."""
        try:
            response = self._client.post("/api/embed", json={"model": self.model, "input": list(texts)})
        except httpx2.HTTPError as error:
            raise self._down(error) from error
        if response.status_code == 404:
            raise self._not_pulled()
        try:
            response.raise_for_status()
            embeddings: list[list[float]] = response.json()["embeddings"]
        except (httpx2.HTTPError, ValueError, KeyError) as error:
            raise self._down(error) from error
        return embeddings


_TRANSLATE = (
    "Translate this question about strength training into English. "
    "Reply with the English question alone. If it is already English, repeat it.\n\n{question}"
)


class OllamaTranslator(Ollama):
    """Questions put into English by a chat model on an Ollama server."""

    def english(self, question: str) -> str:
        """The question in English, as the model wrote it."""
        try:
            response = self._client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "prompt": _TRANSLATE.format(question=question),
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0},
                },
            )
        except httpx2.HTTPError as error:
            raise self._down(error) from error
        if response.status_code == 404:
            raise self._not_pulled()
        try:
            response.raise_for_status()
            return str(response.json()["response"]).strip()
        except (httpx2.HTTPError, ValueError, KeyError) as error:
            raise self._down(error) from error


class Qdrant:
    """Collections on a Qdrant server, through its REST interface."""

    def __init__(self, url: str, transport: httpx2.BaseTransport | None = None) -> None:
        self.where = url
        self._client = httpx2.Client(base_url=url, transport=transport, timeout=_TIMEOUT_S)

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None, *, built: bool = False) -> Any:
        """The call's result; with `built`, a missing collection is the corpus not built."""
        try:
            response = self._client.request(method, path, json=body)
        except httpx2.HTTPError as error:
            storage = home.inside(STORAGE)
            raise QdrantDown(
                f"Qdrant does not answer at {self.where} ({_ascii(error)}); start it with its storage "
                f"in {storage}: set QDRANT__STORAGE__STORAGE_PATH={storage} and run `qdrant`"
            ) from error
        if built and response.status_code == 404:
            raise NotBuilt("the corpus is not built; run `trainer corpus build`")
        try:
            response.raise_for_status()
            return response.json()["result"]
        except (httpx2.HTTPError, ValueError, KeyError) as error:
            raise QdrantDown(
                f"Qdrant at {self.where} refused {method} {path} ({_ascii(error)}: "
                f"{_ascii(response.text[:200])})"
            ) from error

    def ready(self) -> None:
        """Raise QdrantDown."""
        self._call("GET", "/collections")

    def collections(self) -> list[str]:
        """Every collection's name."""
        return [entry["name"] for entry in self._call("GET", "/collections")["collections"]]

    def count(self, name: str) -> int:
        """How many points a collection holds."""
        return int(self._call("POST", f"/collections/{name}/points/count", {"exact": True}, built=True)["count"])

    def create(self, name: str, size: int, *, hybrid: bool = False) -> None:
        """An empty collection of vectors of `size` by cosine; with `hybrid`, named, with words weighted by IDF."""
        dense = {"size": size, "distance": "Cosine"}
        body: dict[str, Any] = (
            {"vectors": {_DENSE: dense}, "sparse_vectors": {_WORDS: {"modifier": "idf"}}} if hybrid else {"vectors": dense}
        )
        self._call("PUT", f"/collections/{name}", body)

    def drop(self, name: str) -> None:
        """Delete a collection."""
        self._call("DELETE", f"/collections/{name}")

    def add(
        self,
        name: str,
        start: int,
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
        words: Sequence[Sparse] | None = None,
    ) -> None:
        """Store points numbered from `start`, waiting until they are searchable."""
        points = [
            {
                "id": start + offset,
                "vector": {_DENSE: list(vector), _WORDS: _sparse(words[offset])} if words else list(vector),
                "payload": payload,
            }
            for offset, (vector, payload) in enumerate(zip(vectors, payloads, strict=True))
        ]
        self._call("PUT", f"/collections/{name}/points?wait=true", {"points": points})

    def nearest(
        self, name: str, vector: Sequence[float], top: int, words: Sparse | None = None
    ) -> list[tuple[dict[str, Any], float]]:
        """The `top` payloads nearest to `vector`, nearest first; with `words`, fused by reciprocal rank."""
        body: dict[str, Any] = (
            {
                "prefetch": [
                    {"query": list(vector), "using": _DENSE, "limit": PREFETCH},
                    {"query": _sparse(words), "using": _WORDS, "limit": PREFETCH},
                ],
                "query": {"fusion": "rrf"},
            }
            if words is not None
            else {"query": list(vector)}
        )
        found = self._call(
            "POST", f"/collections/{name}/points/query", {**body, "limit": top, "with_payload": True}, built=True
        )
        return [(point["payload"], float(point["score"])) for point in found["points"]]


_DENSE = "dense"
_WORDS = "words"


def _sparse(words: Sparse) -> dict[str, list[Any]]:
    return {"indices": list(words), "values": list(words.values())}


class Words:
    """An embedder that hashes words into a vector; the in-memory backend's, never a measurement's."""

    model = "words"
    where = "in memory"
    _SIZE = 512

    def ready(self) -> None:
        """Always ready."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """A bag of hashed lowercase words per text."""
        vectors = []
        for text in texts:
            vector = [0.0] * self._SIZE
            for word in re.findall(r"\w+", text.lower()):
                digest = hashlib.sha256(word.encode("utf-8")).digest()
                vector[int.from_bytes(digest[:4], "big") % self._SIZE] += 1.0
            vectors.append(vector)
        return vectors


class Memory:
    """A store held in this process, compared by cosine."""

    where = "in memory"

    def __init__(self) -> None:
        self._held: dict[str, dict[int, tuple[list[float], dict[str, Any], Sparse]]] = {}

    def ready(self) -> None:
        """Always ready."""

    def collections(self) -> list[str]:
        """Every collection's name."""
        return list(self._held)

    def count(self, name: str) -> int:
        """How many points a collection holds."""
        return len(self._held[name])

    def create(self, name: str, size: int, *, hybrid: bool = False) -> None:
        """An empty collection."""
        self._held[name] = {}

    def drop(self, name: str) -> None:
        """Delete a collection."""
        del self._held[name]

    def add(
        self,
        name: str,
        start: int,
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
        words: Sequence[Sparse] | None = None,
    ) -> None:
        """Store points numbered from `start`."""
        for offset, (vector, payload) in enumerate(zip(vectors, payloads, strict=True)):
            self._held[name][start + offset] = (list(vector), payload, words[offset] if words else {})

    def nearest(
        self, name: str, vector: Sequence[float], top: int, words: Sparse | None = None
    ) -> list[tuple[dict[str, Any], float]]:
        """The `top` payloads nearest by cosine; with `words`, fused by reciprocal rank with BM25 as Qdrant fuses them."""
        if name not in self._held:
            raise NotBuilt("the corpus is not built; run `trainer corpus build`")
        held = list(self._held[name].values())
        dense = sorted(range(len(held)), key=lambda at: _cosine(vector, held[at][0]), reverse=True)
        if words is None:
            return [(held[at][1], _cosine(vector, held[at][0])) for at in dense[:top]]
        seen = {index: sum(1 for _v, _p, theirs in held if index in theirs) for index in words}
        idf = {index: math.log(1 + (len(held) - n + 0.5) / (n + 0.5)) for index, n in seen.items()}

        def bm25(at: int) -> float:
            return sum(weight * held[at][2].get(index, 0.0) * idf[index] for index, weight in words.items())

        sparse = [at for at in sorted(range(len(held)), key=bm25, reverse=True) if bm25(at) > 0]
        fused: dict[int, float] = {}
        for ranking in (dense[:PREFETCH], sparse[:PREFETCH]):
            for rank, at in enumerate(ranking):
                fused[at] = fused.get(at, 0.0) + 1 / (RRF_K + rank)
        best = sorted(fused, key=lambda at: fused[at], reverse=True)[:top]
        return [(held[at][1], fused[at]) for at in best]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


def in_memory(chunks: Sequence[Chunk], version: int) -> Search:
    """The corpus on the in-memory backend, not yet built."""
    return Search(Words(), Memory(), version, chunks)


def _ascii(said: object) -> str:
    """A server's words, safe for the console."""
    return str(said).encode("ascii", "replace").decode("ascii")


def _ollama_host() -> str:
    """Ollama's address as Ollama itself reads `OLLAMA_HOST`: scheme and port optional."""
    host = os.environ.get(OLLAMA_HOST_ENV) or OLLAMA_HOST
    if "://" not in host:
        host = f"http://{host}"
    if not re.search(r":\d+$", host):
        host = f"{host}:{OLLAMA_PORT}"
    return host


_installed: Search | None = None


@contextmanager
def installed(search: Search) -> Iterator[Search]:
    """`search` as the corpus `current` returns, while the block runs."""
    global _installed
    before, _installed = _installed, search
    try:
        yield search
    finally:
        _installed = before


def current() -> Search:
    """The corpus the tools search: the one installed, else the committed corpus served."""
    return _installed if _installed is not None else served()


def served() -> Search:
    """The committed corpus on Ollama and Qdrant, where the environment says they are."""
    model = os.environ.get(EMBEDDER_ENV) or EMBEDDER
    translator = os.environ.get(TRANSLATOR_ENV)
    return Search(
        Ollama(model, _ollama_host()),
        Qdrant(os.environ.get(QDRANT_URL_ENV) or QDRANT_URL),
        corpus.read_manifest().version,
        corpus.read_chunks(),
        translator=OllamaTranslator(translator, _ollama_host()) if translator else None,
        hybrid=os.environ.get(HYBRID_ENV) == "1",
    )
