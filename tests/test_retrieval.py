"""Search over the corpus: built, versioned, searched, and each state that stops it."""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest

from click.testing import CliRunner

from trainer import retrieval
from trainer.cli import main
from trainer.corpus import Chunk


def _chunk(title: str, section: str, text: str, language: str = "en") -> Chunk:
    return Chunk(
        id=f"wikipedia/{language}/{title}/{section}",
        source="wikipedia",
        language=language,
        title=title,
        section=section,
        revision="1",
        link=f"https://{language}.wikipedia.org/w/index.php?title={title}&oldid=1",
        licence="CC BY-SA 4.0",
        author="Wikipedia contributors",
        text=text,
    )


CHUNKS = [
    _chunk("Squat (exercise)", "Form", "Squat with the heels down and the trunk braced as the hips descend."),
    _chunk("Deadlift", "Technique", "The deadlift lifts the barbell from the floor with a neutral spine."),
    _chunk("Bench press", "", "The bench press presses the barbell from the chest while lying on a bench."),
    _chunk("Plank (exercise)", "", "The plank holds the trunk rigid on the forearms and toes."),
    _chunk("Running", "Injuries", "Runners avoid injury by raising their mileage slowly."),
    _chunk("Stretching", "", "Stretching lengthens a muscle before or after training."),
]


def test_a_built_corpus_returns_the_top_five_passages_with_what_cites_them() -> None:
    search = retrieval.in_memory(CHUNKS, version=3)
    search.build()

    passages = search.search("how deep should the squat go with my heels down")

    assert len(passages) == 5
    first = passages[0]
    assert first.chunk.title == "Squat (exercise)"
    assert first.chunk.section == "Form"
    assert first.chunk.language == "en"
    assert first.chunk.link.endswith("oldid=1")
    assert [p.score for p in passages] == sorted((p.score for p in passages), reverse=True)


def test_a_built_corpus_is_ready_at_the_version_it_was_built_at() -> None:
    search = retrieval.in_memory(CHUNKS, version=3)
    search.build()

    assert search.state() is None


def test_an_unbuilt_corpus_is_a_state_naming_the_build() -> None:
    search = retrieval.in_memory(CHUNKS, version=3)

    missing = search.state()

    assert isinstance(missing, retrieval.NotBuilt)
    assert "trainer corpus build" in str(missing)


def test_a_corpus_built_at_another_version_names_both_and_the_build() -> None:
    old = retrieval.in_memory(CHUNKS, version=2)
    old.build()
    search = retrieval.Search(old.embedder, old.store, version=3, chunks=CHUNKS)

    missing = search.state()

    assert isinstance(missing, retrieval.NotBuilt)
    assert "version 2" in str(missing) and "3" in str(missing)
    assert "trainer corpus build" in str(missing)


def test_a_rebuild_at_a_new_version_leaves_only_the_new_build() -> None:
    old = retrieval.in_memory(CHUNKS, version=2)
    old.build()
    search = retrieval.Search(old.embedder, old.store, version=3, chunks=CHUNKS)

    search.build()

    assert search.state() is None
    assert old.store.collections() == [search.collection]


def test_a_build_short_of_the_committed_chunks_is_not_built() -> None:
    partial = retrieval.in_memory(CHUNKS[:2], version=3)
    partial.build()
    search = retrieval.Search(partial.embedder, partial.store, version=3, chunks=CHUNKS)

    missing = search.state()

    assert isinstance(missing, retrieval.NotBuilt)
    assert f"2 of {len(CHUNKS)}" in str(missing)


def _refused(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


def _ollama(pulled: list[str]) -> httpx2.MockTransport:
    words = retrieval.Words()

    def answer(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": name} for name in pulled]})
        if request.url.path == "/api/embed":
            asked = json.loads(request.content)
            if not any(name.split(":")[0] == asked["model"] for name in pulled):
                return httpx2.Response(404, json={"error": f"model \"{asked['model']}\" not found"})
            return httpx2.Response(200, json={"embeddings": words.embed(asked["input"])})
        return httpx2.Response(404)

    return httpx2.MockTransport(answer)


class _FakeQdrant:
    """Qdrant's REST surface, as much of it as the corpus uses, over the in-memory store."""

    def __init__(self) -> None:
        self.held = retrieval.Memory()

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        parts = request.url.path.strip("/").split("/")
        body = json.loads(request.content) if request.content else {}
        if parts == ["collections"]:
            names = [{"name": name} for name in self.held.collections()]
            return httpx2.Response(200, json={"result": {"collections": names}})
        name = parts[1]
        if name not in self.held.collections() and request.method != "PUT":
            return httpx2.Response(404, json={"status": {"error": f"Collection `{name}` doesn't exist!"}})
        if len(parts) == 2 and request.method == "PUT":
            self.held.create(name, body["vectors"]["size"])
        elif len(parts) == 2 and request.method == "DELETE":
            self.held.drop(name)
        elif parts[2:] == ["points", "count"]:
            return httpx2.Response(200, json={"result": {"count": self.held.count(name)}})
        elif parts[2:] == ["points"]:
            points = body["points"]
            self.held.add(
                name, points[0]["id"], [p["vector"] for p in points], [p["payload"] for p in points]
            )
        elif parts[2:] == ["points", "query"]:
            found = self.held.nearest(name, body["query"], body["limit"])
            points = [{"id": 0, "score": score, "payload": payload} for payload, score in found]
            return httpx2.Response(200, json={"result": {"points": points}})
        return httpx2.Response(200, json={"result": True})


def _served(ollama: httpx2.BaseTransport, qdrant: httpx2.BaseTransport) -> retrieval.Search:
    return retrieval.Search(
        retrieval.Ollama("bge-m3", "http://ollama.test", ollama),
        retrieval.Qdrant("http://qdrant.test", qdrant),
        version=3,
        chunks=CHUNKS,
    )


def test_a_corpus_built_through_ollama_into_qdrant_is_searched() -> None:
    search = _served(_ollama(["bge-m3:latest"]), httpx2.MockTransport(_FakeQdrant()))
    search.build()

    assert search.state() is None
    assert search.search("squat heels down")[0].chunk.title == "Squat (exercise)"


def test_ollama_down_names_starting_it() -> None:
    search = _served(httpx2.MockTransport(_refused), httpx2.MockTransport(_FakeQdrant()))

    missing = search.state()

    assert isinstance(missing, retrieval.OllamaDown)
    assert "http://ollama.test" in str(missing) and "ollama serve" in str(missing)


def test_the_model_not_pulled_names_pulling_it() -> None:
    search = _served(_ollama(["qwen3.5:4b"]), httpx2.MockTransport(_FakeQdrant()))

    missing = search.state()

    assert isinstance(missing, retrieval.ModelNotPulled)
    assert "ollama pull bge-m3" in str(missing)


def test_qdrant_down_names_starting_it_on_the_homes_storage(machine_home: Path) -> None:
    search = _served(_ollama(["bge-m3"]), httpx2.MockTransport(_refused))

    missing = search.state()

    assert isinstance(missing, retrieval.QdrantDown)
    assert "http://qdrant.test" in str(missing)
    assert str(machine_home / "qdrant") in str(missing)


def test_a_server_down_mid_session_is_a_state_not_a_crash() -> None:
    qdrant = _FakeQdrant()
    search = _served(_ollama(["bge-m3"]), httpx2.MockTransport(qdrant))
    search.build()
    downed = _served(_ollama(["bge-m3"]), httpx2.MockTransport(_refused))

    with pytest.raises(retrieval.QdrantDown):
        downed.search("squat")
    with pytest.raises(retrieval.OllamaDown):
        _served(httpx2.MockTransport(_refused), httpx2.MockTransport(qdrant)).search("squat")


@pytest.fixture()
def memory(monkeypatch: pytest.MonkeyPatch) -> retrieval.Search:
    """`trainer` reaching the in-memory corpus instead of Ollama and Qdrant."""
    search = retrieval.in_memory(CHUNKS, version=3)
    monkeypatch.setattr(retrieval, "served", lambda: search)
    return search


def test_corpus_build_embeds_every_chunk_and_names_the_version(memory: retrieval.Search) -> None:
    result = CliRunner().invoke(main, ["corpus", "build"])

    assert result.exit_code == 0, result.output
    assert f"built: {len(CHUNKS)} passages, corpus version 3" in result.output
    assert memory.state() is None
    assert result.output.isascii()


def test_corpus_build_with_a_server_down_names_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        retrieval, "served",
        lambda: _served(httpx2.MockTransport(_refused), httpx2.MockTransport(_FakeQdrant())),
    )

    result = CliRunner().invoke(main, ["corpus", "build"])

    assert result.exit_code == 1
    assert "ollama serve" in result.output
    assert "Traceback" not in result.output
