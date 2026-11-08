"""The corpus: pinned pages fetched, cut into chunks and committed."""

from __future__ import annotations

import hashlib
import json
import re
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


MANIFEST_TOML = """\
version = 3

[medlineplus]
date = "2026-11-07"
topics = ["Sprains and Strains"]

[[wger]]
language = "it"
date = "2026-11-08"
sha256 = "abc"

[[wger]]
language = "en"
date = "2026-11-08"
sha256 = "ghi"

[[army]]
publication = "ATP 7-22.02"
title = "Holistic Health and Fitness Drills and Exercises"
url = "https://armypubs.army.mil/x.pdf"
sha256 = "def"
chapters = [3, 14]

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
        wger=(corpus.Wger("it", "2026-11-08", "abc"), corpus.Wger("en", "2026-11-08", "ghi")),
        army=(
            corpus.ArmyPublication(
                "ATP 7-22.02",
                "Holistic Health and Fitness Drills and Exercises",
                "https://armypubs.army.mil/x.pdf",
                "def",
                (3, 14),
            ),
        ),
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
        author="Wikipedia contributors",
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

    for licence in (
        "CC BY-SA 4.0",
        "Public domain (US federal work)",
        "Public domain (US government work)",
    ):
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
        assert chunk.source in {
            "wikipedia", "medlineplus", "wger", "us-army"
        }, chunk.id
        assert chunk.licence in corpus.SOURCES[chunk.source].licences, chunk.id


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

    assert notice == corpus.notice(corpus.read_manifest(), corpus.read_chunks())


def test_a_manifest_naming_a_source_the_corpus_may_not_hold_is_refused(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(
        'version = 1\n\n[free-exercise-db]\ncommit = "a859101"\n', encoding="utf-8"
    )

    with pytest.raises(corpus.CorpusError, match="free-exercise-db"):
        corpus.read_manifest(tmp_path)


WGER_LICENCES = {
    "results": [
        {"id": 1, "short_name": "CC-BY-SA 3"},
        {"id": 2, "short_name": "CC-BY-SA 4"},
        {"id": 3, "short_name": "CC0"},
        {"id": 5, "short_name": "ODbL"},
    ]
}
WGER_LANGUAGES = {"results": [{"id": 2, "short_name": "en"}, {"id": 13, "short_name": "it"}]}


def _translation(id: int, language: int, licence: int, name: str, description: str) -> dict[str, object]:
    return {
        "id": id,
        "language": language,
        "license": licence,
        "license_author": "FEFFO",
        "name": name,
        "description": description,
    }


WGER_FIRST = {
    "next": "https://wger.de/api/v2/exerciseinfo/?offset=200",
    "results": [
        {
            "id": 73,
            "translations": [
                _translation(1, 2, 2, "Bench Press", "<p>Lie on the bench.</p>"),
                _translation(
                    2,
                    13,
                    2,
                    "Panca piana con manubri",
                    "<p>Impugnate due manubri.</p><ol><li>Scendete lentamente.</li></ol>",
                ),
            ],
        }
    ],
}
WGER_SECOND = {
    "next": None,
    "results": [
        {"id": 80, "translations": [_translation(3, 13, 5, "Rematore", "<p>Tirate.</p>")]},
        {"id": 81, "translations": [_translation(4, 13, 3, "Crunch", "<p>Sollevate le spalle.</p>")]},
        {"id": 82, "translations": [_translation(5, 13, 2, "Stacco", "<p>StaccoStacco Stacco</p>")]},
        {
            "id": 83,
            "translations": [
                {
                    **_translation(6, 13, 2, "Plank laterale", "<p>Sdraiati su un fianco.</p>"),
                    "license_author": "http://www.bodybuilding.com/",
                }
            ],
        },
        {
            "id": 84,
            "translations": [
                _translation(
                    7,
                    2,
                    2,
                    "Barbell Squat",
                    "<p>Set the bar on a rack to just below shoulder level and step under it.</p>"
                    "<p>Squat down.</p>",
                ),
                {**_translation(8, 2, 2, "Concentration Curl", "<p>Sit and curl the dumbbell.</p>"), "license_author": "ExRx"},
                _translation(
                    9, 2, 2, "Fire Hydrant Circles", "<p>Source: Joe DeFranco\nPrescription: 10 reps</p>"
                ),
                {**_translation(10, 2, 2, "Toe Taps", "<p>Lie down and tap your toes.</p>"), "license_author": "someone@gmail.com"},
            ],
        },
    ],
}
BORROWED = [
    {"instructions": ["Set the bar on a rack to just below shoulder level and step under it."]},
]


def _wger_getter() -> Callable[[str], bytes]:
    pages = {
        "/license/": WGER_LICENCES,
        "/language/": WGER_LANGUAGES,
        "offset=200": WGER_SECOND,
        "/exerciseinfo/": WGER_FIRST,
        "free-exercise-db": BORROWED,
    }
    return _getter({k: json.dumps(v).encode("utf-8") for k, v in pages.items()})


def _wger_manifest(sha256: str, language: str = "it") -> corpus.Manifest:
    return _manifest(wikipedia=(), wger=(corpus.Wger(language, "2026-11-08", sha256),))


def _wger_pin(language: str = "it") -> str:
    try:
        corpus.fetch(_wger_manifest("0" * 64, language), _wger_getter())
    except corpus.CorpusError as error:
        found = re.search(r"sha256 = \"([0-9a-f]{64})\"", str(error))
        assert found is not None, str(error)
        return found.group(1)
    raise AssertionError("a wrong pin was accepted")


def test_wger_gives_its_italian_descriptions_under_their_own_licence() -> None:
    chunks = corpus.fetch(_wger_manifest(_wger_pin()), _wger_getter())

    assert [(c.title, c.licence, c.text) for c in chunks] == [
        (
            "Panca piana con manubri",
            "CC BY-SA 4.0",
            "Impugnate due manubri.\nScendete lentamente.",
        ),
        ("Crunch", "CC0 1.0", "Sollevate le spalle."),
    ]
    bench = chunks[0]
    assert bench.source == "wger"
    assert bench.language == "it"
    assert bench.revision == "2026-11-08"
    assert bench.link == "https://wger.de/it/exercise/73/view/"


def test_wger_leaves_out_a_description_that_only_repeats_its_title() -> None:
    titles = [c.title for c in corpus.fetch(_wger_manifest(_wger_pin()), _wger_getter())]

    assert "Stacco" not in titles


def test_wger_leaves_out_a_text_credited_to_a_copyrighted_site() -> None:
    titles = [c.title for c in corpus.fetch(_wger_manifest(_wger_pin()), _wger_getter())]

    assert "Plank laterale" not in titles


def _english_titles() -> list[str]:
    return [c.title for c in corpus.fetch(_wger_manifest(_wger_pin("en"), "en"), _wger_getter())]


def test_wger_gives_each_pinned_language_apart() -> None:
    manifest = _manifest(
        wikipedia=(),
        wger=(corpus.Wger("it", "2026-11-08", _wger_pin()), corpus.Wger("en", "2026-11-08", _wger_pin("en"))),
    )

    chunks = corpus.fetch(manifest, _wger_getter())

    assert ("en", "Bench Press") in [(c.language, c.title) for c in chunks]
    assert ("it", "Crunch") in [(c.language, c.title) for c in chunks]
    assert "https://wger.de/en/exercise/73/view/" in [c.link for c in chunks]


def test_wger_leaves_out_a_text_copied_from_bodybuilding_com() -> None:
    assert "Barbell Squat" not in _english_titles()


def test_wger_leaves_out_a_text_whose_author_is_a_site() -> None:
    titles = _english_titles()

    assert "Concentration Curl" not in titles
    assert "Toe Taps" in titles


def test_wger_leaves_out_a_text_that_names_another_source() -> None:
    assert "Fire Hydrant Circles" not in _english_titles()


def test_wger_changed_since_its_pin_names_the_new_pin() -> None:
    with pytest.raises(corpus.CorpusError, match="changed since 2026-11-08"):
        corpus.fetch(_wger_manifest("0" * 64), _wger_getter())


def test_the_notice_credits_each_wger_author(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(MANIFEST_TOML, encoding="utf-8")
    chunks = corpus.fetch(_wger_manifest(_wger_pin()), _wger_getter())

    corpus.write(chunks, tmp_path)

    notice = (tmp_path / "NOTICE.md").read_text(encoding="utf-8")
    assert "Panca piana con manubri" in notice
    assert "FEFFO" in notice
    assert "https://wger.de/it/exercise/73/view/" in notice


ARMY_PAGES = [
    "Contents\nChapter 14 +FREE WEIGHT TRAINING ........ 14-1\n",
    "01 October 2020 ATP 7-22.02 (INCL C1) 14-1 \n \nChapter 14 \n+Free Weight Training \n \n"
    "FREE WEIGHTS \n14-1. Free Weight Training exercises are divided into two groups, core \n"
    "and assistive. \n \nBACK SQUAT \n14-6. The Back Squat is a common variation of the Front Squat. \n"
    "⚫ Keep the knees aligned over the feet and the heels on the ground. \n"
    "⚫ Initially do not squat deeper than 90 degrees. \n \nFigure 14-2. FW2 Back Squat \n",
    "Free Weight Training \n01 October 2022 ATP 7-22.02 (INCL C1) 14-2 \n \n"
    "BACK SQUAT CAUTION \n• Do not round out the upper back. \n"
    "2. REAR LUNGE \n• Step back with the left leg. \n",
    "15-1 ATP 7-22.02 (INCL C1) 01 October 2020 \nChapter 15 \n+Strength Training Machine Drill \n"
    "LEG PRESS \n15-2. Sit on the machine. \n",
]
ARMY_URL = "https://armypubs.army.mil/epubs/DR_pubs/DR_a/ATP_7-22.02.pdf"
ARMY_BYTES = b"%PDF-fake"


def _army_manifest(sha256: str, chapters: tuple[int, ...] = (14,)) -> corpus.Manifest:
    return _manifest(
        wikipedia=(),
        army=(
            corpus.ArmyPublication(
                "ATP 7-22.02",
                "Holistic Health and Fitness Drills and Exercises",
                ARMY_URL,
                sha256,
                chapters,
            ),
        ),
    )


@pytest.fixture()
def army_pages(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(corpus, "pdf_pages", lambda data: list(ARMY_PAGES))
    return hashlib.sha256(ARMY_BYTES).hexdigest()


def test_an_army_manual_is_cut_by_heading_within_its_chosen_chapters(army_pages: str) -> None:
    get = _getter({ARMY_URL: ARMY_BYTES})

    chunks = corpus.fetch(_army_manifest(army_pages), get)

    assert [(c.section, c.text) for c in chunks] == [
        (
            "Free Weights",
            "Free Weight Training exercises are divided into two groups, core and assistive.",
        ),
        (
            "Back Squat",
            "The Back Squat is a common variation of the Front Squat.\n"
            "Keep the knees aligned over the feet and the heels on the ground.\n"
            "Initially do not squat deeper than 90 degrees.",
        ),
        ("Back Squat Caution", "Do not round out the upper back."),
        ("Rear Lunge", "Step back with the left leg."),
    ]
    squat = chunks[1]
    assert squat.source == "us-army"
    assert squat.title == "ATP 7-22.02, Holistic Health and Fitness Drills and Exercises"
    assert squat.language == "en"
    assert squat.licence == "Public domain (US government work)"
    assert squat.link == f"{ARMY_URL}#page=2"
    assert chunks[2].link == f"{ARMY_URL}#page=3"


def test_an_army_manual_other_than_the_pinned_file_is_refused(army_pages: str) -> None:
    get = _getter({ARMY_URL: b"%PDF-another"})

    with pytest.raises(corpus.CorpusError, match="not the pinned file"):
        corpus.fetch(_army_manifest(army_pages), get)
