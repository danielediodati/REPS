"""The corpus: openly licensed pages, pinned by revision, cut into committed chunks."""

from __future__ import annotations

import io
import json
import re
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
    """A source the corpus may draw from, with the licence its text carries."""

    name: str
    licence: str
    licence_url: str


WIKIPEDIA = Source("wikipedia", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/")
MEDLINEPLUS = Source(
    "medlineplus",
    "Public domain (US federal work)",
    "https://medlineplus.gov/about/using/usingcontent/",
)
EXERCISES = Source("free-exercise-db", "The Unlicense", "https://unlicense.org/")
SOURCES = {source.name: source for source in (WIKIPEDIA, MEDLINEPLUS, EXERCISES)}
"""The only sources the corpus may hold; anything NonCommercial or copyrighted stays out."""


@dataclass(frozen=True)
class Page:
    """A Wikipedia page pinned to one revision."""

    language: str
    title: str
    revision: int


@dataclass(frozen=True)
class Manifest:
    """The corpus version and the pinned list it is cut from."""

    version: int
    wikipedia: tuple[Page, ...]
    medlineplus_date: str | None
    medlineplus_topics: tuple[str, ...]
    exercises_commit: str | None


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
    return chunks


def read_manifest(directory: Path | None = None) -> Manifest:
    """The manifest in `directory`, by default the committed corpus."""
    path = (directory or CORPUS_DIRECTORY) / _MANIFEST
    if not path.is_file():
        raise CorpusError(f"no corpus manifest at {path}; the corpus ships with one in the repo")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        medlineplus = data.get("medlineplus", {})
        return Manifest(
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
        _NOTICE: notice(manifest),
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


def notice(manifest: Manifest) -> str:
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
    if manifest.exercises_commit is not None:
        lines += [
            "",
            "## free-exercise-db",
            "",
            f"Licence: [{EXERCISES.licence}]({EXERCISES.licence_url}), public domain. "
            "The `instructions` of every exercise in https://github.com/yuhonas/free-exercise-db "
            f"at commit `{manifest.exercises_commit}`.",
        ]
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
            licence=source.licence,
            text=text,
        )
        for number, (section, anchor, text) in enumerate(_packed(sections))
    ]


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
