"""The corpus: pinned pages fetched, cut into chunks and committed."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

from trainer import corpus
from trainer.cli import main

SQUAT_HTML = """\
<section data-mw-section-id="0">
<div role="note" class="hatnote navigation-not-searchable">"Squats" redirects here.</div>
<style>.mw-parser-output .hatnote{font-style:italic}</style>
<table class="infobox"><tr><td>Muscles: quadriceps</td></tr></table>
<p>A <b>squat</b> is a strength exercise.<sup class="mw-ref reference"><a href="#cite_note-1">[1]</a></sup></p>
</section>
<section data-mw-section-id="1"><h2 id="Form">Form</h2>
<p>The lifter descends by bending the hips and knees.</p>
<ul><li>Keep the heels down.</li><li>Brace the trunk.</li></ul>
<figure><img src="x.jpg"/><figcaption>A squat</figcaption></figure>
</section>
<section data-mw-section-id="2"><h2 id="References">References</h2>
<ol class="references"><li>Some book.</li></ol>
</section>
"""


def _getter(pages: dict[str, bytes]) -> Callable[[str], bytes]:
    def get(url: str) -> bytes:
        for fragment, body in pages.items():
            if fragment in url:
                return body
        raise AssertionError(f"unexpected fetch: {url}")

    return get


def _parsed(title: str, revision: int, html: str) -> bytes:
    return json.dumps(
        {"parse": {"title": title, "revid": revision, "text": html}}
    ).encode("utf-8")


def _manifest(**overrides: object) -> corpus.Manifest:
    fields: dict[str, object] = {
        "version": 1,
        "wikipedia": (corpus.Page("en", "Squat (exercise)", 1383893983),),
        "medlineplus_date": None,
        "medlineplus_topics": (),
        "exercises_commit": None,
    }
    fields.update(overrides)
    return corpus.Manifest(**fields)  # type: ignore[arg-type]


def test_a_wikipedia_page_is_cut_into_its_prose_by_section() -> None:
    get = _getter({"oldid=1383893983": _parsed("Squat (exercise)", 1383893983, SQUAT_HTML)})

    chunks = corpus.fetch(_manifest(), get)

    assert [(c.section, c.text) for c in chunks] == [
        ("", "A squat is a strength exercise."),
        (
            "Form",
            "The lifter descends by bending the hips and knees.\n"
            "Keep the heels down.\nBrace the trunk.",
        ),
    ]
    form = chunks[1]
    assert form.source == "wikipedia"
    assert form.language == "en"
    assert form.title == "Squat (exercise)"
    assert form.revision == "1383893983"
    assert form.licence == "CC BY-SA 4.0"
    assert form.link == (
        "https://en.wikipedia.org/w/index.php?title=Squat_(exercise)"
        "&oldid=1383893983#Form"
    )


def test_a_revision_of_another_page_is_refused() -> None:
    get = _getter({"oldid=1383893983": _parsed("Deadlift", 1383893983, SQUAT_HTML)})

    with pytest.raises(corpus.CorpusError, match="belongs to 'Deadlift'"):
        corpus.fetch(_manifest(), get)


MEDLINEPLUS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<health-topics>
<health-topic title="Sprains and Strains" url="https://medlineplus.gov/sprainsandstrains.html" language="English">
<full-summary>&lt;p&gt;A sprain is a stretched or torn ligament.&lt;/p&gt;
&lt;p&gt;A strain is a stretched or torn muscle.&lt;/p&gt;</full-summary>
</health-topic>
<health-topic title="Esguinces y distensiones" url="https://medlineplus.gov/spanish/sprainsandstrains.html" language="Spanish">
<full-summary>&lt;p&gt;Un esguince.&lt;/p&gt;</full-summary>
</health-topic>
</health-topics>
"""


def _zipped(name: str, text: str) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def test_a_medlineplus_topic_is_cut_from_the_pinned_days_file() -> None:
    get = _getter(
        {
            "mplus_topics_compressed_2026-11-07.zip": _zipped(
                "mplus_topics_2026-11-07.xml", MEDLINEPLUS_XML
            )
        }
    )
    manifest = _manifest(
        wikipedia=(),
        medlineplus_date="2026-11-07",
        medlineplus_topics=("Sprains and Strains",),
    )

    [chunk] = corpus.fetch(manifest, get)

    assert chunk.source == "medlineplus"
    assert chunk.language == "en"
    assert chunk.title == "Sprains and Strains"
    assert chunk.revision == "2026-11-07"
    assert chunk.link == "https://medlineplus.gov/sprainsandstrains.html"
    assert chunk.licence == "Public domain (US federal work)"
    assert chunk.text == (
        "A sprain is a stretched or torn ligament.\nA strain is a stretched or torn muscle."
    )


def test_a_medlineplus_topic_the_file_lacks_is_named() -> None:
    get = _getter(
        {"mplus_topics_compressed": _zipped("mplus_topics.xml", MEDLINEPLUS_XML)}
    )
    manifest = _manifest(
        wikipedia=(), medlineplus_date="2026-11-07", medlineplus_topics=("Back Pain",)
    )

    with pytest.raises(corpus.CorpusError, match="'Back Pain'"):
        corpus.fetch(manifest, get)


def test_a_medlineplus_file_no_longer_published_names_the_fix() -> None:
    def gone(url: str) -> bytes:
        raise corpus.NotPublished(url)

    manifest = _manifest(
        wikipedia=(), medlineplus_date="2020-01-01", medlineplus_topics=("Back Pain",)
    )

    with pytest.raises(corpus.CorpusError, match="pin a date MedlinePlus still publishes"):
        corpus.fetch(manifest, gone)


def test_free_exercise_db_instructions_come_from_the_vendored_commit() -> None:
    manifest = _manifest(wikipedia=(), exercises_commit=corpus.vendored_exercises_commit())

    squat = next(
        c for c in corpus.fetch(manifest, _getter({})) if c.title == "Barbell Squat"
    )
    assert squat.source == "free-exercise-db"
    assert squat.language == "en"
    assert squat.licence == "The Unlicense"
    assert squat.link == (
        "https://github.com/yuhonas/free-exercise-db/blob/"
        f"{manifest.exercises_commit}/exercises/Barbell_Squat.json"
    )
    assert squat.text.startswith("This exercise is best performed inside a squat rack")


MANIFEST_TOML = """\
version = 3

[medlineplus]
date = "2026-11-07"
topics = ["Sprains and Strains"]

[free-exercise-db]
commit = "a859101d633a01c4a1a920d6a8ce41dabba0705f"

[[wikipedia]]
language = "en"
title = "Squat (exercise)"
revision = 1383893983

[[wikipedia]]
language = "it"
title = "Squat"
revision = 150843803
"""


def test_the_manifest_names_the_version_and_the_pinned_list(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(MANIFEST_TOML, encoding="utf-8")

    manifest = corpus.read_manifest(tmp_path)

    assert manifest == corpus.Manifest(
        version=3,
        wikipedia=(
            corpus.Page("en", "Squat (exercise)", 1383893983),
            corpus.Page("it", "Squat", 150843803),
        ),
        medlineplus_date="2026-11-07",
        medlineplus_topics=("Sprains and Strains",),
        exercises_commit="a859101d633a01c4a1a920d6a8ce41dabba0705f",
    )


def test_a_manifest_missing_is_a_state_naming_the_fix(tmp_path: Path) -> None:
    with pytest.raises(corpus.CorpusError, match="manifest.toml"):
        corpus.read_manifest(tmp_path)


def _chunk(number: int, text: str = "Keep the heels down.") -> corpus.Chunk:
    return corpus.Chunk(
        id=f"wikipedia/en/Squat (exercise)/{number}",
        source="wikipedia",
        language="en",
        title="Squat (exercise)",
        section="Form",
        revision="1383893983",
        link="https://en.wikipedia.org/w/index.php?title=Squat_(exercise)&oldid=1383893983#Form",
        licence="CC BY-SA 4.0",
        text=text,
    )


def test_written_chunks_read_back_the_same(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(MANIFEST_TOML, encoding="utf-8")
    chunks = [_chunk(0), _chunk(1, "Brace the trunk.\nBreathe in at the top.")]

    corpus.write(chunks, tmp_path)

    assert corpus.read_chunks(tmp_path) == chunks


def test_writing_the_same_chunks_again_changes_nothing(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(MANIFEST_TOML, encoding="utf-8")
    assert corpus.write([_chunk(0)], tmp_path) is True

    assert corpus.write([_chunk(0)], tmp_path) is False


def test_the_files_use_newlines_git_will_not_rewrite(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(MANIFEST_TOML, encoding="utf-8")
    corpus.write([_chunk(0)], tmp_path)

    for name in ("chunks.jsonl", "NOTICE.md"):
        assert b"\r\n" not in (tmp_path / name).read_bytes()


def test_the_notice_names_each_licence_and_every_pinned_page(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(MANIFEST_TOML, encoding="utf-8")
    corpus.write([_chunk(0)], tmp_path)

    notice = (tmp_path / "NOTICE.md").read_text(encoding="utf-8")

    for licence in ("CC BY-SA 4.0", "The Unlicense", "Public domain (US federal work)"):
        assert licence in notice
    assert "https://en.wikipedia.org/w/index.php?title=Squat_(exercise)&oldid=1383893983" in notice
    assert "https://it.wikipedia.org/w/index.php?title=Squat&oldid=150843803" in notice
    assert "https://medlineplus.gov/xml/mplus_topics_compressed_2026-11-07.zip" in notice
    assert "corpus version 3" in notice


ONE_PAGE_TOML = """\
version = 1

[[wikipedia]]
language = "en"
title = "Squat (exercise)"
revision = 1383893983
"""


@pytest.fixture()
def corpus_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "corpus"
    directory.mkdir()
    (directory / "manifest.toml").write_text(ONE_PAGE_TOML, encoding="utf-8")
    monkeypatch.setattr(corpus, "CORPUS_DIRECTORY", directory)
    monkeypatch.setattr(
        corpus,
        "http_get",
        _getter({"oldid=1383893983": _parsed("Squat (exercise)", 1383893983, SQUAT_HTML)}),
    )
    return directory


def test_the_fetch_command_writes_the_chunks_and_says_so(corpus_directory: Path) -> None:
    result = CliRunner().invoke(main, ["corpus", "fetch"])

    assert result.exit_code == 0, result.output
    assert "chunks: 2, texts: 1, corpus version: 1" in result.output
    assert "written" in result.output
    assert len(corpus.read_chunks(corpus_directory)) == 2
    assert result.output.isascii()


def test_fetching_again_reports_nothing_to_commit(corpus_directory: Path) -> None:
    CliRunner().invoke(main, ["corpus", "fetch"])

    result = CliRunner().invoke(main, ["corpus", "fetch"])

    assert result.exit_code == 0, result.output
    assert "unchanged, nothing to commit" in result.output


def test_a_fetch_that_fails_is_a_message_not_a_traceback(
    corpus_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        corpus,
        "http_get",
        _getter({"oldid=1383893983": _parsed("Deadlift", 1383893983, SQUAT_HTML)}),
    )

    result = CliRunner().invoke(main, ["corpus", "fetch"])

    assert result.exit_code == 1
    assert "Error: " in result.output
    assert "belongs to 'Deadlift'" in result.output


def test_the_committed_corpus_holds_only_allowed_sources_under_their_licence() -> None:
    for chunk in corpus.read_chunks():
        assert chunk.source in {"wikipedia", "medlineplus", "free-exercise-db"}, chunk.id
        assert chunk.licence == corpus.SOURCES[chunk.source].licence, chunk.id


def test_the_committed_corpus_directory_holds_no_vectors() -> None:
    held = {path.name for path in corpus.CORPUS_DIRECTORY.iterdir()}

    assert held == {"manifest.toml", "chunks.jsonl", "NOTICE.md"}


def test_every_pinned_page_and_only_those_is_in_the_committed_chunks() -> None:
    manifest = corpus.read_manifest()
    pinned = {(p.language, p.title, str(p.revision)) for p in manifest.wikipedia}

    cut = {
        (c.language, c.title, c.revision)
        for c in corpus.read_chunks()
        if c.source == "wikipedia"
    }

    assert cut == pinned


def test_the_committed_chunks_have_unique_ids() -> None:
    ids = [chunk.id for chunk in corpus.read_chunks()]

    assert len(ids) == len(set(ids))


def test_the_committed_notice_matches_the_manifest() -> None:
    notice = (corpus.CORPUS_DIRECTORY / "NOTICE.md").read_text(encoding="utf-8")

    assert notice == corpus.notice(corpus.read_manifest())


def test_the_committed_manifest_pins_the_vendored_exercises() -> None:
    assert corpus.read_manifest().exercises_commit == corpus.vendored_exercises_commit()


def test_a_commit_other_than_the_vendored_one_is_refused() -> None:
    manifest = _manifest(wikipedia=(), exercises_commit="0" * 40)

    with pytest.raises(corpus.CorpusError, match="vendored"):
        corpus.fetch(manifest, _getter({}))
