"""The corpus: openly licensed pages, pinned by revision, cut into committed chunks."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import string
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader


Getter = Callable[[str], bytes]

CORPUS_DIRECTORY = Path(__file__).parent / "data" / "corpus"
_MANIFEST = "manifest.toml"
_CHUNKS = "chunks.jsonl"
_NOTICE = "NOTICE.md"
FILES = (_MANIFEST, _CHUNKS, _NOTICE)
"""Everything the corpus directory holds; vectors are built elsewhere, never committed."""

MAX_CHARS = 1200
"""The longest chunk; a paragraph longer than this is split at its sentences."""


@dataclass(frozen=True)
class Source:
    """A source the corpus may draw from, with the licences its texts may carry."""

    name: str
    author: str
    licences: dict[str, str]
    """Each licence allowed for this source, with the address of its terms."""
    label: str
    """The source as a citation names it."""
    terms: str = ""
    """What the notice says of the licence: where it is stated, and what it asks."""

    @property
    def licence(self) -> str:
        """The licence of a source whose texts all carry one."""
        [only] = self.licences
        return only

    @property
    def licence_url(self) -> str:
        """The terms of a source whose texts all carry one licence."""
        return self.licences[self.licence]


_CC_BY_SA_3 = {"CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/"}
_CC_BY_SA_4 = {"CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/"}
_CC_BY_4 = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/"}
_CC0 = {"CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/"}

WIKIPEDIA = Source("wikipedia", "Wikipedia contributors", _CC_BY_SA_4, "Wikipedia")
MEDLINEPLUS = Source(
    "medlineplus",
    "MedlinePlus, National Library of Medicine",
    {"Public domain (US federal work)": "https://medlineplus.gov/about/using/usingcontent/"},
    "MedlinePlus",
)
WGER = Source("wger", "wger contributors", _CC_BY_SA_3 | _CC_BY_SA_4 | _CC_BY_4 | _CC0, "wger")
ARMY = Source(
    "us-army",
    "Headquarters, Department of the Army",
    {"Public domain (US government work)": "https://www.copyright.gov/title17/92chap1.html#105"},
    "US Army",
    "works of the US Government carry no copyright (17 U.S.C. 105). Approved for public "
    "release; distribution is unlimited.",
)
HHS = Source(
    "hhs",
    "Office of Disease Prevention and Health Promotion, "
    "U.S. Department of Health and Human Services",
    {"Public domain (US government work)": "https://odphp.health.gov/copyright-policy"},
    "HHS",
    "ODPHP's copyright policy says its content \"is in the public domain. This means it may "
    "be freely distributed and copied \u2014 but please include a link to our website and "
    "acknowledge ODPHP as the source.\" Source: ODPHP, https://odphp.health.gov.",
)
USUHS = Source(
    "usuhs",
    "Uniformed Services University of the Health Sciences",
    {"Public domain (US government work)": "https://www.copyright.gov/title17/92chap1.html#105"},
    "USUHS",
    "a US government work by authorship (17 U.S.C. 105), inferred from the authors the PDF "
    "names, a federal university's faculty and Navy medical officers; the guide carries no "
    "licence statement of its own. Material it prints from other publishers is left out.",
)
AIR_FORCE = Source(
    "us-air-force",
    "Air Force Personnel Center, U.S. Department of the Air Force",
    {"Public domain (US government work)": "https://www.copyright.gov/title17/92chap1.html#105"},
    "US Air Force",
    "a US government work by authorship (17 U.S.C. 105), inferred from its publisher, the Air "
    "Force Personnel Center; the playbook carries no licence statement of its own. Only its "
    "text is taken: it does not say where its pictures come from.",
)
EUROPE_PMC = Source(
    "europe-pmc",
    "the authors of each article",
    {
        **{
            f"CC BY {version}": f"https://creativecommons.org/licenses/by/{version}/"
            for version in ("2.0", "2.5", "3.0", "4.0")
        },
        **_CC0,
    },
    "Europe PMC",
)
SOURCES = {
    source.name: source
    for source in (WIKIPEDIA, MEDLINEPLUS, WGER, ARMY, HHS, USUHS, AIR_FORCE, EUROPE_PMC)
}
"""The only sources the corpus may hold; anything NonCommercial or copyrighted stays out."""

_MANIFEST_KEYS = {"version", "wikipedia", "medlineplus", "wger", "pdf", "article"}
"""What a manifest may name: the sources the corpus may hold, and its version."""

_WGER_LICENCES = {
    "CC-BY-SA 3": "CC BY-SA 3.0",
    "CC-BY-SA 4": "CC BY-SA 4.0",
    "CC-BY 4": "CC BY 4.0",
    "CC0": "CC0 1.0",
}
"""wger's own names for the licences the corpus accepts; any other wger licence is left out."""

_SITE = re.compile(r"https?://|www[.]|[.](com|net|org)\b|\bexrx\b", re.IGNORECASE)
"""An author that is a web site rather than a person: the text is the site's, not theirs to license."""

_OTHER_SOURCE = re.compile(r"\bsource\s*:", re.IGNORECASE)
"""A description that names where it was taken from, so it is not its author's own."""

_BORROWED_TEXT = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/"
    "a859101d633a01c4a1a920d6a8ce41dabba0705f/dist/exercises.json"
)
"""bodybuilding.com's exercise steps, as free-exercise-db copied them; read, never kept."""

_PHRASE_WORDS = 8
_BORROWED_SHARE = 0.2
"""A wger text whose eight-word phrases are this much bodybuilding.com's was copied from it."""


@dataclass(frozen=True)
class Page:
    """A Wikipedia page pinned to one revision."""

    language: str
    title: str
    revision: int


@dataclass(frozen=True)
class Wger:
    """wger's exercise descriptions in one language, pinned by a hash of what was taken."""

    language: str
    date: str
    sha256: str


@dataclass(frozen=True)
class Pdf:
    """A PDF pinned by the hash of its file, with how it is cut and the chapters taken."""

    source: str
    key: str
    """What names the text in its chunks' ids; an Army manual's is its publication number."""
    title: str
    url: str
    sha256: str
    cut: str
    chapters: tuple[int, ...]
    parts: tuple[str, ...] = ()
    """The parts taken from a PDF that numbers no chapter, as its pages name them."""
    file: str = ""
    """The file's name in the folder of files supplied by hand, when no script may fetch it."""


@dataclass(frozen=True)
class Article:
    """An open-access article pinned by its DOI and by the PMC id of its full text."""

    doi: str
    pmcid: str


@dataclass(frozen=True)
class Manifest:
    """The corpus version and the pinned list it is cut from."""

    version: int
    wikipedia: tuple[Page, ...]
    medlineplus_date: str | None
    medlineplus_topics: tuple[str, ...]
    wger: tuple[Wger, ...] = ()
    pdf: tuple[Pdf, ...] = ()
    article: tuple[Article, ...] = ()


@dataclass(frozen=True)
class Chunk:
    """A stretch of one source text, with what it takes to cite it."""

    id: str
    source: str
    language: str
    title: str
    section: str
    revision: str
    link: str
    licence: str
    author: str
    text: str


class CorpusError(Exception):
    """The pinned list cannot be fetched or cut as it stands."""


class NotPublished(Exception):
    """The address answered that it holds nothing (HTTP 404)."""


SUPPLIED_ENV_VAR = "TRAINER_SOURCES"


def supplied_directory() -> Path:
    """The folder of files supplied by hand: the one the environment names, or one beside the repo."""
    override = os.environ.get(SUPPLIED_ENV_VAR)
    return Path(override) if override else Path(__file__).parents[3] / "reps-sources"


def fetch(manifest: Manifest, get: Getter, supplied: Path | None = None) -> list[Chunk]:
    """Fetch every pinned text and cut it into chunks, in manifest order."""
    chunks: list[Chunk] = []
    for page in manifest.wikipedia:
        chunks.extend(_wikipedia(page, get))
    if manifest.medlineplus_date is not None:
        chunks.extend(_medlineplus(manifest.medlineplus_date, manifest.medlineplus_topics, get))
    if manifest.wger:
        borrowed = _borrowed_phrases(get)
        for pin in manifest.wger:
            chunks.extend(_wger(pin, get, borrowed))
    for pinned in manifest.pdf:
        chunks.extend(_pdf(pinned, get, supplied or supplied_directory()))
    for article in manifest.article:
        chunks.extend(_article(article, get))
    return chunks


def read_manifest(directory: Path | None = None) -> Manifest:
    """The manifest in `directory`, by default the committed corpus."""
    path = (directory or CORPUS_DIRECTORY) / _MANIFEST
    if not path.is_file():
        raise CorpusError(f"no corpus manifest at {path}; the corpus ships with one in the repo")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        unknown = sorted(set(data) - _MANIFEST_KEYS)
        if unknown:
            raise CorpusError(
                f"the corpus manifest {path} names {', '.join(unknown)}, which is not a source "
                f"the corpus may hold ({', '.join(sorted(_MANIFEST_KEYS - {'version'}))})"
            )
        medlineplus = data.get("medlineplus", {})
        return Manifest(
            wger=tuple(
                Wger(str(pin["language"]), str(pin["date"]), str(pin["sha256"]))
                for pin in data.get("wger", [])
            ),
            pdf=tuple(_pdf_pin(entry, path) for entry in data.get("pdf", [])),
            article=tuple(
                Article(str(entry["doi"]), str(entry["pmcid"]))
                for entry in data.get("article", [])
            ),
            version=int(data["version"]),
            wikipedia=tuple(
                Page(str(page["language"]), str(page["title"]), int(page["revision"]))
                for page in data.get("wikipedia", [])
            ),
            medlineplus_date=medlineplus.get("date"),
            medlineplus_topics=tuple(medlineplus.get("topics", ())),
        )
    except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
        raise CorpusError(f"the corpus manifest {path} is unusable: {error}") from error


_VERSION_LINE = re.compile(r"^version = (\d+)$", re.MULTILINE)


def bump(directory: Path | None = None) -> int:
    """Raise the manifest's version by one, keeping the rest of the file as written; the new version."""
    path = (directory or CORPUS_DIRECTORY) / _MANIFEST
    version = read_manifest(directory).version + 1
    text = path.read_text(encoding="utf-8")
    path.write_bytes(_VERSION_LINE.sub(f"version = {version}", text, count=1).encode("utf-8"))
    return version


def _pdf_pin(entry: dict[str, object], path: Path) -> Pdf:
    source, cut = str(entry["source"]), str(entry["cut"])
    if source not in SOURCES:
        raise CorpusError(
            f"the corpus manifest {path} pins a PDF of {source!r}, which is not a source the "
            f"corpus may hold ({', '.join(sorted(SOURCES))})"
        )
    if cut not in _PDF_CUTS:
        raise CorpusError(
            f"the corpus manifest {path} cuts a PDF as {cut!r}; the cuts are "
            f"{', '.join(sorted(_PDF_CUTS))}"
        )
    chapters, parts = entry.get("chapters", []), entry.get("parts", [])
    if not isinstance(chapters, list) or not isinstance(parts, list):
        raise TypeError("a PDF's chapters are a list of numbers, its parts a list of names")
    return Pdf(
        source,
        str(entry["key"]),
        str(entry["title"]),
        str(entry["url"]),
        str(entry["sha256"]),
        cut,
        tuple(int(chapter) for chapter in chapters),
        tuple(str(part) for part in parts),
        str(entry.get("file", "")),
    )


def read_chunks(directory: Path | None = None) -> list[Chunk]:
    """The chunks in `directory`, by default the committed corpus."""
    path = (directory or CORPUS_DIRECTORY) / _CHUNKS
    if not path.is_file():
        raise CorpusError(f"no chunks at {path}; run `trainer corpus fetch`")
    return [
        Chunk(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def write(chunks: list[Chunk], directory: Path | None = None) -> bool:
    """Write the chunks and the NOTICE beside the manifest. True if either changed."""
    directory = directory or CORPUS_DIRECTORY
    manifest = read_manifest(directory)
    files = {
        _CHUNKS: "".join(
            json.dumps(asdict(chunk), ensure_ascii=False) + "\n" for chunk in chunks
        ),
        _NOTICE: notice(manifest, chunks),
    }
    changed = False
    for name, text in files.items():
        path = directory / name
        encoded = text.encode("utf-8")
        if path.is_file() and path.read_bytes() == encoded:
            continue
        # Binary, so the newlines are LF on every platform.
        path.write_bytes(encoded)
        changed = True
    return changed


def notice(manifest: Manifest, chunks: list[Chunk]) -> str:
    """The NOTICE: each source's licence, how to attribute it, and every pinned text."""
    lines = [
        "# Corpus notice",
        "",
        "<!-- Generated by `trainer corpus fetch` from manifest.toml. Do not edit by hand. -->",
        "",
        f"The texts in `{_CHUNKS}` (corpus version {manifest.version}) are not covered by "
        "the repository's MIT licence. Each keeps its own licence, below; the collection "
        "does not change it.",
        "",
        "Changes: each text was reduced to its prose (markup, references, tables, images, "
        "boxes and back-matter sections removed) and cut into chunks at paragraph and "
        "sentence ends. Nothing was translated, summarised or reworded.",
        "",
        "## Wikipedia",
        "",
        f"Licence: [{WIKIPEDIA.licence}]({WIKIPEDIA.licence_url}). Authors: the contributors "
        "listed in each page's history. Each chunk links the revision it was taken from; "
        "the pinned revisions are:",
        "",
    ]
    lines.extend(
        f"- {page.language}: [{page.title}]({_page_link(page)})" for page in manifest.wikipedia
    )
    if manifest.medlineplus_date is not None:
        lines += [
            "",
            "## MedlinePlus",
            "",
            f"Licence: [{MEDLINEPLUS.licence}]({MEDLINEPLUS.licence_url}). "
            "Source: MedlinePlus, National Library of Medicine. Only NLM-written health-topic "
            "summaries are used; A.D.A.M. and other copyrighted MedlinePlus content is not. "
            "Taken from "
            f"https://medlineplus.gov/xml/mplus_topics_compressed_{manifest.medlineplus_date}.zip:",
            "",
        ]
        lines.extend(f"- {topic}" for topic in manifest.medlineplus_topics)
    if manifest.wger:
        licences = ", ".join(f"[{name}]({url})" for name, url in WGER.licences.items())
        lines += [
            "",
            "## wger",
            "",
            f"Licences: each description keeps the licence its author gave it ({licences}).",
        ]
    for pin in manifest.wger:
        lines += [
            "",
            f"The {pin.language} exercise descriptions of https://wger.de as taken on "
            f"{pin.date} (sha256 `{pin.sha256}`). Each, with its author and licence:",
            "",
        ]
        credited = dict.fromkeys(
            (chunk.title, chunk.author, chunk.licence, chunk.link)
            for chunk in chunks
            if chunk.source == WGER.name and chunk.language == pin.language
        )
        lines.extend(
            f"- [{title}]({link}), by {author}, {licence}"
            for title, author, licence, link in credited
        )
    for name in dict.fromkeys(pin.source for pin in manifest.pdf):
        source = SOURCES[name]
        pins = [pin for pin in manifest.pdf if pin.source == name]
        division = "parts" if any(pin.parts for pin in pins) else "chapters"
        lines += [
            "",
            f"## {source.label}",
            "",
            f"Licence: [{source.licence}]({source.licence_url}): {source.terms} "
            f"Author: {source.author}. Only the {division} named are used, and no figure:",
            "",
        ]
        lines.extend(
            f"- *{pin.title}*, {pin.url} (sha256 `{pin.sha256}`), {division} "
            f"{', '.join(pin.parts or [str(chapter) for chapter in pin.chapters])}"
            for pin in pins
        )
    if manifest.article:
        lines += [
            "",
            f"## {EUROPE_PMC.label}",
            "",
            "Open-access articles, taken as full text from Europe PMC (https://europepmc.org). "
            "Each keeps the licence its publisher gave it, read from the article at every "
            "fetch; only CC BY and CC0 articles are taken. Each, with its authors and licence:",
            "",
        ]
        articles = dict.fromkeys(
            (chunk.title, chunk.author, chunk.link, chunk.revision, chunk.licence)
            for chunk in chunks
            if chunk.source == EUROPE_PMC.name
        )
        lines.extend(
            f"- *{title}*, by {author}, {link} ({revision}), "
            f"[{licence}]({EUROPE_PMC.licences[licence]})"
            for title, author, link, revision, licence in articles
        )
    return "\n".join(lines) + "\n"


_USER_AGENT = "REPS-corpus/1.0 (https://github.com/danielediodati/REPS)"
_PAUSE_S = 1.0
_RETRIES = 4


def http_get(url: str) -> bytes:
    """Fetch `url` politely: a named client, a pause first, and a retry when throttled."""
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", _USER_AGENT)]
    for attempt in range(_RETRIES + 1):
        time.sleep(_PAUSE_S * (2**attempt if attempt else 1))
        try:
            with opener.open(url, timeout=60) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise NotPublished(url) from error
            if error.code != 429 or attempt == _RETRIES:
                raise CorpusError(f"{url} answered HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise CorpusError(
                f"{url} could not be reached ({error.reason}); check the connection"
            ) from error
    raise AssertionError("unreachable")


def _medlineplus(date: str, topics: tuple[str, ...], get: Getter) -> list[Chunk]:
    url = f"https://medlineplus.gov/xml/mplus_topics_compressed_{date}.zip"
    try:
        archive = zipfile.ZipFile(io.BytesIO(get(url)))
    except NotPublished as error:
        raise CorpusError(
            f"MedlinePlus no longer publishes its file of {date} ({url}); it keeps about a "
            "week of them, so pin a date MedlinePlus still publishes "
            "(listed at https://medlineplus.gov/xml.html)"
        ) from error
    [name] = archive.namelist()
    root = ElementTree.fromstring(archive.read(name))
    found = {
        topic.get("title"): topic
        for topic in root.iter("health-topic")
        if topic.get("language") == "English"
    }
    chunks = []
    for title in topics:
        topic = found.get(title)
        if topic is None:
            raise CorpusError(f"MedlinePlus's file of {date} has no English topic {title!r}")
        url = topic.get("url") or ""
        sections = _sections(topic.findtext("full-summary") or "", set())
        chunks.extend(_cut(MEDLINEPLUS, "en", title, title, date, sections, lambda _: url))
    return chunks


def _wikipedia(page: Page, get: Getter) -> list[Chunk]:
    query = urllib.parse.urlencode(
        {
            "action": "parse",
            "oldid": page.revision,
            "prop": "text",
            "parsoid": 1,
            "format": "json",
            "formatversion": 2,
        }
    )
    parsed = json.loads(get(f"https://{page.language}.wikipedia.org/w/api.php?{query}"))
    if "parse" not in parsed:
        raise CorpusError(
            f"{page.language} revision {page.revision} of {page.title!r} could not be read: "
            f"{parsed.get('error', {}).get('info', parsed)}"
        )
    if parsed["parse"]["title"] != page.title:
        raise CorpusError(
            f"{page.language} revision {page.revision} belongs to "
            f"{parsed['parse']['title']!r}, not {page.title!r}; fix the manifest"
        )
    base = _page_link(page)
    return _cut(
        WIKIPEDIA,
        page.language,
        page.title,
        page.title,
        str(page.revision),
        _sections(parsed["parse"]["text"], _SKIPPED[page.language]),
        lambda anchor: f"{base}#{anchor}" if anchor else base,
    )


def _cut(
    source: Source,
    language: str,
    title: str,
    key: str,
    revision: str,
    sections: list[tuple[str, str, list[str]]],
    link: Callable[[str], str],
    *,
    licence: str | None = None,
    author: str | None = None,
) -> list[Chunk]:
    """One text's sections packed into chunks, each linked through its section's anchor."""
    return [
        Chunk(
            id=f"{source.name}/{language}/{key}/{number}",
            source=source.name,
            language=language,
            title=title,
            section=section,
            revision=revision,
            link=link(anchor),
            licence=licence or source.licence,
            author=author or source.author,
            text=text,
        )
        for number, (section, anchor, text) in enumerate(_packed(sections))
    ]


def _wger(pin: Wger, get: Getter, borrowed: set[tuple[str, ...]]) -> list[Chunk]:
    api = "https://wger.de/api/v2"
    licences = {
        entry["id"]: _WGER_LICENCES.get(entry["short_name"].strip())
        for entry in json.loads(get(f"{api}/license/?format=json&limit=100"))["results"]
    }
    languages = {
        entry["short_name"]: entry["id"]
        for entry in json.loads(get(f"{api}/language/?format=json&limit=100"))["results"]
    }
    if pin.language not in languages:
        raise CorpusError(f"wger has no language {pin.language!r}; pin one of {sorted(languages)}")
    taken: list[tuple[int, dict[str, object]]] = []
    url: str | None = f"{api}/exerciseinfo/?format=json&limit=200&offset=0"
    while url:
        page = json.loads(get(url))
        for exercise in page["results"]:
            taken.extend(
                (exercise["id"], translation)
                for translation in exercise["translations"]
                if translation["language"] == languages[pin.language]
                and licences.get(translation["license"])
                and _own_text(translation, borrowed)
            )
        url = page["next"]
    taken.sort(key=lambda item: int(str(item[1]["id"])))
    digest = hashlib.sha256(
        json.dumps(
            [
                [t["id"], t["name"], t["description"], licences[t["license"]], t["license_author"]]
                for _, t in taken
            ],
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if digest != pin.sha256:
        raise CorpusError(
            f"wger's {pin.language} descriptions have changed since {pin.date}; to take them as "
            f'they are now, refresh the manifest with date = today and sha256 = "{digest}"'
        )
    chunks = []
    for exercise_id, translation in taken:
        link = f"https://wger.de/{pin.language}/exercise/{exercise_id}/view/"
        chunks.extend(
            _cut(
                WGER,
                pin.language,
                str(translation["name"]),
                str(translation["id"]),
                pin.date,
                _sections(str(translation["description"]), set()),
                lambda _: link,
                licence=licences[translation["license"]],
                author=str(translation["license_author"]),
            )
        )
    return chunks


def _own_text(translation: dict[str, object], borrowed: set[tuple[str, ...]]) -> bool:
    """A description its author wrote, and that says more than its title."""
    author = str(translation["license_author"])
    description = str(translation["description"])
    if ("@" not in author and _SITE.search(author)) or _OTHER_SOURCE.search(description):
        return False
    phrases = _phrases(description)
    if phrases and sum(phrase in borrowed for phrase in phrases) >= _BORROWED_SHARE * len(phrases):
        return False
    words = _clean(re.sub(r"<[^>]+>", " ", description))
    for word in str(translation["name"]).split():
        words = words.replace(word, " ")
    return len(words.split()) >= 3


def _borrowed_phrases(get: Getter) -> set[tuple[str, ...]]:
    """Every eight-word phrase of bodybuilding.com's exercise steps."""
    return {
        phrase
        for record in json.loads(get(_BORROWED_TEXT))
        for phrase in _phrases(" ".join(record["instructions"]))
    }


def _phrases(text: str) -> list[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", re.sub(r"<[^>]+>", " ", text).lower())
    return [tuple(words[i : i + _PHRASE_WORDS]) for i in range(len(words) - _PHRASE_WORDS + 1)]


_CC_LICENCE = re.compile(r"creativecommons\.org/(?:licenses|publicdomain)/([a-z-]+)/(\d\.\d)")
_ARTICLE_DROPPED = {
    "table-wrap",
    "table-wrap-foot",
    "fig",
    "boxed-text",
    "supplementary-material",
    "disp-formula",
    "fn-group",
    "ref-list",
    "def-list",
    "graphic",
    "media",
    "label",
}
"""What an article's prose leaves out: tables, figures, boxes, formulas, notes and list marks."""
_ARTICLE_BACK_TYPES = {
    "supplementary-material",
    "supplementary-materials",
    "associated-data",
    "ack",
    "fn-group",
    "ref-list",
    "glossary",
    "COI-statement",
    "data-availability",
}
_ARTICLE_BACK_TITLES = {
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
    "footnotes",
    "references",
    "competinginterests",
    "conflictofinterest",
    "conflictsofinterest",
    "authorscontributions",
    "authorcontributions",
    "prepublicationhistory",
    "supportinginformation",
    "supplementaryinformation",
    "supplementarymaterial",
    "supplementarymaterials",
    "electronicsupplementarymaterial",
    "abbreviations",
    "dataavailability",
    "dataavailabilitystatement",
    "funding",
    "fundingstatement",
    "ethicsstatements",
    "associateddata",
    "publishersnote",
}
"""An article's sections that are not its prose, by their titles' letters."""
_SECTION_NUMBER = re.compile(r"^\d+(\.\d+)*\.?\s+")
_EMPTIED_CITATION = re.compile(r"\s*[\[(][\s,;\u2013\u2014-]*[\])]")


def _article(pin: Article, get: Getter) -> list[Chunk]:
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pin.pmcid}/fullTextXML"
    try:
        root = ElementTree.fromstring(get(url))
    except NotPublished as error:
        raise CorpusError(
            f"Europe PMC holds no full text of {pin.pmcid}, pinned for the article {pin.doi} "
            f"({url}); check the PMC id, or unpin the article"
        ) from error
    except ElementTree.ParseError as error:
        raise CorpusError(f"{url} is not the XML of an article: {error}") from error
    meta, body = root.find("front/article-meta"), root.find("body")
    if meta is None or body is None:
        raise CorpusError(f"{url} holds no full text of the article {pin.doi}")
    held = [
        (found.text or "").strip()
        for found in meta.findall("article-id")
        if found.get("pub-id-type") == "doi"
    ]
    if pin.doi.lower() not in (doi.lower() for doi in held):
        raise CorpusError(
            f"the manifest pins the article {pin.doi} as {pin.pmcid}, but Europe PMC's "
            f"{pin.pmcid} is {', '.join(held) or 'an article with no DOI'}; correct the pin"
        )
    title = meta.find("title-group/article-title")
    sections = _article_sections(body)
    if not sections:
        raise CorpusError(
            f"the full text of the article {pin.doi} ({pin.pmcid}) holds no prose under a "
            "section, so nothing can be cut from it; unpin it"
        )
    return _cut(
        EUROPE_PMC,
        "en",
        _clean(_article_text(title)) if title is not None else pin.doi,
        pin.pmcid,
        pin.pmcid,
        sections,
        lambda _: f"https://doi.org/{pin.doi}",
        licence=_article_licence(meta, pin),
        author=_article_authors(meta, pin),
    )


def _article_licence(meta: ElementTree.Element, pin: Article) -> str:
    """The licence the article states for itself; anything but CC BY or CC0 stops the fetch."""
    stated = "".join(
        ElementTree.tostring(licence, encoding="unicode") for licence in meta.iter("license")
    )
    found = sorted(set(_CC_LICENCE.findall(stated)))
    only = "only articles under CC BY or CC0 are taken, so unpin it"
    if not found:
        raise CorpusError(
            f"the article {pin.doi} ({pin.pmcid}) states no licence of its own in its full "
            f"text; {only}"
        )
    names = [
        "CC0 1.0" if kind == "zero" else f"CC BY {version}" if kind == "by" else f"{kind} {version}"
        for kind, version in found
    ]
    if len(names) != 1 or names[0] not in EUROPE_PMC.licences:
        raise CorpusError(
            f"the article {pin.doi} ({pin.pmcid}) states the licence {', '.join(names)}; {only}"
        )
    return names[0]


def _article_authors(meta: ElementTree.Element, pin: Article) -> str:
    names = []
    for group in meta.findall("contrib-group"):
        for contrib in group.findall("contrib"):
            if contrib.get("contrib-type", group.get("content-type", "author")) != "author":
                continue
            name = contrib.find("name")
            if name is None:
                name = contrib.find("name-alternatives/name")
            written = (
                f"{name.findtext('given-names') or ''} {name.findtext('surname') or ''}"
                if name is not None
                else contrib.findtext("collab") or ""
            )
            if _clean(written):
                names.append(_clean(written))
    if not names:
        raise CorpusError(
            f"the article {pin.doi} ({pin.pmcid}) names no author in its full text, and its "
            "licence asks that they be credited; unpin it"
        )
    return ", ".join(names)


def _article_sections(body: ElementTree.Element) -> Sections:
    """An article's prose as (section titles from the outermost, no anchor, paragraphs)."""
    sections: Sections = []

    def walk(section: ElementTree.Element, above: list[str]) -> None:
        heading = section.find("title")
        named = _clean(_article_text(heading)) if heading is not None else ""
        title = _SECTION_NUMBER.sub("", named)
        if (
            section.get("sec-type") in _ARTICLE_BACK_TYPES
            or _letters(title).lower() in _ARTICLE_BACK_TITLES
        ):
            return
        path = [*above, title] if title else above
        paragraphs: list[str] = []
        sections.append((": ".join(path), "", paragraphs))
        for child in section:
            if child.tag == "p":
                paragraphs.append(_article_prose(child))
            elif child.tag == "list":
                paragraphs.extend(_article_prose(item) for item in child.findall("list-item"))
            elif child.tag == "sec":
                walk(child, path)

    for section in body.findall("sec"):
        walk(section, [])
    return [
        (heading, anchor, [paragraph for paragraph in paragraphs if paragraph])
        for heading, anchor, paragraphs in sections
        if any(paragraphs)
    ]


def _article_prose(element: ElementTree.Element) -> str:
    """An element's text with its citations gone, and the brackets and spaces they leave."""
    text = _EMPTIED_CITATION.sub("", _article_text(element))
    return re.sub(r"\s+([.,;:])", r"\1", _clean(text))


def _article_text(element: ElementTree.Element) -> str:
    """An element's text without what `_ARTICLE_DROPPED` names or a citation of the references."""
    parts = [element.text or ""]
    for child in element:
        cited = child.tag == "xref" and child.get("ref-type") == "bibr"
        raised = child.tag == "sup" and child.find("xref[@ref-type='bibr']") is not None
        if child.tag not in _ARTICLE_DROPPED and not cited and not raised:
            parts.append(_article_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def pdf_pages(data: bytes) -> list[str]:
    """The text of each page of a PDF."""
    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]


def _pdf(pin: Pdf, get: Getter, supplied: Path) -> list[Chunk]:
    origin = str(supplied / pin.file) if pin.file else pin.url
    if pin.file and not Path(origin).is_file():
        raise CorpusError(
            f"{pin.title} is supplied by hand and is not there yet: its publisher gives it "
            f"to no script, so open {pin.url} in a browser and save the file as {origin}"
        )
    data = Path(origin).read_bytes() if pin.file else get(pin.url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != pin.sha256:
        raise CorpusError(
            f"{origin} is not the pinned file of {pin.title}: its sha256 is {digest}, the "
            f"manifest pins {pin.sha256}; if the publisher has issued a new edition, read it "
            "and refresh the pin"
        )
    return _cut(
        SOURCES[pin.source],
        "en",
        pin.title,
        pin.key,
        digest,
        _PDF_CUTS[pin.cut](data, pin),
        lambda anchor: f"{pin.url}#{anchor}",
    )


Bookmark = tuple[int, str, int | None]
"""A PDF bookmark: its depth, its title and the page it opens, when the file says which."""


def pdf_bookmarked(data: bytes) -> tuple[list[str], list[Bookmark]]:
    """Each page of a PDF as it is laid out, and its bookmarks."""
    reader = PdfReader(io.BytesIO(data))
    bookmarks: list[Bookmark] = []

    def walk(entries: list[object], depth: int) -> None:
        for entry in entries:
            if isinstance(entry, list):
                walk(entry, depth + 1)
                continue
            try:
                opened = reader.get_destination_page_number(entry)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001 - a bookmark that opens nothing has no page
                opened = None
            page = None if opened is None else opened + 1
            bookmarks.append((depth, _clean(str(getattr(entry, "title", ""))), page))

    walk(list(reader.outline), 0)
    pages = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    return pages, bookmarks


_BULLETS = "⚫•●▪"
_CHAPTER = re.compile(r"^Chapter (\d+)\b")
_CAPTION = re.compile(r"^(Table|Figure) [A-Z]?\d*-\d+\.\s")
_CAPTION_NOTE = re.compile(r"^(Note:|Source:|\*)")
_FOLIO = re.compile(r"^\d+(?=\S|\s{3})|\s{2,}\d+$")
_COLUMN_GAP = re.compile(r"\s{5,}")
_CELL_GAP = re.compile(r"\s{4,}")
"""The space between two cells of a table row, once a table is being left out."""
_BULLET = re.compile(rf"^[{_BULLETS}]\s*")
_UNFINISHED = re.compile(r"[^.!?:;\"”)]$")
_BACK_MATTER = {"Resource", "Resources", "References", "Acknowledgment", "Acknowledgments"}
"""Headings inside a chapter that hold citations and thanks rather than prose."""

Sections = list[tuple[str, str, list[str]]]
"""A text as (heading, anchor, paragraphs)."""


def _letters(text: str) -> str:
    """A title as it is compared: its letters and digits, whatever its spacing and punctuation."""
    return re.sub(r"[^A-Za-z0-9]", "", text)


@dataclass(frozen=True)
class _Part:
    """A bookmark at the chapters' depth, with the headings bookmarked under it."""

    title: str
    page: int | None
    headings: frozenset[str]

    @property
    def chapter(self) -> int | None:
        """The chapter's number; None for a part that is not a chapter."""
        found = _CHAPTER.match(self.title)
        return int(found.group(1)) if found else None


def _parts(bookmarks: list[Bookmark], pin: Pdf) -> list[_Part]:
    depths = [depth for depth, title, _ in bookmarks if _CHAPTER.match(title)]
    if not depths:
        raise CorpusError(f"{pin.url} has no bookmark named as a chapter; it cannot be cut by them")
    parts: list[tuple[str, int | None, set[str]]] = []
    for depth, title, page in bookmarks:
        if depth == min(depths):
            parts.append((title, page, set()))
        elif depth > min(depths) and parts:
            parts[-1][2].add(_letters(title))
    return [_Part(title, page, frozenset(headings)) for title, page, headings in parts]


def _page_lines(page: str, pin: Pdf) -> tuple[list[str], str]:
    """A page's lines and its folio, the last line when it is a page number or a running title."""
    lines = [line.rstrip() for line in page.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return [], ""
    last = lines[-1].strip()
    if _FOLIO.search(last) or _letters(pin.title).startswith(_letters(last)):
        return lines[:-1], _FOLIO.sub("", last).strip()
    return lines, ""


def _titled(lines: list[str], index: int, titles: frozenset[str] | set[str]) -> tuple[str, int]:
    """The title that starts at `lines[index]`, alone or with the next line, and how many lines it takes."""
    text = lines[index].strip()
    following = lines[index + 1].strip() if index + 1 < len(lines) else ""
    if _letters(text) in titles:
        return _clean(text), 1
    if following and _letters(f"{text}{following}") in titles:
        return _clean(f"{text} {following}"), 2
    return "", 0


def _joined(paragraph: str, text: str, *, hyphenated: bool) -> str:
    """A paragraph with its next line; `hyphenated` says a line-end hyphen breaks a word."""
    if re.search(r"[A-Za-z0-9]-$", paragraph):
        if hyphenated and text[0].islower() and paragraph[-2].isalpha():
            return f"{paragraph[:-1]}{text}"
        return f"{paragraph}{text}"
    return f"{paragraph} {text}"


def _written(sections: Sections) -> Sections:
    return [
        (heading, anchor, [_clean(p) for p in paragraphs])
        for heading, anchor, paragraphs in sections
        if paragraphs
    ]


def _bookmarked(data: bytes, pin: Pdf) -> Sections:
    """A bookmarked PDF's chosen chapters as (bookmark, page anchor, paragraphs), prose only."""
    pages, bookmarks = pdf_bookmarked(data)
    named = {_letters(part.title): part for part in _parts(bookmarks, pin)}
    sections: Sections = []
    part: _Part | None = None
    for number, page in enumerate(pages, start=1):
        lines, folio = _page_lines(page, pin)
        running = named.get(_letters(folio), part)
        if running is not part:
            part = running
            sections.append((running.title if running else "", f"page={number}", []))
        box: int | None = None
        skipping = False
        after_blank = True
        continues = bool(sections and sections[-1][2] and _UNFINISHED.search(sections[-1][2][-1]))
        index = 0
        while index < len(lines):
            line = lines[index]
            text = line.strip()
            if not text:
                after_blank = True
                index += 1
                continue
            opened, taken = _titled(lines, index, set(named))
            if opened:
                part = named[_letters(opened)]
                sections.append((part.title, f"page={number}", []))
                index += taken
                after_blank, continues = True, False
                continue
            index += 1
            if part is None or part.chapter not in pin.chapters:
                continue
            indent = len(line) - len(line.lstrip())
            if box is not None and indent >= box - 3:
                continue
            if _CAPTION.match(text):
                skipping = True
            elif skipping and after_blank and indent == 0 and not _CAPTION_NOTE.match(text):
                skipping = False
            if skipping:
                after_blank = False
                continue
            gap = _COLUMN_GAP.search(text)
            if gap and not _BULLET.match(text):
                box = indent + gap.end()
                lines[index - 1] = text = text[: gap.start()]
            heading, taken = _titled(lines, index - 1, part.headings)
            if heading:
                sections.append((f"{part.title}: {heading}", f"page={number}", []))
                index += taken - 1
                after_blank, continues = True, False
                continue
            if not sections[-1][2]:
                sections[-1] = (sections[-1][0], f"page={number}", [])
            paragraphs = sections[-1][2]
            bullet = _BULLET.match(text)
            text = _BULLET.sub("", text)
            broken = paragraphs and _UNFINISHED.search(paragraphs[-1]) and text[:1].islower()
            if paragraphs and not bullet and (continues or broken or not after_blank):
                paragraphs[-1] = _joined(paragraphs[-1], text, hyphenated=False)
            else:
                paragraphs.append(text)
            after_blank, continues = False, False
    return _written(sections)


def _indented(data: bytes, pin: Pdf) -> Sections:
    """A PDF of indented paragraphs: its chosen chapters as (bookmark, page anchor, paragraphs)."""
    pages, bookmarks = pdf_bookmarked(data)
    parts = _parts(bookmarks, pin)
    sections: Sections = []
    for position, part in enumerate(parts):
        if part.chapter not in pin.chapters:
            continue
        end = next((later.page for later in parts[position + 1 :] if later.page), len(pages) + 1)
        if part.page is None:
            raise CorpusError(f"{pin.url} does not say which page opens {part.title!r}")
        sections.append((part.title, f"page={part.page}", []))
        left_out = False
        dropping = False
        for number in range(part.page, end):
            lines, _ = _page_lines(pages[number - 1], pin)
            margin = min(
                (len(line) - len(line.lstrip()) for line in lines if line.strip()), default=0
            )
            open_as: str | None = None
            hanging = 0
            at_top = True
            index = 0
            while index < len(lines):
                line = lines[index]
                text = line.strip()
                if not text:
                    open_as = None
                    index += 1
                    continue
                indent = len(line) - len(line.lstrip()) - margin
                heading, taken = _titled(lines, index, part.headings) if indent <= 1 else ("", 0)
                if heading:
                    sections.append((f"{part.title}: {heading}", f"page={number}", []))
                    left_out = heading in _BACK_MATTER
                    index += taken
                    open_as, dropping, at_top = None, False, False
                    continue
                index += 1
                written = sections[-1][2]
                carried = at_top and bool(written) and _UNFINISHED.search(written[-1])
                at_top = False
                if left_out:
                    continue
                if _CAPTION.match(text):
                    open_as, dropping = None, True
                    continue
                if not sections[-1][2]:
                    sections[-1] = (sections[-1][0], f"page={number}", [])
                paragraphs = sections[-1][2]
                if _BULLET.match(text):
                    paragraphs.extend(
                        item.strip() for item in re.split(rf"[{_BULLETS}]", text) if item.strip()
                    )
                    open_as, hanging, dropping = "bullet", indent, False
                elif indent <= 1:
                    if open_as or carried:
                        paragraphs[-1] = _joined(paragraphs[-1], text, hyphenated=True)
                        open_as = open_as or "paragraph"
                    elif not dropping:
                        paragraphs.append(text)
                        open_as = "paragraph"
                elif open_as == "bullet" and hanging + 3 <= indent <= hanging + 8:
                    paragraphs[-1] = _joined(paragraphs[-1], text, hyphenated=True)
                elif not (dropping and _in_cells(lines, index)) and _opens_paragraph(
                    lines, index, margin, part
                ):
                    paragraphs.append(text)
                    open_as, dropping = "paragraph", False
                else:
                    open_as, dropping = None, True
    return _written(sections)


def _in_cells(lines: list[str], index: int) -> bool:
    """Whether `lines[index]` is split into a table's cells."""
    return index < len(lines) and bool(_CELL_GAP.search(lines[index].strip()))


def _opens_paragraph(lines: list[str], index: int, margin: int, part: _Part) -> bool:
    """Whether the indented line before `lines[index]` opens a paragraph: prose or a list follows it."""
    if index >= len(lines) or not lines[index].strip():
        return False
    following = lines[index].strip()
    if _CAPTION.match(following) or _titled(lines, index, part.headings)[0]:
        return False
    indent = len(lines[index]) - len(lines[index].lstrip()) - margin
    return indent <= 1 or bool(_BULLET.match(following))


Span = tuple[float, float, float, str, str]
"""A run of a PDF's text: its x and y from the page's bottom left, its size, typeface and text."""


def pdf_spans(data: bytes) -> list[list[Span]]:
    """Each page of a PDF as its runs of text; one set sideways has no size."""
    pages: list[list[Span]] = []
    for page in PdfReader(io.BytesIO(data)).pages:
        spans: list[Span] = []

        def visit(
            text: str,
            cm: list[float],
            tm: list[float],
            font: dict[str, object] | None,
            size: float,
            spans: list[Span] = spans,
        ) -> None:
            if text.strip():
                face = str((font or {}).get("/BaseFont", "")).lstrip("/").split("+")[-1]
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                spans.append((x, y, abs(tm[0] * cm[0]) * size, face, text))

        page.extract_text(visitor_text=visit)
        pages.append(spans)
    return pages


_PLAYBOOK_LABEL = "NunitoSans-Regular"
_PLAYBOOK_HEADING = "NunitoSans-BoldItalic"
_PLAYBOOK_ENTRY = "SourceSansPro"
_PLAYBOOK_PROSE = "TimesNewRoman"
_PLAYBOOK_PROSE_SIZES = {11.0, 11.6, 12.0}
_PLAYBOOK_COLUMN = 400
"""Where the playbook's main column ends; what starts past it is a box beside the text."""
_PARAGRAPH_GAP = 20
_NUMBERED = re.compile(r"^\d+\.\s+(?=\S)")
_PLAYBOOK_BULLETS = "•◦▪"
"""The marks of a list item, the outermost first."""


def _playbook(data: bytes, pin: Pdf) -> Sections:
    """The Air Force playbook's chosen parts as (heading, page anchor, paragraphs), by typeface."""
    sections: Sections = []
    for number, spans in enumerate(pdf_spans(data), start=1):
        label = _clean(
            " ".join(
                text for _, _, size, face, text in spans if face == _PLAYBOOK_LABEL and size < 1
            )
        )
        if not any(label.startswith(part) for part in pin.parts):
            continue
        if any(face.startswith(_PLAYBOOK_ENTRY) for _, _, _, face, _ in spans):
            sections += _playbook_entries(spans, number)
        else:
            sections += _playbook_prose(spans, label, number)
    return _written(sections)


def _set_lines(spans: list[Span]) -> list[tuple[float, str, float, str]]:
    """Runs gathered into lines, top to bottom, as (y, the face and size of its first run, text)."""
    lines: list[list[Span]] = []
    for span in sorted(spans, key=lambda span: -span[1]):
        if lines and abs(lines[-1][0][1] - span[1]) <= 2:
            lines[-1].append(span)
        else:
            lines.append([span])
    return [
        (
            line[0][1],
            line[0][3] if len({face for _, _, _, face, _ in line}) == 1 else "",
            line[0][2],
            _clean("".join(text for *_, text in line).replace("ﬁ", "fi").replace("ﬀ", "ff")),
        )
        for line in (sorted(line, key=lambda span: span[0]) for line in lines)
    ]


def _playbook_entries(spans: list[Span], number: int) -> Sections:
    """An exercise library page: each entry's name, then what it trains and how it is done."""
    entries: list[tuple[list[str], list[str], list[str]]] = []
    for _, face, _, text in _set_lines(
        [span for span in spans if span[3].startswith((_PLAYBOOK_ENTRY, _PLAYBOOK_PROSE))]
    ):
        if face.endswith("-Bold"):
            if entries and not entries[-1][1] and not entries[-1][2]:
                entries[-1][0].append(text)
            else:
                entries.append(([text], [], []))
        elif entries:
            entries[-1][1 if face.endswith("-It") else 2].append(text)
    return [
        (" ".join(name), f"page={number}", [" ".join(trains), " ".join(done)])
        for name, trains, done in entries
        if done
    ]


def _playbook_prose(spans: list[Span], label: str, number: int) -> Sections:
    """A page of prose: its main column's paragraphs under the page's title and headings."""
    kept = [
        span
        for span in spans
        if (span[3] == _PLAYBOOK_HEADING and span[2] >= 15)
        or (
            span[3].startswith(_PLAYBOOK_PROSE)
            and round(span[2], 1) in _PLAYBOOK_PROSE_SIZES
            and span[0] < _PLAYBOOK_COLUMN
        )
    ]
    sections: Sections = []
    title: list[str] = []
    titled = False
    last = 0.0
    for y, face, size, text in _set_lines(kept):
        numbered = _NUMBERED.match(text) if face.endswith("-BoldMT") else None
        if face == _PLAYBOOK_HEADING and size >= 20:
            title = [*title, text] if titled else [text]
            titled = True
            continue
        titled = False
        above = " ".join(title).rstrip(": ") or label
        if face == _PLAYBOOK_HEADING or numbered:
            heading = text[numbered.end() :] if numbered else text
            sections.append((f"{above}: {heading.rstrip(': ')}", f"page={number}", []))
            continue
        if not sections:
            sections.append((above, f"page={number}", []))
        paragraphs = sections[-1][2]
        item = text.lstrip(_PLAYBOOK_BULLETS + " ")
        nested = text[0] in _PLAYBOOK_BULLETS[1:]
        labelled = nested and bool(paragraphs) and paragraphs[-1][-1] == ":"
        if text[0] in _PLAYBOOK_BULLETS and not labelled:
            if item:
                paragraphs.append(item)
        elif paragraphs and (labelled or last - y <= _PARAGRAPH_GAP):
            paragraphs[-1] = f"{paragraphs[-1]} {item}"
        else:
            paragraphs.append(text)
        last = y
    return sections


def _army_manual(data: bytes, pin: Pdf) -> Sections:
    return _army_sections(pdf_pages(data), pin)


_PARAGRAPH_NUMBER = re.compile(r"^\+?\d+-\d+\.\s*")
_PAGE_ID = re.compile(r"(?:^|\s)(\d+)-\d+(?=\s|$)")


def _army_sections(pages: list[str], pin: Pdf) -> Sections:
    """A manual's chosen chapters as (heading, page anchor, paragraphs), running heads dropped."""
    sections: list[tuple[str, str, list[str]]] = []
    titles: dict[int, str] = {}
    for number, page in enumerate(pages, start=1):
        lines = [line.strip() for line in page.splitlines()]
        header = next((line for line in lines if pin.key in line), None)
        found = _PAGE_ID.search(header) if header else None
        chapter = int(found.group(1)) if found else None
        if chapter not in pin.chapters:
            continue
        running = {f"Chapter {chapter}"}
        for index, line in enumerate(lines[:-1]):
            if line == f"Chapter {chapter}" and chapter not in titles:
                titles[chapter] = lines[index + 1].lstrip("+").strip()
        running.add(titles.get(chapter, ""))
        heading_open = False
        for line in lines:
            if (
                not line
                or pin.key in line
                or line.lstrip("+").strip() in running
                or re.match(r"^Figure \d+-\d+\.", line)
            ):
                continue
            if _is_heading(line):
                if heading_open:
                    sections[-1] = (f"{sections[-1][0]} {_heading(line)}", sections[-1][1], [])
                else:
                    sections.append((_heading(line), f"page={number}", []))
                heading_open = True
                continue
            heading_open = False
            if not sections:
                sections.append((titles.get(chapter, ""), f"page={number}", []))
            paragraphs = sections[-1][2]
            starts = _PARAGRAPH_NUMBER.match(line) or line[0] in _BULLETS
            text = _PARAGRAPH_NUMBER.sub("", line).lstrip(_BULLETS).strip()
            if starts or not paragraphs:
                paragraphs.append(text)
            else:
                paragraphs[-1] = f"{paragraphs[-1]} {text}"
    return [
        (heading, anchor, [_clean(p) for p in paragraphs if _clean(p)])
        for heading, anchor, paragraphs in sections
        if any(_clean(p) for p in paragraphs)
    ]


def _is_heading(line: str) -> bool:
    """An all-capitals line; one with quotes or a full stop is a spoken command, not a title."""
    return (
        line == line.upper()
        and re.search(r"[A-Z]{2}", line) is not None
        and line[0] not in _BULLETS
        and not re.search(r"[\"“”]|\.$", line)
    )


def _heading(line: str) -> str:
    """An all-capitals heading, written the way a title reads."""
    return string.capwords(re.sub(r"^\d+\.\s*", "", _clean(line.lstrip("+"))))


_PDF_CUTS: dict[str, Callable[[bytes, Pdf], Sections]] = {
    "army-manual": _army_manual,
    "bookmarks": _bookmarked,
    "indented": _indented,
    "playbook": _playbook,
}
"""How a pinned PDF is read into (heading, page anchor, paragraphs), by the name its pin gives."""


def _page_link(page: Page) -> str:
    """The address of a page's pinned revision."""
    title = urllib.parse.quote(page.title.replace(" ", "_"), safe="()")
    return f"https://{page.language}.wikipedia.org/w/index.php?title={title}&oldid={page.revision}"


_SKIPPED = {
    "en": {
        "References", "Notes", "See also", "External links", "Further reading",
        "Bibliography", "Sources", "Citations", "Footnotes",
    },
    "it": {
        "Note", "Bibliografia", "Voci correlate", "Collegamenti esterni", "Altri progetti",
        "Riferimenti", "Fonti", "Riferimenti bibliografici",
    },
}
"""Back-matter sections, which hold links and citations rather than prose."""


def _sections(html: str, skipped: set[str]) -> list[tuple[str, str, list[str]]]:
    """The prose of a page as (heading, anchor, paragraphs), back matter left out."""
    reader = _Prose()
    reader.feed(html)
    reader.close()
    sections: list[tuple[str, str, list[str]]] = []
    dropping = False
    for kind, level, anchor, text in reader.blocks:
        if kind == "heading":
            if level == 2:
                dropping = text in skipped
            if not dropping:
                sections.append((text, anchor, []))
        elif not dropping:
            if not sections:
                sections.append(("", "", []))
            sections[-1][2].append(text)
    return [section for section in sections if section[2]]


def _packed(
    sections: list[tuple[str, str, list[str]]],
) -> Iterator[tuple[str, str, str]]:
    """Each section's paragraphs packed into chunks of at most MAX_CHARS."""
    for heading, anchor, paragraphs in sections:
        current: list[str] = []
        for piece in (p for paragraph in paragraphs for p in _pieces(paragraph)):
            if current and len("\n".join([*current, piece])) > MAX_CHARS:
                yield heading, anchor, "\n".join(current)
                current = []
            current.append(piece)
        if current:
            yield heading, anchor, "\n".join(current)


def _pieces(paragraph: str) -> list[str]:
    """A paragraph, split at sentence ends when it is longer than MAX_CHARS."""
    if len(paragraph) <= MAX_CHARS:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
        if current and len(current) + 1 + len(sentence) > MAX_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        pieces.append(current)
    return pieces


_BLOCKS = {"p", "li", "dd", "dt", "blockquote", "div", "section", "ul", "ol", "dl"}
_HEADINGS = {"h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_DROPPED_TAGS = {"style", "script", "table", "figure", "math", "noscript", "link", "meta"}
_DROPPED_CLASSES = {
    "hatnote", "navbox", "infobox", "reflist", "references", "mw-references-wrap",
    "reference", "mw-ref", "noprint", "metadata", "ambox", "sidebar", "thumb",
    "gallery", "mw-editsection", "shortdescription", "mw-empty-elt", "Inline-Template",
    "mw-references", "toc", "vertical-navbox", "navigation-not-searchable", "portal",
}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Prose(HTMLParser):
    """Reads headings and paragraphs out of a page, dropping references, tables and boxes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, int, str, str]] = []
        self._dropping: list[str] = []
        self._text: list[str] = []
        self._heading: tuple[int, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            return
        if self._dropping:
            self._dropping.append(tag)
            return
        found = dict(attrs)
        classes = set((found.get("class") or "").split())
        if tag in _DROPPED_TAGS or classes & _DROPPED_CLASSES or found.get("role") == "note":
            self._dropping.append(tag)
            return
        if tag in _HEADINGS:
            self._flush()
            self._heading = (_HEADINGS[tag], found.get("id") or "")
        elif tag in _BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if self._dropping:
            self._dropping.pop()
            return
        if tag in _HEADINGS and self._heading is not None:
            level, anchor = self._heading
            text = _clean("".join(self._text))
            self._text = []
            self._heading = None
            if text:
                self.blocks.append(("heading", level, anchor, text))
        elif tag in _BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._dropping:
            self._text.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        if self._heading is not None:
            return
        text = _clean("".join(self._text))
        self._text = []
        if text:
            self.blocks.append(("paragraph", 0, "", text))


def _clean(text: str) -> str:
    """Whitespace collapsed to single spaces, and trimmed."""
    return re.sub(r"\s+", " ", text).strip()
