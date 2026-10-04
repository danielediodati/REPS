"""The methodology between mesocycles, which the supervisor reads and the planner does not."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from trainer.coach import planner
from trainer.engine import methodology, variation

VARIATION_PATH = variation.VARIATION_PATH

PLANNER_PROMPTS = {
    "PLANNING": "15d8f2b831b6aecc68e7e911e8c38579842c702f2be340f694ebcaf3e6fb2df4",
    "MESOCYCLE_PLANNING": "835b3fd08e7115b0ea94bac16cde0e4b7eaff552f8133b13f56c46a8b184bac4",
}
"""The planner's prompts as they were before `variation.md` existed; session 15 does not change them."""


def _sections(path: Path) -> tuple[str, str]:
    body, found, sources = path.read_text(encoding="utf-8").partition(methodology.SOURCES_HEADING)
    assert found, f"{path.name} has no {methodology.SOURCES_HEADING!r} section"
    return body, sources


def test_variation_ships_with_the_package_beside_the_methodology() -> None:
    assert VARIATION_PATH.is_file()
    assert "trainer" in VARIATION_PATH.parts


def test_every_citation_is_in_its_own_list_and_every_source_is_cited() -> None:
    body, sources = _sections(VARIATION_PATH)
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", body)}
    listed = {int(n) for n in re.findall(r"^(\d+)\. ", sources, flags=re.MULTILINE)}

    assert cited
    assert cited == listed


def test_the_goal_ranges_are_not_copied_into_it() -> None:
    """They live in `methodology.md` only (ADR-0014 item 7); a copy drifts."""
    body, _ = _sections(VARIATION_PATH)

    assert methodology.RANGES_HEADING not in body
    assert not re.search(r"\d+\s*[–-]\s*\d+\s*(reps|min|s\b)", body)


def test_the_planner_prompts_are_unchanged() -> None:
    for name, digest in PLANNER_PROMPTS.items():
        prompt = getattr(planner, name)
        assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == digest, name


def test_the_planner_does_not_read_it() -> None:
    body, _ = _sections(VARIATION_PATH)
    title = body.splitlines()[0]

    for prompt in (planner.PLANNING, planner.MESOCYCLE_PLANNING):
        assert title not in prompt
        assert "variation.md" not in prompt


def test_the_supervisor_reads_it_without_its_sources() -> None:
    body, sources = _sections(VARIATION_PATH)
    read = variation.committed().for_supervisor

    assert read.strip() == body.strip()
    assert sources.strip() not in read


def test_a_missing_file_is_named(tmp_path: Path) -> None:
    missing = tmp_path / "variation.md"

    with pytest.raises(variation.VariationError, match="variation.md"):
        variation.load(missing)
