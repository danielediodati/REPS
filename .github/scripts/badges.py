"""Write the coverage and release badges as SVG files, with no network."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_CHAR_WIDTH = 6.5
_PADDING = 10
_LABEL_COLOR = "#555"


def badge(label: str, message: str, color: str) -> str:
    """A flat badge in the shape shields.io draws."""
    left = round(len(label) * _CHAR_WIDTH + _PADDING)
    right = round(len(message) * _CHAR_WIDTH + _PADDING)
    width = left + right
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{label}: {message}">
<title>{label}: {message}</title>
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<clipPath id="r"><rect width="{width}" height="20" rx="3" fill="#fff"/></clipPath>
<g clip-path="url(#r)"><rect width="{left}" height="20" fill="{_LABEL_COLOR}"/><rect x="{left}" width="{right}" height="20" fill="{color}"/><rect width="{width}" height="20" fill="url(#s)"/></g>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
<text x="{left / 2}" y="15" fill="#010101" fill-opacity=".3">{label}</text><text x="{left / 2}" y="14">{label}</text>
<text x="{left + right / 2}" y="15" fill="#010101" fill-opacity=".3">{message}</text><text x="{left + right / 2}" y="14">{message}</text>
</g>
</svg>
"""


def coverage_color(percent: float) -> str:
    """Shields' colour steps for a coverage percentage."""
    for floor, color in ((90, "#4c1"), (80, "#97ca00"), (70, "#a4a61d"), (60, "#dfb317")):
        if percent >= floor:
            return color
    return "#e05d44"


def release_color(tag: str) -> str:
    """Orange for a pre-release, blue for a release."""
    return "#fe7d37" if re.search(r"\d(a|b|rc)\d", tag) else "#007ec6"


def main(coverage_json: str, tag: str, out: str) -> None:
    """Write coverage.svg and release.svg into `out`."""
    percent = json.loads(Path(coverage_json).read_text())["totals"]["percent_covered"]
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    (target / "coverage.svg").write_text(badge("coverage", f"{percent:.0f}%", coverage_color(percent)))
    (target / "release.svg").write_text(badge("release", tag, release_color(tag)))


if __name__ == "__main__":
    main(*sys.argv[1:4])
