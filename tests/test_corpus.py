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

[[pdf]]
source = "us-army"
key = "ATP 7-22.02"
title = "ATP 7-22.02, Holistic Health and Fitness Drills and Exercises"
url = "https://armypubs.army.mil/x.pdf"
sha256 = "def"
cut = "army-manual"
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
        pdf=(
            corpus.Pdf(
                "us-army",
                "ATP 7-22.02",
                "ATP 7-22.02, Holistic Health and Fitness Drills and Exercises",
                "https://armypubs.army.mil/x.pdf",
                "def",
                "army-manual",
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
            "wikipedia",
            "medlineplus",
            "wger",
            "us-army",
            "hhs",
            "usuhs",
            "us-air-force",
            "europe-pmc",
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
        pdf=(
            corpus.Pdf(
                "us-army",
                "ATP 7-22.02",
                "ATP 7-22.02, Holistic Health and Fitness Drills and Exercises",
                ARMY_URL,
                sha256,
                "army-manual",
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

    with pytest.raises(corpus.CorpusError, match="not the pinned file") as refused:
        corpus.fetch(_army_manifest(army_pages), get)

    assert army_pages in str(refused.value)
    assert hashlib.sha256(b"%PDF-another").hexdigest() in str(refused.value)


HHS_OUTLINE: list[tuple[int, str, int | None]] = [
    (0, "Physical Activity Guidelines", 1),
    (1, "Table of Contents", 1),
    (1, "Chapter 3. Active Children", 2),
    (2, "Aerobic Activity", 3),
    (1, "Chapter 4. Active Adults", None),
    (2, "Explaining the Key Guidelines", 5),
    (3, "Muscle-Strengthening Activity", 5),
    (1, "Glossary", 7),
]
HHS_PAGES = [
    "Table of Contents\nChapter 4. Active Adults ........ 55\n",
    "Chapter 3. Active Children\n",
    "Aerobic Activity\nChildren play.\n\n\n\n46Physical Activity Guidelines",
    "Chapter 4. Active Adults\n",
    "Adults who are active are healthier, feel better,\n"
    "and are less likely to develop disease.                         Learn More\n"
    "They sleep better.                                              See Chapter 6.\n"
    "                                                                It says more.\n"
    "Explaining the Key Guidelines\n"
    "The guidelines focus on two types of activity.\n"
    "Muscle-Strengthening Activity\n"
    "Muscle-strengthening activities include lifting weights. A warm-up for muscle-\n"
    "strengthening activity involves lighter weight (see Table 4-1).\n"
    "\n"
    "Table 4-1. Examples of Activities,\n"
    "Based on Intensity\n"
    "\n"
    "  Moderate          Walking briskly\n"
    "  Vigorous          Running\n"
    "\n"
    "Note: Only strong evidence is included.\n"
    "\n"
    "The best strategies are to:\n"
    "      •     Be regularly active; and\n"
    "      •     Follow the other guidance\n"
    "         in this chapter.\n"
    "\n"
    "One set of 8 to 12 repetitions is effective, although 2 or 3 sets may\n"
    "\n\n\n"
    "                                                    Chapter 4. Active Adults      57\n",
    "be more effective.\n"
    "\n"
    "Figure 4-1. Benefit by Amount\n"
    "    1.1\n"
    "      1      No lower threshold\n"
    "\n"
    "Source: Adapted from Moore SC.\n"
    "\n"
    "Increases in weight will result in stronger muscles.\n"
    "\n\n\n"
    "58Physical Activity Guidelines\n",
    "Glossary\nAerobic: with oxygen.\n",
]
HHS_URL = "https://odphp.health.gov/guidelines.pdf"
HHS_BYTES = b"%PDF-guidelines"


def _hhs_manifest() -> corpus.Manifest:
    return _manifest(
        wikipedia=(),
        pdf=(
            corpus.Pdf(
                "hhs",
                "physical-activity-guidelines-2",
                "Physical Activity Guidelines for Americans, 2nd edition",
                HHS_URL,
                hashlib.sha256(HHS_BYTES).hexdigest(),
                "bookmarks",
                (4,),
            ),
        ),
    )


@pytest.fixture()
def hhs_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        corpus, "pdf_bookmarked", lambda data: (list(HHS_PAGES), list(HHS_OUTLINE))
    )


def test_a_bookmarked_pdf_is_cut_by_its_bookmarks_within_its_chosen_chapters(
    hhs_pdf: None,
) -> None:
    chunks = corpus.fetch(_hhs_manifest(), _getter({HHS_URL: HHS_BYTES}))

    assert [(c.section, c.text) for c in chunks] == [
        (
            "Chapter 4. Active Adults",
            "Adults who are active are healthier, feel better, and are less likely to "
            "develop disease. They sleep better.",
        ),
        (
            "Chapter 4. Active Adults: Explaining the Key Guidelines",
            "The guidelines focus on two types of activity.",
        ),
        (
            "Chapter 4. Active Adults: Muscle-Strengthening Activity",
            "Muscle-strengthening activities include lifting weights. A warm-up for "
            "muscle-strengthening activity involves lighter weight (see Table 4-1).\n"
            "The best strategies are to:\n"
            "Be regularly active; and\n"
            "Follow the other guidance in this chapter.\n"
            "One set of 8 to 12 repetitions is effective, although 2 or 3 sets may be "
            "more effective.\n"
            "Increases in weight will result in stronger muscles.",
        ),
    ]
    first, _, last = chunks
    assert first.id == "hhs/en/physical-activity-guidelines-2/0"
    assert first.source == "hhs"
    assert first.title == "Physical Activity Guidelines for Americans, 2nd edition"
    assert first.licence == "Public domain (US government work)"
    assert first.author == (
        "Office of Disease Prevention and Health Promotion, "
        "U.S. Department of Health and Human Services"
    )
    assert first.link == f"{HHS_URL}#page=5"
    assert last.link == f"{HHS_URL}#page=5"


def test_the_notice_lists_the_guidelines_with_the_wording_of_their_publisher() -> None:
    notice = corpus.notice(_hhs_manifest(), [])

    assert "## HHS" in notice
    assert (
        '"is in the public domain. This means it may be freely distributed and copied — '
        'but please include a link to our website and acknowledge ODPHP as the source."'
    ) in notice
    assert "https://odphp.health.gov/copyright-policy" in notice
    assert (
        f"- *Physical Activity Guidelines for Americans, 2nd edition*, {HHS_URL} "
        f"(sha256 `{hashlib.sha256(HHS_BYTES).hexdigest()}`), chapters 4"
    ) in notice


SEAL_OUTLINE: list[tuple[int, str, int | None]] = [
    (0, "SEALFITNESS.pdf", None),
    (1, "Chapter 5 Swimming for Fitness", 1),
    (1, "Chapter 6 Strength Training", 2),
    (2, "Repetition Maximum or RM", 2),
    (2, "Periodization", 3),
    (2, "Resource", 4),
    (1, "Appendix A Weight Lifting Techniques", 5),
]
SEAL_PAGES = [
    "        Swimming is an excellent exercise\n"
    "for overall fitness.\n"
    "\n\n"
    "72                         Swimming for Fitness\n",
    "                                      Chapters\n"
    "          Strength Training\n"
    "\n\n\n"
    "        Muscular strength and endurance training enhance agility,\n"
    "speed, strength, and endurance. Pure strength alone will\n"
    "not improve mission perfor-\n"
    "mance.\n"
    "Repetition Maximum or\n"
    "RM\n"
    "\n"
    "         A repetition maximum or RM is the maximum amount of weight you can lift for a given\n"
    "number of repetitions.                    For example, your 1RM would be the amount of weight\n"
    "you could lift for only 1 repetition.\n"
    "\n"
    "           Your 1RM would be the amount of weight you\n"
    "                            can lift for only 1 repetition\n"
    "         To find your 5RM:\n"
    "         •   Select a weight you know is light enough for 10\n"
    "               repetitions.\n"
    "         •   Rest for two minutes.\n"
    "                   Multiply your 5RM times 1.15\n"
    "                          to establish your 1RM.\n"
    "Figure 6-2.   Determining Your 1RM from 5RM\n"
    "\n"
    "                   5RM = 75\n"
    "         1RM = 75 X 1.15 = 86\n"
    "\n"
    "The Navy SEAL Physical Fitness Guide                                        \n",
    "Table 6-4. Intensity Levels Relative to a 1RM*\n"
    "      % of 1RM                           Number of Repetitions\n"
    "           80 - 95                                           2 - 5\n"
    "                     Lift the load in good form using the\n"
    " Heavy Lifts         weight slowly, then lower it.                  Hips\n"
    "   *Adapted with permission from Strength Training for Sports; Applied Futuristics, Inc.\n"
    "Periodization\n"
    "\n"
    "         Periodization of training is a technique that involves altering training variables\n"
    "to achieve well-defined gains. Your schedule would be adapted to\n"
    "\n\n"
    "100                                                          Strength Training\n",
    "achieve that goal.\n"
    "   The goal of the muscular endurance phase\n"
    "    is to take strength gains and convert them.\n"
    "\n"
    "Resource\n"
    "\n"
    "        Bompa, T. Strength Training for Sports. Applied Futuristics,\n"
    "1993.\n"
    "\n\n"
    "The Navy SEAL Physical Fitness Guide                                        \n",
    "                Appendix A\n"
    "   Weight Lifting Techniques\n"
    "\n"
    "        Squats: keep the back straight\n"
    "and the head up.\n",
]
SEAL_URL = "https://champ.usuhs.edu/navysealfitnessguide.pdf"
SEAL_BYTES = b"%PDF-seal"


def _seal_manifest() -> corpus.Manifest:
    return _manifest(
        wikipedia=(),
        pdf=(
            corpus.Pdf(
                "usuhs",
                "navy-seal-physical-fitness-guide",
                "The Navy SEAL Physical Fitness Guide",
                SEAL_URL,
                hashlib.sha256(SEAL_BYTES).hexdigest(),
                "indented",
                (6,),
            ),
        ),
    )


@pytest.fixture()
def seal_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        corpus, "pdf_bookmarked", lambda data: (list(SEAL_PAGES), list(SEAL_OUTLINE))
    )


def test_an_indented_pdf_gives_its_chosen_chapters_and_no_table_or_appendix(
    seal_pdf: None,
) -> None:
    chunks = corpus.fetch(_seal_manifest(), _getter({SEAL_URL: SEAL_BYTES}))

    assert [(c.section, c.text) for c in chunks] == [
        (
            "Chapter 6 Strength Training",
            "Muscular strength and endurance training enhance agility, speed, strength, "
            "and endurance. Pure strength alone will not improve mission performance.",
        ),
        (
            "Chapter 6 Strength Training: Repetition Maximum or RM",
            "A repetition maximum or RM is the maximum amount of weight you can lift for "
            "a given number of repetitions. For example, your 1RM would be the amount of "
            "weight you could lift for only 1 repetition.\n"
            "To find your 5RM:\n"
            "Select a weight you know is light enough for 10 repetitions.\n"
            "Rest for two minutes.",
        ),
        (
            "Chapter 6 Strength Training: Periodization",
            "Periodization of training is a technique that involves altering training "
            "variables to achieve well-defined gains. Your schedule would be adapted to "
            "achieve that goal.",
        ),
    ]
    assert [c.link for c in chunks] == [f"{SEAL_URL}#page={n}" for n in (2, 2, 3)]
    assert {c.source for c in chunks} == {"usuhs"}
    assert {c.author for c in chunks} == {
        "Uniformed Services University of the Health Sciences"
    }
    assert {c.licence for c in chunks} == {"Public domain (US government work)"}


def test_the_notice_says_the_seal_guide_is_public_domain_by_authorship_inferred() -> None:
    notice = corpus.notice(_seal_manifest(), [])

    assert "## USUHS" in notice
    assert "17 U.S.C. 105" in notice
    assert "inferred from the authors the PDF names" in notice
    assert "no licence statement of its own" in notice
    assert f"- *The Navy SEAL Physical Fitness Guide*, {SEAL_URL}" in notice


PLAYBOOK_URL = "https://www.afpc.af.mil/Portals/70/documents/FITNESS/playbook.pdf"
PLAYBOOK_FILE = "The Warfighter's Fitness Playbook.pdf"
PLAYBOOK_BYTES = b"%PDF-playbook"
_TIMES, _TIMES_BOLD = "TimesNewRomanPSMT", "TimesNewRomanPS-BoldMT"
_NUNITO, _SOURCE = "NunitoSans-BoldItalic", "SourceSansPro-Regular"


def _furniture(label: str, folio: str) -> list[tuple[float, float, float, str, str]]:
    return [
        (574.0, 20.6, 13.0, "Poppins-Regular", folio),
        (272.8, 768.4, 8.0, _NUNITO, "The Warﬁghter's Fitness Playbook"),
        (39.6, 28.8, 0.0, "Poppins-Regular", "Appendix Title"),
        (39.6, 23.2, 0.0, "NunitoSans-Regular", label),
    ]


PLAYBOOK_SPANS: list[list[tuple[float, float, float, str, str]]] = [
    [
        *_furniture("Understanding Workout Programs", "13"),
        (89.2, 714.4, 21.6, _NUNITO, "Understanding Workout Programs: \n"),
        (89.2, 688.4, 21.6, _NUNITO, "Resistance/Strength Training "),
        (89.2, 651.6, 15.6, _NUNITO, "Repetitions, Volume, and Intensity "),
        (89.2, 625.0, 11.0, _TIMES, "Workout sessions are built around reps and sets. Lower \n"),
        (89.2, 609.2, 11.0, _TIMES, "reps use higher weight. \n"),
        (89.2, 577.5, 11.0, _TIMES, "Repetition ranges are also linked to eﬀort. "),
        (249.9, 469.9, 12.4, _TIMES_BOLD, "Exercise Prescription Guidelines: "),
        (77.7, 402.6, 11.3, _TIMES_BOLD, "Muscular Endurance "),
        (224.0, 402.6, 11.3, _TIMES, "12+ 2-3 5.5-6.5 30 seconds or less "),
        (76.6, 345.0, 10.2, _TIMES_BOLD, "Position "),
        (93.3, 178.4, 11.0, _TIMES, "•"),
        (102.7, 178.4, 11.0, _TIMES_BOLD, " Muscular Endurance: "),
        (102.7, 178.4, 11.0, _TIMES, "The ability to repeatedly contract a muscle \n"),
        (102.7, 165.2, 11.0, _TIMES, "over time. "),
        (93.3, 149.3, 11.0, _TIMES, "•"),
        (102.7, 149.3, 11.0, _TIMES_BOLD, " Resistance Training: "),
        (111.0, 133.5, 11.0, _TIMES, "◦"),
        (120.0, 133.5, 11.0, _TIMES, " Uses external load or bodyweight. "),
        (461.3, 178.4, 11.0, _TIMES_BOLD, "Fatigue Accumulation: "),
        (461.3, 165.2, 11.0, _TIMES, "Remember that fatigue builds up. "),
    ],
    [
        *_furniture("Appendix B Dynamic Warm-Up", " B3"),
        (121.4, 772.3, 17.0, "Poppins-Regular", "1\n"),
        (119.2, 540.0, 17.0, "Poppins-Regular", "2"),
        (83.2, 732.6, 11.6, _SOURCE, "Stand with feet shoulder width apart and \n"),
        (83.2, 718.7, 11.6, _SOURCE, "arms straight out from the body. Make small arm circles. "),
        (89.4, 576.7, 17.5, "SourceSansPro-Bold", "Bird Dog"),
        (89.4, 566.3, 11.5, "SourceSansPro-It", "Upper and Lower Extremity, Core: Low Demand"),
        (83.2, 766.4, 17.5, "SourceSansPro-Bold", "Arm Circles"),
        (83.2, 756.0, 11.5, "SourceSansPro-It", "Upper Extremity: Low Demand"),
        (89.4, 544.3, 11.6, _SOURCE, "Start with hands and knees on the \n"),
        (89.4, 529.9, 11.6, _SOURCE, "ground. Switch sides."),
    ],
    [
        *_furniture("Appendix H", "H1"),
        (39.6, 193.0, 0.0, "NunitoSans-Regular", " Warmups"),
        (89.2, 718.6, 21.6, _NUNITO, "Warmups"),
        (92.3, 587.8, 12.0, _TIMES_BOLD, "2. Arm Rotations (5x) "),
        (92.3, 563.4, 12.0, _TIMES, "Face forward with feet shoulder width apart. Raise \n"),
        (92.3, 549.0, 12.0, _TIMES, "your right arm. "),
    ],
    [
        *_furniture("Appendix A Sample Workouts", "A7"),
        (89.2, 625.0, 11.0, _TIMES, "Walking Knee Hugs x 10 yds "),
    ],
]


def _playbook_manifest() -> corpus.Manifest:
    return _manifest(
        wikipedia=(),
        pdf=(
            corpus.Pdf(
                "us-air-force",
                "warfighters-fitness-playbook-2",
                "The Warfighter's Fitness Playbook 2.0",
                PLAYBOOK_URL,
                hashlib.sha256(PLAYBOOK_BYTES).hexdigest(),
                "playbook",
                (),
                ("Understanding Workout Programs", "Appendix B Dynamic Warm-Up", "Appendix H"),
                PLAYBOOK_FILE,
            ),
        ),
    )


@pytest.fixture
def playbook_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(corpus, "pdf_spans", lambda data: [list(p) for p in PLAYBOOK_SPANS])


def test_a_pdf_supplied_by_hand_is_read_from_its_folder_and_never_fetched(
    playbook_pdf: None, tmp_path: Path
) -> None:
    (tmp_path / PLAYBOOK_FILE).write_bytes(PLAYBOOK_BYTES)

    chunks = corpus.fetch(_playbook_manifest(), _getter({}), tmp_path)

    assert [(c.section, c.text) for c in chunks] == [
        (
            "Understanding Workout Programs: Resistance/Strength Training: "
            "Repetitions, Volume, and Intensity",
            "Workout sessions are built around reps and sets. Lower reps use higher weight.\n"
            "Repetition ranges are also linked to effort.\n"
            "Muscular Endurance: The ability to repeatedly contract a muscle over time.\n"
            "Resistance Training: Uses external load or bodyweight.",
        ),
        (
            "Arm Circles",
            "Upper Extremity: Low Demand\n"
            "Stand with feet shoulder width apart and arms straight out from the body. "
            "Make small arm circles.",
        ),
        (
            "Bird Dog",
            "Upper and Lower Extremity, Core: Low Demand\n"
            "Start with hands and knees on the ground. Switch sides.",
        ),
        (
            "Warmups: Arm Rotations (5x)",
            "Face forward with feet shoulder width apart. Raise your right arm.",
        ),
    ]
    assert [c.link for c in chunks] == [f"{PLAYBOOK_URL}#page={n}" for n in (1, 2, 2, 3)]
    assert {c.source for c in chunks} == {"us-air-force"}
    assert {c.licence for c in chunks} == {"Public domain (US government work)"}


def test_a_file_not_yet_supplied_is_reported_with_where_to_put_it_and_where_it_is_published(
    tmp_path: Path,
) -> None:
    with pytest.raises(corpus.CorpusError) as missing:
        corpus.fetch(_playbook_manifest(), _getter({}), tmp_path)

    assert "supplied by hand" in str(missing.value)
    assert str(tmp_path / PLAYBOOK_FILE) in str(missing.value)
    assert PLAYBOOK_URL in str(missing.value)


def test_a_supplied_file_that_is_not_the_pinned_one_is_refused_with_both_hashes(
    tmp_path: Path,
) -> None:
    (tmp_path / PLAYBOOK_FILE).write_bytes(b"%PDF-another-edition")

    with pytest.raises(corpus.CorpusError) as refused:
        corpus.fetch(_playbook_manifest(), _getter({}), tmp_path)

    assert hashlib.sha256(b"%PDF-another-edition").hexdigest() in str(refused.value)
    assert hashlib.sha256(PLAYBOOK_BYTES).hexdigest() in str(refused.value)


def test_the_manifest_names_a_supplied_file_and_the_parts_taken_from_it(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(
        "version = 1\n\n[[pdf]]\n"
        'source = "us-air-force"\nkey = "playbook"\ntitle = "The Playbook"\n'
        f'url = "{PLAYBOOK_URL}"\nsha256 = "abc"\ncut = "playbook"\n'
        f'parts = ["Appendix H"]\nfile = "{PLAYBOOK_FILE}"\n',
        encoding="utf-8",
    )

    (pin,) = corpus.read_manifest(tmp_path).pdf

    assert (pin.parts, pin.file, pin.chapters) == (("Appendix H",), PLAYBOOK_FILE, ())


def test_the_notice_says_the_playbook_is_public_domain_by_authorship_and_only_its_text() -> None:
    notice = corpus.notice(_playbook_manifest(), [])

    assert "## US Air Force" in notice
    assert "17 U.S.C. 105" in notice
    assert "inferred from its publisher" in notice
    assert "Only its text is taken" in notice
    assert "Only the parts named are used" in notice
    assert (
        f"- *The Warfighter's Fitness Playbook 2.0*, {PLAYBOOK_URL} "
        f"(sha256 `{hashlib.sha256(PLAYBOOK_BYTES).hexdigest()}`), parts "
        "Understanding Workout Programs, Appendix B Dynamic Warm-Up, Appendix H"
    ) in notice


ARTICLE_DOI = "10.1000/squat.1"
ARTICLE_XML = """<article xmlns:xlink="http://www.w3.org/1999/xlink">
<front><article-meta>
<article-id pub-id-type="pmcid">PMC111</article-id>
<article-id pub-id-type="doi">10.1000/squat.1</article-id>
<title-group><article-title>Deep squats and the <italic>knee</italic></article-title></title-group>
<contrib-group>
<contrib contrib-type="author"><name><surname>Rossi</surname><given-names>Anna</given-names></name></contrib>
<contrib contrib-type="author"><name><surname>Bianchi</surname><given-names>Luca M.</given-names></name></contrib>
</contrib-group>
<contrib-group content-type="editor">
<contrib><name><surname>Verdi</surname><given-names>Ed</given-names></name></contrib>
</contrib-group>
<permissions>LICENCE</permissions>
</article-meta></front>
<body>
<boxed-text><p>What is already known on this topic.</p></boxed-text>
<sec sec-type="intro"><title>1. Introduction</title>
<p>Deep squats load the knee [<xref ref-type="bibr" rid="B1">1</xref>,<xref ref-type="bibr" rid="B2">2</xref>].
Depth matters (<xref ref-type="fig" rid="F1">Figure 1</xref>).</p>
<fig id="F1"><label>Figure 1</label><caption><p>A squat at three depths.</p></caption></fig>
</sec>
<sec><title>Methods</title>
<sec><title>Search strategy</title>
<p>We searched three databases.<sup><xref ref-type="bibr" rid="B3">3</xref></sup></p>
<table-wrap><label>Table 1</label><table><tr><td>a cell</td></tr></table></table-wrap>
<list><list-item><p>Trials of adults.</p></list-item><list-item><p>Squats below parallel.</p></list-item></list>
</sec>
</sec>
<sec sec-type="supplementary-material"><title>Supplementary Information</title><p>Below is the link.</p></sec>
<sec><title>Acknowledgments</title><p>We thank the laboratory.</p></sec>
<sec sec-type="ref-list"><title>References</title><p>1. A reference.</p></sec>
</body>
<back><ack><p>Thanks again.</p></ack><ref-list><ref><mixed-citation>A reference.</mixed-citation></ref></ref-list></back>
</article>"""
CC_BY = (
    '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>This '
    "article is distributed under the Creative Commons Attribution License (CC BY).</license-p>"
    "</license>"
)


def _article(licence: str = CC_BY) -> Callable[[str], bytes]:
    return _getter({"rest/PMC111/fullTextXML": ARTICLE_XML.replace("LICENCE", licence).encode()})


def _article_manifest(doi: str = ARTICLE_DOI) -> corpus.Manifest:
    return _manifest(wikipedia=(), article=(corpus.Article(doi, "PMC111"),))


def test_an_article_is_fetched_as_full_text_and_cut_by_its_sections() -> None:
    chunks = corpus.fetch(_article_manifest(), _article())

    assert [(c.section, c.text) for c in chunks] == [
        ("Introduction", "Deep squats load the knee. Depth matters (Figure 1)."),
        (
            "Methods: Search strategy",
            "We searched three databases.\nTrials of adults.\nSquats below parallel.",
        ),
    ]
    assert {c.title for c in chunks} == {"Deep squats and the knee"}
    assert {c.author for c in chunks} == {"Anna Rossi, Luca M. Bianchi"}
    assert {c.link for c in chunks} == {"https://doi.org/10.1000/squat.1"}
    assert {c.licence for c in chunks} == {"CC BY 4.0"}
    assert {(c.source, c.language, c.revision) for c in chunks} == {("europe-pmc", "en", "PMC111")}


@pytest.mark.parametrize(
    ("licence", "said"),
    [
        ('<license xlink:href="https://creativecommons.org/licenses/by-nc/4.0/"/>', "by-nc"),
        ('<license xlink:href="https://creativecommons.org/licenses/by-nd/4.0/"/>', "by-nd"),
        ("<copyright-statement>(c) The Publisher 2015</copyright-statement>", "no licence"),
    ],
)
def test_an_article_whose_own_licence_is_not_cc_by_or_cc0_stops_the_fetch(
    licence: str, said: str
) -> None:
    with pytest.raises(corpus.CorpusError) as refused:
        corpus.fetch(_article_manifest(), _article(licence))

    assert ARTICLE_DOI in str(refused.value)
    assert said in str(refused.value)


def test_an_article_in_the_public_domain_is_taken_as_cc0() -> None:
    cc0 = '<license xlink:href="https://creativecommons.org/publicdomain/zero/1.0/"/>'

    chunks = corpus.fetch(_article_manifest(), _article(cc0))

    assert {c.licence for c in chunks} == {"CC0 1.0"}


def test_a_full_text_that_is_not_the_pinned_article_is_refused() -> None:
    with pytest.raises(corpus.CorpusError, match=r"10\.1000/another.*10\.1000/squat\.1"):
        corpus.fetch(_article_manifest("10.1000/another"), _article())


def test_an_article_with_no_prose_under_a_section_stops_the_fetch() -> None:
    bare = ARTICLE_XML.replace("LICENCE", CC_BY)
    bare = bare[: bare.index("<body>")] + "<body><p>Only a letter.</p></body></article>"

    with pytest.raises(corpus.CorpusError, match="no prose under a section"):
        corpus.fetch(_article_manifest(), _getter({"PMC111": bare.encode()}))


def test_the_notice_lists_each_article_with_its_authors_link_and_licence() -> None:
    manifest = _article_manifest()

    notice = corpus.notice(manifest, corpus.fetch(manifest, _article()))

    assert "## Europe PMC" in notice
    assert (
        "- *Deep squats and the knee*, by Anna Rossi, Luca M. Bianchi, "
        "https://doi.org/10.1000/squat.1 (PMC111), "
        "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)"
    ) in notice


def test_the_manifest_pins_an_article_by_its_doi_and_its_pmc_id(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(
        'version = 1\n\n[[article]]\ndoi = "10.1000/squat.1"\npmcid = "PMC111"\n',
        encoding="utf-8",
    )

    assert corpus.read_manifest(tmp_path).article == (corpus.Article(ARTICLE_DOI, "PMC111"),)
