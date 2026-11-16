"""The corpus: openly licensed pages, pinned by revision, cut into committed chunks."""

from __future__ import annotations

import hashlib
import io
import json
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
SOURCES = {source.name: source for source in (WIKIPEDIA, MEDLINEPLUS, WGER, ARMY, HHS)}
"""The only sources the corpus may hold; anything NonCommercial or copyrighted stays out."""

_MANIFEST_KEYS = {"version", "wikipedia", "medlineplus", "wger", "pdf"}
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


@dataclass(frozen=True)
class Manifest:
    """The corpus version and the pinned list it is cut from."""

    version: int
    wikipedia: tuple[Page, ...]
    medlineplus_date: str | None
    medlineplus_topics: tuple[str, ...]
    wger: tuple[Wger, ...] = ()
    pdf: tuple[Pdf, ...] = ()


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


def fetch(manifest: Manifest, get: Getter) -> list[Chunk]:
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
        chunks.extend(_pdf(pinned, get))
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
    chapters = entry["chapters"]
    if not isinstance(chapters, list):
        raise TypeError("a PDF's chapters are a list of numbers")
    return Pdf(
        source,
        str(entry["key"]),
        str(entry["title"]),
        str(entry["url"]),
        str(entry["sha256"]),
        cut,
        tuple(int(chapter) for chapter in chapters),
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
        lines += [
            "",
            f"## {source.label}",
            "",
            f"Licence: [{source.licence}]({source.licence_url}): {source.terms} "
            f"Author: {source.author}. Only the chapters named are used, and no figure:",
            "",
        ]
        lines.extend(
            f"- *{pin.title}*, {pin.url} (sha256 `{pin.sha256}`), chapters "
            f"{', '.join(str(chapter) for chapter in pin.chapters)}"
            for pin in manifest.pdf
            if pin.source == name
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


def pdf_pages(data: bytes) -> list[str]:
    """The text of each page of a PDF."""
    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]


def _pdf(pin: Pdf, get: Getter) -> list[Chunk]:
    data = get(pin.url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != pin.sha256:
        raise CorpusError(
            f"{pin.url} is not the pinned file of {pin.title}: its sha256 is {digest}, the "
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


def pdf_bookmarked(data: bytes) -> tuple[list[str], list[tuple[int, str]]]:
    """Each page of a PDF as it is laid out, and its bookmarks as (depth, title)."""
    reader = PdfReader(io.BytesIO(data))
    bookmarks: list[tuple[int, str]] = []

    def walk(entries: list[object], depth: int) -> None:
        for entry in entries:
            if isinstance(entry, list):
                walk(entry, depth + 1)
            else:
                bookmarks.append((depth, _clean(str(getattr(entry, "title", "")))))

    walk(list(reader.outline), 0)
    pages = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    return pages, bookmarks


_BULLETS = "⚫•●▪"
_CHAPTER = re.compile(r"^Chapter (\d+)\.")
_CAPTION = re.compile(r"^(Table|Figure) [A-Z]?\d*-\d+\. ")
_CAPTION_NOTE = re.compile(r"^(Note:|Source:|\*)")
_FOLIO = re.compile(r"^\d+\S|\s{2,}\d+$")
_COLUMN_GAP = re.compile(r"\s{5,}")
_BULLET = re.compile(rf"^[{_BULLETS}]\s*")
_UNFINISHED = re.compile(r"[^.!?:;\"\u201d)]$")


def _letters(text: str) -> str:
    """A title as it is compared: its letters and digits, whatever its spacing and punctuation."""
    return re.sub(r"[^A-Za-z0-9]", "", text)


def _bookmarked(data: bytes, pin: Pdf) -> list[tuple[str, str, list[str]]]:
    """A bookmarked PDF's chosen chapters as (bookmark, page anchor, paragraphs).

    Left out: the folio, the boxes set beside the text, and each table or figure from its
    caption to the next paragraph at the margin.
    """
    pages, bookmarks = pdf_bookmarked(data)
    depths = [depth for depth, title in bookmarks if _CHAPTER.match(title)]
    if not depths:
        raise CorpusError(f"{pin.url} has no bookmark named as a chapter; it cannot be cut by them")
    parts: dict[str, set[str]] = {}
    """Each bookmark at the chapters' depth, with the headings bookmarked under it."""
    for depth, title in bookmarks:
        if depth == min(depths):
            part = title
            parts[part] = set()
        elif depth > min(depths) and parts:
            parts[part].add(_letters(title))
    named = {_letters(part): part for part in parts}

    sections: list[tuple[str, str, list[str]]] = []
    part = ""
    for number, page in enumerate(pages, start=1):
        lines = [line.rstrip() for line in page.splitlines()]
        while lines and not lines[-1]:
            lines.pop()
        if lines and _FOLIO.search(lines[-1]):
            running = named.get(_letters(re.sub(r"\s{2,}\d+$", "", lines.pop())), part)
            if running != part:
                part = running
                sections.append((part, f"page={number}", []))
        box: int | None = None
        skipping = False
        after_blank = True
        continues = bool(sections and sections[-1][2] and _UNFINISHED.search(sections[-1][2][-1]))
        index = 0
        while index < len(lines):
            line = lines[index]
            index += 1
            text = line.strip()
            if not text:
                after_blank = True
                continue
            following = lines[index].strip() if index < len(lines) else ""
            two_lines = f"{text} {following}"
            opened = next((c for c in (text, two_lines) if _letters(c) in named), None)
            if opened:
                part = named[_letters(opened)]
                sections.append((part, f"page={number}", []))
                index += opened is two_lines
                after_blank, continues = True, False
                continue
            found = _CHAPTER.match(part)
            if not found or int(found.group(1)) not in pin.chapters:
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
                text = text[: gap.start()]
            two_lines = f"{text} {following}"
            heading = next((c for c in (text, two_lines) if _letters(c) in parts[part]), None)
            if heading:
                sections.append((f"{part}: {_clean(heading)}", f"page={number}", []))
                index += heading is two_lines
                after_blank, continues = True, False
                continue
            if not sections[-1][2]:
                sections[-1] = (sections[-1][0], f"page={number}", [])
            paragraphs = sections[-1][2]
            bullet = _BULLET.match(text)
            text = _BULLET.sub("", text)
            broken = paragraphs and _UNFINISHED.search(paragraphs[-1]) and text[0].islower()
            if paragraphs and not bullet and (continues or broken or not after_blank):
                joint = "" if re.search(r"[a-z]-$", paragraphs[-1]) else " "
                paragraphs[-1] = f"{paragraphs[-1]}{joint}{text}"
            else:
                paragraphs.append(text)
            after_blank, continues = False, False
    return [
        (heading, anchor, [_clean(p) for p in paragraphs])
        for heading, anchor, paragraphs in sections
        if paragraphs
    ]


def _army_manual(data: bytes, pin: Pdf) -> list[tuple[str, str, list[str]]]:
    return _army_sections(pdf_pages(data), pin)


_PARAGRAPH_NUMBER = re.compile(r"^\+?\d+-\d+\.\s*")
_PAGE_ID = re.compile(r"(?:^|\s)(\d+)-\d+(?=\s|$)")


def _army_sections(pages: list[str], pin: Pdf) -> list[tuple[str, str, list[str]]]:
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


_PDF_CUTS: dict[str, Callable[[bytes, Pdf], list[tuple[str, str, list[str]]]]] = {
    "army-manual": _army_manual,
    "bookmarks": _bookmarked,
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
