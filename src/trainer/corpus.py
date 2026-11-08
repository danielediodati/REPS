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

from trainer.engine import catalog

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

    @property
    def licence(self) -> str:
        """The licence of a source whose texts all carry one."""
        [only] = self.licences
        return only


_CC_BY_SA_3 = {"CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/"}
_CC_BY_SA_4 = {"CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/"}
_CC_BY_4 = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/"}
_CC0 = {"CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/"}

WIKIPEDIA = Source("wikipedia", "Wikipedia contributors", _CC_BY_SA_4)
MEDLINEPLUS = Source(
    "medlineplus",
    "MedlinePlus, National Library of Medicine",
    {"Public domain (US federal work)": "https://medlineplus.gov/about/using/usingcontent/"},
)
EXERCISES = Source(
    "free-exercise-db", "free-exercise-db contributors", {"The Unlicense": "https://unlicense.org/"}
)
WGER = Source("wger", "wger contributors", _CC_BY_SA_3 | _CC_BY_SA_4 | _CC_BY_4 | _CC0)
ARMY = Source(
    "us-army",
    "Headquarters, Department of the Army",
    {"Public domain (US government work)": "https://www.copyright.gov/title17/92chap1.html#105"},
)
SOURCES = {source.name: source for source in (WIKIPEDIA, MEDLINEPLUS, EXERCISES, WGER, ARMY)}
"""The only sources the corpus may hold; anything NonCommercial or copyrighted stays out."""

_WGER_LICENCES = {
    "CC-BY-SA 3": "CC BY-SA 3.0",
    "CC-BY-SA 4": "CC BY-SA 4.0",
    "CC-BY 4": "CC BY 4.0",
    "CC0": "CC0 1.0",
}
"""wger's own names for the licences the corpus accepts; any other wger licence is left out."""


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
class ArmyPublication:
    """A US Army manual pinned by the hash of its PDF, with the chapters taken from it."""

    publication: str
    title: str
    url: str
    sha256: str
    chapters: tuple[int, ...]


@dataclass(frozen=True)
class Manifest:
    """The corpus version and the pinned list it is cut from."""

    version: int
    wikipedia: tuple[Page, ...]
    medlineplus_date: str | None
    medlineplus_topics: tuple[str, ...]
    exercises_commit: str | None
    wger: Wger | None = None
    army: tuple[ArmyPublication, ...] = ()


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
    if manifest.exercises_commit is not None:
        chunks.extend(_exercises(manifest.exercises_commit))
    if manifest.wger is not None:
        chunks.extend(_wger(manifest.wger, get))
    for publication in manifest.army:
        chunks.extend(_army(publication, get))
    return chunks


def read_manifest(directory: Path | None = None) -> Manifest:
    """The manifest in `directory`, by default the committed corpus."""
    path = (directory or CORPUS_DIRECTORY) / _MANIFEST
    if not path.is_file():
        raise CorpusError(f"no corpus manifest at {path}; the corpus ships with one in the repo")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        medlineplus = data.get("medlineplus", {})
        wger = data.get("wger")
        return Manifest(
            wger=(
                Wger(str(wger["language"]), str(wger["date"]), str(wger["sha256"]))
                if wger is not None
                else None
            ),
            army=tuple(
                ArmyPublication(
                    str(entry["publication"]),
                    str(entry["title"]),
                    str(entry["url"]),
                    str(entry["sha256"]),
                    tuple(int(chapter) for chapter in entry["chapters"]),
                )
                for entry in data.get("army", [])
            ),
            version=int(data["version"]),
            wikipedia=tuple(
                Page(str(page["language"]), str(page["title"]), int(page["revision"]))
                for page in data.get("wikipedia", [])
            ),
            medlineplus_date=medlineplus.get("date"),
            medlineplus_topics=tuple(medlineplus.get("topics", ())),
            exercises_commit=data.get("free-exercise-db", {}).get("commit"),
        )
    except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
        raise CorpusError(f"the corpus manifest {path} is unusable: {error}") from error


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
        f"Licence: [{WIKIPEDIA.licence}]({WIKIPEDIA.licences[WIKIPEDIA.licence]}). Authors: the contributors "
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
            f"Licence: [{MEDLINEPLUS.licence}]({MEDLINEPLUS.licences[MEDLINEPLUS.licence]}). "
            "Source: MedlinePlus, National Library of Medicine. Only NLM-written health-topic "
            "summaries are used; A.D.A.M. and other copyrighted MedlinePlus content is not. "
            "Taken from "
            f"https://medlineplus.gov/xml/mplus_topics_compressed_{manifest.medlineplus_date}.zip:",
            "",
        ]
        lines.extend(f"- {topic}" for topic in manifest.medlineplus_topics)
    if manifest.exercises_commit is not None:
        lines += [
            "",
            "## free-exercise-db",
            "",
            f"Licence: [{EXERCISES.licence}]({EXERCISES.licences[EXERCISES.licence]}), public domain. "
            "The `instructions` of every exercise in https://github.com/yuhonas/free-exercise-db "
            f"at commit `{manifest.exercises_commit}`.",
        ]
    if manifest.wger is not None:
        licences = ", ".join(f"[{name}]({url})" for name, url in WGER.licences.items())
        lines += [
            "",
            "## wger",
            "",
            f"Licences: each description keeps the licence its author gave it ({licences}). "
            f"The {manifest.wger.language} exercise descriptions of https://wger.de as taken on "
            f"{manifest.wger.date} (sha256 `{manifest.wger.sha256}`). Each, with its author and "
            "licence:",
            "",
        ]
        credited = dict.fromkeys(
            (chunk.title, chunk.author, chunk.licence, chunk.link)
            for chunk in chunks
            if chunk.source == WGER.name
        )
        lines.extend(
            f"- [{title}]({link}), by {author}, {licence}"
            for title, author, licence, link in credited
        )
    if manifest.army:
        lines += [
            "",
            "## US Army",
            "",
            f"Licence: [{ARMY.licence}]({ARMY.licences[ARMY.licence]}): works of the US "
            "Government carry no copyright (17 U.S.C. 105). Approved for public release; "
            f"distribution is unlimited. Author: {ARMY.author}. Only the chapters named are "
            "used, and no figure:",
            "",
        ]
        lines.extend(
            f"- {publication.publication}, *{publication.title}*, {publication.url} "
            f"(sha256 `{publication.sha256}`), chapters "
            f"{', '.join(str(chapter) for chapter in publication.chapters)}"
            for publication in manifest.army
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


def vendored_exercises_commit() -> str:
    """The upstream commit the vendored free-exercise-db was copied from."""
    provenance = (catalog.DATASET_DIRECTORY / "PROVENANCE.md").read_text(encoding="utf-8")
    found = re.search(r"\| commit \| `([0-9a-f]{40})` \|", provenance)
    if found is None:
        raise CorpusError("free-exercise-db's PROVENANCE.md names no commit")
    return found.group(1)


def _exercises(commit: str) -> list[Chunk]:
    vendored = vendored_exercises_commit()
    if commit != vendored:
        raise CorpusError(
            f"the manifest pins free-exercise-db at {commit}, but the vendored copy is "
            f"{vendored}; pin the vendored commit"
        )
    chunks = []
    for exercise in sorted(catalog.load(), key=lambda e: e.id):
        link = (
            f"https://github.com/yuhonas/free-exercise-db/blob/{commit}/exercises/{exercise.id}.json"
        )
        paragraphs = [_clean(step) for step in exercise.instructions if _clean(step)]
        chunks.extend(
            _cut(
                EXERCISES,
                "en",
                exercise.name,
                exercise.id,
                commit,
                [("", "", paragraphs)],
                lambda _: link,
            )
        )
    return chunks


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


def _wger(pin: Wger, get: Getter) -> list[Chunk]:
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


def pdf_pages(data: bytes) -> list[str]:
    """The text of each page of a PDF."""
    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]


def _army(publication: ArmyPublication, get: Getter) -> list[Chunk]:
    data = get(publication.url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != publication.sha256:
        raise CorpusError(
            f"{publication.url} is not the pinned file of {publication.publication} (sha256 "
            f"{digest}); the Army may have issued a change, so refresh the manifest from the "
            "publication's details page"
        )
    return _cut(
        ARMY,
        "en",
        f"{publication.publication}, {publication.title}",
        publication.publication,
        digest,
        _army_sections(pdf_pages(data), publication),
        lambda anchor: f"{publication.url}#{anchor}",
    )


_BULLETS = "⚫•●▪"
_PARAGRAPH_NUMBER = re.compile(r"^\+?\d+-\d+\.\s*")
_PAGE_ID = re.compile(r"(?:^|\s)(\d+)-\d+(?=\s|$)")


def _army_sections(
    pages: list[str], publication: ArmyPublication
) -> list[tuple[str, str, list[str]]]:
    """A manual's chosen chapters as (heading, page anchor, paragraphs), running heads dropped."""
    sections: list[tuple[str, str, list[str]]] = []
    titles: dict[int, str] = {}
    for number, page in enumerate(pages, start=1):
        lines = [line.strip() for line in page.splitlines()]
        header = next((line for line in lines if publication.publication in line), None)
        found = _PAGE_ID.search(header) if header else None
        chapter = int(found.group(1)) if found else None
        if chapter not in publication.chapters:
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
                or publication.publication in line
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
    return string.capwords(_clean(line.lstrip("+")))


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
